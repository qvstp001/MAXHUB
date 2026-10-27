"""稳定 JSON 契约的路由表：路径 → 处理器，以及只读端的放行清单。

前端只认这三张表。它们单独成一个模块，是为了让「加一个端点」变成一处改动：
处理器写在自己的域模块里，在这里登记一行。反过来说，这个文件是唯一需要 import
全部域模块的地方，所以域模块之间不必互相认识。

`READ_ONLY_POST_ROUTES` 是这里最容易出事的一张表：写入端闸门管的是账本分叉，
而有些 POST 只是因为要带请求体才用 POST，根本不碰账本。漏登记的表现是用户在
只读端点某个按钮直接吃 409。
"""
from __future__ import annotations

from .review_csv import candidate_root_version
from .web_activity import (
    w_activity,
    w_feedback,
    w_play,
    w_preference,
    w_quality_goal,
    w_watch_later,
)
from .web_batch import q_ads, q_duplicates, w_batch
from .web_catalog import q_editions, q_facets, q_item, q_items, q_parts, q_related, q_tops, w_item_tag
from .web_entity import (
    SUGGEST_GROUP_LIMIT,
    SUGGEST_KIND_LIMIT,
    q_entity,
    q_entity_photos,
    q_entity_shapes,
    q_index,
    q_photo_set,
    q_suggest,
    suggest_kinds,
    w_entity_alias,
    w_entity_name,
)
from .web_links import w_links
from .player_library import q_library_processing, q_library_processing_issues, w_library_processing
from .web_media_repair import q_media_repair, w_media_repair
from .web_orphan_records import q_orphan_records, w_orphan_attach
from .web_playlists import q_playlist, q_playlists, w_playlist
from .web_resource_sync import w_library_scan
from .web_review import q_review, w_review_decision, w_review_genre
from .web_settings import q_settings, w_settings
from .web_library_shortcuts import q_library_shortcuts, w_library_shortcuts
from .web_folders import q_folders, w_folder_preview, w_folder_rule
from .web_state import WebContract, path_version
from .web_tasks import q_tasks
from .web_timeline_thumbnails import (
    q_media_processing, q_thumbnail_jobs, q_timeline, w_media_processing, w_thumbnail_jobs,
)
from .web_stats import q_quality_goals, q_search_history, q_stats, w_search_history


class ContractRouteNotFound(KeyError):
    """The stable JSON contract has no handler for this path."""


def _get_item(contract, args):
    return q_item(contract, int(args["id"]))


def _get_index(contract, args):
    return q_index(
        contract,
        args.get("kind", "tags"),
        args.get("q", ""),
        min(max(int(args.get("limit", "180")), 1), 600),
        max(int(args.get("offset", "0")), 0),
        args.get("category", ""),
    )


def _get_stats(contract, _args):
    return contract.cached("stats", lambda: q_stats(contract))


def _get_tops(contract, args):
    n = min(int(args.get("n", "28")), 60)
    jav = args.get("jav") == "1"
    seed = str(args.get("seed", ""))[:32]
    state = str(args.get("state", ""))
    # 横滚续接一页一页地要，页号必须进缓存键：不进的话第二页拿回的是第一页的答案。
    page = max(int(args.get("page", "0")), 0)
    folders = {key: args[key] for key in ('folder', 'folder_recursive') if args.get(key)}
    return contract.cached(
        f"tops{n}p{page}{'-jav' if jav else ''}:{seed}:{state}:{sorted(folders.items())}",
        lambda: q_tops(contract, n, jav=jav, seed=seed, state=state, page=page, filters=folders),
    )


def _get_ads(contract, args):
    return q_ads(
        contract,
        min(int(args.get("limit", "60")), 200),
        max(int(args.get("offset", "0")), 0),
        args.get("kind", ""),
        args.get("status", "pending"),
    )


def _get_related(contract, args):
    """相关推荐走 LRU 缓存：打分是纯 Python 对几千个候选做 MMR，一次几百毫秒。

    每打开一次资料页都现算太贵，而结果只读不写；写路径（标签、反馈、播放、复核）
    本来就调 `cache_bust()`，缓存跟着一起作废。上面几个聚合用的是 `cached()`，
    这里必须用 `cached_lru()`：键跟着浏览过的资产走，键空间不封闭。
    键里带上 limit——同一个资产要不同条数就是不同结果。
    """
    asset_id = int(args["id"])
    limit = min(int(args.get("limit", "24")), 60)
    return contract.cached_lru(
        f"related:{asset_id}:{limit}", lambda: q_related(contract, asset_id, limit))


def _get_facets(contract, args):
    jav = args.get("jav") == "1"
    scope_kind = str(args.get("scope_kind", ""))
    scope_name = str(args.get("scope_name", ""))
    asset_id = int(args["id"]) if args.get("id") else None
    state = str(args.get("state", ""))
    scope_key = f"{scope_kind}:{scope_name}:{asset_id or ''}:{state}"
    filters = {key: args[key] for key in (
        'loc', 'creator', 'performer', 'studio', 'series', 'agency', 'tag', 'tag_match',
        'len', 'dur_min', 'dur_max', 'orient', 'region', 'exclude_vertical', 'q', 'thumb',
        'library', 'folder', 'folder_recursive',
    ) if args.get(key)}
    scope_key += repr(sorted(filters.items()))
    return contract.cached(
        f"facets{'-jav' if jav else ''}:{scope_key}",
        lambda: q_facets(
            contract,
            jav=jav, scope_kind=scope_kind, scope_name=scope_name, asset_id=asset_id,
            state=state, filters=filters or None,
        ),
    )


def _get_suggest(contract, args):
    """搜索栏每敲一下就来一次，所以走 LRU：键是用户输入，键空间不封闭。

    键里带上 limit 与 kind——同一段输入要不同条数、不同种类就是不同结果。写路径调
    `cache_bust()` 时它跟着一起作废，补全不会在新片入库后还给出旧的一批。
    """
    query = str(args.get("q") or "").strip()[:64]
    limit = min(max(int(args.get("limit", str(SUGGEST_GROUP_LIMIT))), 1), SUGGEST_KIND_LIMIT)
    kinds = suggest_kinds(args.get("kind", ""))
    if not query:
        return q_suggest(contract, "")
    return contract.cached_lru(
        f"suggest:{limit}:{','.join(kinds)}:{query}",
        lambda: q_suggest(contract, query, limit, kinds))


def _get_search_history(contract, args):
    return q_search_history(contract, int(args.get("limit", "10")))


def _get_review(contract, args):
    # 账本之外，复核读三处磁盘：抓取脚本写的候选 CSV、卡片封面徽章用的封面目录、
    # 创作者头像与取景用的头像目录。
    payload = contract.cached_until_changed(
        "review", lambda: q_review(contract),
        candidate_root_version(contract.candidate_root),
        path_version(contract.cover_root), path_version(contract.avatar_root))
    # 数据管理页只要一个待复核条数。完整 payload 带着每条候选的全文，实测是
    # 兆级；卡片上的一个数字不值这趟传输，但计数本身仍来自同一份缓存快照，
    # 不另立一套口径。
    if str(args.get("counts") or "") in {"1", "true"}:
        return {key: payload[key] for key in ("counts", "sources", "skipped_rows")
                if key in payload}
    return payload


def _get_entity_shapes(contract, args):
    # 每一页开头都要这一份（骨架照它留位），全部来自账本，账本不变就一直用同一份。
    return contract.cached_until_changed("entity-shapes",
                                         lambda: q_entity_shapes(contract, args))


GET_HANDLERS = {
    "/api/media-processing": q_media_processing,
    "/api/folders": q_folders,
    "/api/tasks": q_tasks,
    "/api/library-processing": q_library_processing,
    "/api/library-processing/issues": q_library_processing_issues,
    "/api/thumbnail-jobs": q_thumbnail_jobs,
    "/api/timeline": q_timeline,
    "/api/settings": q_settings,
    "/api/library-shortcuts": q_library_shortcuts,
    "/api/library-scan": lambda contract, args: contract.library_scan_job.snapshot() or {"status": "idle"},
    "/api/media-repair": q_media_repair,
    "/api/orphan-records": q_orphan_records,
    "/api/items": q_items,
    "/api/item": _get_item,
    "/api/parts": q_parts,
    "/api/editions": q_editions,
    "/api/entity": q_entity,
    "/api/entity/shapes": _get_entity_shapes,
    "/api/links": w_links,
    "/api/photos": q_entity_photos,
    "/api/photo-set": q_photo_set,
    "/api/index": _get_index,
    "/api/duplicates": q_duplicates,
    "/api/quality-goals": q_quality_goals,
    "/api/stats": _get_stats,
    "/api/tops": _get_tops,
    "/api/ads": _get_ads,
    "/api/related": _get_related,
    "/api/playlists": q_playlists,
    "/api/playlist": q_playlist,
    "/api/facets": _get_facets,
    "/api/suggest": _get_suggest,
    "/api/search-history": _get_search_history,
    "/api/review": _get_review,
}

POST_HANDLERS = {
    "/api/media-processing": w_media_processing,
    "/api/folders/preview": w_folder_preview,
    "/api/folders/rule": w_folder_rule,
    "/api/library-processing": w_library_processing,
    "/api/thumbnail-jobs": w_thumbnail_jobs,
    "/api/activity": w_activity,
    "/api/play": w_play,
    "/api/feedback": w_feedback,
    "/api/watch-later": w_watch_later,
    "/api/playlist": w_playlist,
    "/api/preference": w_preference,
    "/api/quality-goal": w_quality_goal,
    "/api/item-tag": w_item_tag,
    "/api/batch": w_batch,
    "/api/search-history": w_search_history,
    "/api/orphan-records/attach": w_orphan_attach,
    "/api/library-scan": w_library_scan,
    "/api/media-repair": w_media_repair,
    "/api/review/decision": w_review_decision,
    "/api/review/genre": w_review_genre,
    "/api/settings": w_settings,
    "/api/library-shortcuts": w_library_shortcuts,
    "/api/entity-name": w_entity_name,
    "/api/entity-alias": w_entity_alias,
}


#: 这些 POST 只读媒体或写本机缓存，不修改 ledger。
READ_ONLY_POST_ROUTES = frozenset({
    "/api/media-processing",
    "/api/folders/preview",
    # 修复只写 `transcode_root` 里的边车，那是本机缓存，不是账本。
    "/api/media-repair",
})


def dispatch_api_get(contract: WebContract, path, args):
    """Dispatch the stable JSON read contract used by the current web client."""
    try:
        handler = GET_HANDLERS[path]
    except KeyError as exc:
        raise ContractRouteNotFound(path) from exc
    return handler(contract, args)


def dispatch_api_post(contract: WebContract, path, body):
    try:
        handler = POST_HANDLERS[path]
    except KeyError as exc:
        raise ContractRouteNotFound(path) from exc
    return handler(contract, body)
