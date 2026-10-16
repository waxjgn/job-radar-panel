# 部署与上线指南

本文覆盖两件事：

1. **查询站点**（`docs/`）发布到 GitHub Pages —— 免费、自带域名
2. **平台后端**（`projects/打工避雷平台/`）发布到公网 —— Render / PythonAnywhere / 自建 Ubuntu

先分清哪些能放 Pages：

| 内容 | 位置 | 能不能放 Pages |
| --- | --- | --- |
| 查询站点（静态） | `docs/` | ✅ 免费托管 |
| 平台后端（Flask，带举报/审核/防刷） | `projects/打工避雷平台/` | ❌ Pages 跑不了 Python |
| 可视化部署面板（Flask） | 仓库根 `app.py` + `core/` + `web/` | ❌ 同上，本机运行最方便 |

---

## 一、查询站点上线

### 1.1 你的免费域名（不需要注册）

仓库名直接变成域名：

```
https://waxjgn.github.io/job-radar-panel/
```

由 GitHub Pages 免费提供，长期有效，无需备案、无需 DNS 配置。

### 1.2 开启 Pages（二选一）

**方式 A：用仓库自带的 Action（推荐）**

仓库已有 `.github/workflows/pages.yml`，推送后自动发布。首次需打开开关：

1. 打开 <https://github.com/waxjgn/job-radar-panel/settings/pages>
2. **Build and deployment → Source** 选 **GitHub Actions**
3. 到 <https://github.com/waxjgn/job-radar-panel/actions> 等 `Deploy static site to GitHub Pages` 跑完（约 40 秒）
4. 访问 <https://waxjgn.github.io/job-radar-panel/>

之后只要改 `docs/` 里任何文件并推送，站点自动更新。

**方式 B：不用 Action，直接指目录**

1. Settings → Pages
2. **Source** 选 **Deploy from a branch**，Branch 选 `main`，目录选 `/docs`
3. 等约 1 分钟，访问 <https://waxjgn.github.io/job-radar-panel/>

### 1.3 本地预览

`docs/` 是纯静态站，用任意静态服务器打开：

```bash
cd docs
python -m http.server 8080     # 打开 http://127.0.0.1:8080
```

> 直接双击 `index.html` 用 `file://` 打开会因浏览器安全限制读不到 `data/companies.json`，必须走本地服务器。

---

## 二、自定义域名（可选）

### 2.1 注册域名

Cloudflare Registrar、Namecheap、阿里云 / 腾讯云都可以。免费顶级域名（如 Freenom）稳定性与续期风险较高，长期使用建议直接购买，年付通常几十元。

### 2.2 在仓库里放 CNAME 文件

在 `docs/` 下新建文件 `CNAME`（无扩展名），内容只写一行域名：

```
job-radar.example.com
```

### 2.3 配置 DNS

| 场景 | 记录类型 | 值 |
| --- | --- | --- |
| 子域名（`job-radar.example.com`） | `CNAME` | `waxjgn.github.io` |
| 根域名（`example.com`） | `A` × 4 | `185.199.108.153`、`185.199.109.153`、`185.199.110.153`、`185.199.111.153` |

### 2.4 在 Pages 设置里绑定

Settings → Pages → **Custom domain** 填域名 → Save → 等证书签发后勾选 **Enforce HTTPS**（通常几分钟到一小时）。

DNS 生效后，站点同时可用自定义域名和 `waxjgn.github.io` 访问。

---

## 三、平台后端上线（Pages 做不到的部分）

### 3.1 方案对比

| 平台 | 免费额度 | 怎么做 | 限制 |
| --- | --- | --- | --- |
| **Ubuntu 轻量云** | 付费（几十元/月） | 用部署面板「导出部署脚本+配置」，把 `deploy/` 拷到服务器执行 `sudo bash deploy/deploy.sh` | 需自行配置安全组与备案（境内） |
| **Render** | 免费 Web Service | 仓库连到 Render，选 Blueprint，自动读取 `deploy/render.yaml` | 实例会休眠；磁盘临时，SQLite 重启丢数据 |
| **PythonAnywhere** | 免费额度 | 把 `deploy/pythonanywhere_wsgi.py` 内容粘到 Web → WSGI configuration file，Reload | 免费版禁止任意出站请求，定时同步不可用 |
| **Vercel** | 免费静态托管 | 只放静态页，后端另找地方 | 不能跑 Flask |

### 3.2 Ubuntu 部署（正式方案）

面板导出 `deploy/` 后，服务器上执行：

```bash
cd /path/to/app
sudo bash deploy/deploy.sh
```

脚本会依次：安装系统依赖 → 建虚拟环境 → 装 Python 依赖 → 写 `.env` → 初始化数据库 → 安装 systemd 服务与 Nginx 配置并启动。

之后常用命令：

```bash
sudo systemctl status dgbilei --no-pager     # 查看状态
sudo journalctl -u dgbilei -f                # 跟踪日志
sudo systemctl restart dgbilei               # 重启
sudo nginx -t && sudo systemctl reload nginx # 改完 Nginx 后校验并重载
```

记得在云控制台安全组放行 `80`（或你配置的对外端口）。

### 3.3 MySQL（生产建议）

```bash
mysql -u root -p < deploy/mysql.sql
```

然后把 `.env` 的 `DB_ENGINE` 改为 `mysql` 并填 `MYSQL_*`。

---

## 四、用可视化面板完成上面这些

面板可以把「选源 → 配环境 → 生成配置 → 部署」全部图形化：

```bash
python -m pip install -r requirements.txt   # 仓库根
python app.py                               # 打开 http://127.0.0.1:8765
```

面板能直接生成并导出：

- `deploy/nginx.conf`（含 HTTPS 与反代配置）
- `deploy/dgbilei.service`（systemd 单元）
- `deploy/gunicorn.conf.py`
- `deploy/deploy.sh`（Ubuntu 一键部署脚本）
- `deploy/render.yaml`（Render Blueprint）
- `deploy/vercel.json`（Vercel 静态部署）
- `deploy/pythonanywhere_wsgi.py`（PythonAnywhere WSGI 入口）
- `deploy/mysql.sql`（MySQL 建库建表）

---

## 五、常见问题

| 现象 | 处理 |
| --- | --- |
| Pages 显示 404 | 确认 `docs/index.html` 存在；方式 B 时目录要选 `/docs`（不是 `/`） |
| 页面样式丢失或数据加载失败 | 检查 `docs/assets/` 与 `docs/data/` 是否一起推送；站点需挂在仓库子路径下访问 |
| Action 报 `Pages not enabled` / `Get Pages site failed` | 到 Settings → Pages 把 Source 切成 **GitHub Actions**，重新跑 workflow |
| 改了 docs 但线上没变 | 强制刷新（Ctrl+F5）；或到 Actions 看本次部署是否成功 |
| Render 上数据重启就丢 | 免费实例磁盘是临时的，改用外部数据库或升级实例 |
| 自定义域名一直未生效 | DNS 传播需要时间；用 `nslookup 你的域名` 确认解析是否已指向目标 |
| 证书签发卡住 | 确认 DNS 已生效且 Custom domain 已保存，再等一段或重试 |

更多排查见 [使用说明.md](../使用说明.md) 第 10 章。
