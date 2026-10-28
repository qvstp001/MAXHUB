# QMaxHub 媒体库播放器

基于 [Peach](https://github.com/peach-mitao/peach) 的单人自托管媒体库，以本地媒体和 STRM 播放为核心，适用于 NAS Docker。

## 功能

- 浏览媒体库、人物、标签和播放列表，支持搜索、自然番号排序及收藏、稍后看。
- 海报和横幅两种视图，分别保存卡片尺寸；详情读取本地封面、横幅和 NFO。
- 扫描媒体目录并导入本地资料；缺少资料时使用文件名，媒体保持只读。
- 网页播放、Range、播放进度、本地字幕，以及 SubtitleCat、迅雷在线字幕。
- STRM 支持代理和 302 直连，可导出 M3U 或调用 PotPlayer、Android mpv。
- FFmpeg 软件转码及既有硬件转码探测、失败回退。

服务不提供影片或人物刮削、订阅追更、在线作品发现、资源搜索、云下载、浏览历史口味采集和资料候选复核。已有影片资料、人物档案、收藏和观看记录继续保存在原数据库中。

## Docker

镜像地址：`ghcr.io/qvstp001/qmaxhub:latest`。源码修改须经构建、容器验收和发布后才进入该标签。

使用 [STRM Docker 部署说明](docs/STRM_DOCKER.md) 配置专用 `/data` 与只读 `/media`，在网页设置中添加容器内媒体路径。已有部署保留原来的端口、用户、挂载和网络配置，更新前备份数据库与专用数据目录。

镜像只安装媒体库运行依赖，不包含 OpenCV、NumPy、人脸模型、爬虫浏览器传输、云下载客户端和桌面托盘依赖。FFmpeg 与现有 VAAPI 软件栈保留。体积以发布工作流记录为准。

## 开发与验证

Python 依赖通过 `pyproject.toml` 和 `uv.lock` 固定。开发环境使用 `uv sync --locked --all-extras`；镜像使用 `uv sync --locked --no-dev --no-editable`。历史模块和桌面工具回归所需依赖只属于开发环境。

前端源码位于 `frontend/`，构建产物位于 `web/dist/`。验证通过统一入口 `scripts/test.ps1` 或 `scripts/test.sh`，见 [测试说明](docs/TESTING.md)。

## 来源与许可

Peach 基线为 `de22796c04919aaa057d77930c33c81313765569`（0.46.1），保留上游版权及 [AGPL-3.0-or-later](LICENSE)。产品精简边界见 [ADR-0114](docs/adr/0114-library-player-runtime.md)。

定制代码仅发布到用户仓库。原 QMaxHub 保留于 `qmaxhub-legacy-before-peach` 标签及完整 Git 历史；旧功能的历史设计文档不代表播放器当前提供这些功能。

[English](README.en.md)
