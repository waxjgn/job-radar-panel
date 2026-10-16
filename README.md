# 打工避雷平台（Job Radar）

> 入职之前先查一查：这家公司有没有拖欠工资、虚假招聘、押金诈骗、强制加班的记录。

[![Live Site](https://img.shields.io/badge/在线站点-waxjgn.github.io%2Fjob--radar--panel-b91c1c?style=flat-square)](https://waxjgn.github.io/job-radar-panel/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![ECharts](https://img.shields.io/badge/ECharts-5.5-aa344d?style=flat-square)](https://echarts.apache.org/)
[![License](https://img.shields.io/badge/License-MIT-f59e0b?style=flat-square)](LICENSE)

## 一、项目介绍

### 1.1 这是什么

**打工避雷平台**是一个面向求职者与打工人的**用工风险曝光平台**：谁都能匿名上传自己遇到的坑，把拖欠工资、虚假招聘、押金诈骗、强制加班的公司摆到台面上。

平台规则就三条：

- **上传随便**——不设人工审核、不要求实名，提交即直接发布，目的是曝光垃圾公司；
- **申诉要审核**——被曝光的公司可以提交申诉并自证材料，平台审核后公示受理 / 驳回结论；
- **链接限四大平台**——视频证据只接受 B站 / 抖音 / 快手 / 视频号，避免外站引流与失效链接。

信息可信度靠三件事支撑：**统一社会信用代码**锚定主体（避免同名误伤）、**「我有相同问题」**计数（多人独立印证）、**申诉公示**（给被曝光方开口的机会）。

> 站点顶部常驻声明：本站不设人工审核，任何人都可以随意上传避雷记录，上传即刻发布。

## 二、快速体验

**只想查一家公司**：打开 <https://waxjgn.github.io/job-radar-panel/>，搜公司名或 18 位统一社会信用代码；可按分类、城市筛选，看中国地图热力分布，点 ▲ 标记「我有相同问题」。

**想跑完整平台**（含上传、申诉与后台审核）：

```bash
git clone https://github.com/waxjgn/job-radar-panel.git
cd job-radar-panel
python -m pip install -r projects/打工避雷平台/requirements.txt
cd projects/打工避雷平台
python manage.py init-db      # 建表 + 写入示例数据
python app.py                 # 打开 http://127.0.0.1:5000
```

觉得命令麻烦，可以用自带的图形面板：`python -m pip install -r requirements.txt && python app.py`，打开 <http://127.0.0.1:8765> 按「项目源 → 部署环境 → 配置 → 检测 → 装依赖 → 一键部署」走完即可。

## 三、部署方法

### 3.1 方式一：纯静态站（免费，2 分钟）

只有查询站、不需要提交举报时，这是最省事的路子——托管在 GitHub Pages，零成本、零运维。

```bash
cd docs
python -m http.server 8080     # 本地预览，打开 http://127.0.0.1:8080
```

正式发布：把仓库推到 GitHub，然后在 **Settings → Pages** 把 Source 设为 **GitHub Actions**（仓库已带 `.github/workflows/pages.yml`），或选 `main` 分支 + `/docs` 目录。几十秒后访问：

```
https://<你的用户名>.github.io/<仓库名>/
```

站点数据是纯前端检索，改 `docs/data/companies.json` 推送即生效，不需要任何后端。

### 3.2 方式二：本机 / 内网跑后端（验证功能）

```bash
cd projects/打工避雷平台
cp deploy/.env.example .env                   # Windows: copy deploy\.env.example .env
python manage.py init-db
python app.py                                 # 默认 127.0.0.1:5000
```

改 `.env` 里 `APP_BIND=0.0.0.0` 可让同网段设备访问。数据库默认 SQLite（`data/app.db`），备份直接拷这个文件。

### 3.3 方式三：Ubuntu 轻量云（正式对外）

推荐用自带的图形面板生成配置，它会按你的实际参数产出全套产物：

```bash
python -m pip install -r requirements.txt
python app.py            # 面板 → 选「Ubuntu 轻量云服务器」→ 填域名与端口 → 导出部署脚本+配置
```

把导出的 `deploy/` 目录放到服务器项目根目录，执行：

```bash
sudo bash deploy/deploy.sh
```

脚本会依次安装系统依赖、建虚拟环境、装 Python 依赖、写 `.env`、初始化数据库、装 systemd 服务与 Nginx 配置并启动。之后常用命令：

```bash
sudo systemctl status dgbilei --no-pager      # 状态
sudo journalctl -u dgbilei -f                 # 日志
sudo systemctl restart dgbilei                # 重启
sudo nginx -t && sudo systemctl reload nginx  # 改完 Nginx 后
```

用 MySQL 就执行 `mysql -u root -p < deploy/mysql.sql`，再把 `.env` 的 `DB_ENGINE` 改为 `mysql`。记得在云控制台放行 80（或你配置的端口）。

### 3.4 方式四：托管平台（免费额度）

| 平台 | 适合 | 要点 | 限制 |
| --- | --- | --- | --- |
| **Render** | 免费全栈演示 | 仓库连到 Render，自动读取 `deploy/render.yaml` | 实例会休眠；免费磁盘临时，SQLite 重启丢数据 |
| **PythonAnywhere** | 免费后端原型 | 把 `deploy/pythonanywhere_wsgi.py` 内容粘到 Web → WSGI configuration file | 免费版禁止出站请求，定时同步不可用 |
| **Vercel** | 只放静态页 | `deploy/vercel.json` | 跑不了 Flask，后端要另找地方 |

### 3.5 部署前必须自己改的几项

```bash
SECRET_KEY=换成一串随机值          # 后台凭据由它派生，别用默认值
ENABLE_CAPTCHA=true               # 人机验证，挡机器人灌水
ENABLE_RATE_LIMIT=true            # 防刷，按 IP 限速
RATE_LIMIT_PER_MIN=10             # 视流量调整
VIDEO_ALLOWLIST=...               # 只保留你要放行的平台
```

更细的参数说明与排错见 [使用说明.md](使用说明.md)，域名与 HTTPS 见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 四、抛砖引玉

这个项目**不是成品，是一块砖**。它的价值不在于功能齐全，而在于把「一套用工风险曝光平台该长什么样」拆开摆在这里：

- **数据怎么组织**：用统一社会信用代码锚定主体，避开同名误伤；记录带分类、城市、岗位、证据类型与时间；
- **可信度怎么建立**：多人「我有相同问题」印证 + 主体申诉与结论公示，让读者看到正反两面；
- **内容治理怎么取舍**：上传免审保证曝光效率，申诉审核保证纠错通道，链接限定四大平台降低失效与引流；
- **界面怎么表达**：红色警示主题、密度热力地图、随机榜与可筛选排行榜、垂直条形榜单、动态数显；
- **部署怎么落地**：静态站免费托管，后端给出四种从本地到云端的路径，附带图形化面板。

### 它现在显然不够的地方

- **申诉工单是半闭环**：提交与结论公示有，举证/补充材料/通知的完整流转没有；
- **后台没有鉴权**：只有演示级凭据，正式用必须自己接入登录与角色权限；
- **数据全靠用户上传**：没有与公开信息源做交叉核验，单条记录的可信度只能靠同问数与申诉状态间接判断；
- **没有防滥用上限**：免审直发意味着有人恶意刷记录也一样能发出去，需要你按自己的场景加规则。

### 欢迎这样用

**换成你的领域**：把公司换成店铺、房东、培训机构、医美机构、装修队，同一套「主体 + 记录 + 同问 + 申诉」的结构直接成立；

**换成你的地区**：改 `docs/data/companies.json` 与地图聚合口径，就能做成本地版；

**换个治理策略**：如果你更在意准确性，把免审改成先审后发、加实名或手机验证、接入第三方内容审核 API，都在 `safety.py` 与 `routes/report.py` 两处能改完；

**接你的数据源**：接裁判文书、信用信息公示、企业工商数据，把「用户上传」变成「公开信息 + 用户补充」。

### 动手前提醒三件事

1. **示例数据是假的**：所有公司名、统一社会信用代码、申诉内容都是构造数据，不对应任何真实主体，上线前必须清空或替换；
2. **内容责任跟着你走**：一旦你加了人工审核、实名或申诉处理，就意味着你开始对内容负责，请按所在地的法律法规评估并保留处置能力；
3. **别把它当征信服务**：本站只做信息汇集，不构成对企业信用的评定，也不构成法律意见。

## 五、结构

```
docs/                        查询站点（GitHub Pages 发布目录）
projects/打工避雷平台/         平台后端（Flask + SQLite/MySQL）
app.py + core/ + web/        可视化部署面板（本机运行）
tests/                       离线自测 60 项 + 端到端验收 37 项
```

## 六、免责声明

内容均由用户上传，平台只做汇集展示，**请自行核实后再做决定**；示例数据中的公司名、信用代码、申诉内容均为构造数据，不对应任何真实主体。本项目不提供征信服务，不构成法律意见。

## 七、许可

[MIT](LICENSE)
