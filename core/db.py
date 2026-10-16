# -*- coding: utf-8 -*-
"""数据库初始化：SQLite 直接建表，MySQL 生成并可选执行建库脚本。"""
import os
import sqlite3

from . import config_schema as schema
from . import paths
from . import templates_gen


def source_dir(cfg):
    flat = schema.flatten(cfg)
    sub = flat.get("project.subdir") or ""
    return paths.safe_join(paths.SOURCE_DIR, sub) if sub else paths.SOURCE_DIR


def schema_sql(cfg):
    """优先取源码目录里的 schema.sql，其次用模板内置语句。"""
    candidates = [
        os.path.join(source_dir(cfg), "schema.sql"),
        os.path.join(source_dir(cfg), "deploy", "schema.sql"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    return fh.read(), p
            except Exception:
                continue
    return templates_gen._template_schema(), "builtin"


def seed_sql(cfg):
    p = os.path.join(source_dir(cfg), "seeds.sql")
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                return fh.read(), p
        except Exception:
            pass
    return "", ""


def sqlite_path(cfg):
    flat = schema.flatten(cfg)
    rel = flat.get("database.sqlite_path") or "data/app.db"
    rel = rel.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("SQLite 路径不允许使用 ..")
    return paths.safe_join(source_dir(cfg), *rel.split("/"))


def init_sqlite(cfg, with_seed=True):
    """建库建表；返回 (ok, messages)。"""
    messages = []
    try:
        db = sqlite_path(cfg)
    except ValueError as exc:
        return False, [str(exc)]
    os.makedirs(os.path.dirname(db), exist_ok=True)
    sql, origin = schema_sql(cfg)
    messages.append("建表脚本来源：%s" % origin)
    con = sqlite3.connect(db)
    try:
        con.executescript(sql)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        messages.append("数据库文件：%s" % db)
        messages.append("已建表：%s" % (", ".join(tables) if tables else "（无）"))
        if with_seed:
            seed, seed_origin = seed_sql(cfg)
            if seed:
                con.executescript(seed)
                messages.append("已写入示例数据：%s" % seed_origin)
            else:
                messages.append("未找到 seeds.sql，跳过示例数据")
        con.commit()
    except sqlite3.Error as exc:
        return False, messages + ["SQLite 错误：%s" % exc]
    finally:
        con.close()
    return True, messages


def table_overview(cfg):
    """列出当前 SQLite 的表与行数，用于面板展示。"""
    flat = schema.flatten(cfg)
    if flat.get("database.engine") != "sqlite":
        return {"engine": "mysql", "tables": []}
    try:
        db = sqlite_path(cfg)
    except ValueError:
        return {"engine": "sqlite", "tables": [], "error": "路径不合法"}
    if not os.path.isfile(db):
        return {"engine": "sqlite", "path": db, "tables": [], "exists": False}
    con = sqlite3.connect(db)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        tables = []
        for n in names:
            try:
                cnt = con.execute("SELECT COUNT(*) FROM \"%s\"" % n).fetchone()[0]
            except sqlite3.Error:
                cnt = -1
            tables.append({"name": n, "rows": cnt})
    finally:
        con.close()
    return {"engine": "sqlite", "path": db, "exists": True, "tables": tables}


def mysql_script(cfg):
    """MySQL 建库脚本内容（供导出与手动执行）。"""
    return templates_gen.mysql_sql(cfg)


def mysql_apply_hint(cfg):
    flat = schema.flatten(cfg)
    db = flat.get("database.mysql_dbname") or "dgbilei"
    user = flat.get("database.mysql_user") or "root"
    return ("mysql -u %s -p < deploy/mysql.sql   # 会创建数据库 %s 并建表" % (user, db))
