# 验证记录

日期：2026-10-16。

## 已验证

- Python 3.12.14：12 项本地集成测试通过。测试实际启动 HTTP 服务，使用隔离媒体目录与 SQLite 数据库。
- 测试覆盖 NFO 的中文、XML 转义、CDATA、演员头像、剧照自然排序、多分段归并、缺失 / 损坏 / 恢复后状态保留。
- 测试覆盖 Cookie 登录 / 退出、图片访问、跨站修改拒绝、目录越界与 DTD 拒绝。
- 测试覆盖更换管理员密码后的会话失效、共用分段 NFO 与重新扫描后身份和收藏保留。
- 测试覆盖 Emby 兼容播放接口格式、API Key 验证、GET / HEAD 302、票据过期与资源范围、实时读取更新后的 STRM、地址替换保留签名参数。
- 前端 JavaScript 语法检查通过。
- 浏览器实测：登录、示例海报加载、按番号搜索、详情资源选择、生成 PotPlayer / Android mpv 链接、演员索引。
- 390 × 844 手机视口：底部导航、双列海报及搜索控件正常显示，页面未出现横向溢出。桌面视图正常显示侧边导航与多列海报。
- 截图为虚构 NFO 和程序生成的抽象海报，不是用户真实媒体库。

## Podman 容器验收

本机 Windows + Podman 5.6.0，WSL Linux / amd64，容器内 Python 3.13.16；Compose 使用 Docker Compose v5.5.0，通过 Podman 的 Docker 兼容接口运行。

- 项目 Dockerfile 已实际构建成功，且通过 `podman compose up --build --force-recreate` 完成构建与启动。
- 修复了基础镜像已有 `/media` 时普通 `mkdir` 导致构建失败的问题。
- 健康检查改为 `python -m qmaxhub.healthcheck`，避免 Podman Docker 兼容接口拆分含空格的 `python -c` 参数。Compose 也显式定义健康检查，避免默认 OCI 镜像格式忽略 Dockerfile 中的健康检查。
- 最终容器状态为 `running / healthy`；检查模块在不可达端口正确以状态码 1 退出。
- Linux 镜像内以默认非 root 用户运行现有 12 项集成测试，全部通过。
- Windows 宿主机到容器完成 18 项 HTTP 检查，覆盖登录、匿名访问拒绝、手动扫描、中文元数据、双资源归并、海报和剧照、收藏 / 已看 / 评分、媒体源接口、签名 302、HEAD 与外部播放器链接。
- 重建容器后，先验证原有收藏、已看状态和评分仍存在，再执行接口检查，确认命名数据卷持久化有效。
- 媒体来自独立虚构目录，只读挂载；容器实测 `media_writable=False`。运行 UID 与数据库所有者均为 10001，`CapEff=0`，`NoNewPrivs=1`。
- 测试容器 `qmaxhub-container-test` 仅绑定 `127.0.0.1:18097`，数据卷 `qmaxhub-smoke_qmaxhub-data`。没有接入真实媒体或外部反代工具。

可复用的测试资料生成与 HTTP 检查脚本：`tests/container_smoke.py`。本机隔离 Compose 参数保存在被 Git 忽略的 `.test-data/container-smoke/`，不上传测试密码与本机路径。

## 0.1.1 通用播放配置

- 界面、公开配置示例和文档使用通用的「302 反代入口」及「STRM 地址直连」描述，不要求指定工具或端口。
- 设置字段为 `proxy_url`，环境变量为 `PLAYBACK_PROXY_URL`。旧版本数据库中的地址和模式自动迁移，保留个人状态、登录会话、API Key、签名密钥和旧播放票据。
- 新增迁移幂等性、新配置优先级、HTTPS / 自定义端口 / 路径前缀测试。无效端口和空反代入口被拒绝。
- 容器使用自定义内部端口 `19096`、宿主机端口 `18097` 完成 18 项接口与状态恢复检查；健康检查为 `healthy`。
- 旧字段名称只保留在内部升级兼容逻辑及其回归测试中，不出现在设置页面或新配置接口。

## 未验证

- GitHub Actions 已使用 Docker Engine 完成镜像构建、容器检查及 GHCR 发布；本机使用 Podman 完成验收。
- 未连接用户实际反代工具或网盘账号。Emby 兼容接口已通过合同测试，不代表所有第三方工具都已完成实机联调。
- 未实际唤起 Windows PotPlayer 或 Android mpv 播放真实影片。已验证生成链接的格式及 QMaxHub 端的跳转行为，设备上的协议注册、Intent 支持、网盘 UA / IP 约束仍需实机确认。
- 未进行大规模媒体库性能或跨平台容器验收。
