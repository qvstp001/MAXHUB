"""JSON 契约的 HTTP 出口。

绝大多数端点不在这里逐个声明：`/api/{route:path}` 把路径交给 `web_router` 的两张
处理器表，加一个 API 只需要在那里注册。这里只留三类必须自己写的：
探测类（providers、sources）、本机副作用（reveal）和流式上传（taste/import）。

注册顺序有意义。`/api/{route:path}` 是 catch-all，`api.py` 必须最后 include 这个
router；同理本模块内部两条 catch-all 写在文件末尾，具名端点写在前面。
`/api/stream-plan` 与 `/api/stream-cancel` 在 `routes_media` 里，那个 router 也要
先 include。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from . import web_contract, web_tasks
from .field_owners import RevisionConflict
from .folder_rules import FolderRuleConflict
from .interaction import reveal_path
from .jobs import TaskRunConflict
from .update_tasks import UpdateBusy
from .platform import is_unmapped, translate_ledger_path
from .routes_auth import require_auth
from .task_runs import task_label

router = APIRouter()

LOGGER = logging.getLogger(__name__)


@router.get("/api/sources")
def source_health(request: Request, args: dict[str, str] = Depends(require_auth)):
    """无副作用的来源可达性。前端据此把脱盘来源的筛选置灰。"""
    rows = request.app.state.mount_reachability.sources()
    rows.append({"location": "online", "declared": None, "resolved": None,
                 "mapped": True, "online": True, "state": "ok", "message": ""})
    return {
        "ok": True,
        "sources": rows,
        "offline": [row["location"] for row in rows if row["online"] is False],
    }


@router.get("/api/libraries")
def media_library_list(request: Request, args: dict[str, str] = Depends(require_auth)):
    from . import media_libraries, settings_file
    from .media_sources import cost_for
    config = settings_file.active()
    return {"libraries": [{"id": row["id"], "name": row["name"], "icon": row["icon"], "folders": len(row["roots"]),
                           "metered": any(cost_for(root['location'], root['root'], config) == 'metered'
                                          for root in row['roots'])}
                          for row in media_libraries.libraries(config)]}


def _own_data_path(raw: str) -> Path | None:
    """把前端递回来的路径收回到 Peach 自己的数据目录里，越界的一律返回 `None`。

    页面上看得见的本机路径只有这一类：凭据文件、问题日志、卸载会删的那几个目录，
    全都是服务端按 `DIRECTORY_KEYS` 自己算出来发下去的。所以这里不信任递回来的那
    一串，而是拿同一份设置重算一遍边界再比对——`resolve()` 之后 `..` 与符号链接都
    已经落到真实位置上，能过这一关的只可能是服务端本来就展示过的东西。
    """
    from . import settings_file

    if not raw.strip():
        return None
    config = settings_file.active()
    try:
        target = Path(raw).expanduser().resolve()
    except OSError:
        return None
    for root in [config.data_root, *(config.directory(key) for key in settings_file.DIRECTORY_KEYS)]:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if target == resolved or target.is_relative_to(resolved):
            return target
    return None


@router.post("/api/reveal")
def reveal(request: Request, body: dict[str, Any] = Body(default_factory=dict), args: dict[str, str] = Depends(require_auth)):
    """在本机文件管理器里定位一个文件：媒体资产按 `id`，Peach 自己的数据按 `path`。

    媒体那条用于「跳过去自己整理网盘目录」：A:/B: 是 CloudDrive 挂上来的盘符，在
    资源管理器里和本地目录没有区别。它的路径一律由服务端按 asset id 查出来——
    `q_item` 刻意不把 `path` 发给前端，这里不能反过来让前端把路径传进来，所以
    `id` 在场时 `path` 连看都不看。

    `path` 那条留给页面上本来就印着全路径的几处（凭据文件、问题日志、数据目录）：
    人读到路径，下一步就是去那儿看一眼。边界仍在服务端（`_own_data_path`）。

    写不进 ledger，所以不受 reader 的只读闸门约束；但它会在**服务端所在的
    机器**上弹窗，从 Mac 浏览时弹在 Windows 那台，也正是文件所在的机器。
    """
    if body.get("id") is None and body.get("path") is not None:
        # 这一条的原因要一路显示到路径旁边，所以每种都自带一句中文：页面那层的统一错误
        # 映射按状态码说话，410／501 落在它的表外，只剩一句「操作未完成」。
        target = _own_data_path(str(body.get("path") or ""))
        if target is None:
            return JSONResponse({"error": "path not in the data root",
                                 "message": "这个位置不归 Peach 管，只能自己打开"}, status_code=403)
        if not target.exists():
            return JSONResponse({"error": "file missing",
                                 "message": "这个位置已经不在了"}, status_code=410)
        try:
            if not reveal_path(target):
                return JSONResponse({"error": "unsupported platform",
                                     "message": "这台机器上打不开文件管理器"}, status_code=501)
        except OSError as error:
            LOGGER.warning("reveal failed for %s: %s", target, error)
            return JSONResponse({"error": "reveal failed",
                                 "message": "打开文件管理器失败，请重试"}, status_code=500)
        return {"ok": True, "path": str(target)}
    try:
        asset_id = int(body.get("id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "id must be an integer"}, status_code=400)
    asset = request.app.state.repository.media_asset(asset_id)
    if asset is None or not asset.path:
        return JSONResponse({"error": "not found"}, status_code=404)
    target = translate_ledger_path(asset.path)
    if is_unmapped(target):
        return JSONResponse(
            {"error": "source not mapped", "location": asset.location},
            status_code=409)
    if not target.exists():
        # 文件已经不在了——正是「删完回来同步」的入口，前端据此提示对账。
        return JSONResponse(
            {"error": "file missing", "location": asset.location},
            status_code=410)
    try:
        if not reveal_path(target):
            return JSONResponse({"error": "unsupported platform"}, status_code=501)
    except OSError as error:
        LOGGER.warning("reveal failed for asset %s: %s", asset_id, error)
        return JSONResponse({"error": "reveal failed"}, status_code=500)
    return {"ok": True, "id": asset_id, "location": asset.location}


@router.get("/api/tasks/{run_id}")
def task_run_detail(request: Request, run_id: int,
                    _args: dict[str, str] = Depends(require_auth)):
    """任务中心里的某一轮。带路径参数，所以进不了 `web_router` 那两张精确匹配的表。"""
    try:
        return web_tasks.q_task(request.app.state.web_contract, run_id)
    except KeyError as exc:
        # `str(KeyError(...))` 会把消息连引号一起带出来，取 args 才是那句话本身。
        return JSONResponse({"error": str(exc.args[0])}, status_code=404)


def _conflict(error: TaskRunConflict) -> JSONResponse:
    """手动触发撞上在跑的那一轮：409，并带上挡路那一轮的 id。

    不用 500 也不用 200：这不是故障，用户的请求也没有生效。前端拿 `blocking_run_id`
    直接跳到活动页上的那一行，比一句「已有任务在进行」有用得多。

    `message` 是给人看的那句话，所以在这里用 `task_label` 翻一次：异常自己住在 `jobs`
    里，那一层在 `task_runs` 下面，拿不到中文名表。
    """
    return JSONResponse(
        {"error": "task already running", "task_key": error.task_key,
         "blocking_run_id": error.blocking_run_id,
         "message": f"{task_label(error.task_key)}已有一轮在进行，等它跑完再试"},
        status_code=409)


@router.get("/api/{route:path}")
def api_get(request: Request, route: str, args: dict[str, str] = Depends(require_auth)):
    state = request.app.state
    sync = state.sync
    try:
        payload = web_contract.dispatch_api_get(
            state.web_contract, f"/api/{route}", args)
        if route == "review" and sync is not None and sync.read_only:
            payload = state.review_mirror.resolve(payload)
        return payload
    except TaskRunConflict as exc:
        return _conflict(exc)
    except UpdateBusy as exc:
        return JSONResponse({'error': 'update in progress', 'message': str(exc)}, status_code=409)
    except FolderRuleConflict as exc:
        return JSONResponse({'error': 'folder rule conflict', 'message': str(exc)}, status_code=409)
    except KeyError:
        return JSONResponse({"error": "not found"}, status_code=404)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=400)
    except Exception:
        LOGGER.exception("unhandled GET contract error for /api/%s", route)
        return JSONResponse({"error": "internal server error"}, status_code=500)


@router.post("/api/{route:path}")
def api_post(
    request: Request,
    route: str,
    body: dict[str, Any] = Body(default_factory=dict),
    _args: dict[str, str] = Depends(require_auth),
):
    sync = request.app.state.sync
    route_path = f"/api/{route}"
    if route_path not in web_contract.POST_HANDLERS:
        return JSONResponse({"error": "not found"}, status_code=404)
    if (sync is not None and sync.read_only
            and route_path not in web_contract.READ_ONLY_POST_ROUTES):
        # 非写入端或冲突状态都只读；继续写只会产生无法自动合并的分叉。
        # 但只读的 POST 要放行：它们用 POST 只是因为要带请求体，并不碰账本。
        # `detail` 是诊断信息，`message` 是给用户的可读解释与恢复方式。
        return JSONResponse(
            {
                "error": "ledger read-only",
                "detail": sync.detail,
                "message": sync.read_only_message,
            },
            status_code=409,
        )
    try:
        return web_contract.dispatch_api_post(
            request.app.state.web_contract, route_path, body)
    except TaskRunConflict as exc:
        return _conflict(exc)
    except UpdateBusy as exc:
        return JSONResponse({'error': 'update in progress', 'message': str(exc)}, status_code=409)
    except KeyError:
        return JSONResponse({"error": "not found"}, status_code=404)
    except RevisionConflict as exc:
        # 客户端手上的取值已经不是账本现在这一个。回 409 并带上现值，页面据此刷新
        # 再让人重判；当成 400 的话，「你填错了」和「有人先改了」读起来一模一样。
        return JSONResponse(
            {
                "error": "field revision conflict",
                "message": str(exc),
                "expected_revision": exc.expected,
                "revisions": {str(key): value for key, value in exc.revisions.items()},
            },
            status_code=409,
        )
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=400)
    except Exception:
        LOGGER.exception("unhandled POST contract error for /api/%s", route)
        return JSONResponse({"error": "internal server error"}, status_code=500)
