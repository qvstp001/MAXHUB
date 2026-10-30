# MAXHUB 开发约定

先读 [README.md](README.md)、[开发交接](docs/DEVELOPMENT.md) 和 [版本说明](CHANGELOG.md)。它们与代码一起维护，避免新电脑依赖旧聊天记录。

## 产品边界

- 面向 fnOS NAS、Docker、局域网单用户使用，网页无需密码。
- 读取本地 STRM/NFO/poster/fanart/thumb/演员头像，来源目录只读。
- 必须保留 LitePan Emby 302 反代兼容；不转码、不下载或代理视频流。
- 演员、厂商、影片标签、目录组合管理，参考 Peach 桌面交互，保持轻量。
- 只验收桌面端；后续另做 App，不主动加入手机网页专项工作。
- 不扩展在线发现、订阅、云下载、远程刮削、多用户、播放墙等功能。

## 实现与数据

- 后端入口 `python -m maxhub`，Python 3.12+、SQLite、Pillow。原生 JavaScript，无前端构建步骤。
- 列表与资料页只用 `catalog` 索引；分页、按需加载、缩略图缓存必须保留，不把完整媒体库发到浏览器。
- `maxhub/store.py` 中的 `qmaxhub.sqlite3` 是兼容文件名；扫描指纹、影片/资源 ID、播放密钥和用户状态不可随更名重置。
- 浏览器只持久化显示/播放器偏好，不持久化临时播放链接。切换资源或影片必须使旧请求失效。
- `.env`、真实媒体、数据库、凭据、测试生成目录与截图不提交。测试只使用虚构资料，不连接真实 NAS/网盘。
- `.codegraph/` 存在时先用 CodeGraph 理解代码；不存在时不自行建立索引。

## 验证与发布

- 修改服务后运行 `python -m unittest discover -s tests -v`；地址状态运行 `node tests/browse_state.test.cjs`。
- 界面交互按交接文档运行两个桌面浏览器脚本，窗口为 1440 × 1000 和 1100 × 800。
- 运行依赖与开发期 Playwright 分开；不要为界面引入不必要的框架。
- 新功能同步文档，说明实际验证范围，不能把协议检查表述为真实 LitePan/网盘联调完成。
- 用户明确要求发布时再推送；主分支和版本标签由 GitHub Actions 构建、测试并发布 GHCR。
- 新分支使用 `codex/` 前缀。不要强推、删除用户历史、修改真实媒体或清空数据卷。
