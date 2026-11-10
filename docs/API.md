# MAXHUB 浏览接口

`/api/movies` 现在返回分页摘要 `{items,total,page,limit}`；详情使用 `/api/movies/{id}`。如有使用旧版完整列表响应的外部脚本，需要改用分页和详情接口。

组合筛选接口示例：`/api/movies?actor=演员名&studio=厂商名&tag=标签一&tag=标签二&root=/media&folder=分类&recursive=0`。重复 `tag` 表示交集，最多 20 项。`recursive=0` 仅查看直属影片，默认 `1` 包含子目录。目录接口 `/api/folders` 额外返回 `selected` 和 `ancestors`；节点含 `name`、`count`、`direct_count`、`has_children`，支持 `search`、`page`、`limit`。

资料页接口 `/api/entities?kind=actor&name=演员名` 或 `kind=studio` 返回影片数、可用影片数、资源数、年份和关联筛选项；每类关联项最多 8 个，其余通过通用筛选器查找。统计仅查询数据库索引，资源可用指扫描时的本地文件状态。详情资源新增相对于来源根目录的 `folder`，可用于目录跳转；剧照 `?size=preview` 返回最大 320 × 200 的 WebP 缩略图。

演员收藏和清单 API 见 [开发交接](DEVELOPMENT.md#验证)。播放对接范围见 [使用指南](USAGE.md#litepan-对接)。
