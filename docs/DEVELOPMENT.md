# MAXHUB 开发交接

本文与 `0.2.0` 同步，用于在另一台电脑上直接接手。产品要求不依赖此前聊天记录。

## 已确定的方向

用户在 fnOS NAS 上用 Docker 管理本地保存的网盘 STRM。NFO、poster、fanart、thumb 和演员头像已刮削好。网页仅局域网使用，不需要密码。播放必须兼容现有 LitePan 的 Emby 302 反代，不下载或转码视频。

媒体从演员、厂商、影片标签和文件夹交叉浏览；界面参考 Peach 的桌面交互，控制依赖与页面请求规模。当前只验证桌面端，后续独立做 App，网页接口应可复用。

目前组合筛选、目录树、演员/厂商资料页和影片详情已经完成。未接入用户真实 NAS、LitePan 或网盘，不要把模拟接口检查当作实机播放成功。

## 新电脑开始

安装 Git、Python 3.12 或以上。Node.js 22 或以上仅用于地址测试和浏览器验收，应用运行不需要 Node.js。容器测试需 Docker Engine 或 Podman。

```sh
git clone https://github.com/qvstp001/MAXHUB.git
cd MAXHUB
git switch main
git pull --ff-only
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tests/preview.py
```

Linux/macOS：

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tests/preview.py
```

打开 `http://127.0.0.1:18096`。这是独立虚构馆藏，不会扫描真实媒体；资料写在被忽略的 `.test-data/preview-profiles/`。停止时按 Ctrl+C。

真实目录调试要显式配置环境变量。应用不会自动读取 `.env`，`.env` 仅供 Compose 使用。PowerShell 示例：

```powershell
$env:DATA_DIR='./data'
$env:LIBRARY_ROOTS='D:/Media/strm'
$env:PUBLIC_URL='http://127.0.0.1:8096'
$env:HOST='127.0.0.1'
.\.venv\Scripts\python.exe -m maxhub
```

真实媒体只读处理，开发优先使用虚构预览。不要复制旧电脑的 `.venv`、凭据或缓存到仓库。

## 代码入口

| 路径 | 职责 |
| --- | --- |
| `maxhub/__main__.py` | 环境配置、服务启动和扫描调度 |
| `maxhub/server.py` | HTTP/JSON、图片、播放链接和 LitePan Emby 兼容接口 |
| `maxhub/store.py` | SQLite、配置、旧状态和数据迁移 |
| `maxhub/catalog.py` | 分页摘要、字段索引、目录索引、资料页聚合 |
| `maxhub/scanner.py` | STRM/NFO/图片解析、增量扫描和稳定 ID |
| `maxhub/artwork.py` | 受限并发、WebP 缩略图缓存 |
| `web/app.js` | 页面、列表、资料页与导航 |
| `web/browse-state.js` | 规范地址、组合条件、兼容旧链接 |
| `web/filter-picker.js`、`web/folder-browser.js` | 按需筛选和目录树 |
| `web/movie-detail.js` | 详情、剧照、资源选择、播放器偏好 |
| `web/styles.css`、`catalog-controls.css`、`profiles.css` | 基础、筛选/目录、资料/详情样式 |
| `tests/` | 单元/HTTP、虚构资料、桌面交互、容器检查 |

网页无需构建。新增脚本或样式时要同步 `server.py` 的静态文件白名单与 `index.html`。API 的参数语义和数据兼容由服务端负责。

## 验证

将下面的 `python` 替换为虚拟环境 Python，或先激活环境：

```sh
python -m unittest discover -s tests -v
node tests/browse_state.test.cjs
git diff --check
```

浏览器验收使用开发依赖，不加入容器。可安装到被忽略的目录：

```sh
npm install --prefix .test-data/browser-tools playwright
```

PowerShell 终端一启动虚构服务：

```powershell
.\.venv\Scripts\python.exe tests/desktop_fixture.py
```

终端二：

```powershell
$env:NODE_PATH=(Resolve-Path '.test-data/browser-tools/node_modules').Path
$env:PLAYWRIGHT_BROWSER_CHANNEL='msedge'
node tests/desktop_browse.cjs
node tests/desktop_profiles.cjs
```

Linux/macOS 可用 `NODE_PATH="$PWD/.test-data/browser-tools/node_modules"`；未安装 Edge 时，通过本地 Playwright CLI `node .test-data/browser-tools/node_modules/playwright/cli.js install chromium` 安装测试浏览器，并清除 `PLAYWRIGHT_BROWSER_CHANNEL`。脚本仅使用 1440 × 1000、1100 × 800 桌面窗口，地址默认 `http://127.0.0.1:18099`，可用 `MAXHUB_TEST_URL` 指定。失败截图在 `artifacts/`，不用提交。

容器验收：

```sh
python tests/container_smoke.py prepare .test-data/container-smoke/media
docker build -t maxhub:test .
docker run -d --name maxhub-test --cap-drop ALL --security-opt no-new-privileges:true --publish 127.0.0.1:18097:8096 --env PUBLIC_URL=http://127.0.0.1:18097 --env SCAN_INTERVAL=0 --mount type=bind,src=<虚构媒体目录的绝对路径>,dst=/media,readonly --mount type=volume,src=maxhub-test-data,dst=/data maxhub:test
python tests/container_smoke.py check http://127.0.0.1:18097
docker restart maxhub-test
python tests/container_smoke.py check http://127.0.0.1:18097 --expect-persisted
docker exec maxhub-test python -m maxhub.healthcheck
docker stop maxhub-test
docker rm maxhub-test
```

测试卷保留便于后续恢复验证。不要删除真实应用数据卷。Podman 可使用对应同名命令。

## 发布与回退

源码仓库：[qvstp001/MAXHUB](https://github.com/qvstp001/MAXHUB)。容器镜像：`ghcr.io/qvstp001/maxhub`。GitHub Actions 的 `Publish GHCR image` 在 `main` 推送或 `v*` 标签时运行。

流程先执行 Python 和地址测试，再构建镜像、启动虚构只读媒体容器、验证 302 和数据持久化，通过后才推送。`main` 发布 `latest` 和 `sha-<前七位>`；`v0.2.0` 发布 `0.2.0` 与对应 SHA 标签。发布凭据来自 Actions 的 `GITHUB_TOKEN`，新电脑不需要复制密码或在代码里保存 token。

修改版本时同步 `maxhub/__init__.py`、`.env.example`、README、CHANGELOG，再在获准发布后推送主分支和未使用的版本标签。到 Actions 确认成功，不能只凭 Git 推送成功判断镜像已发布。GHCR 首次建立的软件包可能需要在包设置中设为 Public，确认匿名拉取正常。

NAS 部署读 README。升级前停止容器并备份整个数据卷；固定版本或 SHA 镜像有利于回退。若新版写入了数据库结构，回退应结合升级前的数据备份，不只换镜像。

旧 Peach 主分支保存在 `archive/peach-before-maxhub-0.2.0`，其数据库和运行方式与 MAXHUB 独立。仅需查看旧界面时用该分支或提交 `a9bd476bdb61cf83f753e0e10ee52f2460e92953`，不要把完整旧框架重新并入轻量实现。

## 下一步

1. 在 fnOS 上用只读真实媒体目录验收扫描、中文路径、NFO 图片、多来源与资料数量；备份数据卷。
2. 配置真实 LitePan Emby 上游与反代入口，验证多资源、签名地址和播放器；不要将临时网盘链接持久化。
3. 观察 NAS 实际首屏和图片耗时，再按数据量优化；现有一万部合成基准不能替代 NAS 测试。
4. 按实际需要考虑搜索分组建议和桌面表格，参考 `docs/desktop-ui-review.md`。不默认扩展新的大功能。
5. App 阶段再确定平台与界面框架，复用已有分页、资料、目录、图片及播放接口。

本机目录、测试端口和旧聊天均不是项目依赖。接手时先检查 `git status`、当前分支、最近提交、Actions 与上述测试，再开始修改。
