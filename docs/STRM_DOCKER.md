# STRM 定制版与 Docker 部署

本分支在 Peach 的馆藏界面、NFO 和海报读取、网页播放能力上，提供 STRM 302 直连、PotPlayer 与 Android mpv 入口。原 QMaxHub 保留在仓库 `main` 分支；本分支为可独立构建的完整 Peach 定制源码。

## 来源与许可

上游是 [peach-mitao/peach](https://github.com/peach-mitao/peach)，基于提交 `de22796c04919aaa057d77930c33c81313765569`（0.46.1）；STRM 定制内容对应本地 Peach 提交 `5bfe412`。保留上游版权、资源归属与 [AGPL-3.0-or-later 许可证](../LICENSE)。

迁移分支导入上游的完整源码快照、测试和构建资源，原仓库历史由 `main` 保留。涉及的定制实现为外部播放票据与路由、STRM 跳转策略、详情媒体类型查询、外部播放器组件、测试和配套说明。

## 部署

在 NAS SSH 终端使用 Bash，克隆定制分支：

```sh
git clone --branch codex/peach-strm --single-branch https://github.com/qvstp001/qmaxhub.git peach-strm
cd peach-strm
cp deploy/.env.strm.example .env.strm
```

编辑 `.env.strm`，填写已存在的 STRM 目录、专用数据目录和可读取媒体的用户 UID/GID。先在 NAS 管理界面创建专用数据目录，并确保对应用户可写；原媒体权限保持原样。模板拒绝自动创建不存在的绑定源目录。

`PEACH_BIND` 默认只监听本机。需要局域网访问时填写 NAS 的局域网地址，保留登录认证。数据目录和端口与原 QMaxHub 分开。

构建并启动：

```sh
docker compose --env-file .env.strm -f deploy/compose.strm.yaml up -d --build
```

初次启动自动准备独立配置和数据库。查看首次登录口令：

```sh
docker compose --env-file .env.strm -f deploy/compose.strm.yaml exec peach peach token
```

浏览器打开配置的地址和端口，登录后在 Peach 配置页添加媒体目录 `/media`。选择扫描以读取 STRM、配套 NFO 和海报。宿主机目录在 Compose 中挂入，网页填写容器内路径。

`/media` 使用只读绑定，应用扫描、播放和本地配套资料读取不要求媒体写权限。所有配置、数据库和缓存保存在独立 `/data`。STRM 无需补齐 Emby 兼容接口；LitePan 的 `/api/strm/play/...` 入口可直接作为指针使用，已有 Emby 上游配置可保留。

## 播放

网页播放器通过 Peach 代理读取上游。影片详情的「外部播放器 / VR」可选择「302 直连」或「Peach 代理」，生成短时链接或 M3U，再选择 PotPlayer（Windows）或 mpv（Android）。Android intent 对应 `is.xyz.mpv` 包；其他发行版可使用网络播放地址。

仅在可信来源的 HTTPS CDN 域名解析为 Fake-IP 时，设置 `PEACH_STRM_FAKE_IP_ORIGINS` 为该来源的协议、主机与端口。跨来源 HTTPS 证书验证仍开启，私网、回环、链路本地目标与混合私网解析仍受限制。详细协议与约束见[外部播放器](EXTERNAL_PLAYERS.md)。

## 横幅与字幕

首页视频卡片提供「横幅」与「海报」模式。横幅优先使用本地 fanart，缺图时沿用已有封面或预览图；海报宽度可在 140–260 像素之间调整，默认 180 像素。模式与尺寸保存在浏览器设置中。首页支持按番号或名称排序，番号按字母和数字自然顺序排列（例如 `ABC-2` 在 `ABC-10` 前），再次点击可翻转方向；没有番号的影片排在末尾。名称使用资料标题，空缺时使用文件名。

库内采集先读取本地 NFO 和图片。有效 NFO 或账本已有影片资料时，该影片只处理本地资料，不再查询外部元数据、封面或人物资料；缺少部分字段也不触发联网补齐。只有没有本地资料的影片才进入外部采集，无法解析或身份不匹配的 NFO 不阻止该流程。

影片详情优先使用同目录横幅作为待播画面，点击「查看图片」可在横幅、封面和正片之间切换。
支持 `<影片文件名>-fanart.jpg`、`-landscape`、`-banner`、`-backdrop`，图片可为 JPG、PNG、WebP；
单影片目录也支持 `fanart.jpg` 等通用文件名。本地 NFO 的 `fanart/thumb`、`art/fanart`、
`art/landscape`、`art/banner` 引用同样可用。添加图片后刷新页面即可读取。

播放器「设置 → 字幕 → 在线搜索字幕 → 字幕来源」可选择 SubtitleCat 或迅雷字幕库。
按当前影片番号或片名搜索，选中文件后加载到本次播放；迅雷结果保留来源标注的语言，未标注时显示「语言未标注」。
支持 SRT、ASS、SSA、VTT 文本字幕，单文件上限 4 MiB。

## 验证与保留范围

STRM 票据、302/HEAD、Range、代理、Fake-IP 策略及隐私检查的专项测试通过；桌面与手机浏览器验证通过。NAS Linux 容器已验证非 root、只读媒体、NFO 与海报入库、实际影片片头解码、认证和重启持久化。具体设备、目录、馆藏与验收日志属于私有记录，不进入代码仓库。

Windows 全量测试仍有两项在未修改上游中同样失败的进程检测用例；未声明全量通过。PotPlayer 和 Android mpv 的协议链接已检查，应用内唤起需要对应设备验收。

停用测试部署时，在相同目录运行：

```sh
docker compose --env-file .env.strm -f deploy/compose.strm.yaml stop
```

保留专用数据目录和媒体挂载，可随时重新启动。原 QMaxHub 的主分支、数据目录与服务独立保留。
