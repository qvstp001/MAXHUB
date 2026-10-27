# 媒体库播放器与 Docker 部署

本仓库 `main` 提供基于 Peach 的媒体库播放器。媒体以只读方式挂载，服务只负责本地资料入库、浏览和播放。保留上游版权和 [AGPL-3.0-or-later](../LICENSE)；原 QMaxHub 保留在 `qmaxhub-legacy-before-peach` 标签及完整 Git 历史。

## 部署

在 NAS SSH 的 Bash 终端克隆用户仓库，复制公开配置示例：

```sh
git clone --branch main --single-branch https://github.com/qvstp001/qmaxhub.git peach-strm
cd peach-strm
cp deploy/.env.strm.example .env.strm
```

填写已有媒体目录、专用数据目录和媒体读取用户的 UID/GID，先创建并授权专用数据目录。模板不自动创建缺失的媒体绑定源，不要求修改媒体权限。局域网访问填写 NAS 局域网地址；默认绑定本机。

```sh
docker compose --env-file .env.strm -f deploy/compose.strm.yaml pull peach
docker compose --env-file .env.strm -f deploy/compose.strm.yaml up -d --no-deps --no-build --wait peach
docker compose --env-file .env.strm -f deploy/compose.strm.yaml exec peach peach token
```

首次启动准备专用配置和数据库，最后一条命令查看首次登录口令。在网页设置中添加容器路径 `/media`，启动本地扫描，读取媒体、STRM、配套 NFO 与图片。资料不足时显示文件名，不自动联网补全。

`/media` 只读；配置、数据库、缓存和播放记录保存到 `/data`。STRM 可使用 LitePan 的独立播放 URL，保留既有 LitePan 和 Emby 配置，无需将 Peach 配成 Emby 上游。

## 浏览与播放

支持海报／横幅视图、独立卡片尺寸、自然番号或名称排序、人物和标签、播放列表、收藏与稍后看。横幅可为同名 `-fanart`、`-landscape`、`-banner`、`-backdrop` 图片；单影片目录支持通用文件名，NFO 本地横幅引用也可读取。

STRM 提供代理、302 直连、Range、GET/HEAD、M3U、PotPlayer 和 Android mpv 入口。播放器可加载本地字幕，也可用 SubtitleCat 或迅雷按片名／番号搜索文本字幕；支持 SRT、ASS、SSA、VTT，单文件不超过 4 MiB。

影片和人物刮削、订阅、在线作品发现、资源搜索、云下载及浏览历史口味采集不在服务运行范围。已有资料与历史记录保留，旧任务不自动续跑。

## 构建与发布

镜像使用锁定的默认 Python 依赖，不安装视觉或开发依赖，不下载人脸模型。FFmpeg 和既有 VAAPI 软件栈保留，以支持软件转码及硬件失败回退。Debian FFmpeg 本身依赖 Mesa/LLVM，因此不直接删除底层共享库。

`main` 的镜像相关提交触发 GitHub Actions。工作流完成非 root、鉴权、配置、本地扫描、Range、转码回退、重载、重启持久化及精简依赖验收，记录镜像大小后发布 `ghcr.io/qvstp001/qmaxhub:latest` 与 `sha-<七位提交号>`；PR 只构建验收。

## 更新与回退

更新前使用 SQLite backup API 保存一致性数据库备份，停止 Peach 后保存专用数据快照、实际容器配置及镜像摘要。已有部署保留现场的端口、用户、环境、网络、重启策略和只读媒体挂载，仅更换镜像。

拉取镜像不会改变正在运行的容器。执行 `up` 会短暂重启 Peach，不更新其他服务。`PEACH_IMAGE` 可指定提交标签或固定摘要；回退使用保存的镜像及必要的配套数据快照，不删除媒体、旧镜像或备份。

默认资料路径和现有数据库兼容；本地验证与 Linux 镜像验收分别报告，不以源码测试代替实际部署。外部播放器协议唤起和目标 GPU 转码需在对应设备验收。
