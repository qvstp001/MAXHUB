"""媒体字节的出口：播放、分片、字幕、缩图、封面与本地头像。

这一层只做取路径与拼响应头，不做媒体判断——能不能播、走 Range 还是 HLS、要不要
转码，全在 `media`／`transcodes`／`segments` 里。三个媒体异常（`MediaNotFound`、
`MediaOffline`、`MediaUnavailable`）由 `api.py` 的异常处理器统一收口，路由里不要
再手抄同一组 try/except。

STRM 代理遵守上游地址隔离，外部直连由单资产票据明确授权，302 将该指针交给播放器。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from functools import partial
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import (
    FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response,
)
from starlette.staticfiles import StaticFiles

from . import images, jav_poster_crop, subtitles, timeline_sheets
from .entities import resolve_entity_id
from .media import MediaUnavailable, normalized_path
from .platform import within_root
from .previews import ENTITY_THUMB_TYPE, PreviewUnavailable, entity_image_key
from .remote_media_cache import AVATAR_REFRESH_SECONDS
from .routes_auth import require_auth
from .segments import SegmentCancelled, SegmentUnavailable, build_hls_playlist
from .streaming import BufferedFileResponse, CancellableFileResponse, SplicedMp4Response
from .transcodes import TranscodeCancelled, TranscodeUnavailable

router = APIRouter()

#: 生成物的缓存时长。这些端点按 asset id 取图：内容换了 id 也就换了
#: （封面重生成写的是新文件），所以一年也不嫌长。
#: 不加 immutable——那会让浏览器连刷新都不再回源，真要换图就只能干等过期。
MEDIA_CACHE_SECONDS = 365 * 24 * 3600

#: 头像单独短一档：id 不变但人会换头像，作者换得还挺勤。
AVATAR_CACHE_SECONDS = AVATAR_REFRESH_SECONDS


#: 文件名里不能出现的字符，按 Windows 的最严口径取——落盘的那台多半是它。
_UNSAFE_FILENAME = re.compile('[\\/:*?"<>|]+|[\x00-\x1f]+')

LOGGER = logging.getLogger(__name__)


def _image_response(request: Request, path: Path, media_type: str | None = None):
    """固定图片 URL 使用私有缓存，并按文件 ETag 复验。"""
    response = FileResponse(path, media_type=media_type, stat_result=path.stat())
    response.headers["Cache-Control"] = "private, no-cache"
    if StaticFiles().is_not_modified(response.headers, request.headers):
        return Response(status_code=304, headers={
            "ETag": response.headers["etag"],
            "Cache-Control": response.headers["cache-control"],
        })
    return response


def _attachment_disposition(title: str, url: str) -> str:
    """按条目标题构造下载文件名，扩展名沿用上游地址的后缀。

    不回传上游地址：主机名和签名同样是不该外露的东西，和 `/follow-stream`
    整体的边界一致。`filename*` 用 RFC 5987 编码，标题里的中文和日文才落得下来。
    """
    stem = _UNSAFE_FILENAME.sub(" ", str(title or "")).strip() or "peach-media"
    stem = " ".join(stem.split())[:120]
    suffix = Path(urlsplit(str(url or "")).path).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{2,5}", suffix):
        suffix = ".mp4"
    name = f"{stem}{suffix}"
    # 标题整条都是中日文时，ascii 回退会只剩空格和标点，浏览器落下来是个没名字的
    # 文件。回退名必须自己站得住，不能是「把非 ASCII 删掉之后剩下的」。
    ascii_stem = "".join(ch for ch in stem if ch.isascii() and (ch.isalnum() or ch in " -_[]().")).strip()
    ascii_name = f"{ascii_stem}{suffix}" if ascii_stem else f"peach-media{suffix}"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def _repaired_header(state, asset_id: int, source: Path):
    """已经修好的 MP4 头；没有就是 None。只查不算，算是 `_needs_conversion` 的事。"""
    store = getattr(state, "header_repairs", None)
    return None if store is None else store.lookup(asset_id, source)


def _needs_conversion(state, asset_id: int, source: Path, session: str) -> bool:
    """起播时要不要转码。只有 `/api/stream-plan` 问这一句。

    缺 ctts 的片子只是时间戳错乱，重建一份头就能直接按 Range 播，不必重编码。头还没
    算出来时先照旧走 HLS，同时在后台补上；补好之后同一部片下次起播就走 Range。

    HLS 那两个端点不问：一次播放的分片计划要在整段会话里保持同一个形状，边车中途落地
    会让固定 6 秒的计划换成按关键帧切的，剩下的分片索引全对不上。
    """
    if not state.transcode_service.requires_conversion(
            source, session=session, registry=state.stream_sessions):
        return False
    store = getattr(state, "header_repairs", None)
    if store is None or not state.transcode_service.decode_order_timestamps(
            source, session=session, registry=state.stream_sessions):
        return True
    if store.lookup(asset_id, source) is not None:
        return False
    store.request(asset_id, source)
    return True


def _hls_plan(state, asset_id: int, session: str = "", conversion: bool | None = None):
    """解析 HLS 的片源路径与分片计划；任何一步不成立就返回 None 走 Range。

    要重编码的片源按固定 6 秒切，时长先看账本，账本没记或记成负数就用 ffprobe 报的；
    探测也拿不到才放弃，否则浏览器只能退回 `/stream`，那条路要先把整部片转完才出第一个字节。
    原样封装的 HLS 仍要账本时长与关键帧表。

    `conversion` 是起播时已经得出的结论。给不出时按片源本身判：播放列表和分片端点走的
    就是这条，它们不看重建好的 MP4 头，理由见 `_needs_conversion`。
    """
    asset = state.media_engine.asset(asset_id)
    # 播放列表和分片端点本身就是 HLS 路径，按 ADR-0016 显式要计划，不受默认值影响。
    choice = state.media_engine.stream_plan(asset_id, mode="hls")
    source = state.media_engine.filesystem.file_for(asset, thumbnail=False)
    duration = asset.duration if asset.duration and asset.duration > 0 else 0.0
    if conversion if conversion is not None else state.transcode_service.requires_conversion(
            source, session=session, registry=state.stream_sessions):
        duration = duration or state.transcode_service.media_duration(
            source, session=session, registry=state.stream_sessions)
        plan = state.hls_service.conversion_plan(duration) if duration > 0 else []
        return (asset, source, plan, True) if plan else None
    if choice.protocol != "hls" or duration <= 0:
        return None
    plan = state.hls_service.plan(source, duration)
    return None if not plan else (asset, source, plan, False)


@router.post("/api/external-playback")
def external_playback(request: Request, id: int, mode: Literal['proxy', 'direct'] = 'proxy',
                      args: dict[str, str] = Depends(require_auth)):
    from .external_playback import TTL_SECONDS, issue
    from .routes_auth import _named_origin, _origin_key, _tunnel_origin
    from fastapi import HTTPException
    from . import strm
    state = request.app.state
    asset = state.media_engine.asset(id)
    source = state.media_engine.filesystem.file_for(asset, thumbnail=False)
    if mode == 'direct':
        if not strm.is_pointer(source):
            raise HTTPException(400, '302 直连只适用于 STRM 资源')
        try:
            strm.read_target(source)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
    supplied = request.headers.get('origin')
    raw = supplied or str(request.base_url)
    parsed = urlsplit(raw)
    if any(ord(char) <= 32 or ord(char) == 127 for char in raw) or parsed.username or parsed.password:
        raise HTTPException(400, '播放地址无效')
    key = _origin_key(raw) if supplied else (_tunnel_origin(request) or _named_origin(request) or _origin_key(raw))
    if key is None:
        raise HTTPException(400, '播放地址无效')
    scheme, host, port = key
    host = f'[{host}]' if ':' in host else host
    origin = f'{scheme}://{host}' + (f':{port}' if port is not None else '')
    ticket = issue(state.external_playback_key, id, origin=origin, mode=mode)
    query = f"ticket={ticket}&origin={quote(origin, safe='')}"
    if mode == 'direct':
        query += '&mode=direct'
    path = f"/external-stream/{id}?{query}"
    playlist = f"/external-playlist/{id}.m3u?{query}"
    return JSONResponse({"url": path, "playlist": playlist, "expires_in": TTL_SECONDS},
                        headers={"Cache-Control": "no-store"})


def _external_asset(request: Request, asset_id: int, ticket: str, origin: str, mode: str = 'proxy'):
    from .external_playback import valid
    from fastapi import HTTPException
    state = request.app.state
    if not origin or not valid(state.external_playback_key, asset_id, ticket, origin=origin, mode=mode):
        raise HTTPException(401, "播放链接已失效，请在作品详情重新打开")
    asset = state.media_engine.asset(asset_id)
    return state.media_engine.filesystem.file_for(asset, thumbnail=False)


@router.api_route("/external-stream/{id}", methods=["GET", "HEAD"])
def external_stream(request: Request, id: int, ticket: str, origin: str = '',
                    mode: Literal['proxy', 'direct'] = 'proxy'):
    path = _external_asset(request, id, ticket, origin, mode)
    from . import strm, strm_stream
    if strm.is_pointer(path):
        if mode == 'direct':
            try:
                target = strm.read_target(path)
            except ValueError as error:
                return JSONResponse({'error': str(error)}, status_code=400)
            return RedirectResponse(target, status_code=302,
                                    headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
        return strm_stream.proxy(request, id, path)
    if mode == 'direct':
        return JSONResponse({'error': '302 直连只适用于 STRM 资源'}, status_code=400)
    return BufferedFileResponse(path, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/external-playlist/{id}.m3u")
def external_playlist(request: Request, id: int, ticket: str, origin: str = '',
                      mode: Literal['proxy', 'direct'] = 'proxy'):
    _external_asset(request, id, ticket, origin, mode)
    url = origin + f"/external-stream/{id}?ticket={ticket}&origin={quote(origin, safe='')}"
    if mode == 'direct':
        url += '&mode=direct'
    return PlainTextResponse(f"#EXTM3U\n#EXTINF:-1,Peach {id}\n{url}\n", media_type="audio/x-mpegurl",
                             headers={"Content-Disposition": f'attachment; filename="peach-{id}.m3u"',
                                      "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.api_route("/stream", methods=["GET", "HEAD"])
def stream(request: Request, id: int, session: str = "", args: dict[str, str] = Depends(require_auth)):
    state = request.app.state
    asset = state.media_engine.asset(id)
    path = state.media_engine.filesystem.file_for(asset, thumbnail=False)
    from . import strm, strm_stream
    if strm.is_pointer(path):
        return strm_stream.proxy(request, id, path, session)
    if path.suffix.lower() in strm.DISC_SUFFIXES:
        return JSONResponse({'error': 'ISO 原盘请使用作品详情中的外部播放器打开'}, status_code=415)
    header = _repaired_header(state, id, path)
    if header is not None:
        return SplicedMp4Response(
            path, header, session=session, registry=state.stream_sessions,
        )
    try:
        path, transcoded = state.transcode_service.browser_path(
            id, path, session=session, registry=state.stream_sessions,
        )
    except TranscodeCancelled:
        return Response(status_code=410, headers={"Cache-Control": "no-store"})
    except TranscodeUnavailable:
        LOGGER.exception("browser transcode failed for asset %s", id)
        return JSONResponse({"error": "transcode unavailable"}, status_code=503)
    media_type = "video/mp4" if transcoded else None
    response = (
        CancellableFileResponse(
            path, session=session, registry=state.stream_sessions, media_type=media_type,
        )
        if session else BufferedFileResponse(path, media_type=media_type)
    )
    if transcoded:
        response.headers["X-Peach-Transcoded"] = "1"
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/api/stream-plan")
def stream_plan(request: Request, id: int, session: str = "", mode: str = "", args: dict[str, str] = Depends(require_auth)):
    state = request.app.state
    if session and len(session) > 128:
        return JSONResponse({"error": "invalid session"}, status_code=400)
    if session and state.stream_sessions.is_cancelled(session):
        return JSONResponse({"error": "stream cancelled"}, status_code=410)
    asset = state.media_engine.asset(id)
    plan = state.media_engine.stream_plan(id, mode=mode or "auto")
    # 只有真的能读出关键帧才宣告 HLS，否则客户端会拿到一个必然 404 的播放列表。
    source_path = state.media_engine.filesystem.file_for(asset, thumbnail=False)
    from . import strm, strm_stream
    if strm.is_pointer(source_path):
        try:
            target = strm.read_target(source_path)
        except ValueError as error:
            return JSONResponse({'error': str(error)}, status_code=400)
        mime = strm_stream.mime_type(target)
        return {'id': id, 'protocol': 'hls' if mime in strm_stream.PLAYLIST_TYPES else 'range',
                'mime_type': mime, 'duration': asset.duration,
                'src': f'/stream?id={id}&session={quote(session, safe="")}', 'reason': 'strm-pointer'}
    if source_path.suffix.lower() in strm.DISC_SUFFIXES:
        return JSONResponse({'error': 'ISO 原盘请使用作品详情中的外部播放器打开'}, status_code=415)
    conversion = _needs_conversion(state, id, source_path, session)
    resolved = (_hls_plan(state, id, session, conversion)
                if conversion or plan.protocol == "hls" else None)
    if resolved and session:
        return {
            "id": id,
            "protocol": "hls",
            "mime_type": "application/vnd.apple.mpegurl",
            "duration": round(sum(length for _, length in resolved[2]), 3),
            "segment_seconds": plan.segment_seconds,
            "segments": len(resolved[2]),
            "src": f"/stream/hls/{id}/index.m3u8?session={quote(session, safe='')}",
            "reason": plan.reason,
        }
    source = f"/stream?id={id}"
    if session:
        source += f"&session={quote(session, safe='')}"
    return {
        "id": id,
        "protocol": "range",
        "mime_type": plan.mime_type,
        "duration": asset.duration,
        "src": source,
        "reason": plan.reason,
    }


@router.api_route('/strm-resource/{id}/{key}', methods=['GET', 'HEAD'])
def strm_resource(request: Request, id: int, key: str, session: str = '',
                  ticket: str = '', origin: str = ''):
    from . import strm, strm_stream
    if ticket:
        path = _external_asset(request, id, ticket, origin)
    else:
        require_auth(request)
        path = request.app.state.media_engine.file_for(id)
    if not strm.is_pointer(path):
        return Response(status_code=404)
    return strm_stream.proxy(request, id, path, session, key)


@router.get("/stream/hls/{id}/index.m3u8")
def hls_playlist(request: Request, id: int, session: str = "", args: dict[str, str] = Depends(require_auth)):
    state = request.app.state
    # 分片必须带 session 才能被取消，播放列表这层就要求它；
    # 否则会生成一份每个分片都必然 400 的目录。
    if not session or len(session) > 128:
        return PlainTextResponse("session required", status_code=400)
    if state.stream_sessions.is_cancelled(session):
        return PlainTextResponse("stream cancelled", status_code=410)
    try:
        resolved = _hls_plan(state, id, session)
    except (MediaUnavailable, TranscodeUnavailable):
        return PlainTextResponse("hls unavailable", status_code=404)
    if resolved is None:
        return PlainTextResponse("hls unavailable", status_code=404)
    query = f"?session={quote(session, safe='')}"
    playlist = build_hls_playlist(
        resolved[2], lambda index: f"/stream/hls/{id}/{index}.ts{query}",
    )
    response = PlainTextResponse(playlist, media_type="application/vnd.apple.mpegurl")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/stream/hls/{id}/{index}.ts")
async def hls_segment(request: Request, id: int, index: int, session: str = "", args: dict[str, str] = Depends(require_auth)):
    state = request.app.state
    if not session or len(session) > 128:
        return JSONResponse({"error": "invalid session"}, status_code=400)
    if state.stream_sessions.is_cancelled(session):
        return Response(status_code=410, headers={"Cache-Control": "no-store"})
    try:
        loop = asyncio.get_running_loop()
        resolved = await loop.run_in_executor(
            state.hls_plan_executor, partial(_hls_plan, state, id, session),
        )
        if resolved is None:
            return JSONResponse({"error": "hls unavailable"}, status_code=404)
        _, source, plan, conversion = resolved
        if index < 0 or index >= len(plan):
            return JSONResponse({"error": "invalid segment"}, status_code=416)
        start, duration = plan[index]
        path = await state.hls_service.generate(
            source, start, duration, asset_id=id, index=index,
            session=session, registry=state.stream_sessions,
            **({"transcode": True} if conversion else {}),
        )
    except SegmentCancelled:
        return Response(status_code=410, headers={"Cache-Control": "no-store"})
    except TranscodeCancelled:
        return Response(status_code=410, headers={"Cache-Control": "no-store"})
    except TranscodeUnavailable:
        LOGGER.exception("browser transcode failed for asset %s", id)
        return JSONResponse({"error": "transcode unavailable"}, status_code=503)
    except SegmentUnavailable:
        LOGGER.exception("HLS segment failed for asset %s", id)
        return JSONResponse({"error": "segment unavailable"}, status_code=503)
    # 片段现在留在缓存里而不是随响应删除：回放、重连和多设备都会重复请求同一段，
    # 每次重跑 FFmpeg 等于让 CloudDrive 再预取一次块。
    response = FileResponse(path, media_type="video/mp2t")
    response.headers["Cache-Control"] = f"private, max-age={MEDIA_CACHE_SECONDS}"
    response.headers["X-Peach-HLS-Segment"] = "1"
    return response


@router.post("/api/stream-cancel")
async def stream_cancel(request: Request, session: str, args: dict[str, str] = Depends(require_auth)):
    if not session or len(session) > 128:
        return JSONResponse({"error": "invalid session"}, status_code=400)
    cancelled = request.app.state.stream_sessions.cancel(session)
    return JSONResponse({"ok": True, "cancelled": cancelled})


#: 单份字幕的读取上限。两小时的片子字幕撑死几百 KB；比这更大的多半不是字幕，
#: 整份读进内存的代价不该由播放器那一次请求承担。
SUBTITLE_BYTE_LIMIT = 4 * 1024 * 1024


def _subtitle_rows(state, asset_id: int):
    """资产本身加它的字幕行。资产不存在时抛 `MediaNotFound`，由 `api.py` 收口。"""
    asset = state.media_engine.asset(asset_id)
    with state.database.read_connection() as connection:
        return asset, subtitles.subtitles_for(connection, asset_id)


def _subtitle_path(state, asset, row) -> Path | None:
    """字幕文件在本机的位置；逃出正片所在目录或授权根一律拒绝。

    路径来自账本而不是前端，这一层仍然要查：`asset_subtitle.path` 由扫描写入，
    而扫描根本身可以被改设置改掉，判据不能寄托在「写进去的那一刻是对的」。
    """
    if not asset.path:
        return None
    directory = normalized_path(asset.path).parent
    path = normalized_path(row["path"])
    if str(path.parent).casefold() != str(directory).casefold():
        return None
    if not any(within_root(path, root)
               for root in state.media_engine.filesystem.allowed_roots):
        return None
    return path


def _subtitle_bytes(state, asset, row) -> tuple[bytes | None, str]:
    """字幕文件的内容，以及取不到时的原因。原因直接进列表给人看。"""
    path = _subtitle_path(state, asset, row)
    if path is None:
        return None, "不在正片所在目录"
    try:
        if path.stat().st_size > SUBTITLE_BYTE_LIMIT:
            return None, "文件过大"
        return path.read_bytes(), ""
    except OSError:
        return None, "文件未找到"


def _subtitle_note(state, asset, row) -> str:
    """这一条为什么不能播；能播返回空串。"""
    if not subtitles.is_playable_format(row["format"]):
        return "图形字幕，播放器里不显示"
    data, note = _subtitle_bytes(state, asset, row)
    if data is None:
        return note
    try:
        subtitles.decode(data)
    except subtitles.SubtitleUndecodable:
        return "编码未识别"
    return ""


@router.get("/api/assets/{id}/subtitles")
def asset_subtitles(request: Request, id: int, args: dict[str, str] = Depends(require_auth)):
    """这个资产有哪些字幕轨，以及每一条能不能播。

    序号就是这张表里的位置，`/api/assets/{id}/subtitles/{n}` 按同一个顺序取。
    不能播的也列出来并说明原因：界面上「有三条字幕、只挂上两条」要能解释得清。
    """
    state = request.app.state
    asset, rows = _subtitle_rows(state, id)
    tracks = []
    for index, row in enumerate(rows):
        note = _subtitle_note(state, asset, row)
        tracks.append({
            "index": index,
            "name": row["name"],
            "format": row["format"],
            "language": row["language"],
            "label": subtitles.track_label(row["name"], row["language"], asset.name),
            "pairing": row["pairing"],
            "note": note,
            "playable": not note,
            "src": f"/api/assets/{id}/subtitles/{index}",
        })
    return {"id": id, "subtitles": tracks}


@router.api_route("/api/assets/{id}/subtitles/{index}", methods=["GET", "HEAD"])
def asset_subtitle_track(request: Request, id: int, index: int,
                         args: dict[str, str] = Depends(require_auth)):
    """一条字幕的 WebVTT。浏览器的 text track 只认这一种格式。"""
    state = request.app.state
    asset, rows = _subtitle_rows(state, id)
    if index < 0 or index >= len(rows):
        return JSONResponse({"error": "no such subtitle"}, status_code=404)
    row = rows[index]
    data, _note = _subtitle_bytes(state, asset, row)
    if data is None:
        return JSONResponse({"error": "subtitle unavailable"}, status_code=404)
    try:
        text = subtitles.to_webvtt(data, row["format"])
    except subtitles.SubtitleUndecodable as error:
        return JSONResponse({"error": str(error)}, status_code=415)
    response = PlainTextResponse(text, media_type="text/vtt; charset=utf-8")
    response.headers["Cache-Control"] = "private, no-cache"
    return response


@router.api_route("/thumb", methods=["GET", "HEAD"])
def thumbnail(request: Request, id: int, args: dict[str, str] = Depends(require_auth)):
    path = request.app.state.media_engine.file_for(id, thumbnail=True)
    return _image_response(request, path)


@router.api_route("/photo", methods=["GET", "HEAD"])
def photo(request: Request, id: int, args: dict[str, str] = Depends(require_auth)):
    """图片资产原图。灯箱看大图用这条，图片墙一律走 `/photo-thumb`。"""
    path = request.app.state.media_engine.file_for(id)
    return _image_response(request, path)


@router.api_route("/photo-thumb", methods=["GET", "HEAD"])
def photo_thumb(request: Request, id: int, args: dict[str, str] = Depends(require_auth)):
    """图片墙的缩略图。缓存命中就此返回，不去解析原图。

    解析原图要在挂载的网盘上确认它还在，实测一次 0.1–0.4 秒；一屏几十张缩略图全部命中
    缓存，也要为这几十次往返等上好几秒。缩略图缩好之后原图在不在都不改变这次的响应。
    """
    state = request.app.state
    path = state.photo_service.cached(id)
    if path is None:
        try:
            path = state.photo_service.thumbnail(id, state.media_engine.file_for(id))
        except PreviewUnavailable:
            return JSONResponse({"error": "unavailable"}, status_code=404)
    return _image_response(request, path, media_type="image/jpeg")


def _sample_response(request: Request, code: str, n: int, *, thumb: bool):
    """只提供数据目录中已有的样张缓存。"""
    path = request.app.state.sample_cache.cached(code, n, thumb=thumb)
    if path is None:
        return JSONResponse({"error": "unavailable"}, status_code=404)
    return _image_response(request, path, media_type="image/jpeg")


@router.api_route("/sample-thumb", methods=["GET", "HEAD"])
def sample_thumb(request: Request, code: str = "", n: int = 0,
                 args: dict[str, str] = Depends(require_auth)):
    """照片墙上那一档样张缩略图，宽度与 `/photo-thumb` 相同。"""
    return _sample_response(request, code, n, thumb=True)


@router.api_route("/sample-image", methods=["GET", "HEAD"])
def sample_image(request: Request, code: str = "", n: int = 0,
                 args: dict[str, str] = Depends(require_auth)):
    """灯箱里看的样张原图。"""
    return _sample_response(request, code, n, thumb=False)


@router.api_route("/poster", methods=["GET", "HEAD"])
def poster(request: Request, id: int, c: int = 4, args: dict[str, str] = Depends(require_auth)):
    try:
        path = request.app.state.preview_service.poster(id, c)
    except PreviewUnavailable:
        return JSONResponse({"error": "unavailable"}, status_code=404)
    return _image_response(request, path, media_type="image/jpeg")


@router.api_route("/backdrop", methods=["GET", "HEAD"])
def backdrop(request: Request, id: int, args: dict[str, str] = Depends(require_auth)):
    """影片同目录的本地横幅原图。"""
    path = request.app.state.web_contract.backdrop_path(id)
    if path is None:
        return JSONResponse({"error": "no backdrop"}, status_code=404)
    return _image_response(request, path, media_type='image/jpeg' if path.suffix.lower() == '.tbn' else None)


@router.api_route("/timeline", methods=["GET", "HEAD"])
def timeline(request: Request, id: int, s: int = 0, args: dict[str, str] = Depends(require_auth)):
    """时间轴预览的一张接触印相。只发已经铺好的，这里不现抽。

    `/poster` 那条取不到会当场抽一帧，因为九宫格只要九张。这里一张图是一百帧，现抽要
    几分钟，悬停的人早走了；没铺到就回 404，页面退回九宫格。
    """
    contract = request.app.state.web_contract
    path = timeline_sheets.sheet_path(contract.timeline_root, id, s)
    if id <= 0 or s < 0 or not path.is_file():
        return JSONResponse({"error": "unavailable"}, status_code=404)
    return _image_response(request, path, media_type="image/jpeg")


@router.api_route("/cover", methods=["GET", "HEAD"])
def cover(request: Request, code: str = "", thumb: int = 0,
          args: dict[str, str] = Depends(require_auth)):
    """官方封套原图。存原图不裁：4:3 与 16:9 两种版式在界面上按比例取景。

    `thumb=1` 要的是卡片网格那一档派生件（`COVER_THUMB_EDGE`），详情与裁切取原件。
    开关是布尔而不是像素数，理由同 `/entity-image`。
    """
    path = request.app.state.web_contract.cover_path(code)
    if path is None:
        return JSONResponse({"error": "no cover"}, status_code=404)
    if thumb:
        derived = request.app.state.cover_thumb_service.thumbnail(path.stem, path)
        if derived is not None:
            return _image_response(request, derived, media_type=ENTITY_THUMB_TYPE)
    return _image_response(request, path, media_type="image/jpeg")


@router.post("/api/cover-crop")
async def cover_crop(request: Request, args: dict[str, str] = Depends(require_auth)):
    """人自己框的正封那一块，或者把它撤掉换回算出来的那个。

    写的是封面旁边的 `.poster.json`，不生成第二张图片：正封本来就不是一张新图，
    而是一组坐标（`jav_poster_crop` 的约定）。所以封面原图一个字节都不动，撤掉
    手工框就是删掉这份 sidecar，下一次取景重新按折痕判据算。

    `box` 是源图像素的 `{x0,y0,x1,y1}`，右下开区间；`box` 为 null 表示恢复默认。
    """
    state = request.app.state.web_contract
    sent = await request.json()
    payload = sent if isinstance(sent, dict) else {}
    code = str(payload.get("code") or "")
    path = state.cover_path(code)
    if path is None:
        return JSONResponse({"error": "这个番号没有封面"}, status_code=404)
    size = images.measure_image_size(path.read_bytes())
    if size is None:
        return JSONResponse({"error": "这张封面读不出来"}, status_code=422)
    if payload.get("box") is None:
        # 恢复默认是当场按折痕判据重算一遍，不是删掉 sidecar：删掉之后没有人会
        # 再来算，页面拿到的是「这张图不该裁」，正封从此再也回不来。
        def read_evidence(suffix):
            try:
                value = json.loads(path.with_suffix(suffix).read_text(encoding='utf-8'))
                return value if isinstance(value, dict) else {}
            except (OSError, ValueError):
                return {}
        face = read_evidence('.face.json')
        current_face = face.get('px') == list(size)
        title = (jav_poster_crop.read_sidecar(path) or {}).get('title') or read_evidence('.scraping.json').get('title', '')
        record = jav_poster_crop.crop_record(
            code, size[0], size[1], jav_poster_crop.file_gradient(path), title=title,
            face=face.get('face') if current_face else None)
        if current_face and face.get('layout') == 'still':
            record['box'] = dict(x0=0, y0=0, x1=size[0], y1=size[1], method=jav_poster_crop.NONE)
    else:
        record = jav_poster_crop.manual_record(size[0], size[1], payload.get("box"))
    if record is None:
        return JSONResponse({"error": "框选的区域不成立"}, status_code=400)
    jav_poster_crop.write_sidecar(path, record)
    state.cache_bust()
    return JSONResponse({"ok": True, "code": code,
                         "poster_box": jav_poster_crop.projection(record)})


@router.api_route("/endcard-frame", methods=["GET", "HEAD"])
def endcard_frame(request: Request, id: int, name: str, args: dict[str, str] = Depends(require_auth)):
    """Serve only generated OCR evidence frames, never a client-provided path."""
    if (id <= 0 or not name.endswith(".png") or "/" in name or "\\" in name
            or name.startswith(".")):
        return JSONResponse({"error": "invalid frame"}, status_code=400)
    root = (request.app.state.settings.candidate_root
            / "endcard-evidence" / str(id)).resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        return JSONResponse({"error": "no frame"}, status_code=404)
    response = FileResponse(path, media_type="image/png")
    response.headers["Cache-Control"] = f"private, max-age={MEDIA_CACHE_SECONDS}"
    return response


@router.api_route("/avatar", methods=["GET", "HEAD"])
def avatar(request: Request, id: int, args: dict[str, str] = Depends(require_auth)):
    try:
        path = request.app.state.preview_service.avatar(id)
    except PreviewUnavailable:
        return JSONResponse({"error": "unavailable"}, status_code=404)
    return _image_response(request, path, media_type="image/jpeg")


@router.api_route("/logo", methods=["GET", "HEAD"])
def logo(request: Request, studio: str = "", variant: str = "",
         args: dict[str, str] = Depends(require_auth)):
    try:
        path, content_type = request.app.state.preview_service.logo(studio, variant)
    except PreviewUnavailable:
        return JSONResponse({"error": "unavailable"}, status_code=404)
    response = FileResponse(path, media_type=content_type)
    # Logo 可以缓存，但文件会在人工批准或重新归一后原地替换。固定 URL 若缓存
    # 一整天，浏览器会继续显示旧图；no-cache 会复用本地副本并用 ETag 重验。
    response.headers["Cache-Control"] = "public, no-cache"
    return response


@router.api_route("/entity-image", methods=["GET", "HEAD"])
def entity_image(request: Request, kind: str, id: int, thumb: int = 0,
                 args: dict[str, str] = Depends(require_auth)):
    """实体图。`thumb=1` 要的是索引页那一档派生件，不带就是资料页用的原件。

    开关是布尔而不是像素数：尺寸由服务端一处定死，页面递多少像素进来就等于让每个
    调用点各存一份尺寸，改一次得追七处，而缓存目录里会长出一堆只差几十像素的派生件。
    """
    state = request.app.state
    try:
        path, content_type = state.preview_service.entity_image(kind, id)
    except PreviewUnavailable:
        # 并入别人的实体没有自己的图：按墓碑跳到现在那一条。只在取不到时查库，
        # 索引页一屏几百张图的常规路径不多一次查询。
        target = current_entity_id(state.web_contract, id)
        if target != id:
            # 只换 id，其余参数（缩略图开关、口令）原样带上；写相对地址，不依赖反代给的主机名。
            moved = request.url.include_query_params(id=target)
            return RedirectResponse(f"{moved.path}?{moved.query}", status_code=307)
        return JSONResponse({"error": "unavailable"}, status_code=404)
    if thumb:
        derived = state.entity_thumb_service.thumbnail(entity_image_key(kind, id), path)
        if derived is not None:
            path, content_type = derived, ENTITY_THUMB_TYPE
    return _image_response(request, path, media_type=content_type)


def current_entity_id(contract, entity_id: int) -> int:
    """页面递来的实体 id 按合并墓碑换成现在的实体；解析不到就原样返回，交给接口自己的判据。"""
    if entity_id <= 0:
        return entity_id
    with contract.read_connection() as connection:
        return resolve_entity_id(connection, entity_id) or entity_id
