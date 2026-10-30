# 版本说明

## 0.2.0 — 2026-10-30

项目正式命名为 **MAXHUB**，GitHub 仓库为 `qvstp001/MAXHUB`，镜像为 `ghcr.io/qvstp001/maxhub`。

这次发布将主分支切换为面向本地 STRM 媒体库的轻量实现，参考 Peach 的桌面交互。原 Peach 版本提交 `a9bd476bdb61cf83f753e0e10ee52f2460e92953` 保留在 Git 历史和 `archive/peach-before-maxhub-0.2.0` 分支。

### 已完成

- 本地 NFO、演员头像、海报、fanart、thumb 和剧照读取，多分段资源归并。
- SQLite 摘要索引、分页查询、增量扫描、图片 WebP 缩略图与条件缓存。
- 演员/厂商/多标签/目录/关键词组合筛选，独立移除，地址与浏览记录恢复。
- 按需目录树、祖先路径、搜索、直属/递归范围。
- 演员与厂商资料页，影片/资源/年份统计，关联筛选。
- 桌面影片详情、海报切换、剧照放大、方向键、本页前后切换、目录跳转和播放器偏好。
- 局域网免密、LitePan Emby 接口子集、多媒体源、签名 GET/HEAD 302、PotPlayer/mpv/M3U。
- GitHub Actions 验证与 GHCR 镜像发布、fnOS 部署说明、新电脑开发交接与智能体约定。

### 升级说明

- 推荐固定镜像 `ghcr.io/qvstp001/maxhub:0.2.0`；`latest` 跟随主分支已验证构建，`sha-<提交前七位>` 用于精确定位。
- Python 入口改为 `python -m maxhub`；容器与 Compose 服务名改为 `maxhub`。
- 新环境变量为 `MAXHUB_PORT`、`MAXHUB_IMAGE_TAG`、`MAXHUB_DATA_VOLUME`。`QMAXHUB_PORT` 保留回退。
- 数据库继续使用 `/data/qmaxhub.sqlite3`；旧 QMaxHub 数据卷应通过 `MAXHUB_DATA_VOLUME` 明确复用，先停止旧容器并备份。默认新卷为 `maxhub-data`。
- Peach 的 `ledger.db` 与此版本不兼容，使用独立数据卷重新扫描只读媒体。旧 Peach 环境保留作回退，不能覆盖其数据库。
- `/api/movies` 现在返回分页摘要，旧版完整列表调用需迁移至分页与按 ID 详情接口。

### 验证范围

31 项 Python 测试、浏览地址检查、两套桌面交互脚本、1440/1100 像素布局和本机 Linux 容器检查通过。真实 fnOS、LitePan 配置、网盘取链与外部播放器实机播放仍需在 NAS 环境确认。后续 App 尚未开发，本轮未执行手机端验收。
