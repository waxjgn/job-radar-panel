# -*- coding: utf-8 -*-
"""配置：全部从环境变量读取，.env 由部署面板生成。

优先使用 python-dotenv；没装时用内置的极简 .env 解析器，
保证「零依赖也能跑起来」。
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path=None):
    path = path or os.path.join(BASE_DIR, ".env")
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except OSError:
        pass


_load_dotenv()
try:                                    # 有 python-dotenv 时再兜一层
    from dotenv import load_dotenv       # type: ignore
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except Exception:                        # noqa: BLE001
    pass


def _bool(name, default=False):
    return str(os.environ.get(name, str(default))).strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


class Config(object):
    # --- 基础 ---
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get("SECRET_KEY") or "change-me-in-production"
    APP_PORT = _int("APP_PORT", 5000)
    APP_BIND = os.environ.get("APP_BIND", "127.0.0.1")
    APP_DOMAIN = os.environ.get("APP_DOMAIN", "localhost")
    DEBUG = _bool("FLASK_DEBUG", False)
    SITE_NAME = os.environ.get("SITE_NAME", "打工避雷平台")

    # --- 数据库 ---
    DB_ENGINE = os.environ.get("DB_ENGINE", "sqlite").strip().lower()
    SQLITE_PATH = os.path.join(BASE_DIR, os.environ.get("SQLITE_PATH", "data/app.db"))
    MYSQL = {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": _int("MYSQL_PORT", 3306),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "db": os.environ.get("MYSQL_DB", "dgbilei"),
        "charset": "utf8mb4",
    }

    # --- 视频链接：只收四大平台 ---
    VIDEO_ALLOWLIST = [d.strip().lower() for d in
                       os.environ.get("VIDEO_ALLOWLIST",
                                      "bilibili.com,douyin.com,kuaishou.com,channels.weixin.qq.com"
                                      ).split(",") if d.strip()]
    PROXY_IMAGES = _bool("PROXY_IMAGES", True)

    # --- 技术防护（不涉及人工审核）---
    ENABLE_CAPTCHA = _bool("ENABLE_CAPTCHA", True)
    CAPTCHA_PROVIDER = os.environ.get("CAPTCHA_PROVIDER", "builtin")
    ENABLE_CONTENT_REVIEW = _bool("ENABLE_CONTENT_REVIEW", True)
    ENABLE_RATE_LIMIT = _bool("ENABLE_RATE_LIMIT", True)
    RATE_LIMIT_PER_MIN = _int("RATE_LIMIT_PER_MIN", 10)

    # 命中只做记录与提示，不拦截（站点不设人工审核）
    REVIEW_BLOCK_WORDS = [w for w in os.environ.get(
        "REVIEW_BLOCK_WORDS",
        "傻逼,妈逼,操你,加微信,加QQ,联系电话,私聊我,代开发票,刷单,博彩,赌博,贷款,套现"
    ).split(",") if w]

    @classmethod
    def load_allowlist_from_db(cls):
        """数据库里的白名单优先（面板写入的表）。"""
        try:
            from models import query_all
            rows = query_all("SELECT domain FROM video_allowlist WHERE enabled=1")
            domains = [r["domain"] for r in rows if r.get("domain")]
            if domains:
                return domains
        except Exception:  # noqa: BLE001
            pass
        return cls.VIDEO_ALLOWLIST


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


CONFIG_MAP = {"development": DevelopmentConfig, "production": ProductionConfig}


def get_config():
    env = os.environ.get("FLASK_ENV", "development").strip().lower()
    return CONFIG_MAP.get(env, DevelopmentConfig)
