# MAXHUB

面向 **fnOS NAS、Docker 和局域网单用户**的轻量 STRM 媒体库。读取本地已刮削的 NFO、海报和演员头像，通过 LitePan Emby 302 反代连接设备上的播放器。

[![Docker image](https://github.com/qvstp001/MAXHUB/actions/workflows/publish-image.yaml/badge.svg)](https://github.com/qvstp001/MAXHUB/actions/workflows/publish-image.yaml)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[Docker 镜像 / Packages](https://github.com/qvstp001/MAXHUB/pkgs/container/maxhub) · [使用指南](docs/USAGE.md) · [更新记录](CHANGELOG.md) · [开发交接](docs/DEVELOPMENT.md)

## 能做什么

- 按演员、厂商、标签和目录浏览；支持搜索、组合筛选、分页与横竖封面。
- 演员与厂商资料页、演员收藏、自定义影片清单。
- 本地海报、剧照、演员头像及按需缩略图缓存。
- 多个 STRM 资源按影片归并，增量扫描与定时扫描。
- LitePan 所需的 Emby 接口、签名 302 播放链接、PotPlayer、mpv 和 M3U。

网页无需密码，适合局域网使用。来源目录只读；不改写 NFO、不移动媒体，不下载、代理或转码视频。界面以桌面使用为主。

## Docker 部署

项目**只发布 Docker 镜像**，通过 GitHub Packages / GHCR 分发，不维护 GitHub Releases 或安装包。当前稳定版本为 **0.3.0**。

### 1. 准备配置

下载 [compose.ghcr.yaml](compose.ghcr.yaml) 和 [.env.example](.env.example)，放到同一目录，将 `.env.example` 复制为 `.env`。也可在 NAS 终端执行：

```sh
mkdir -p maxhub
cd maxhub
curl -fsSLO https://raw.githubusercontent.com/qvstp001/MAXHUB/main/compose.ghcr.yaml
curl -fsSL https://raw.githubusercontent.com/qvstp001/MAXHUB/main/.env.example -o .env
```

编辑 `.env`，按 NAS 实际路径和局域网地址填写：

```dotenv
MEDIA_PATH=/vol1/1000/media/strm
MAXHUB_PORT=8096
MAXHUB_IMAGE_TAG=0.3.0
MAXHUB_DATA_VOLUME=maxhub-data
PUBLIC_URL=http://192.168.1.10:8096
PLAYBACK_PROXY_URL=
SCAN_INTERVAL=1800
```

`MEDIA_PATH` 指向包含 STRM、NFO 和图片的目录。`PLAYBACK_PROXY_URL` 填 LitePan 实际显示的反代入口；留空使用 STRM 地址直连。`SCAN_INTERVAL=0` 关闭定时扫描，启动时仍扫描一次。

### 2. 启动

```sh
docker compose -f compose.ghcr.yaml pull
docker compose -f compose.ghcr.yaml up -d
```

打开 `.env` 中的 `PUBLIC_URL`，等待首次扫描完成即可浏览。飞牛 Docker 的 Compose 项目也可使用同一份配置。端口被占用时，同时修改 `MAXHUB_PORT` 和 `PUBLIC_URL`。

媒体只读挂载到 `/media`；索引、收藏、清单和缩略图保存在命名卷 `maxhub-data`。容器以 UID/GID `10001:10001` 运行，需能读取和遍历媒体目录。环境变量只用于首次初始化，之后的播放设置在网页「设置」中修改。

### 3. 更新

先备份数据卷，在 `.env` 中设置目标镜像版本，再运行：

```sh
docker compose -f compose.ghcr.yaml pull
docker compose -f compose.ghcr.yaml up -d
```

更新时保留 `MAXHUB_DATA_VOLUME` 和容器内媒体挂载路径。已有 QMaxHub 数据迁移、多目录挂载及备份方法见[数据与升级](docs/USAGE.md#数据与升级)。

## 镜像与版本

| 标签 | 用途 |
| --- | --- |
| `ghcr.io/qvstp001/maxhub:0.3.0` | 当前稳定版本，推荐部署 |
| `ghcr.io/qvstp001/maxhub:latest` | 跟随 `main`，通过测试后更新 |
| `ghcr.io/qvstp001/maxhub:sha-<提交前七位>` | 固定某次构建，便于定位与回退 |

镜像由 [GitHub Actions](https://github.com/qvstp001/MAXHUB/actions/workflows/publish-image.yaml) 完成服务测试、容器构建、302 协议和数据持久化检查后推送。版本 Git 标签用于标记源码和镜像，不创建 GitHub Release。

## 文档

- [使用指南](docs/USAGE.md)：收藏、清单、目录、媒体布局、LitePan 配置及数据迁移。
- [开发交接](docs/DEVELOPMENT.md)：本地开发、测试与 Docker 镜像发布。
- [浏览接口](docs/API.md) · [验证记录](docs/validation.md) · [桌面交互说明](docs/desktop-ui-review.md)。

当前已验证虚构媒体下的服务、Docker/Podman 容器和 1440/1100 像素桌面交互。真实 fnOS、LitePan、网盘取链及外部播放器仍需实机联调。

## 开源与来源

项目保留原仓库及 [Peach](https://github.com/peach-mitao/peach) 的版权与 [AGPL-3.0-or-later 许可证](LICENSE)。桌面交互参考 Peach，轻量版使用 Python、SQLite、Pillow 和原生 JavaScript，无前端构建步骤。旧 Peach 版本保留在 Git 历史和归档分支，详见[开发交接](docs/DEVELOPMENT.md)。
