# -*- coding: utf-8 -*-
"""部署产物生成：nginx.conf / systemd / gunicorn / render.yaml / vercel.json / WSGI / 脚本。

全部按内存字符串返回，需要落盘时用 write_artifacts()。
"""
import json
import os
import re

from . import config_schema as schema
from . import config_store
from . import paths
from . import presets

APP_NAME = "打工避雷平台"
SERVICE_NAME = "dgbilei"


def _flat(cfg):
    return schema.flatten(cfg)


def _domain(flat):
    return (flat.get("network.domain") or "localhost").strip() or "localhost"


def _app_port(flat):
    return int(flat.get("target.app_port") or 5000)


def _service_name(flat):
    return flat.get("service_name") or SERVICE_NAME


# --------------------------------------------------------------------------- #
# Nginx
# --------------------------------------------------------------------------- #
def nginx_conf(cfg):
    """生成 nginx.conf（含 http 块或 server 块，取决于是否独立文件）。"""
    flat = _flat(cfg)
    env = flat.get("target.env", "local")
    domain = _domain(flat)
    app_port = _app_port(flat)
    listen = int(flat.get("network.listen_port") or 80)
    static_alias = flat.get("nginx.static_alias") or "/static/"
    body = flat.get("nginx.client_max_body_size") or "10m"
    gz = bool(flat.get("nginx.gzip"))
    ssl_on = bool(flat.get("nginx.ssl"))
    extra = (flat.get("nginx.extra_raw") or "").strip()
    source_dir = _source_path(flat)

    if not presets.supports(env, "nginx"):
        return (
            "# 当前环境（%s）不使用 Nginx。\n"
            "# 这份配置留作参考：如果你以后迁到 Ubuntu 服务器，可以直接拿去用。\n"
            "# 需要真正生成时，把部署环境切换为「Ubuntu 轻量云服务器」。\n\n"
            % presets.get_env(env)["name"]
        ) + _nginx_server_block(domain, listen, app_port, static_alias, body, gz,
                                ssl_on, flat, source_dir, extra)

    if env == "ubuntu" and not flat.get("nginx.enable"):
        return "# 已关闭 Nginx（面板配置里 nginx.enable=false）。\n# 直接访问 http://%s:%s 即可。\n" % (
            domain, app_port)

    inner = _nginx_server_block(domain, listen, app_port, static_alias, body, gz,
                                ssl_on, flat, source_dir, extra)
    header = """# %s —— 由「可视化部署面板」生成
# 用法（Ubuntu）：
#   1) 把本文件放到 /etc/nginx/sites-available/%s
#   2) sudo ln -s /etc/nginx/sites-available/%s /etc/nginx/sites-enabled/
#   3) sudo nginx -t && sudo systemctl reload nginx
""" % (APP_NAME, _service_name(flat), _service_name(flat))
    return header + "\n" + inner


def _nginx_server_block(domain, listen, app_port, static_alias, body, gz, ssl_on, flat,
                        source_dir, extra):
    lines = []
    if not ssl_on:
        lines.append("server {")
        lines.append("    listen      %d;" % listen)
        lines.append("    listen      [::]:%d;" % listen)
        lines.append("    server_name %s;" % domain)
    else:
        cert = flat.get("nginx.ssl_cert") or "/etc/ssl/certs/app.pem"
        key = flat.get("nginx.ssl_key") or "/etc/ssl/private/app.key"
        lines.append("# --- HTTP 跳 HTTPS ---")
        lines.append("server {")
        lines.append("    listen      %d;" % listen)
        lines.append("    server_name %s;" % domain)
        lines.append("    return 301 https://$host$request_uri;")
        lines.append("}")
        lines.append("")
        lines.append("server {")
        lines.append("    listen      %d ssl;" % (listen if listen != 80 else 443))
        lines.append("    server_name %s;" % domain)
        lines.append("    ssl_certificate     %s;" % cert)
        lines.append("    ssl_certificate_key %s;" % key)
        lines.append("    ssl_protocols       TLSv1.2 TLSv1.3;")
        lines.append("    ssl_ciphers         HIGH:!aNULL:!MD5;")

    lines.append("")
    lines.append("    access_log  /var/log/nginx/%s.access.log;" % _service_name(flat))
    lines.append("    error_log   /var/log/nginx/%s.error.log;" % _service_name(flat))
    lines.append("")
    lines.append("    client_max_body_size %s;" % body)
    lines.append("")
    lines.append("    # 静态资源交给 Nginx 直出，减轻应用压力")
    lines.append("    location %s {" % static_alias if static_alias.startswith("/")
                 else "    location /static/ {")
    lines.append("        alias %s;" % source_dir.rstrip("/") + (static_alias if static_alias.startswith("/") else "/static/"))
    lines.append("        expires 7d;")
    lines.append("        access_log off;")
    lines.append("    }")
    lines.append("")
    if gz:
        lines.append("    gzip on;")
        lines.append("    gzip_min_length 1k;")
        lines.append("    gzip_comp_level 5;")
        lines.append("    gzip_types text/plain text/css application/json application/javascript text/xml application/xml image/svg+xml;")
        lines.append("")
    lines.append("    # 反代到 Flask / gunicorn")
    lines.append("    location / {")
    lines.append("        proxy_pass         http://127.0.0.1:%d;" % app_port)
    lines.append("        proxy_http_version 1.1;")
    lines.append("        proxy_set_header   Host              $host;")
    lines.append("        proxy_set_header   X-Real-IP         $remote_addr;")
    lines.append("        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;")
    lines.append("        proxy_set_header   X-Forwarded-Proto $scheme;")
    lines.append("        proxy_set_header   Upgrade           $http_upgrade;")
    lines.append("        proxy_set_header   Connection        \"upgrade\";")
    lines.append("        proxy_read_timeout 120s;")
    lines.append("    }")
    lines.append("")
    lines.append("    # 上传/举报接口单独放宽一点")
    lines.append("    location /api/report {")
    lines.append("        proxy_pass         http://127.0.0.1:%d;" % app_port)
    lines.append("        proxy_set_header   X-Real-IP $remote_addr;")
    lines.append("        client_max_body_size %s;" % body)
    lines.append("    }")
    if extra:
        lines.append("")
        lines.append("    # --- 高级模式追加 ---")
        for line in extra.splitlines():
            lines.append("    " + line)
    lines.append("}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# systemd / gunicorn
# --------------------------------------------------------------------------- #
def systemd_unit(cfg):
    flat = _flat(cfg)
    source_dir = _source_path(flat)
    app_port = _app_port(flat)
    bind = flat.get("network.bind_host") or "127.0.0.1"
    workers = int(flat.get("network.workers") or 2)
    user = flat.get("service_user") or "www-data"
    return """# /etc/systemd/system/{svc}.service
# 由「可视化部署面板」生成
[Unit]
Description={app} (Flask/gunicorn)
After=network.target

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={cwd}
Environment="APP_PORT={port}"
Environment="APP_BIND={bind}"
EnvironmentFile=-{cwd}/.env
ExecStart={py} -m gunicorn -w {workers} -b {bind}:{port} --access-logfile - --error-logfile - app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
""".format(svc=_service_name(flat), app=APP_NAME, user=user, cwd=source_dir,
           port=app_port, bind=bind, workers=workers, py=_sys_python())


def gunicorn_conf(cfg):
    flat = _flat(cfg)
    app_port = _app_port(flat)
    bind = flat.get("network.bind_host") or "127.0.0.1"
    workers = int(flat.get("network.workers") or 2)
    return """# gunicorn.conf.py —— 由部署面板生成
import multiprocessing
import os

bind = "%s:%s"
workers = %d
threads = 2
timeout = 120
graceful_timeout = 30
keepalive = 5

accesslog = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "gunicorn.access.log")
errorlog = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "gunicorn.error.log")
loglevel = "info"
proc_name = "%s"
""" % (bind, app_port, workers, _service_name(flat))


# --------------------------------------------------------------------------- #
# 平台配置
# --------------------------------------------------------------------------- #
def render_yaml(cfg):
    flat = _flat(cfg)
    py_ver = "%d.%d.%d" % __import__("sys").version_info[:3]
    starter = "python app.py"
    return """# render.yaml —— 由部署面板生成
# 用法：把仓库推到 GitHub 后，在 Render 选择 Blueprint 部署并指向该仓库。
services:
  - type: web
    name: {svc}
    runtime: python
    plan: free
    buildCommand: "pip install -r requirements.txt"
    startCommand: "{starter}"
    healthCheckPath: /healthz
    autoDeploy: true
    envVars:
      - key: PYTHON_VERSION
        value: "{pyver}"
      - key: FLASK_ENV
        value: production
      - key: DB_ENGINE
        value: {engine}
      - key: APP_PORT
        value: "{port}"
      - key: SECRET_KEY
        generateValue: true
""".format(svc=_service_name(flat), starter=starter, pyver=py_ver,
           engine=flat.get("database.engine", "sqlite"), port=_app_port(flat))


def vercel_json(cfg):
    flat = _flat(cfg)
    return json.dumps({
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "version": 2,
        "name": _service_name(flat) + "-static",
        "cleanUrls": True,
        "trailingSlash": False,
        "builds": [{"src": "static/**", "use": "@vercel/static"}],
        "routes": [
            {"src": "/api/(.*)", "dest": "https://API_DOMAIN/api/$1"},
            {"src": "/(.*)", "dest": "/static/$1"},
        ],
        "headers": [{
            "source": "/static/(.*)",
            "headers": [{"key": "Cache-Control", "value": "public, max-age=604800"}],
        }],
    }, ensure_ascii=False, indent=2) + "\n"


def pythonanywhere_wsgi(cfg):
    flat = _flat(cfg)
    source_dir = _source_path(flat).replace("\\", "/")
    return """# pythonanywhere_wsgi.py —— 由部署面板生成
# 用法：把下面内容整段粘贴到 PythonAnywhere 的
#   Web -> Code -> WSGI configuration file 里，然后点 Reload。
import sys
import os

project_home = r"{cwd}"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ.setdefault("FLASK_ENV", "production")
os.environ.setdefault("DB_ENGINE", "{engine}")

from app import app as application  # noqa: E402  (Flask 实例作为 WSGI 入口)
""".format(cwd=source_dir, engine=flat.get("database.engine", "sqlite"))


def requirements_txt(cfg, project_deps=None):
    """requirements.txt —— 面板自身依赖 + 项目依赖。"""
    deps = list(project_deps or [])
    flat = _flat(cfg)
    lines = [
        "# 由部署面板生成",
        "flask>=3.0",
        "python-dotenv>=1.0",
    ]
    if flat.get("database.engine") == "mysql":
        lines.append("pymysql>=1.1")
    if flat.get("target.env") in ("ubuntu", "render"):
        lines.append("gunicorn>=21.2")
    for d in deps:
        if d.split(">=")[0].split("==")[0].strip().lower() in ("flask",):
            continue
        lines.append(d)
    return "\n".join(sorted(set(lines), key=lines.index)) + "\n"


def env_file(cfg):
    return config_store.to_env(_flat(cfg))


def deploy_sh(cfg):
    flat = _flat(cfg)
    source_dir = _source_path(flat).replace("\\", "/")
    svc = _service_name(flat)
    return """#!/usr/bin/env bash
# deploy.sh —— 由「可视化部署面板」生成，可直接拷到 Ubuntu 服务器执行
set -e

APP_DIR="{cwd}"
SERVICE="{svc}"

echo "==> 1/6 安装系统依赖"
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx git

echo "==> 2/6 创建虚拟环境"
cd "$APP_DIR"
python3 -m venv .venv
. .venv/bin/activate

echo "==> 3/6 安装 Python 依赖"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> 4/6 写入 .env"
if [ ! -f .env ]; then
  cp deploy/.env.example .env 2>/dev/null || true
  echo "请检查 $APP_DIR/.env 内的数据库与密钥配置"
fi

echo "==> 5/6 初始化数据库"
python manage.py init-db || true

echo "==> 6/6 安装并启动服务"
sudo cp deploy/{svc}.service /etc/systemd/system/{svc}.service
sudo cp deploy/nginx.conf /etc/nginx/sites-available/{svc}
sudo ln -sf /etc/nginx/sites-available/{svc} /etc/nginx/sites-enabled/{svc}
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now {svc}.service
sudo systemctl reload nginx

echo
echo "部署完成。查看状态："
echo "  sudo systemctl status {svc} --no-pager"
echo "  sudo journalctl -u {svc} -f"
""".format(cwd=source_dir, svc=svc)


def run_local_sh(cfg):
    flat = _flat(cfg)
    source_dir = _source_path(flat)
    port = _app_port(flat)
    bind = flat.get("network.bind_host") or "127.0.0.1"
    if paths.IS_WINDOWS:
        return """@echo off
REM run_local.bat —— 由部署面板生成，双击即可本地跑起来
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv )
call .venv\\Scripts\\activate
pip install -r requirements.txt
if not exist .env ( copy deploy\\.env.example .env )
python manage.py init-db
echo 启动中，稍后访问 http://{bind}:{port}
python app.py
""".format(bind=bind, port=port)
    return """#!/usr/bin/env bash
# run_local.sh —— 由部署面板生成
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp deploy/.env.example .env
python manage.py init-db || true
echo "启动中，稍后访问 http://{bind}:{port}"
python app.py
""".format(bind=bind, port=port)


def mysql_sql(cfg):
    flat = _flat(cfg)
    db = flat.get("database.mysql_dbname") or "dgbilei"
    user = flat.get("database.mysql_user") or "root"
    pwd = flat.get("database.mysql_password") or "CHANGE_ME"
    schema_sql = _template_schema()
    return """-- mysql.sql —— 由部署面板生成
-- 用法：mysql -u root -p < deploy/mysql.sql
CREATE DATABASE IF NOT EXISTS `{db}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY '{pwd}';
GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'%';
FLUSH PRIVILEGES;

USE `{db}`;

-- 如果 SQLite 版本用的语句与你不同，请对照 deploy/schema.sql 调整
{schema}
""".format(db=db, user=user, pwd=pwd, schema=_mysqlify(schema_sql))


def readme_for_env(cfg):
    flat = _flat(cfg)
    env = flat.get("target.env", "local")
    preset = presets.get_env(env)
    lines = ["# %s —— 部署指引（%s）" % (APP_NAME, preset["name"]), ""]
    lines.append(preset["summary"])
    lines.append("")
    lines.append("## 需要你自己准备的")
    if preset["caps"]["needs_remote_account"]:
        lines.append("- 对应平台的账号与实例（面板不代管服务器、域名、备案）")
    else:
        lines.append("- 本机已安装 Python 3.8+")
    lines.append("")
    lines.append("## 步骤")
    for i, step in enumerate(_steps_for(env, flat), 1):
        lines.append("%d. %s" % (i, step))
    lines.append("")
    lines.append("## 注意事项")
    for n in preset["notes"]:
        lines.append("- %s" % n)
    if extra := _env_specific_notes(flat, env):
        for n in extra:
            lines.append("- %s" % n)
    lines.append("")
    return "\n".join(lines)


def _steps_for(env, flat):
    if env == "local":
        return [
            "在工作目录执行 `pip install -r requirements.txt`",
            "复制 `deploy/.env.example` 为 `.env`，按需修改端口与数据库",
            "执行 `python manage.py init-db` 初始化数据库",
            "执行 `python app.py`，浏览器访问 http://%s:%s" % (
                flat.get("network.bind_host", "127.0.0.1"), _app_port(flat)),
        ]
    if env == "ubuntu":
        return [
            "把整个项目目录上传到服务器（或用 GitHub 拉取）",
            "在项目根目录执行 `bash deploy/deploy.sh`",
            "确认 `.env` 内的域名与数据库配置正确",
            "浏览器访问 http://%s" % _domain(flat),
        ]
    if env == "pythonanywhere":
        return [
            "在 Files 页面上传项目（或用 Git 面板克隆）",
            "Bash 控制台执行 `pip install --user -r requirements.txt`",
            "把 `deploy/pythonanywhere_wsgi.py` 的内容粘贴到 Web -> WSGI configuration file",
            "在 Web 页面设置源码目录与虚拟环境，点 Reload",
        ]
    if env == "render":
        return [
            "把项目推到 GitHub 仓库",
            "Render 控制台 New -> Blueprint，选择该仓库",
            "确认读取到 `deploy/render.yaml` 后创建服务",
            "等待构建完成，访问分配的 onrender.com 域名",
        ]
    if env == "vercel":
        return [
            "确认 `static/` 内是你要发布的前端文件",
            "npx vercel --prod（或把仓库连到 Vercel 自动构建）",
            "把静态页里的接口地址改为你另外部署的后端域名",
            "访问分配的 vercel.app 域名",
        ]
    return ["按平台文档部署", "遇到问题时把日志贴到面板的日志窗口"]


def _env_specific_notes(flat, env):
    notes = []
    if env == "ubuntu":
        notes.append("记得在云控制台安全组放行 %s 端口" % (flat.get("network.listen_port") or 80))
        if flat.get("nginx.ssl"):
            notes.append("HTTPS 证书路径需要在服务器上真实存在，面板只生成配置")
    if env == "render":
        notes.append("免费实例磁盘是临时的，SQLite 数据重启后会丢；如需持久化请改用外部数据库")
    if env == "vercel":
        notes.append("Vercel 只托管静态文件，后端接口必须部署在别处")
    if flat.get("database.engine") == "mysql" and env not in ("ubuntu", "pythonanywhere"):
        notes.append("当前环境默认不提供 MySQL，请确认你有可用的数据库实例")
    return notes


# --------------------------------------------------------------------------- #
# 汇总与落盘
# --------------------------------------------------------------------------- #
def artifacts(cfg):
    """返回要生成的产物 {相对路径: 内容}。"""
    flat = _flat(cfg)
    env = flat.get("target.env", "local")
    cap = presets.caps(env)
    out = {}

    out["deploy/.env.example"] = env_file(cfg)
    out["deploy/requirements.txt"] = requirements_txt(cfg, _template_deps())
    out["deploy/README.md"] = readme_for_env(cfg)

    if cap["nginx"] or env == "local":
        out["deploy/nginx.conf"] = nginx_conf(cfg)
    if env == "ubuntu":
        out["deploy/%s.service" % _service_name(flat)] = systemd_unit(cfg)
        out["deploy/gunicorn.conf.py"] = gunicorn_conf(cfg)
        out["deploy/deploy.sh"] = deploy_sh(cfg)
    if env in ("local",):
        out["deploy/run_local.%s" % ("bat" if paths.IS_WINDOWS else "sh")] = run_local_sh(cfg)
    if env == "render":
        out["deploy/render.yaml"] = render_yaml(cfg)
        out["deploy/gunicorn.conf.py"] = gunicorn_conf(cfg)
    if env == "vercel":
        out["deploy/vercel.json"] = vercel_json(cfg)
    if env == "pythonanywhere":
        out["deploy/pythonanywhere_wsgi.py"] = pythonanywhere_wsgi(cfg)
    if flat.get("database.engine") == "mysql":
        out["deploy/mysql.sql"] = mysql_sql(cfg)
    out["deploy/schema.sql"] = _template_schema()
    return out


def write_artifacts(cfg, dest_dir=None):
    """把产物写到指定目录（默认 build 目录）。"""
    dest_dir = dest_dir or paths.BUILD_DIR
    written = []
    for rel_path, content in artifacts(cfg).items():
        target = paths.safe_join(dest_dir, *rel_path.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        _write_text(target, content)
        written.append(target)
    return written


def write_all(cfg, source_dir=None, build_dir=None):
    """同时写入源码目录的 deploy/ 与 build 目录，返回 (source_files, build_files)。"""
    source_dir = source_dir or _source_path(_flat(cfg))
    return (write_artifacts(cfg, source_dir),
            write_artifacts(cfg, build_dir or paths.BUILD_DIR))


def _write_text(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def _source_path(flat):
    sub = flat.get("project.subdir") or ""
    return paths.safe_join(paths.SOURCE_DIR, sub) if sub else paths.SOURCE_DIR


def _sys_python():
    import sys
    return sys.executable


def _template_deps():
    return ["flask>=3.0", "python-dotenv>=1.0"]


def _template_schema():
    """建表 SQL —— 从内置模板读取，读不到时用兜底内容。"""
    from . import config_schema
    tpl = config_schema.find_template("打工避雷平台")
    if tpl:
        p = os.path.join(tpl["path"], "schema.sql")
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    return fh.read()
            except Exception:
                pass
    return _FALLBACK_SCHEMA


_DROP_AUTOINCREMENT = re.compile(r"\bAUTOINCREMENT\b", re.I)


def _mysqlify(sql):
    out = _DROP_AUTOINCREMENT.sub("AUTO_INCREMENT", sql)
    out = out.replace("INTEGER PRIMARY KEY AUTO_INCREMENT", "INT PRIMARY KEY AUTO_INCREMENT")
    out = re.sub(r"\bTEXT\b", "TEXT", out)
    return out


_FALLBACK_SCHEMA = """-- 基础表结构（内置模板缺失时的兜底）
CREATE TABLE IF NOT EXISTS company (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    industry    TEXT,
    city        TEXT,
    risk_level  INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS report (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER,
    category    TEXT,
    content     TEXT NOT NULL,
    video_url   TEXT,
    status      TEXT DEFAULT 'pending',
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);
"""
