# 页面路由

媒体库播放器使用本地资产与实体身份。查询参数保存筛选、排序和播放上下文；人物名字用于展示和检索。

## 浏览与详情

| 地址 | 用途 |
| --- | --- |
| `/`、`/wall` | 媒体库与播放墙 |
| `/?browse=folders` | 原目录浏览，支持 `folder` 与 `folder_recursive` |
| `/assets/:id` | 一条本地媒体记录的详情与播放 |
| `/works/:code` | 查询本地有效资产并重定向至资产详情；无本地记录时 404 |
| `/performers`、`/studios`、`/creators`、`/agencies`、`/tags` | 本地人物、厂牌、创作者、事务所与标签名册 |
| `/performers/:id` 等实体路径 | 本地实体资料与相关媒体；系列支持 `/series/:id` |
| `/playlists` | 播放列表 |
| `/unseen`、`/watch-later`、`/flagged` | 没看过、稍后看与已标记 |
| `/trash`、`/junk-files` | 本地媒体状态筛选 |
| `/immerse` | 沉浸浏览 |

实体合并后沿用最终身份，名称与别名地址转到对应的数字 ID。不存在或种类不匹配的实体返回 404。详情覆盖在原列表上，关闭时保留列表筛选与滚动位置。

## 播放上下文

| 示例 | 上下文 |
| --- | --- |
| `/assets/30741?playlist=7` | 播放列表 7 |
| `/assets/30741?mix=30740` | 以资产 30740 为起点的 Mix |
| `/assets/30741?parts=30740` | 分卷组 |
| `/assets/30741?editions=30740` | 版本组 |

路径标识当前资产，队列键标识播放来源。旧 `/item/:id` 与 `/mix/:seed/:item`、`/parts/:seed/:item`、`/editions/:seed/:item`、`/playlists/:playlist/:item` 重定向至相应资产和队列参数。

## 设置

| 地址 | 用途 |
| --- | --- |
| `/settings`、`/settings/appearance` | 外观与导航 |
| `/settings/playback` | 浏览与播放、海报／横幅尺寸 |
| `/settings/jav` | 本地作品显示 |
| `/settings/search`、`/settings/content` | 本地搜索和内容显示 |
| `/settings/library` | 媒体目录、本地资料导入与缺失索引检查 |
| `/settings/network` | 网络与访问 |
| `/settings/maintenance` | 应用与维护 |
| `/configuration` | 重定向至媒体库设置 |
| `/stats` | 本地馆藏统计 |
| `/login` | 登录 |

设置支持直接打开、刷新和浏览器前进后退。配置写入仍由服务端的鉴权和本机配置权限检查保护。

## 服务接口

媒体库保留 `/api/items`、`/api/item`、`/api/entity`、`/api/entity/shapes`、`/api/index`、`/api/photos`、`/api/playlists` 等本地接口。播放、图片、字幕、STRM 和签名票据使用各自媒体接口。

`/api/library-processing` 读取媒体目录并导入本地 NFO 与图片；`/api/library-scan` 检查既有索引并隐藏缺失文件，保留资产行与个人记录。两者由用户发起。

订阅、关注、RSS、刮削、在线发现、资源检索、云下载和浏览历史采集接口不注册。对应页面及旧别名返回 404，不触发历史任务。作品番号入口只解析本地资产，不访问在线作品详情。

启用接口文档时，`/docs`、`/docs/oauth2-redirect` 和 `/openapi.json` 提供服务文档。首次运行页在未配置状态显示，健康检查只使用 `/healthz`。
