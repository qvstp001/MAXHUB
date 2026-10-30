# MAXHUB

在飞牛 fnOS NAS 上通过 Docker 运行的私人 STRM 媒体库。仅面向局域网部署，网页不设登录。读取已经刮削好的本地 NFO 和图片，通过 LitePan 的 Emby 反代入口播放。

当前版本：**0.2.0**。界面参考 Peach 的桌面交互重新实现，支持可收起侧栏、演员与厂商资料页、组合筛选、目录树、影片详情、浅色/深色主题。列表使用独立分页索引，前端无需构建。

源码：[qvstp001/MAXHUB](https://github.com/qvstp001/MAXHUB) · 镜像：`ghcr.io/qvstp001/maxhub:0.2.0` · [版本说明](CHANGELOG.md) · [换电脑继续开发](docs/DEVELOPMENT.md)

项目保留原仓库及 [Peach 上游](https://github.com/peach-mitao/peach) 的版权与 [AGPL-3.0-or-later 许可证](LICENSE)（上游基线 `de22796c04919aaa057d77930c33c81313765569`）。界面参考来源与交互对照见文末及桌面说明。

网页以桌面浏览与管理为主，后续另做 App，本阶段不进行手机网页专项验收。Peach 后续可参考的交互、实施优先级和 App 接口边界见 [桌面界面对照](docs/desktop-ui-review.md)。

## 核心功能

- 本地 STRM 入库，读取同名 NFO、分段共用 NFO 或 `movie.nfo`；相同番号的多个资源归并展示。
- 读取本地 `poster`、`fanart`、`thumb`、`.actors` 和剧照，不请求远程刮削网站。
- 从**演员、文件夹、厂商、影片标签**浏览媒体库；支持组合筛选、多标签交集、搜索、排序、横竖封面与缺失资源筛选。
- 目录树按分支展开，支持目录搜索、完整路径导航，以及只看本层或包含子文件夹。
- 演员、厂商资料页显示本地头像、馆藏影片/资源数量、发行年份和关联筛选；多分段按一部影片统计。
- 桌面详情采用图片与资料分区，支持本页上一部/下一部、本地剧照放大、资源切换和设备播放器偏好。
- 数据库完成筛选和分页，每页默认 60 部，最大 100 部；点击影片后才读取完整简介、演员和资源信息。
- 海报墙和演员列表按需生成 WebP 缩略图并保存到数据卷；图片支持条件缓存。原始图片保持不变。
- 增量扫描跳过文件属性未变化的 STRM/NFO/图片；启动扫描、手动扫描与可配置的定时扫描。
- LitePan 需要的 Emby 接口子集、签名播放链接、PotPlayer、Android mpv、复制链接和 M3U。

主界面已去掉收藏、已看、个人评分和随机发现等入口。旧数据库中的个人状态仍然保存，升级不清空数据。媒体目录始终只读；这里的管理指浏览、分类与筛选，不改写 NFO 或移动源文件。

## 桌面筛选与目录浏览

在筛选条中选择演员、厂商或影片标签，再点「应用筛选」。各类条件同时生效；标签可选择多个，影片需要满足全部所选标签。生效条件逐项展示，可单独移除，也可「全部清除」。

点击「文件夹」打开目录树，会保留当前筛选。展开节点才读取该分支；可搜索目录并沿完整路径跳转。「包含子文件夹」默认开启，关闭后仅查看当前目录直属的影片。目录树的数量按全库统计，影片区和筛选条显示实际匹配数量。

筛选、目录范围、搜索、排序和页码保存在地址中。刷新和浏览器前进/后退会恢复这些条件；当前会话中返回列表也会恢复滚动位置。候选筛选项、目录分支和影片均分页读取，不在浏览器加载全库详情。

点击演员或厂商进入资料页；关联演员、厂商和标签按钮会在该资料页内叠加筛选，页头读数保持该演员/厂商的全部馆藏统计。移除主要身份条件会回到媒体库，保留其它条件。

影片详情可切换本页作品（左右方向键），查看海报、横幅和原图。剧照展开后才请求缩略图，每次最多新增 12 张；放大后用方向键切换、Esc 返回详情。播放资源旁可跳到所在目录。切换影片或资源会清除旧播放链接，播放器选择保存在当前设备；播放链接不会写入浏览器存储。

## 飞牛 fnOS 部署

将源码放入 NAS 的应用目录，通过终端或飞牛 Docker 的 Compose 项目部署。

推荐使用已发布镜像：下载本仓库的 `compose.ghcr.yaml` 和 `.env.example`，按下文配置后运行：

```sh
docker compose -f compose.ghcr.yaml pull
docker compose -f compose.ghcr.yaml up -d
```

`.env.example` 默认固定 `0.2.0`；`MAXHUB_IMAGE_TAG=latest` 跟随主分支的已验证构建。源码构建方式如下。

1. 复制 `.env.example` 为 `.env`。
2. 设置本地媒体路径、NAS 访问地址和 LitePan 反代入口。下面的媒体路径仅为示例，使用飞牛中该文件夹的实际路径。

```dotenv
MEDIA_PATH=/vol1/1000/media/strm
MAXHUB_PORT=8096
MAXHUB_IMAGE_TAG=0.2.0
MAXHUB_DATA_VOLUME=maxhub-data
PUBLIC_URL=http://192.168.1.10:8096
PLAYBACK_PROXY_URL=http://192.168.1.10:18443
SCAN_INTERVAL=1800
```

3. 在项目目录构建并启动：

```sh
docker compose up -d --build
```

打开 `PUBLIC_URL` 即可使用，无需密码。启动时后台扫描，已有媒体库可直接浏览。初次部署需要等扫描入库。

`18443` 只是反代端口示例，应填写 LitePan 实际显示的反代入口。若已有服务占用 8096，可将 `MAXHUB_PORT` 和 `PUBLIC_URL` 改为 8097。修改网页中保存过的播放配置时，使用「设置」，环境变量只用于首次初始化。无需设置管理员密码或 Cookie 配置；旧环境中保留这些变量也不会启用登录。

容器以 UID/GID `10001:10001` 运行，需有媒体目录的读取和遍历权限。媒体以只读方式挂载到 `/media`；SQLite 与缩略图保存在 `MAXHUB_DATA_VOLUME` 指定的命名卷，默认 `maxhub-data`。更新时保留此卷。

多目录需要增加 Compose 挂载项，并将 `LIBRARY_ROOTS` 改为 `/media-a;/media-b` 或 JSON 数组。不同来源的同名文件夹独立显示；目录内的多分段按影片计数。

## LitePan 对接

```text
MAXHUB 页面 → 此设备的外部播放器 → LitePan Emby 反代入口
  → MAXHUB Emby 接口返回 STRM 地址 → LitePan 解析并提供播放
```

在 LitePan 的「增强工具 → Emby 反代」中：

1. Emby 地址填写 LitePan 可访问的 MAXHUB 地址，例如 `http://NAS-IP:8096`。如果两个容器在同一 Docker 网络，也可使用 `http://maxhub:8096`。
2. API Key 从 MAXHUB「设置 → LitePan 对接」复制，测试连接并启用反代。此 Key 用于 LitePan 的服务对接，网页无需输入。
3. 将 LitePan 显示的反代入口保存到 MAXHUB 的播放设置，选择「302 反代入口」。这个入口需要能被实际播放设备访问。

媒体源中的 `Path` 是每次重新读取的 STRM HTTP(S) 地址，不是 NAS 的文件路径，不缓存临时网盘直链。已按 LitePan 公开实现验证 `/System/Info`、`/emby/Items?Ids=...&Fields=Path,MediaSources`、多媒体源选择、API Key 认证和刷库接口；真实网盘、UA/IP 限制及已安装的 LitePan 版本仍需实机联调。LitePan 自己的入口访问控制由 LitePan 管理。

LitePan 的反代实现识别自己的 STRM 路径，须使用其可识别的生成地址。如果 STRM 已指向其他可播放 HTTP(S) 服务，可在高级使用中选择「STRM 地址直连」。不支持本地视频路径、`file://`、Kodi `URL|Header=...`，也不传输或转码视频。

参考：[LitePan 配置说明](https://www.litepan.top/guide/tools/enhanced.html)、[LitePan 反代实现](https://github.com/Ponphil/LitePan/blob/main/internal/embyproxy/service.go)。

## 媒体目录

```text
strm/
  厂商或自定义分类/
    ABC-123/
      ABC-123.strm
      ABC-123.nfo        # 也支持 movie.nfo
      ABC-123-poster.jpg # 或 poster.jpg / folder.jpg
      ABC-123-fanart.jpg # 或 fanart.jpg / thumb.jpg
      .actors/
        演员名字.jpg
      extrafanart/
        1.jpg
```

优先匹配 STRM 同名 NFO，`ABC-123-CD1.strm` 可共用 `ABC-123.nfo`。共用 `movie.nfo` 只用于可确定为单影片的目录，避免将不同影片错误归并。无番号时按资源路径确定身份。

NFO 为 UTF-8 或 UTF-8 BOM，最大 2 MiB，根节点为 `movie`。图片支持 JPEG、PNG、WebP、GIF、AVIF。厂商从 `studio` 或 `maker` 读取，影片标签来自 `tag` 和 `genre`，演员来自 `actor/name`。

## 数据与升级

`/data/qmaxhub.sqlite3` 是资料索引、配置和旧个人状态；`/data/artwork` 是可重建的缩略图缓存。来源 STRM/NFO/图片独立保存。备份时停止容器，再备份整个数据卷。

升级旧库时自动建立新的浏览索引，保留影片 ID、播放密钥及旧状态。新索引建立一次，之后不需要每次重启重建。扫描遇到损坏文件会记录异常；目录访问失败不会直接当作文件被删除。增量判断使用文件大小、修改/变更时间及本地资料目录内容，不是实时文件监听。如果来源存储未正确更新文件属性，可以在设置中点击「重读全部资料」，强制重新读取本地元数据。

数据库文件名继续使用 `qmaxhub.sqlite3`，便于保留旧版数据。若已经运行 QMaxHub，先停止旧容器并备份数据卷，再将 `MAXHUB_DATA_VOLUME` 设置为旧卷的实际名称（用 `docker volume ls` 确认，常见为 `qmaxhub_qmaxhub-data`），保持媒体在容器内的挂载路径一致后启动 MAXHUB。旧 `QMAXHUB_PORT` 变量仍可作为兼容回退，新部署使用 `MAXHUB_PORT`。浏览器的主题、密度和播放器偏好会自动迁移。

这里的旧库指旧 QMaxHub 的 `qmaxhub.sqlite3`。远端 Peach 版的 `ledger.db` 不属于该格式；此轻量版使用独立数据卷，从只读媒体目录重新扫描入库，不改写 Peach 数据库。切勿直接把 Peach 数据卷当作 MAXHUB 的现成数据库。

## 开发与验证

运行时为 Python 3.12+、SQLite 与 Pillow（仅负责图片缩放），前端为原生 JavaScript，无前端构建步骤。

```sh
python -m pip install -r requirements.txt
# 先配置 LIBRARY_ROOTS、PUBLIC_URL 等环境变量
python -m maxhub
```

```sh
python -m unittest discover -s tests -v
node tests/browse_state.test.cjs
python tests/benchmark_catalog.py 10000
python tests/preview.py
```

预览只使用虚构资料，访问 `http://127.0.0.1:18096`。详情、分页、目录、缩略图和 LitePan 接口的验证范围见 [验证记录](docs/validation.md)。

桌面浏览器验收使用独立的 80 部虚构影片：先在一个终端运行 `python tests/desktop_fixture.py`，再在具备 Playwright 开发环境的终端运行 `node tests/desktop_browse.cjs` 和 `node tests/desktop_profiles.cjs`。可用 `PLAYWRIGHT_BROWSER_CHANNEL` 指定已安装的浏览器，例如 `msedge`。此工具只用于开发验收，不属于容器运行依赖；不执行手机端检查。

`/api/movies` 现在返回分页摘要 `{items,total,page,limit}`；详情使用 `/api/movies/{id}`。如有使用旧版完整列表响应的外部脚本，需要改用分页和详情接口。

组合筛选接口示例：`/api/movies?actor=演员名&studio=厂商名&tag=标签一&tag=标签二&root=/media&folder=分类&recursive=0`。重复 `tag` 表示交集，最多 20 项。`recursive=0` 仅查看直属影片，默认 `1` 包含子目录。目录接口 `/api/folders` 额外返回 `selected` 和 `ancestors`；节点含 `name`、`count`、`direct_count`、`has_children`，支持 `search`、`page`、`limit`。

资料页接口 `/api/entities?kind=actor&name=演员名` 或 `kind=studio` 返回影片数、可用影片数、资源数、年份和关联筛选项；每类关联项最多 8 个，其余通过通用筛选器查找。统计仅查询数据库索引，资源可用指扫描时的本地文件状态。详情资源新增相对于来源根目录的 `folder`，可用于目录跳转；剧照 `?size=preview` 返回最大 320 × 200 的 WebP 缩略图。

MAXHUB 提供供 LitePan 使用的 Emby 接口子集，不提供完整 Emby 客户端登录、多用户、转码、在线刮削、DLNA 或播放进度同步。

界面参考的是远端 `main` 在 `a9bd476bdb61cf83f753e0e10ee52f2460e92953` 的 Peach 基线，具体布局依据为其顶栏、侧栏、演员/厂牌快捷条与卡片样式。本地旧检出不含该界面。轻量版没有加载 Peach 的完整前端包或附带功能。参考 [该版本源码](https://github.com/qvstp001/qmaxhub/tree/a9bd476bdb61cf83f753e0e10ee52f2460e92953)。
