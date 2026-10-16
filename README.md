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

## 二、使用

**只想查一家公司**：打开 <https://waxjgn.github.io/job-radar-panel/>，搜公司名或 18 位统一社会信用代码；可按分类、城市筛选，看中国地图热力分布，点 ▲ 标记「我有相同问题」。

**本机跑完整平台**（含上传与申诉审核）：

```bash
git clone https://github.com/waxjgn/job-radar-panel.git
cd job-radar-panel
python -m pip install -r projects/打工避雷平台/requirements.txt
cd projects/打工避雷平台 && python manage.py init-db && python app.py
# 打开 http://127.0.0.1:5000
```

**用图形面板一键部署**：

```bash
cd job-radar-panel
python -m pip install -r requirements.txt
python app.py          # 打开 http://127.0.0.1:8765
```

面板里按「项目源 → 部署环境 → 配置 → 检测 → 装依赖 → 一键部署」走完即可，详见 [使用说明.md](使用说明.md)。

## 三、结构

```
docs/                        查询站点（GitHub Pages 发布目录）
projects/打工避雷平台/         平台后端（Flask + SQLite/MySQL）
app.py + core/ + web/        可视化部署面板（本机运行）
tests/                       离线自测 60 项 + 端到端验收 37 项
```

上线与域名见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 四、免责声明

内容均由用户上传，平台只做汇集展示，**请自行核实后再做决定**；示例数据中的公司名、信用代码、申诉内容均为构造数据，不对应任何真实主体。本项目不提供征信服务，不构成法律意见。

## 五、许可

[MIT](LICENSE)
