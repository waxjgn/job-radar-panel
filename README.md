# 打工避雷平台（Job Radar）

> 入职之前先查一查：这家公司有没有拖欠工资、虚假招聘、押金诈骗、强制加班的记录。

[![Live Site](https://img.shields.io/badge/在线站点-waxjgn.github.io%2Fjob--radar--panel-b91c1c?style=flat-square)](https://waxjgn.github.io/job-radar-panel/)
[![GitHub Pages](https://img.shields.io/badge/托管-GitHub%20Pages-16a34a?style=flat-square)](https://waxjgn.github.io/job-radar-panel/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![ECharts](https://img.shields.io/badge/ECharts-5.5-aa344d?style=flat-square)](https://echarts.apache.org/)
[![License](https://img.shields.io/badge/License-MIT-f59e0b?style=flat-square)](LICENSE)

---

## 一、项目介绍

### 1.1 这是什么

**打工避雷平台**是一个面向求职者与打工人的**用工风险信息查询平台**。它把「谁被欠过薪、谁收过押金、谁在招聘上造假」这类分散在群聊、贴吧、短视频评论里的零散信息，收敛成**可检索、可分级、可核验、可申诉**的结构化记录。

它由三个部分组成，可以单独使用，也可以组合使用：

| 组成 | 说明 | 形态 |
| --- | --- | --- |
| **查询站点** | 面向所有人的公开查询入口：搜索、风险榜、中国地图热力总览 | 纯静态页面，GitHub Pages 免费托管 |
| **平台后端** | 举报提交与内容治理：人机验证、内容审核、防刷限制、后台审核队列、申诉处理 | Flask + SQLite / MySQL |
| **可视化部署面板** | 把上面的后端从源码跑起来：图形化选源、检测环境、装依赖、启停服务、看日志、备份导出 | 本机运行的 Flask 面板 |

### 1.2 要解决的问题

求职信息的不对称是双向的：招聘方对候选人了解很多，候选人对招聘方几乎一无所知。常见的坑集中在四类：

| 类型 | 典型表现 | 取证难点 |
| --- | --- | --- |
| **拖欠工资** | 工资拆两笔发放、每月延后、离职才结清、年终奖不认账 | 口头承诺难留痕 |
| **虚假招聘** | 挂假岗位刷 KPI、面试变课程推销、offer 与合同不一致 | 招聘页面截图易被删除 |
| **押金诈骗** | 培训费、押金、保证金、设备损耗费，收款后失联或拒不退还 | 多为现金或私人收款 |
| **强制加班 / 社保** | 大小周无加班费、按最低基数缴社保、公积金断缴、试用期不缴 | 制度内部不公开 |

现有信息渠道的问题在于：**名字对不上主体**（同名公司容易误伤）、**时间线混乱**（旧记录被当成现状）、**没有申诉通道**（被举报方无处辩解，信息可信度反而下降）。

### 1.3 本项目的应对方式

1. **用统一社会信用代码锚定主体**
   凭公司名查公司会误伤同名企业，因此平台要求举报必须填 **18 位统一社会信用代码**：列表里以徽章展示，详情页展示核验状态，未填写的主体会被显式标注，查询也支持直接按信用代码检索。示例数据里的代码是按规则构造的示例值，不对应任何真实主体。

2. **让申诉与举报同等醒目**
   被举报主体可以提交申诉，申诉状态（申诉中 / 已受理 / 已驳回）与理由会**公示在详情页顶部和列表条目上**，视觉权重和举报记录相同。信息对等，读者才能自行判断。

3. **用「我有相同问题」把孤例变成共识**
   每条记录都带 ▲▼ 上下箭头：▲ 表示「我有相同问题」，计数实时增长。单条匿名举报可信度有限，但同一个主体被多人独立标记同一类问题，可信度会显著上升。

4. **用地图看全国分布，用榜单看集中度**
   中国地图按「每家公司平均被举报数」着色（**越密越红、越稀越蓝、无记录白色**），一眼看出哪些省份问题集中；随机榜侧重曝光、排行榜提供可筛选的排序视图。

5. **内容治理前置到提交环节**
   内置人机验证、敏感词与联系方式审核、按 IP 的防刷限制：命中高危词直接拒绝入库，命中疑似内容转人工审核队列，降低灌水与广告污染。

### 1.4 项目状态（请以这里为准）

| 能力 | 状态 | 位置 |
| --- | --- | --- |
| 查询 / 搜索 / 分类与城市筛选 / URL 可分享 | ✅ 已实现 | `docs/` |
| 统一社会信用代码展示、检索、提交校验 | ✅ 已实现 | `docs/`、`projects/打工避雷平台/` |
| 申诉公示（三种状态、详情页顶部 + 列表内联） | ✅ 已实现 | `docs/`、后端表结构已预留 |
| 同问上下箭头（计数 + 本地持久化） | ✅ 已实现（静态站为本地存储） | `docs/` |
| 随机榜（主）+ 可筛选排行榜 + 垂直条形侧栏 | ✅ 已实现 | `docs/` |
| 中国地图热力可视化（缩放 / 平移 / 点击筛选 / 降级网格） | ✅ 已实现 | `docs/` |
| 举报提交：人机验证 + 内容审核 + 防刷 | ✅ 已实现（后端） | `projects/打工避雷平台/safety.py` |
| 后台审核队列与审核流水 | ✅ 已实现（骨架级） | `projects/打工避雷平台/routes/admin.py` |
| 申诉工单流转（受理 / 驳回 / 结果通知） | ⏳ 表结构已就绪，后台流程待补 | `projects/打工避雷平台/schema.sql` |
| 登录鉴权与角色权限 | ⏳ 预留 `admin_user` 表，尚未接入 | 同上 |
| 数据来源与真实性背书 | ⏳ 规划：接入公开裁判文书 / 信用信息查询 | — |

### 1.5 技术栈

| 层次 | 选型 | 说明 |
| --- | --- | --- |
| 前端 | 原生 HTML / CSS / JavaScript | 无框架、无构建步骤，`docs/` 可直接托管 |
| 地图 | Apache ECharts 5 + 官方 GeoJSON | 开源（Apache-2.0），三级 CDN 回退 |
| 后端 | Python + Flask | 轻量，适合单机与低配服务器 |
| 数据库 | SQLite（默认）/ MySQL | 业务代码统一 `?` 占位符，双引擎自动转换 |
| 生产运行 | gunicorn + nginx + systemd | 由部署面板生成配置与脚本 |
| 部署目标 | 本机 / Ubuntu 轻量云 / Render / PythonAnywhere / Vercel | 面板按环境生成对应产物 |

---

## 二、目录结构

```
job-radar-panel/
├── docs/                              查询站点（GitHub Pages 发布目录）
│   ├── index.html                     页面结构
│   ├── assets/style.css               红色主题样式
│   ├── assets/app.js                  搜索 / 双榜 / 地图 / 同问 / 申诉
│   ├── data/companies.json            示例数据（可替换为真实数据）
│   └── DEPLOY.md                      上线与域名配置说明
│
├── projects/打工避雷平台/               平台后端（Flask，可独立运行）
│   ├── app.py                         应用入口与蓝图注册
│   ├── config.py                      环境变量配置（.env 驱动）
│   ├── models.py                      数据访问层（SQLite / MySQL 双引擎）
│   ├── safety.py                      白名单 / 内容审核 / 防刷 / 验证码
│   ├── routes/query.py                查询接口：搜索、详情、白名单
│   ├── routes/report.py               举报接口：提交、验证码
│   ├── routes/admin.py                后台接口：审核队列、通过驳回
│   ├── schema.sql                     建表语句（6 张表）
│   ├── seeds.sql                      示例数据
│   ├── manage.py                      运维命令：init-db / tables / allowlist / run
│   ├── templates/ + static/           查询页与管理页
│   └── deploy/                        部署产物样例（nginx / systemd / gunicorn / 平台配置）
│
├── app.py + core/ + web/              可视化部署面板（本机运行）
│   ├── app.py                         面板 HTTP 接口
│   ├── core/                          配置 Schema / 环境检测 / 任务 / 产物生成 / 备份
│   └── web/                           面板前端（原生 HTML/CSS/JS）
│
├── tests/
│   ├── smoke_test.py                  60 项离线自测（配置/产物/安全/任务/接口）
│   └── e2e_verify.py                  37 项端到端验收（真实部署一条链路）
│
├── .github/workflows/pages.yml        Pages 自动发布
└── requirements.txt                   部署面板依赖
```

---

## 三、如何使用

### 场景 A：我只想查一家公司（不需要安装任何东西）

直接打开线上站点：**<https://waxjgn.github.io/job-radar-panel/>**

| 想做的事 | 操作 |
| --- | --- |
| 按公司名或信用代码查 | 顶部搜索框输入公司名或 18 位统一社会信用代码（如 `91330106`），结果实时过滤 |
| 换个角度找问题 | 点分类标签（拖欠工资 / 押金诈骗 …），或选城市下拉 |
| 看全国分布 | 视图切到「中国地图」，颜色越红表示该省平均被举报越密；滚轮缩放、拖拽平移，点省份筛选 |
| 找问题集中的主体 | 左侧「排行榜」切换排序（风险 / 同问 / 记录数 / 最新）与筛选（高风险 / 有申诉 / 缺信用代码） |
| 看随机曝光 | 左侧「随机榜」每 10 秒自动换一批，也可点「换一批」 |
| 标记相同遭遇 | 在记录条目上点 ▲（我有相同问题），计数 +1；再点一次取消 |
| 看主体申诉 | 红底斜纹条即申诉公示；点开主体详情，顶部有完整申诉理由与状态 |
| 提交一条避雷 | 点「提交避雷」，**必须填统一社会信用代码**，填完会有格式与校验位提示 |

### 场景 B：在我自己的机器上跑完整平台（含提交与审核）

```bash
# 1) 取代码
git clone https://github.com/waxjgn/job-radar-panel.git
cd job-radar-panel

# 2) 安装后端依赖
python -m pip install -r projects/打工避雷平台/requirements.txt

# 3) 建库并写入示例数据
cd projects/打工避雷平台
python manage.py init-db

# 4) 启动
python app.py
# 浏览器打开 http://127.0.0.1:5000
```

常用命令：

```bash
python manage.py init-db      # 建表 + 写示例数据
python manage.py tables       # 查看表与行数
python manage.py allowlist    # 查看视频域名白名单
python manage.py run          # 建表后直接启动
```

后台审核入口：<http://127.0.0.1:5000/admin>（演示级保护，需在 URL 带 `?token=SECRET_KEY前8位`；正式使用请接入登录鉴权）。

### 场景 C：用可视化面板一键部署（不想敲命令）

```bash
cd job-radar-panel
python -m pip install -r requirements.txt     # 只需要 Flask
python app.py                                 # 打开 http://127.0.0.1:8765
```

面板里按顺序操作：**选项目源**（上传 zip / 拉 GitHub / 直接用内置模板）→ **选部署环境** → **改配置**（域名、端口、数据库、视频白名单、安全开关、Nginx）→ **检测环境** → **安装依赖** → **一键部署** → 日志窗口显示绿色即成功。之后可一键备份、导出部署脚本与配置。

面板的详细说明见 [使用说明.md](使用说明.md)。

---

## 四、部署

### 4.1 查询站点（GitHub Pages，免费）

站点在 `docs/`，仓库已配好 Pages 工作流，推送到 `main` 即自动发布：

1. 打开 <https://github.com/waxjgn/job-radar-panel/settings/pages>
2. **Source** 选 **GitHub Actions**（或选 `main` 分支 + `/docs` 目录）
3. 访问 <https://waxjgn.github.io/job-radar-panel/>

本地预览：

```bash
cd docs
python -m http.server 8080     # 打开 http://127.0.0.1:8080
```

> 直接双击 `index.html` 会因浏览器 `file://` 限制读不到 JSON，必须走本地服务器。

### 4.2 平台后端（三选一）

| 方案 | 适合 | 要点 |
| --- | --- | --- |
| **Ubuntu 轻量云** | 正式对外 | 面板导出 `deploy/`，服务器上 `sudo bash deploy/deploy.sh`（nginx + gunicorn + systemd） |
| **Render** | 免费演示 | 仓库连到 Render，自动读取 `deploy/render.yaml`；免费实例磁盘临时，SQLite 重启会丢数据 |
| **PythonAnywhere** | 免费原型 | 把 `deploy/pythonanywhere_wsgi.py` 内容粘到 Web → WSGI 配置文件后 Reload |

### 4.3 自定义域名（可选）

`waxjgn.github.io/job-radar-panel` 是免费域名，不需要注册。想挂自己的域名：注册后在 `docs/` 放一个 `CNAME` 文件（内容为域名），再按 [docs/DEPLOY.md](docs/DEPLOY.md) 配置 DNS 与 Pages Custom domain 即可。

---

## 五、接口与数据

### 5.1 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 查询首页（搜索 + 结果 + 举报表单） |
| `GET` | `/api/search?q=` | 按公司名 / 城市 / 行业 / 标题搜索已发布记录 |
| `GET` | `/api/company/<id>` | 主体详情与全部已发布记录 |
| `POST` | `/api/report` | 提交举报（人机验证 → 内容审核 → 白名单 → 防刷，任一不过即拒绝） |
| `GET` | `/api/captcha` | 获取算术验证题 |
| `GET` | `/api/allowlist` | 查看视频域名白名单 |
| `GET` | `/api/admin/queue` | 后台待审核队列（需凭据） |
| `POST` | `/api/admin/review` | 审核通过 / 驳回（需凭据） |
| `GET` `POST` `DELETE` | `/api/admin/allowlist` | 白名单增删查（需凭据） |
| `GET` | `/healthz` | 健康检查（部署平台与面板使用） |

### 5.2 数据表

| 表 | 作用 | 关键字段 |
| --- | --- | --- |
| `company` | 用工主体 | `name`、`industry`、`city`、`scale`、`risk_level`、`tags` |
| `report` | 避雷记录 | `company_id`、`category`、`title`、`content`、`video_url`、`status`、`ip_hash` |
| `review_log` | 审核流水 | `report_id`、`rule`、`action`、`detail` |
| `rate_limit` | 防刷计数 | `ip_hash`、`window_key`、`hits` |
| `video_allowlist` | 视频域名白名单 | `domain`、`enabled` |
| `admin_user` | 管理账号（预留） | `username`、`password_hash` |

### 5.3 内容治理规则

| 环节 | 规则 | 结果 |
| --- | --- | --- |
| 人机验证 | 内置算术题（答案存 session） | 未通过直接拒绝 |
| 内容审核 | 命中辱骂 / 广告词 | 转人工审核（`pending`） |
| 内容审核 | 命中高危词（刷单、博彩、贷款、代开发票…） | 直接拒绝 |
| 内容审核 | 含手机号 / 联系方式 / 多外链 | 转人工审核 |
| 视频白名单 | 链接域名不在白名单 | 直接拒绝并提示允许的域名 |
| 防刷限制 | 单 IP 每分钟超过阈值 | 返回 HTTP 429 |

---

## 六、开发

### 6.1 自测

```bash
python tests/smoke_test.py        # 60 项离线自测：配置 / 产物 / 上传安全 / 任务 / HTTP 接口
python tests/e2e_verify.py        # 37 项端到端：真实跑一遍「部署 → 建库 → 启服务 → 备份 → 导出」
```

`smoke_test.py` 装了 Flask 会自动加测接口部分；`e2e_verify.py` 需要一个运行中的面板地址作参数。

### 6.2 替换为真实数据

静态站数据在 `docs/data/companies.json`，字段含义：

```jsonc
{
  "site":    { "name": "...", "tagline": "...", "notice": "...", "updated": "YYYY-MM-DD" },
  "regions": { "杭州": { "province": "浙江", "adcode": "330000", "coord": [120.155, 30.274] } },
  "companies": [{
    "name": "公司全称",
    "credit_code": "18 位统一社会信用代码",
    "province": "浙江", "adcode": "330000", "city": "杭州", "coord": [120.155, 30.274],
    "industry": "互联网", "scale": "100-499人", "risk_level": 2,
    "tags": ["试用期不缴社保"],
    "appeal": { "status": "pending|accepted|rejected|none", "count": 1, "latest": "申诉理由" },
    "metoo": 18,
    "reports": [{
      "category": "试用期社保", "title": "…", "content": "…", "job": "前端开发",
      "date": "2026-03-11", "metoo": 12, "evidence": ["社保明细截图"], "video": ""
    }]
  }]
}
```

改完推送到 `main`，Pages 会自动重新发布。

### 6.3 扩展后端

- **新增分类**：改 `docs/data/companies.json` 的 `categories`；后端无需改动（分类为自由文本）。
- **新增审核规则**：在 `projects/打工避雷平台/config.py` 的 `REVIEW_BLOCK_WORDS` 加词，或在 `safety.py` 增加正则。
- **接申诉工单流程**：`report` 表加申诉关联字段，`routes/admin.py` 增加受理/驳回动作，前端在详情页展示结果。
- **换数据库**：把 `config.py` 的 `DB_ENGINE` 改成 `mysql`，执行 `deploy/mysql.sql` 建库即可，业务代码不用改。

### 6.4 开发约定

- 换行统一 LF（`.gitattributes` 已固定），避免 Linux 服务器上脚本因 CRLF 报错。
- Python 侧不引入 ORM，保持「一个 `models.py` 就能读懂」的规模。
- 前端不引入构建链：`docs/` 是可直接托管的静态文件。
- 提交前跑一遍 `tests/smoke_test.py`。

---

## 七、常见问题

| 现象 | 处理 |
| --- | --- |
| 打开 `docs/index.html` 页面空白、数据加载失败 | 必须用本地服务器打开（`python -m http.server`），`file://` 下浏览器禁止读取 JSON |
| 地图显示成网格 | 表示 ECharts 或 GeoJSON 的 CDN 都不可达，已自动降级（功能等价）；网络恢复后刷新即可 |
| 提交举报提示「视频域名不在白名单」 | 白名单只允许 B站/抖音/快手/视频号，可在 `.env` 的 `VIDEO_ALLOWLIST` 里增删 |
| 提交返回 429 | 触发了防刷限制，调整 `RATE_LIMIT_PER_MIN` 或等下一分钟 |
| 后台 `/admin` 提示缺凭据 | URL 带 `?token=SECRET_KEY前8位`；正式使用请接入登录鉴权 |
| 部署面板检测到 nginx / git 标黄 | 本地测试环境不需要它们，只有 Ubuntu 生产部署才需要 |
| GitHub Pages 404 | 确认 Settings → Pages 的 Source 已选 GitHub Actions 或 `main` + `/docs` |

---

## 八、后续计划

- 申诉工单闭环：受理、举证、结果公示的完整流转与通知
- 登录鉴权与角色权限（管理员 / 审核员 / 举报人）
- 数据可信度提升：信用代码批量核验、公开文书与信用信息关联
- 记录时效管理：旧记录标注时间衰减、主体整改后的状态更新
- 移动端体验优化与 PWA（离线可查已加载数据）

---

## 九、免责声明

- 站点内容由用户提交，平台仅作信息汇集与展示，**请自行核实后再做决定**。
- 示例数据中的公司名称、统一社会信用代码、申诉内容均为演示用构造数据，不对应任何真实主体。
- 平台不提供企业征信服务，不构成任何法律意见。

## 十、许可

[MIT](LICENSE)
