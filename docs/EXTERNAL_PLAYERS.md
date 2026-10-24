# 外部播放器与 VR

本地或已挂载视频的作品详情提供「外部播放器 / VR」。选择此设备的播放器后，点击「生成播放链接」，
再打开播放器或下载 M3U 播放列表。VR 播放器可使用生成的网络播放地址。

| 选项 | 使用方式 |
| --- | --- |
| M3U 播放列表 | 用支持网络地址的外部播放器打开下载的 `.m3u` |
| PotPlayer（Windows） | 调用 `potplayer://` 协议；需要安装播放器并注册协议 |
| mpv（Android） | 调用 Android Intent；官方包名为 `is.xyz.mpv`，浏览器需支持 Intent |
| VLC（iPhone / iPad） | 调用 VLC 的 `vlc-x-callback` 协议 |
| IINA（Mac） | 调用 IINA 的 `iina://weblink` 协议 |

播放器和 STRM 播放方式选择只保存在当前浏览器。另一台设备需要能访问当前 Peach 地址；电脑上用 `localhost`
生成的地址不能供手机访问。HTTPS 使用项目证书时，外部设备也需要信任该证书。

播放链接有效期为 6 小时，Peach 重启后失效。链接只允许读取选中的资产，不包含本机盘符路径或
长期登录凭据。代理请求支持 HTTP Range，传输原始文件；解码能力、VR 投影方式由外部播放器决定。
生成链接和打开播放器不计作观看记录，也不能证明播放器已经起播。

## STRM 播放方式

STRM 资源可选择以下方式，选定后点击「生成播放链接」：

- **302 直连**：播放器访问 Peach 的签名入口，Peach 每次读取当前 STRM 并返回 302；视频由播放器直接读取。
  STRM 地址及后续重定向地址必须能从播放器所在设备访问。网盘 UA、IP 和请求头要求由上游服务与播放器处理。
- **Peach 代理**：视频经过 Peach，沿用 Range 和 HLS 子资源代理；适用于只有 Peach 能访问 STRM 地址的部署。

STRM 的外部播放默认选择 302 直连，网页播放器继续使用 Peach 代理。本地视频使用 Peach 原文件传输。
STRM 应保存长期可用的解析入口；文件内临时网盘直链过期时，需要在生成工具中更新 STRM。

### LitePan 与 Fake-IP DNS

LitePan 生成的 `/api/strm/play/…` 或 `/api/strm/path/…` 是独立播放入口。外部播放器可通过
Peach 的 302 直连访问该入口，现有 LitePan → Emby 反代可继续用于原来的客户端。

网盘域名在本机代理中解析为 `198.18.0.0/15` 的 Fake-IP 时，网页代理默认会拒绝该跨源跳转。
可在启动前通过 `PEACH_STRM_FAKE_IP_ORIGINS` 指定可信 STRM 来源，例如 `http://litepan.example:5211`，
多个来源以分号分隔。只填写协议、主机和端口，不填写 STRM 路径或令牌。
该来源返回的 HTTPS 公网域名可解析为 Fake-IP；跨源私有地址、IP 字面量和 HTTP 目标仍被拒绝，
HTTPS 证书校验继续生效。实际 DNS 全部为公网地址时不需要此配置。

## 协议与验证

签发接口 `POST /api/external-playback?id=…&mode=proxy|direct` 使用现有登录及同源检查；省略 `mode` 时使用 `proxy`。
`direct` 只接受 STRM。流和 M3U 端点验证进程内密钥签发的单资产限时票据，资产、入口和播放方式均参与签名，
每次读取仍经过现有媒体根目录检查。直连票据不能切换成代理票据，M3U 保留签名入口与播放方式。
播放地址的 origin 一并签名：优先使用通过同源检查的页面 Origin；无 Origin 的客户端使用已配置的
隧道入口或当前服务地址。M3U 使用该签名地址，代理转发的本机 Host 不会改写列表中的公网入口。

VLC 协议参考 [VideoLAN 官方实现说明](https://mailman.videolan.org/pipermail/vlc-devel/2014-October/099830.html)，
IINA 协议参考 [IINA 上游协议讨论](https://github.com/iina/iina/issues/3922)。播放器实现不进入 Peach，
无新增依赖。协议打开后的实际播放取决于访问端是否安装对应播放器；自动化验证覆盖票据、Range、
M3U 内容和页面交互，不替代真实设备的解码验收。

PotPlayer 与 Android mpv 的链接形状参考 QMaxHub `0e5501f` 的外部播放入口，并使用 Peach 的资产票据。
自动回归验证 HTTP/HTTPS Intent、签名查询参数、GET/HEAD 302、播放时重读 STRM、模式与资产隔离。

Windows 原生验证使用现有 ffplay、临时 HTTPS 服务与专用测试证书，播放 M3U 中的签名网络地址。
两秒 H.264 合成测试画面在关闭音频、隐藏输出时正常播放并退出，ffprobe 确认解码 20 帧；
TLS 校验保持开启。该验证不覆盖 VLC / IINA 协议唤起或 VR 投影。
