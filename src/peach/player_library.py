"""媒体库的本地扫描与边车导入；输入仅来自已声明的媒体目录。"""
from __future__ import annotations

import shutil
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from . import settings_file
from .catalog_rules import normalise_code_key, release_code_from_filename, same_release_code
from .entities import upsert_asset_entity
from .field_owners import SCAN_FILENAME, auto_owner, write_owned_fields
from .fsutil import atomic_path
from .library_nfo import SidecarIndex, directory_files, local_art, read_nfo
from .platform import is_unmapped, root_online, translate_ledger_path
from .scan import scan_location


def q_library_processing(contract, _args):
    return contract.library_processing_job.snapshot() or {"status": "idle"}


def q_library_processing_issues(contract, args):
    state = q_library_processing(contract, {})
    rows = state.get("issues", [])
    offset = max(0, int(args.get("offset") or 0))
    limit = max(1, min(200, int(args.get("limit") or 50)))
    return {"job_id": state.get("job_id", ""), "total": len(rows), "offset": offset,
            "rows": rows[offset:offset + limit]}


def _selection(raw):
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw or any(type(value) is not int or value <= 0 for value in raw):
        raise ValueError("请选择有效的视频项目")
    return sorted(set(raw))


def w_library_processing(contract, body):
    """用户发起一次本地导入，服务启动不会恢复历史任务。"""
    if body.get("action") or "retry" in body:
        raise ValueError("请重新发起本地媒体库扫描")
    if "asset_ids" in body and body["asset_ids"] is None:
        raise ValueError("请选择有效的视频项目")
    config = settings_file.active()
    if not config.configured or not config.locations:
        raise ValueError("请先添加媒体目录")
    if contract.db_path.resolve() != (config.directory("database") / "ledger.db").resolve():
        raise ValueError("当前馆藏与媒体配置不一致")
    stage = str(body.get("stage") or "all")
    if stage not in {"all", "scan", "collect", "metadata"}:
        raise ValueError("播放器仅支持本地扫描与资料导入")
    selected = _selection(body.get("asset_ids"))
    def work(job_id):
        result = process_library(config, contract.db_path, contract.candidate_root, contract.cover_root,
                                 stage=stage, asset_ids=selected, database=contract.database,
                                 report=lambda state: contract.library_processing_job.update(job_id, **state))
        contract.cache_bust()
        return result
    return contract.library_processing_job.start_result(work)


def _copy_image(source: Path, target: Path) -> bool:
    """验证本地图片并生成 JPEG 缓存；媒体目录始终只读。"""
    with Image.open(source) as image:
        image.verify()
        original_jpeg = image.format == "JPEG"
    if target.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with atomic_path(target) as temporary:
        if original_jpeg:
            shutil.copyfile(source, temporary)
        else:
            with Image.open(source) as image:
                image.convert("RGB").save(temporary, format="JPEG", quality=95)
    return True


def _import_nfo(connection, row, payload, code):
    fields = {column: str(payload.get(key) or "").strip() for key, column in (
        ("title", "catalog_title"), ("original_title", "original_title"), ("maker", "studio"),
        ("series", "series"), ("release_date", "release_date")) if payload.get(key)}
    write_owned_fields(connection, [row["id"]], fields, auto_owner("local_nfo"), require_empty=True)
    held = connection.execute("SELECT studio,series FROM asset WHERE id=?", (row["id"],)).fetchone()
    if code and not row["code"]:
        write_owned_fields(connection, [row["id"]], {"code": code}, SCAN_FILENAME, require_empty=True)
    people = [str(person.get("japanese_name") or "").strip() for person in payload.get("actresses", [])]
    for kind, names in (("performer", people), ("tag", payload.get("local_tags", [])),
                        ("studio", [payload.get("maker")]), ("series", [payload.get("series")])):
        for name in names:
            if not name:
                continue
            if kind in {"studio", "series"} and held[kind] != name:
                continue
            upsert_asset_entity(connection, kind=kind, name=name, asset_id=row["id"], role=kind,
                                source="local_nfo", update_entity_metadata=False)
            if kind in {"performer", "tag"}:
                tag = "演员:" + name if kind == "performer" else name
                connection.execute("INSERT OR IGNORE INTO asset_tag(asset_id,tag,confidence,source) VALUES(?,?,1,?)",
                                   (row["id"], tag, "local_nfo"))


def process_library(config, db_path, candidate_root, cover_root, *, location="configured", stage="all",
                    asset_ids=None, database=None, report=lambda state: None, **_unused):
    """扫描文件并导入本地 NFO 与图片，不访问外部资料或媒体地址。"""
    from .repository import LedgerDatabase
    if config.replication.enabled:
        from .sync import writer_device
        device_path = config.directory("state") / "device-id"
        device = device_path.read_text(encoding="utf-8").strip() if device_path.is_file() else ""
        if not device or writer_device(Path(db_path), config.shared_root / "database" / "ledger.db") != device:
            raise ValueError("这台电脑是只读端，请在写入端扫描和导入资料")
    if stage not in {"all", "scan", "collect", "metadata"}:
        raise ValueError("播放器仅支持本地扫描与资料导入")
    database = database or LedgerDatabase(db_path)
    selected = _selection(asset_ids)
    locations = tuple(config.locations) if location == "configured" else (location,)
    if any(name not in config.locations for name in locations):
        raise ValueError("媒体来源尚未声明")
    state = {"status": "running", "stage": "本地扫描", "checked": 0, "total": 0,
             "identified": 0, "covers": 0, "issues": [], "issue_count": 0, "followups": []}
    online = []
    for name in locations:
        for root in config.locations[name]:
            actual = translate_ledger_path(root)
            if is_unmapped(actual) or not root_online(actual):
                state["issues"].append({"message": "媒体来源离线", "location": name})
                continue
            online.append((name, root))
            if selected is None and stage in {"all", "scan"}:
                scan_location(db_path, name, root, declared_roots=config.locations, mounts=config.mounts)
    with database.read_connection() as connection:
        rows = [dict(row) for row in connection.execute("SELECT * FROM asset WHERE medium='video' AND disposal IS NULL")
                if row["location"] in locations and (selected is None or row["id"] in selected)]
    state.update(stage="导入本地资料", total=len(rows))
    listings = {}
    for row in rows:
        video = translate_ledger_path(row["path"])
        try:
            if not any(row["location"] == name and (video == translate_ledger_path(root)
                       or video.is_relative_to(translate_ledger_path(root))) for name, root in online):
                continue
            listing = listings.get(video.parent)
            if listing is None:
                listing = listings[video.parent] = SidecarIndex(directory_files(video.parent))
            nfo, posters = listing.for_video(video)
            payload = read_nfo(nfo)[0] if nfo else {}
            code = normalise_code_key(row["code"] or release_code_from_filename(video.stem) or payload.get("id"))
            if payload.get("id") and code and not same_release_code(code, payload["id"]):
                raise ValueError("文件名与 NFO 番号冲突，请复核")
            with database.write_transaction() as connection:
                _import_nfo(connection, row, payload, code)
            if payload:
                state["identified"] += 1
            artwork = local_art(video, payload)
            artwork = artwork or next(iter(posters), None)
            if artwork:
                if not artwork.resolve().is_relative_to(video.parent.resolve()):
                    raise ValueError("配套图片不在影片目录内")
                if code and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}", code):
                    raise ValueError("本地图片的作品编号格式无效")
                target = Path(cover_root) / ((code or f"ASSET-ID-{row['id']}") + ".jpg")
                state["covers"] += int(_copy_image(artwork, target))
        except (OSError, ValueError, ET.ParseError) as error:
            state["issues"].append({"asset_id": row["id"], "message": str(error)})
        finally:
            state["checked"] += 1
            state["issue_count"] = len(state["issues"])
            report(dict(state))
    state["issue_count"] = len(state["issues"])
    state["status"] = "complete"
    return state
