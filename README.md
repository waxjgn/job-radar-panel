# 打工避雷平台 · 可视化一键部署面板

一个跑在自己电脑上的 Web 图形面板，用来把「打工避雷平台」从源码一键跑起来。
不用敲一大堆命令：选项目源 → 选部署环境 → 填写配置 → 检测环境 → 装依赖 → 启动服务 → 看日志 → 备份导出。

- 后端：Python + Flask（单机运行）
- 前端：原生 HTML / CSS / JavaScript（无框架、无构建步骤）
- 内置模板：整套「打工避雷平台」（数据库表、接口、页面、部署产物）
- 完全离线可用：不依赖 npm、不依赖 Node 构建、GitHub 拉取也不需要本机装 git

---

## 零、线上地址（GitHub Pages 免费托管）

**查询站点**：https://waxjgn.github.io/job-radar-panel/

这是「打工避雷平台」的静态演示：可搜索、可按分类/城市筛选、可点开看每条避雷记录，
数据是示例数据（`docs/data/companies.json`）。免费域名由 GitHub Pages 提供，不需要额外注册或备案。

| 内容 | 位置 | 能不能放 Pages |
| --- | --- | --- |
| 查询站点（静态） | `docs/` | ✅ 免费托管，就是上面那个地址 |
| Flask 后端（带举报/审核/防刷） | `projects/打工避雷平台/` | ❌ Pages 跑不了 Python，要 Render / PythonAnywhere / 自建服务器 |
| 部署面板（本 README 介绍的这个工具） | 仓库根 `app.py` + `core/` + `web/` | ❌ 同上，本机跑最方便 |

Pages 开启方式、自定义域名（`CNAME` + DNS）与后端上公网的三种免费方案，见 [docs/DEPLOY.md](docs/DEPLOY.md)。

本地预览这个静态站：

```bash
cd docs
python -m http.server 8080
# 打开 http://127.0.0.1:8080
```

---

## 一、快速开始

```bash
cd tools/deploy_panel

# 1) 安装面板依赖（只需要 Flask）
python -m pip install -r requirements.txt

# 2) 启动面板
python app.py
```

启动后浏览器会自动打开 <http://127.0.0.1:8765>。

常用参数：

```bash
python app.py --port 9000        # 换个面板端口
python app.py --host 0.0.0.0     # 允许局域网访问（默认只监听本机）
python app.py --no-browser       # 不自动打开浏览器
python app.py --debug            # 调试模式
```

> 面板自己是「部署工具」，不是被部署的项目。面板监听的 8765 和「打工避雷平台」运行的 5000 是两个端口。

---

## 二、六步走完全流程

| 步骤 | 做什么 | 结果 |
| --- | --- | --- |
| 1. 项目源 | 上传 zip／拉取 GitHub／选内置模板 | 代码落到工作目录 |
| 2. 部署环境 | 下拉选择 5 种目标之一 | 自动加载依赖清单与产物清单 |
| 3. 可视化配置 | 域名、端口、数据库、白名单、安全开关、Nginx | 保存到 `config.json` 并生成配置文件 |
| 4. 环境检测 | 点「检测环境」 | 绿/黄/红 彩色结果，缺依赖标红 |
| 5. 部署与运维 | 一键部署 / 启动 / 停止 / 重启 / 日志 | 服务起来，端口可访问 |
| 6. 备份与导出 | 一键备份 / 导出脚本 / 导出代码包 | 压缩包下载到本地 |

---

## 三、两种项目来源（互斥）

### 1）本地上传模式
- 把项目打成 `.zip`，在面板里选择文件 → 点「上传并解压」。
- 面板会做安全检查：拒绝 `../` 路径穿越、拒绝符号链接、限制单文件 200MB / 总量 800MB / 条目 2 万条。
- 如果压缩包里只有一层顶层目录（例如 `proj/app.py`），会自动剥离 `proj/`。

### 2）GitHub 仓库映射模式
- 填仓库地址 `https://github.com/owner/repo.git` + 分支（默认 `main`）+ 可选 Token。
- 点「测试连接」可以看仓库是否可访问、有哪些分支、默认分支是哪个。
- 点「一键拉取代码」把代码拉到工作目录。
- 打开「定时同步」后，面板按间隔自动拉取更新（面板进程存活期间有效）。
- 实现方式：走 `codeload.github.com` 的 tar.gz 归档接口，**不需要本机安装 git**；Token 只用于私有仓库鉴权。

> 提示：没有 Token 也能拉公开仓库；私有仓库必须在 GitHub 里生成一个有 `repo` 读权限的 Token。

---

## 四、五种部署环境

| 环境 | 面板会自动做什么 | 你需要自己准备 |
| --- | --- | --- |
| 本地测试环境（本机） | 生成 `.env`、运行脚本；点启动直接在本机跑起来 | Python 3.8+ |
| Ubuntu 轻量云服务器 | 生成 `nginx.conf`、`dgbilei.service`、`gunicorn.conf.py`、`deploy.sh` | 服务器与安全组放行端口 |
| PythonAnywhere 免费托管 | 生成 `pythonanywhere_wsgi.py` 与依赖清单 | 平台账号，粘贴 WSGI 配置 |
| Render 部署 | 生成 `render.yaml`、gunicorn 配置 | GitHub 仓库 + Render 账号 |
| Vercel（仅前端静态） | 生成 `vercel.json`，导出 `static/` 目录 | Vercel 账号；后端需另外部署 |

面板**只做部署自动化、环境拉取、配置生成**：服务器、域名、备案都要你自己准备，面板不代办。

---

## 五、可视化配置都生成什么

- **域名 / 端口映射**：`80 -> 5000` 这种映射会写进 Nginx 的 `proxy_pass`，应用仍监听 5000。
- **数据库**：SQLite 免安装，MySQL 需要服务器上已建库；切换后字段与生成的配置随之变化，MySQL 会额外生成 `deploy/mysql.sql`。
- **视频域名白名单**：可视化增删（预置 B站/抖音/快手/视频号），保存后写进 `.env` 的 `VIDEO_ALLOWLIST` 与模板的 `video_allowlist` 表，后端据此校验视频链接。
- **安全开关**：人机验证、内容审核、防刷限制；开启后 `ENABLE_*` 为 `true`，内置模板会启用对应中间件。
- **Nginx**：图形表单填写，点「重新生成」看预览；支持 HTTPS（证书路径要自己在服务器上准备好）。

生成的文件（点「预览全部生成文件」可以只看不下载）：

```
deploy/.env.example            环境变量样板
deploy/requirements.txt        合并后的依赖清单
deploy/nginx.conf              Nginx 反向代理配置
deploy/dgbilei.service         systemd 守护单元（Ubuntu）
deploy/gunicorn.conf.py        gunicorn 配置
deploy/render.yaml             Render Blueprint
deploy/vercel.json             Vercel 静态部署
deploy/pythonanywhere_wsgi.py  PythonAnywhere WSGI 入口
deploy/deploy.sh               Ubuntu 一键部署脚本
deploy/run_local.sh / .bat     本机一键运行脚本
deploy/mysql.sql               MySQL 建库建表脚本
deploy/schema.sql              建表 SQL
deploy/README.md               当前环境的分步指引
```

---

## 六、内置「打工避雷平台」模板

选择模板后点「一键部署」，面板会自动展开：

- **数据库表（6 张）**：`company` 公司表、`report` 避雷记录、`review_log` 审核流水、`rate_limit` 防刷计数、`video_allowlist` 视频白名单、`admin_user` 管理账号。
- **接口（9 个）**：首页、搜索、公司详情、提交举报、获取验证码、白名单查询、后台队列、审核动作、健康检查。
- **页面（2 个）**：查询页（搜索 + 举报表单 + 验证码）、管理页（待审核队列 + 通过/驳回）。
- **部署产物**：整套 `deploy/` 配置。

模板源码在 `projects/打工避雷平台/`，可以直接阅读、修改，或者完全不用它、只上传自己的 zip。

---

## 七、运行时目录

面板所有运行期数据都在工具目录下的 `.workdir/`（可用环境变量 `DEPLOY_PANEL_WORKDIR` 改到别处）：

```
.workdir/
├── config.json     面板配置（含 token/密码，注意不要提交到公开仓库）
├── source/         解压或拉取后的项目源码（含 .env、deploy/、数据库文件）
├── uploads/        上传的 zip 暂存
├── build/          生成的部署产物副本
├── logs/app.log    应用运行日志（面板日志窗口「应用运行日志」读它）
├── backups/        一键备份的压缩包
└── exports/        导出的脚本与代码包
```

`.workdir/` 已加入 `.gitignore`，可以整体删除重置。

---

## 八、面对的问题怎么办

| 现象 | 原因与处理 |
| --- | --- |
| 启动面板提示缺少 Flask | 执行 `python -m pip install -r requirements.txt` |
| 检测结果里 nginx / git 标黄 | 本地测试环境不需要它们；Ubuntu 部署才需要 |
| 端口标红「已被占用」 | 换一个应用端口，或先停掉占用端口的进程（面板会给出排查命令） |
| 停止服务失败 | 看日志窗口给出的 pid 与手动命令；无 systemd 时面板用进程方式管理 |
| 上传报「路径穿越」 | 压缩包里含 `../` 或绝对路径条目，重新打包即可 |
| GitHub 拉取报「分支不存在」 | 用「测试连接」看分支列表，改成正确分支名 |
| Vercel 环境点启动没反应 | Vercel 只托管静态页面，后端要部署在别处，面板已按设计禁用启动 |
| 备份里没有数据库 | 该环境使用 MySQL 或还没初始化 SQLite；点「初始化数据库」后再备份 |

---

## 九、高级模式与自测

- **高级模式**：左侧导航下方勾选后展开「底层命令」面板，里面列出的就是面板**真正执行**的命令；可以逐条覆盖成自己的写法（例如换成 `python3.11`、改 pip 源），保存后立即生效。命令回显与日志中的 token、密码会自动打码。
- **自测**：

```bash
python tools/deploy_panel/tests/smoke_test.py
```

离线可跑，覆盖配置校验、产物生成、上传安全、模板完整性、任务与日志、以及全部 HTTP 接口（装了 Flask 时自动加测接口部分）。

---

## 十、目录结构

```
tools/deploy_panel/
├── app.py                  Flask 入口与全部 HTTP 接口
├── requirements.txt
├── core/                   后端核心逻辑
│   ├── paths.py            路径与安全拼接
│   ├── config_schema.py    配置 Schema（前后端唯一数据源）
│   ├── config_store.py     配置读写/校验/脱敏
│   ├── presets.py          5 种环境的预设与能力矩阵
│   ├── detect.py           环境探测（python/pip/nginx/git/mysql/端口）
│   ├── runner.py           命令执行、日志脱敏、进程管理
│   ├── jobs.py             任务注册表、进度、日志缓冲、取消
│   ├── commands.py         底层命令生成与覆盖
│   ├── templates_gen.py    nginx/systemd/gunicorn/render/vercel/WSGI/脚本生成
│   ├── db.py               SQLite 建表与 MySQL 脚本
│   ├── project_source.py   上传解压、GitHub 拉取、定时同步
│   ├── service.py          启停重启与状态机
│   ├── logs.py             日志读取与跟随
│   └── backup.py           备份与导出
├── web/                    前端页面（原生 HTML/CSS/JS）
└── projects/打工避雷平台/   内置模板（含 deploy/ 全套配置）
```

详细使用手册见 [使用说明.md](使用说明.md)。
