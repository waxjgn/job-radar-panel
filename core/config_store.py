# -*- coding: utf-8 -*-
"""配置读写、校验、脱敏。"""
import json
import os
import re
import threading

from . import config_schema as schema
from . import paths
from . import presets

_LOCK = threading.RLock()

SECRET_KEYS = [f["key"] for f in schema.FIELDS if f.get("secret")]
MASK = "********"


def load():
    """读 config.json；文件不存在/损坏时回退默认配置。"""
    with _LOCK:
        if not os.path.isfile(paths.CONFIG_FILE):
            return schema.default_config()
        try:
            with open(paths.CONFIG_FILE, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
        except Exception:
            return schema.default_config()
    flat = schema.flatten(saved)
    merged = schema.default_config()
    for k, v in flat.items():
        if k in merged or k in schema.FIELDS_BY_KEY:
            merged[k] = v
    # 配置里保存过掩码值时不覆盖真实密码（避免脱敏值被写回）
    for key in SECRET_KEYS:
        if merged.get(key) == MASK:
            current = _load_raw().get(key)
            merged[key] = current if current is not None else schema.FIELDS_BY_KEY[key]["default"]
    return merged


def _load_raw():
    try:
        with open(paths.CONFIG_FILE, "r", encoding="utf-8") as fh:
            return schema.flatten(json.load(fh))
    except Exception:
        return {}


def save(cfg):
    """校验并落盘；返回 (ok, errors, warnings)。"""
    paths.ensure_runtime_dirs()
    flat = schema.flatten(cfg)
    old = _load_raw()
    for key in SECRET_KEYS:
        if flat.get(key) == MASK:
            flat[key] = old.get(key, "")
    ok, errors, warnings = validate(flat)
    if not ok:
        return False, errors, warnings
    with _LOCK:
        tmp = paths.CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(schema.expand(flat), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, paths.CONFIG_FILE)
    return True, [], warnings


def masked(cfg):
    """返回给前端的配置：密钥打码。"""
    flat = dict(schema.flatten(cfg))
    for key in SECRET_KEYS:
        if flat.get(key):
            flat[key] = MASK
    return schema.expand(flat)


def secret_value(key, cfg=None):
    """取真实密钥（服务端内部使用，绝不返回给前端）。"""
    cfg = cfg if cfg is not None else load()
    return schema.flatten(cfg).get(key, "")


_URL_RE = re.compile(r"^https?://github\.com/[\w.\-]+/[\w.\-]+?(\.git)?/?$", re.I)
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
                        r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$")


def validate(flat):
    errors = []
    warnings = []
    ctx = schema.context(flat)

    def is_visible(key):
        f = schema.FIELDS_BY_KEY.get(key)
        return bool(f) and schema._visible(f, ctx)

    # --- 端口 ---
    for key, label in (("target.app_port", "应用端口"), ("network.listen_port", "对外端口")):
        if not is_visible(key):
            continue
        v = flat.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or not (1 <= v <= 65535):
            errors.append("%s 必须是 1-65535 的整数" % label)

    # --- 端口冲突 ---
    if flat.get("target.app_port") == flat.get("network.listen_port") and \
            flat.get("network.listen_port") and ctx["env"] in ("local", "ubuntu"):
        warnings.append("对外端口与应用端口相同，Nginx 反代将无法工作；建议对外 80、应用 5000。")

    # --- 项目源 ---
    mode = flat.get("project.source_mode")
    if mode not in ("upload", "github"):
        errors.append("项目来源必须是 upload 或 github")
    if mode == "github":
        url = (flat.get("project.github_url") or "").strip()
        if not url:
            errors.append("GitHub 模式下必须填写仓库地址")
        elif not _URL_RE.match(url):
            errors.append("GitHub 地址格式应为 https://github.com/owner/repo(.git)")
        if not (flat.get("project.branch") or "").strip():
            errors.append("GitHub 模式下必须填写分支名")
        if not flat.get("project.token"):
            warnings.append("未填写 Token：公开仓库可正常拉取，私有仓库会失败。")

    # --- 域名 ---
    if is_visible("network.domain"):
        d = (flat.get("network.domain") or "").strip()
        if d and d != "localhost" and not _DOMAIN_RE.match(d):
            errors.append("域名格式不正确：%s" % d)

    # --- 白名单 ---
    domains = flat.get("allowlist.video_domains")
    if not isinstance(domains, list):
        errors.append("视频域名白名单必须是列表")
    else:
        cleaned = []
        for d in domains:
            d = str(d).strip().lower()
            if not d:
                continue
            if "://" in d:
                from urllib.parse import urlparse
                d = urlparse(d).netloc or d
            d = d.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
            if d.startswith("www."):
                d = d[4:]
            if not _DOMAIN_RE.match(d):
                errors.append("白名单域名不合法：%s" % d)
                continue
            if d not in cleaned:
                cleaned.append(d)
        # 把归一化结果写回，保存时落盘的就是干净值
        flat["allowlist.video_domains"] = cleaned
        if not cleaned:
            warnings.append("视频域名白名单为空，所有视频链接都会被拒绝。")

    # --- 数据库 ---
    if flat.get("database.engine") == "mysql":
        for key, label in (("database.mysql_host", "MySQL 地址"),
                           ("database.mysql_user", "MySQL 用户"),
                           ("database.mysql_dbname", "MySQL 库名")):
            if is_visible(key) and not str(flat.get(key) or "").strip():
                errors.append("%s 不能为空" % label)
    else:
        p = str(flat.get("database.sqlite_path") or "").strip()
        if not p:
            errors.append("SQLite 文件路径不能为空")
        elif os.path.isabs(p) or ".." in p.replace("\\", "/").split("/"):
            warnings.append("SQLite 路径建议使用项目内的相对路径，例如 data/app.db")

    # --- nginx ssl ---
    if flat.get("nginx.ssl") and ctx["env"] == "ubuntu":
        if not flat.get("nginx.ssl_cert") or not flat.get("nginx.ssl_key"):
            errors.append("启用 HTTPS 时必须填写证书与私钥路径")

    # --- 环境能力冲突 ---
    env = ctx["env"]
    caps = presets.caps(env)
    if not caps["nginx"] and flat.get("nginx.enable") and env == "ubuntu":
        errors.append("当前环境不支持 Nginx")
    if flat.get("database.engine") == "mysql" and not caps["mysql"]:
        warnings.append("所选环境不提供 MySQL，将改为 SQLite 或需要你自备数据库。")

    return (len(errors) == 0), errors, warnings


def to_env(flat):
    """把配置转成项目可读的 .env 文本（不含换行的值会被转义）。"""
    e = schema.flatten(flat)
    lines = [
        "# 由「打工避雷平台 · 可视化部署面板」生成，请勿手工提交到公开仓库",
        "FLASK_ENV=%s" % ("production" if e.get("target.env") != "local" else "development"),
        "APP_PORT=%s" % e.get("target.app_port", 5000),
        "APP_BIND=%s" % e.get("network.bind_host", "127.0.0.1"),
        "APP_DOMAIN=%s" % e.get("network.domain", "localhost"),
        "DB_ENGINE=%s" % e.get("database.engine", "sqlite"),
    ]
    if e.get("database.engine") == "mysql":
        lines += [
            "MYSQL_HOST=%s" % e.get("database.mysql_host", "127.0.0.1"),
            "MYSQL_PORT=%s" % e.get("database.mysql_port", 3306),
            "MYSQL_USER=%s" % e.get("database.mysql_user", "root"),
            "MYSQL_PASSWORD=%s" % _esc(e.get("database.mysql_password", "")),
            "MYSQL_DB=%s" % e.get("database.mysql_dbname", ""),
        ]
    else:
        lines.append("SQLITE_PATH=%s" % e.get("database.sqlite_path", "data/app.db"))
    lines += [
        "VIDEO_ALLOWLIST=%s" % ",".join(e.get("allowlist.video_domains") or []),
        "PROXY_IMAGES=%s" % str(bool(e.get("allowlist.proxy_images"))).lower(),
        "ENABLE_CAPTCHA=%s" % str(bool(e.get("security.captcha"))).lower(),
        "CAPTCHA_PROVIDER=%s" % e.get("security.captcha_provider", "builtin"),
        "ENABLE_CONTENT_REVIEW=%s" % str(bool(e.get("security.content_review"))).lower(),
        "ENABLE_RATE_LIMIT=%s" % str(bool(e.get("security.rate_limit"))).lower(),
        "RATE_LIMIT_PER_MIN=%s" % e.get("security.rate_limit_per_min", 10),
        "SECRET_KEY=%s" % _secret_key(),
    ]
    return "\n".join(lines) + "\n"


def _esc(v):
    return str(v or "").replace("\n", "").replace("\r", "")


def _secret_key():
    import hashlib
    seed = "%s|%s" % (os.path.abspath(paths.WORKDIR), os.path.getmtime(paths.PANEL_DIR) if os.path.isdir(paths.PANEL_DIR) else 0)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
