# -*- coding: utf-8 -*-
"""配置 Schema —— 前后端唯一数据源。

前端按这里的分组/类型动态渲染表单，后端按这里校验与取默认值，
新增字段只需要改本文件一处，避免前后端字段漂移。

字段定义：
    key      配置键（点号分组）
    type     text | number | password | select | switch | list | textarea
    default  默认值
    label    中文标签
    help     帮助提示（面板上每个选项后面的问号气泡）
    options  仅 select 使用，[(value, 标签)]
    group    所属分组 key
    min/max  仅 number
"""
from . import presets

GROUPS = [
    {
        "key": "project",
        "title": "1. 项目源",
        "desc": "上传本地压缩包，或从 GitHub 仓库拉取代码；两种模式互斥，只能选一种。",
    },
    {
        "key": "target",
        "title": "2. 部署目标环境",
        "desc": "选择代码要跑到哪里，面板会自动套用对应预设模板与依赖清单。",
    },
    {
        "key": "network",
        "title": "3. 域名与端口",
        "desc": "域名用于生成 Nginx server_name；端口映射是「访问端口 -> 应用端口」。",
    },
    {
        "key": "database",
        "title": "4. 数据库",
        "desc": "SQLite 适合个人小体量；MySQL 适合数据量大或需要多实例共用。",
    },
    {
        "key": "allowlist",
        "title": "5. 视频域名白名单",
        "desc": "只有白名单内的域名可以被解析/嵌入，防止外站链接和引流。",
    },
    {
        "key": "security",
        "title": "6. 安全开关",
        "desc": "人机验证、内容审核、防刷限制；开启后会写入后端配置并生成对应中间件。",
    },
    {
        "key": "nginx",
        "title": "7. Nginx 配置",
        "desc": "图形化填写，面板自动生成 nginx.conf；可在预览里再改行。",
    },
    {
        "key": "advanced",
        "title": "8. 高级模式",
        "desc": "展开后可以看/改每条底层 shell 命令，懂技术的用户用。",
    },
]

# 每个字段归属哪个分组、在哪些环境下可见（envs=None 表示全部环境可见）
FIELDS = [
    # ---------------- project ----------------
    dict(key="project.source_mode", group="project", type="select", default="upload",
         label="项目来源", options=[("upload", "本地上传（zip）"), ("github", "GitHub 仓库映射")],
         help="两种来源互斥。上传适合本地写好的代码；GitHub 适合托管在仓库并想定时同步的代码。"),
    dict(key="project.upload_zip", group="project", type="file", default="",
         label="项目压缩包", envs=["all"],
         help="只接受 .zip，面板会安全解压到工作目录；拒绝路径穿越、软链接与超大压缩包。"),
    dict(key="project.template", group="project", type="select", default="打工避雷平台",
         label="内置项目模板", options_loader="templates",
         help="选内置模板可自动填入数据库表、接口与页面代码，不用手动粘贴。"),
    dict(key="project.github_url", group="project", type="text", default="",
         label="GitHub 仓库地址",
         help="形如 https://github.com/owner/repo.git ，也支持不带 .git。"),
    dict(key="project.branch", group="project", type="text", default="main",
         label="分支", help="常见为 main 或 master。"),
    dict(key="project.token", group="project", type="password", default="",
         label="访问 Token", secret=True,
         help="私有仓库才需要。仅保存在本机工作目录，接口回传时自动打码。"),
    dict(key="project.subdir", group="project", type="text", default="",
         label="子目录", help="仓库/压缩包里如果项目在下一级目录，填这里，例如 backend。"),
    dict(key="project.auto_sync", group="project", type="switch", default=False,
         label="定时同步", help="开启后按间隔自动拉取仓库最新代码。"),
    dict(key="project.sync_interval_min", group="project", type="number", default=30,
         label="同步间隔（分钟）", min=1, max=1440),

    # ---------------- target ----------------
    dict(key="target.env", group="target", type="select", default="local",
         label="部署环境", options_loader="envs",
         help="本地测试=本机直接跑；其余为云端环境，面板生成对应产物与步骤。"),
    dict(key="target.app_port", group="target", type="number", default=5000,
         label="应用端口", min=1, max=65535,
         help="Flask/gunicorn 实际监听端口，默认 5000。"),

    # ---------------- network ----------------
    dict(key="network.domain", group="network", type="text", default="localhost",
         label="域名", help="用于 Nginx server_name 与访问地址；本地测试填 localhost。"),
    dict(key="network.listen_port", group="network", type="number", default=80,
         label="对外端口", min=1, max=65535, envs=["local", "ubuntu"],
         help="用户访问的端口，默认 80，通过 Nginx 反代到应用端口。"),
    dict(key="network.bind_host", group="network", type="text", default="127.0.0.1",
         label="绑定地址", envs=["local", "ubuntu", "render"],
         help="本地测试用 127.0.0.1 最安全；云服务器可填 0.0.0.0 由 Nginx 反代。"),
    dict(key="network.workers", group="network", type="number", default=2, min=1, max=32,
         label="并发进程数", envs=["ubuntu", "render"],
         help="gunicorn worker 数量，个人服务器 2 个够用。"),

    # ---------------- database ----------------
    dict(key="database.engine", group="database", type="select", default="sqlite",
         label="数据库类型", options=[("sqlite", "SQLite（文件，免安装）"), ("mysql", "MySQL")],
         help="SQLite 开箱即用；MySQL 需要服务器上已安装并建好库。"),
    dict(key="database.sqlite_path", group="database", type="text", default="data/app.db",
         label="SQLite 文件路径", envs=["sqlite"],
         help="相对于项目根目录，面板会自动创建上级目录。"),
    dict(key="database.mysql_host", group="database", type="text", default="127.0.0.1", envs=["mysql"]),
    dict(key="database.mysql_port", group="database", type="number", default=3306, min=1, max=65535, envs=["mysql"]),
    dict(key="database.mysql_user", group="database", type="text", default="root", envs=["mysql"]),
    dict(key="database.mysql_password", group="database", type="password", default="", secret=True, envs=["mysql"]),
    dict(key="database.mysql_dbname", group="database", type="text", default="dgbilei", envs=["mysql"]),

    # ---------------- allowlist ----------------
    dict(key="allowlist.video_domains", group="allowlist", type="list", default=[
            "bilibili.com", "douyin.com", "kuaishou.com", "channels.weixin.qq.com"],
         label="允许的视频域名", list_placeholder="例如 bilibili.com",
         help="可增删。后端会用这份清单校验视频链接，不在清单内的一律拒绝。"),
    dict(key="allowlist.proxy_images", group="allowlist", type="switch", default=True,
         label="代理站外图片", help="关闭后站外图片一律不加载，更省流量。"),

    # ---------------- security ----------------
    dict(key="security.captcha", group="security", type="switch", default=True,
         label="人机验证", help="提交举报/评论前需要验证，减少机器人灌水。"),
    dict(key="security.captcha_provider", group="security", type="select", default="builtin",
         label="验证方式", options=[("builtin", "内置算术/图形"), ("turnstile", "Cloudflare Turnstile")],
         envs=["captcha"], help="内置方式零依赖；Turnstile 需要自己去官网申请 key。"),
    dict(key="security.content_review", group="security", type="switch", default=True,
         label="内容标记", help="命中辱骂、广告、联系方式等只做记录与提示，不影响发布（平台不设人工审核）。"),
    dict(key="security.rate_limit", group="security", type="switch", default=True,
         label="防刷限制", help="按 IP 限制提交频率，超出后返回 429。"),
    dict(key="security.rate_limit_per_min", group="security", type="number", default=10, min=1, max=600,
         label="每分钟最大提交次数", envs=["rate_limit"]),

    # ---------------- nginx ----------------
    dict(key="nginx.enable", group="nginx", type="switch", default=True, envs=["ubuntu"],
         label="启用 Nginx", help="云服务器建议用 Nginx 反代；本地测试可关闭。"),
    dict(key="nginx.server_name", group="nginx", type="text", default="localhost", envs=["ubuntu"]),
    dict(key="nginx.static_alias", group="nginx", type="text", default="/static/", envs=["ubuntu"],
         help="静态资源路径前缀，交给 Nginx 直出以减轻 Flask 压力。"),
    dict(key="nginx.client_max_body_size", group="nginx", type="text", default="10m", envs=["ubuntu"]),
    dict(key="nginx.gzip", group="nginx", type="switch", default=True, envs=["ubuntu"]),
    dict(key="nginx.ssl", group="nginx", type="switch", default=False, envs=["ubuntu"],
         label="启用 HTTPS", help="需要自己准备证书；面板只生成配置，不申请证书。"),
    dict(key="nginx.ssl_cert", group="nginx", type="text", default="/etc/ssl/certs/APP.pem", envs=["nginx_ssl"]),
    dict(key="nginx.ssl_key", group="nginx", type="text", default="/etc/ssl/private/APP.key", envs=["nginx_ssl"]),
    dict(key="nginx.extra_raw", group="nginx", type="textarea", default="", envs=["ubuntu"],
         label="追加原始配置", help="高级用法，生成时会原样贴在 server 块末尾。"),

    # ---------------- advanced ----------------
    dict(key="advanced.command_overrides", group="advanced", type="kv", default={},
         label="命令覆盖", help="键为命令 id，值为替代命令；留空则用面板生成的默认命令。"),
    dict(key="advanced.keep_backups", group="advanced", type="number", default=5, min=0, max=50,
         label="保留备份份数", help="超过份数时自动删除最旧的备份。"),
]

FIELDS_BY_KEY = {f["key"]: f for f in FIELDS}


def _visible(field, ctx):
    """按当前上下文判断字段是否可见。

    ctx: {"env":..., "source_mode":..., "database":..., "security":..., "nginx":...}
    """
    envs = field.get("envs")
    if not envs or "all" in envs:
        return True
    env = ctx.get("env")
    source_mode = ctx.get("source_mode")
    engine = ctx.get("database")
    security = ctx.get("security") or {}
    nginx = ctx.get("nginx") or {}

    if "github" in field["key"] or field["key"].startswith("project.github"):
        if source_mode != "github":
            return False
    if field["key"] == "project.upload_zip" and source_mode != "upload":
        return False
    if field["key"] == "project.template" and source_mode != "upload":
        return False
    if field["key"] in ("project.auto_sync", "project.sync_interval_min") and source_mode != "github":
        return False

    if "sqlite" in envs and engine != "sqlite":
        return False
    if "mysql" in envs and engine != "mysql":
        return False
    if "captcha" in envs and not security.get("captcha"):
        return False
    if "rate_limit" in envs and not security.get("rate_limit"):
        return False
    if "nginx_ssl" in envs and not nginx.get("ssl"):
        return False
    concrete = [e for e in envs if e not in ("all", "sqlite", "mysql", "captcha", "rate_limit", "nginx_ssl")]
    if concrete and env not in concrete:
        return False
    return True


def default_config():
    cfg = {}
    for f in FIELDS:
        cfg[f["key"]] = f["default"] if not isinstance(f["default"], (list, dict)) else _copy(f["default"])
    return cfg


def _copy(v):
    if isinstance(v, dict):
        return {k: _copy(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_copy(x) for x in v]
    return v


def flatten(cfg):
    """把配置归一化成点号键的扁平字典。"""
    out = {}
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            if isinstance(v, dict) and "." not in k:
                for kk, vv in v.items():
                    out["%s.%s" % (k, kk)] = vv
            else:
                out[k] = v
    return out


def expand(flat):
    """把点号键展开成分组结构，便于前端按分组渲染。"""
    nested = {}
    for k, v in flat.items():
        if "." in k:
            g, name = k.split(".", 1)
            nested.setdefault(g, {})[name] = v
        else:
            nested[k] = v
    return nested


def get(cfg, key, default=None):
    flat = flatten(cfg)
    return flat.get(key, FIELDS_BY_KEY.get(key, {}).get("default", default))


def context(cfg):
    flat = flatten(cfg)
    return {
        "env": flat.get("target.env", "local"),
        "source_mode": flat.get("project.source_mode", "upload"),
        "database": flat.get("database.engine", "sqlite"),
        "security": {
            "captcha": flat.get("security.captcha", False),
            "rate_limit": flat.get("security.rate_limit", False),
        },
        "nginx": {"ssl": flat.get("nginx.ssl", False)},
    }


def visible_fields(cfg):
    ctx = context(cfg)
    return [f for f in FIELDS if _visible(f, ctx)]


def ui_model():
    """给前端的渲染模型：分组 + 字段 + 选项 + 依赖条件。"""
    groups = []
    for g in GROUPS:
        groups.append(dict(g, fields=[_ui_field(f) for f in FIELDS if f["group"] == g["key"]]))
    return {"groups": groups, "envs": presets.env_options(), "presets": presets.all_presets()}


def _ui_field(f):
    item = {
        "key": f["key"],
        "label": f.get("label") or f["key"],
        "type": f["type"],
        "default": _copy(f["default"]),
        "help": f.get("help", ""),
        "envs": f.get("envs") or ["all"],
        "secret": bool(f.get("secret")),
    }
    for extra in ("min", "max", "list_placeholder", "options"):
        if extra in f:
            item[extra] = _copy(f[extra])
    if f.get("options_loader") == "templates":
        item["options"] = [[t["id"], t["name"]] for t in available_templates()]
    return item


def available_templates():
    """扫描 projects/ 目录下的内置模板。"""
    import json
    import os
    from . import paths
    out = []
    if not os.path.isdir(paths.PROJECTS_DIR):
        return out
    for name in sorted(os.listdir(paths.PROJECTS_DIR)):
        d = os.path.join(paths.PROJECTS_DIR, name)
        manifest = os.path.join(d, "manifest.json")
        if os.path.isdir(d) and os.path.isfile(manifest):
            try:
                with open(manifest, "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
            except Exception:
                meta = {}
            out.append({
                "id": meta.get("id", name),
                "name": meta.get("name", name),
                "desc": meta.get("desc", ""),
                "path": d,
                "manifest": meta,
            })
    return out


def find_template(template_id):
    for t in available_templates():
        if t["id"] == template_id or t["name"] == template_id:
            return t
    return None
