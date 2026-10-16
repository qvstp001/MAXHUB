# QMaxHub

面向 STRM 与本地 NFO 的私人影片资料库。浏览器管理，Docker 常驻运行，Windows PotPlayer / Android mpv 外部播放。

当前为 **0.1.0 基础版本**。后端使用 Python 标准库与 SQLite，前端为原生 JavaScript，无需安装第三方运行依赖或构建前端。管理方式参考本机 Javdex 的番号、演员、标签与系列组织方式，代码独立实现。

## 已实现

- 递归扫描多个来源目录中的 `.strm`，读取同名 NFO、分段共用 NFO、`movie.nfo`。
- 提取番号、片名、简介、发行日期、时长、制作商、导演、系列、评分、标签与演员。
- 读取本地海报、封面、演员头像与剧照；支持 `poster`、`fanart`、`.actors`、`extrafanart`、`screenshots`、`javdex-samples`。
- 同番号的多个文件归并为一部影片，详情中选择具体资源。
- 搜索、排序、横竖封面切换、演员 / 标签 / 系列 / 制作商导航。
- 收藏、手动已看标记、个人评分持久保存；重新扫描不覆盖个人状态。
- 启动扫描、手动扫描、定时扫描与逐项错误报告。源文件消失或损坏时保留收藏记录并标记资源不可用。
- 管理员密码登录、会话 Cookie、限速、限定资源的 12 小时播放票据。
- 提供 LitePan 所需的 Emby API 子集、302 跳转、PotPlayer 协议链接、Android mpv Intent、复制链接与 M3U 下载。

## 播放链路

```text
浏览器打开 QMaxHub（8096）
  → 选择影片及 STRM 资源
  → 在本机打开 PotPlayer / Android mpv
  → 请求 LitePan 反代入口（42069）的 /Videos/.../stream
  → LitePan 读取 QMaxHub（8096）的媒体源信息
  → LitePan 解析网盘资源并返回直链
  → 播放器访问网盘文件
```

QMaxHub 在 `MediaSources[].Path` 中提供 STRM 内的 HTTP(S) 地址，供 LitePan 识别。它不下载媒体、不探测视频、不转码，也不提前缓存临时网盘直链。每次读取播放信息或直接跳转时都会重新读取 STRM 文件。

另提供「直接跳转 STRM 地址」模式，播放器先访问 QMaxHub 的签名播放地址，再由 QMaxHub 返回 302，适用于 STRM 本身已指向可直接播放的服务。

## Docker 部署

需要 Docker Engine / Docker Desktop 与 Compose。

1. 复制 `.env.example` 为 `.env`。
2. 修改 `ADMIN_PASSWORD`（至少 10 个字符）、`MEDIA_PATH` 和两个访问地址。
3. 在本项目目录执行：

```sh
docker compose up -d --build
```

浏览器访问 `http://服务器IP:8096`，用 `.env` 中的密码登录。启动会自动扫描一次；进入「设置与扫描」查看结果。

示例配置：

```dotenv
ADMIN_PASSWORD=use-your-own-long-password
MEDIA_PATH=D:/Media/JAV
QMAXHUB_PORT=8096
PUBLIC_URL=http://192.168.1.10:8096
LITEPAN_PUBLIC_URL=http://192.168.1.10:42069
SCAN_INTERVAL=1800
COOKIE_SECURE=false
```

Linux / NAS 的 `MEDIA_PATH` 可以是 `/volume1/media/jav`。镜像以 UID / GID `10001:10001` 运行，需要对来源目录有读取与遍历权限。数据库默认保存在命名卷 `qmaxhub-data`；媒体目录以 `:ro` 挂载。

若原 Emby 占用 8096，可先设 `QMAXHUB_PORT=8097`，同时把 `PUBLIC_URL` 和 LitePan 上游改成宿主机的 `8097`；容器内仍使用 8096。确认新库工作正常后再自行决定如何处理原 Emby。

### LitePan 配置

在 QMaxHub「设置与扫描 → LitePan 接入」复制 API Key，然后在 LitePan 的 Emby 反代中设置：

| 配置项 | 示例 |
| --- | --- |
| Emby 地址 | `http://192.168.1.10:8096` |
| API Key | QMaxHub 页面复制出的 Key |
| 反代端口 | `42069` |

点击 LitePan 的「测试」，启用并保存。将其反代入口 `http://192.168.1.10:42069` 填入 QMaxHub 播放设置。**42069 是你配置的 Emby 反代端口，不是 LitePan 管理端口。** 请确认 LitePan 容器已映射该 TCP 端口。

两个容器在同一个 Docker 网络时，LitePan 上游可设为 `http://qmaxhub:8096`。不同 Compose 项目默认网络不互通，需要自行接入同一网络，或使用可达的宿主机地址。播放器地址必须使用 Windows / Android 都能访问的主机名或 IP，不能填写容器名或其他设备的 `127.0.0.1`。

LitePan 通过 API 读取 STRM 地址，本项目不要求 LitePan 挂载同一份 STRM 目录。

如果 STRM 内容是 `http://127.0.0.1:5211/...`，而播放器在其他设备，可在「STRM 地址替换」中设置旧、新地址前缀。替换不改变路径、查询参数和原有签名；路径签名仍须由 LitePan 验证。QMaxHub 只允许 HTTP(S) 资源，不支持 `file://`、本地视频文件或 Kodi 的 `URL|Header=...` 格式。

> LitePan 兼容实现依据其公开的 Emby 反代接口；尚未在用户实际 LitePan 版本、网盘账号和真实播放器上完成联调。LitePan 的播放拦截与认证行为由 LitePan 控制，QMaxHub 的播放票据不能替代 LitePan 入口的访问控制。请将这两个服务限制在可信网络，跨互联网访问时应配置 HTTPS 与相应的入口控制。

### 本地播放器

进入影片详情，选择资源，点击「选择播放器」，再点击对应播放器链接。

- **Windows PotPlayer**：需要已安装 PotPlayer，并为浏览器注册 `potplayer://` 协议处理程序。不同安装方式不一定自动注册；如果浏览器没有唤起播放器，可下载 M3U 后用 PotPlayer 打开，或复制播放链接到 PotPlayer 的「打开链接」。
- **Android mpv**：使用 `intent://...#Intent;scheme=http(s);type=video/any;package=is.xyz.mpv;end;`，要求安装官方包名 `is.xyz.mpv` 的 mpv-android，并使用允许 Intent 跳转的浏览器。其他 mpv 分支可能需要不同包名。
- **其他播放器**：复制 HTTP 播放链接，或下载 M3U。

浏览器无法确认外部播放器是否真正启动，也无法收取它的播放进度；观看状态需要手动标记。播放链接有效期 12 小时，过期后重新打开即可。网盘的 UA、IP 或账号限制由 LitePan 和播放器实际处理，本项目不代传自定义播放请求头。

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
$env:LITEPAN_PUBLIC_URL = 'http://192.168.1.10:42069'
python -m qmaxhub
```

运行自动化测试：

```sh
python -m unittest discover -s tests -v
```

打开虚构资料预览（不读取真实媒体，不包含有效视频地址）：

```sh
python tests/preview.py
```

访问 `http://127.0.0.1:18096`，密码 `preview-only-123`。数据与抽象示例海报写入 `.test-data/preview`，与实际应用数据隔离。此预览只监听本机。

## 当前兼容范围

提供 `/System/Info`、`/Items/{id}`、`/Items/{id}/PlaybackInfo`、`/Items?Ids=...`、`/Videos/{id}/stream`、媒体目录列表和扫描任务接口；支持可选 `/emby` 前缀以及常见 Emby API Key 传递方式。

这是供 LitePan 使用的 **Emby 接口子集**，不是完整 Emby 服务，未承诺 Emby / Infuse 等客户端完整接入。没有转码、内置播放器、刮削、多用户权限、DLNA、远程图片采集或外部播放器进度同步。

验证记录与实际边界见 [验证记录](docs/validation.md)。

设计与接口依据：[LitePan 官方说明](https://www.litepan.top/guide/tools/enhanced.html)、[LitePan 反代实现](https://github.com/Ponphil/LitePan/blob/main/internal/embyproxy/service.go)、[mpv-android Intent 规范](https://github.com/mpv-android/mpv-android/blob/master/docs/intent.html)。
