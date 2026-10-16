# QMaxHub

面向 STRM 与本地 NFO 的私人影片资料库。浏览器管理，Docker 常驻运行，Windows PotPlayer / Android mpv 外部播放。

当前为 **0.1.1 基础版本**。后端使用 Python 标准库与 SQLite，前端为原生 JavaScript，无需安装第三方运行依赖或构建前端。管理方式参考本机 Javdex 的番号、演员、标签与系列组织方式，代码独立实现。

## 已实现

- 递归扫描多个来源目录中的 `.strm`，读取同名 NFO、分段共用 NFO、`movie.nfo`。
- 提取番号、片名、简介、发行日期、时长、制作商、导演、系列、评分、标签与演员。
- 读取本地海报、封面、演员头像与剧照；支持 `poster`、`fanart`、`.actors`、`extrafanart`、`screenshots`、`javdex-samples`。
- 同番号的多个文件归并为一部影片，详情中选择具体资源。
- 搜索、排序、横竖封面切换、演员 / 标签 / 系列 / 制作商导航。
- 收藏、手动已看标记、个人评分持久保存；重新扫描不覆盖个人状态。
- 启动扫描、手动扫描、定时扫描与逐项错误报告。源文件消失或损坏时保留收藏记录并标记资源不可用。
- 管理员密码登录、会话 Cookie、限速、限定资源的 12 小时播放票据。
- 提供播放反代对接所需的 Emby 兼容 API 子集、302 跳转、PotPlayer 协议链接、Android mpv Intent、复制链接与 M3U 下载。

## 播放链路

支持两种 STRM 302 播放方式，可按实际部署选择工具和地址。

```text
302 反代入口：
浏览器选择影片 → 本地播放器 → 自定义反代播放入口
  → 反代工具读取 QMaxHub 媒体源 → 解析 STRM 并返回网盘直链

STRM 地址直连：
浏览器选择影片 → 本地播放器 → QMaxHub 签名播放地址
  → 302 跳转到 STRM 中的 HTTP(S) 地址 → 对应服务解析或播放
```

QMaxHub 在 `MediaSources[].Path` 中提供 STRM 内的 HTTP(S) 地址，供兼容的反代工具识别。它不下载媒体、不探测视频、不转码，也不提前缓存临时网盘直链。每次读取播放信息或直接跳转时都会重新读取 STRM 文件。

服务访问地址、反代地址、端口和路径前缀均可配置。反代模式需要工具支持 QMaxHub 提供的 Emby 兼容接口；如果其他工具直接提供可播放的 STRM 地址，可选择 STRM 地址直连模式。

## Docker 部署

需要 Docker Engine / Docker Desktop 与 Compose。

1. 复制 `.env.example` 为 `.env`。
2. 修改 `ADMIN_PASSWORD`（至少 10 个字符）、`MEDIA_PATH` 和 `PUBLIC_URL`；使用外部反代时再填写 `PLAYBACK_PROXY_URL`。
3. 在本项目目录执行：

```sh
docker compose up -d --build
```

浏览器访问配置的 `PUBLIC_URL`，用 `.env` 中的密码登录。启动会自动扫描一次；进入「设置与扫描」查看结果。

### 使用 GHCR 镜像

镜像地址：`ghcr.io/qvstp001/qmaxhub:latest`，当前发布平台为 Linux / amd64。准备同样的 `.env`，使用预构建镜像启动：

```sh
docker compose -f compose.ghcr.yaml pull
docker compose -f compose.ghcr.yaml up -d
```

Podman 使用对应的 `podman compose -f compose.ghcr.yaml` 命令。该镜像已公开，可匿名拉取。

仓库的 `Publish GHCR image` 工作流会在推送到 `main` 时运行集成测试与容器检查，通过后发布 `latest` 和 `sha-<提交短编号>`。推送 `v*` 标签时还会发布去掉 `v` 的版本标签。可以在 `.env` 中设置 `QMAXHUB_IMAGE_TAG=sha-...` 固定某次镜像。发布使用 GitHub 自动提供的临时令牌，不需要在仓库保存个人访问令牌。

示例配置：

```dotenv
ADMIN_PASSWORD=use-your-own-long-password
MEDIA_PATH=D:/Media/JAV
QMAXHUB_PORT=8096
PUBLIC_URL=http://192.168.1.10:8096
PLAYBACK_PROXY_URL=https://proxy.example/media
SCAN_INTERVAL=1800
COOKIE_SECURE=false
```

Linux / NAS 的 `MEDIA_PATH` 可以是 `/volume1/media/jav`。镜像以 UID / GID `10001:10001` 运行，需要对来源目录有读取与遍历权限。数据库默认保存在命名卷 `qmaxhub-data`；媒体目录以 `:ro` 挂载。

若原 Emby 占用 8096，可先设 `QMAXHUB_PORT=8097`，同时把 `PUBLIC_URL` 和反代工具的上游改成对应的宿主机地址。容器内部默认 8096，也可通过 `PORT` 单独配置。确认新库工作正常后再自行决定如何处理原 Emby。

### 302 反代配置

在「设置与扫描 → 播放连接」选择播放方式：

- **302 反代入口**：填写反代工具对外提供的完整播放地址，例如 `https://proxy.example/media` 或 `http://192.168.1.10:18443`。没有指定的必用工具或端口。
- **STRM 地址直连（302 跳转）**：播放器先访问 QMaxHub，再由 QMaxHub 302 跳转至 STRM 内地址。适用于 STRM 本身已指向其他工具提供的播放服务。

对接支持 Emby 兼容接口的工具时，在「反代工具对接」复制 API Key，将本服务可达地址设为工具的上游。工具与 QMaxHub 在同一个 Docker 网络时可使用容器名和实际内部端口；跨 Compose 项目需要加入同一网络，或使用可达的宿主机地址。播放器使用的入口必须是其设备能访问的地址。

如 STRM 内填写的是容器内部地址或 `127.0.0.1`，可以在「STRM 地址替换」中配置原地址前缀与替换地址。替换保留路径、查询参数和原有签名。QMaxHub 只支持 HTTP(S) 资源，不支持 `file://`、本地视频路径或 Kodi 的 `URL|Header=...` 格式。

反代工具的播放拦截与认证行为由对应工具控制。QMaxHub 的播放票据不能替代反代入口的访问控制。外部工具的具体兼容性仍需按其版本联调。

升级时会自动迁移数据库中的旧反代地址和播放模式，保留 API Key、签名密钥与收藏状态。新部署使用通用环境变量 `PLAYBACK_PROXY_URL`，也可以直接在网页中配置。

### 使用 Podman

已在 Windows + Podman 5.6.0 / WSL Linux amd64 上验证镜像构建、Compose 启动、健康检查及容器重建后的数据保留。

虚拟机未启动时先执行 `podman machine start`。准备好 `.env` 后运行：

```sh
podman compose up -d --build
```

Windows 的 Podman WSL 环境挂载路径请填写虚拟机可访问的路径，例如宿主机 `D:/Media/JAV` 对应 `.env` 中的 `MEDIA_PATH=/mnt/d/Media/JAV`。Docker Desktop 仍使用前文的 Windows 路径示例。

如果单独使用 `podman build`，建议使用 `podman build --format docker -t qmaxhub .` 保留镜像健康检查。Compose 已显式定义同一检查，因此不依赖镜像格式是否保留它。

本次测试遇到 WSL 虚拟机继承的 `127.0.0.1:7897` 代理不可达；单次拉取时清除代理环境变量后成功下载 Python 基础镜像。遇到同类下载错误时，应先检查虚拟机的代理可达性。

### 本地播放器

进入影片详情，选择资源，点击「选择播放器」，再点击对应播放器链接。

- **Windows PotPlayer**：需要已安装 PotPlayer，并为浏览器注册 `potplayer://` 协议处理程序。不同安装方式不一定自动注册；如果浏览器没有唤起播放器，可下载 M3U 后用 PotPlayer 打开，或复制播放链接到 PotPlayer 的「打开链接」。
- **Android mpv**：使用 `intent://...#Intent;scheme=http(s);type=video/any;package=is.xyz.mpv;end;`，要求安装官方包名 `is.xyz.mpv` 的 mpv-android，并使用允许 Intent 跳转的浏览器。其他 mpv 分支可能需要不同包名。
- **其他播放器**：复制 HTTP 播放链接，或下载 M3U。

浏览器无法确认外部播放器是否真正启动，也无法收取它的播放进度；观看状态需要手动标记。播放链接有效期 12 小时，过期后重新打开即可。网盘的 UA、IP 或账号限制由对应播放服务和播放器实际处理，本项目不代传自定义播放请求头。

## 媒体目录布局

```text
JAV/
  ABC-123/
    ABC-123.strm
    ABC-123.nfo            # 或 movie.nfo
    ABC-123-poster.jpg     # 或 poster.jpg / folder.jpg
    ABC-123-fanart.jpg     # 或 fanart.jpg / ABC-123-landscape.jpg
    .actors/
      演员名字.jpg
    extrafanart/
      1.jpg
      2.jpg
```

优先读取和 STRM 同名的 NFO；`ABC-123-CD1.strm` 也可读取 `ABC-123.nfo`。仅单影片目录或相同分段名目录使用共用 `movie.nfo`；单 STRM 目录还可匹配唯一 NFO，避免误用其他影片资料。

图片支持 JPG、JPEG、PNG、WebP、GIF、AVIF（显示能力取决于浏览器）。只读取媒体根目录内的本地文件；NFO 中的远程图片引用不会自动下载。NFO 使用 UTF-8 / UTF-8 BOM，每个文件上限 2 MiB，不允许 DTD 或实体声明。

来源目录为只读，应用不修改 STRM、NFO 或图片。缺失标记以完整成功遍历的目录为依据；目录访问错误会记录异常，不把访问失败直接当成文件被删除。扫描是全量元数据重读，未实现文件监听或增量指纹加速。

## 数据与配置

`/data/qmaxhub.sqlite3` 保存索引、用户状态、会话、API Key 与签名密钥。备份时停止容器，再备份整个数据卷，避免遗漏 SQLite 的 WAL 文件；来源媒体目录独立备份。不要删除数据卷来更新程序。

首次启动用环境变量初始化播放设置。之后网页中保存的配置优先，不会被每次重启覆盖。更改播放地址或扫描周期请在网页保存。修改 `ADMIN_PASSWORD` 后重建容器，已有登录会话失效。

多目录可修改 Compose 的挂载项，并将环境变量 `LIBRARY_ROOTS` 设为 `/media-a;/media-b`，或 JSON 数组。不同库中相同番号会合并为一部影片的多个资源。

## 本地开发与验证

Python 3.12 或更高版本：

```powershell
$env:ADMIN_PASSWORD = 'your-local-test-password'
$env:LIBRARY_ROOTS = 'D:/Media/JAV'
$env:PUBLIC_URL = 'http://localhost:8096'
$env:PLAYBACK_PROXY_URL = 'https://proxy.example/media'
python -m qmaxhub
```

运行自动化测试：

```sh
python -m unittest discover -s tests -v
```

容器验收可先用 `python tests/container_smoke.py prepare .test-data/container-smoke/media` 生成独立虚构媒体，再将该目录只读挂载到测试容器的 `/media`。它包含一部 `SMOKE-001` 影片、两个 STRM 和本地图片。只对该隔离测试库运行以下检查：

```powershell
$env:QMAXHUB_TEST_PASSWORD = 'your-isolated-container-password'
python tests/container_smoke.py check http://127.0.0.1:18097
# 重建容器后，先验证此前写入的状态仍在
python tests/container_smoke.py check http://127.0.0.1:18097 --expect-persisted
```

检查只验证 STRM 的 302 跳转，不会访问占位播放地址或真实网盘。

打开虚构资料预览（不读取真实媒体，不包含有效视频地址）：

```sh
python tests/preview.py
```

访问 `http://127.0.0.1:18096`，密码 `preview-only-123`。数据与抽象示例海报写入 `.test-data/preview`，与实际应用数据隔离。此预览只监听本机。

## 当前兼容范围

提供 `/System/Info`、`/Items/{id}`、`/Items/{id}/PlaybackInfo`、`/Items?Ids=...`、`/Videos/{id}/stream`、媒体目录列表和扫描任务接口；支持可选 `/emby` 前缀以及常见 Emby API Key 传递方式。

这是供播放反代工具使用的 **Emby 兼容接口子集**，不是完整 Emby 服务，未承诺 Emby / Infuse 等客户端完整接入。没有转码、内置播放器、刮削、多用户权限、DLNA、远程图片采集或外部播放器进度同步。

验证记录与实际边界见 [验证记录](docs/validation.md)。

外部播放器接口参考：[mpv-android Intent 规范](https://github.com/mpv-android/mpv-android/blob/master/docs/intent.html)。
