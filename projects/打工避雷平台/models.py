# -*- coding: utf-8 -*-
"""数据访问层：SQLite 与 MySQL 双引擎，接口一致。

业务代码统一用 `?` 占位符，MySQL 分支自动转成 `%s`。
"""
import hashlib
import os
import re
import sqlite3
import time

from config import Config as CFG

IS_MYSQL = CFG.DB_ENGINE == "mysql"
_PLACEHOLDER = re.compile(r"\?")


def _dsn():
    return CFG.MYSQL


def get_conn():
    if IS_MYSQL:
        import pymysql  # type: ignore
        conn = pymysql.connect(
            host=_dsn()["host"], port=int(_dsn()["port"]), user=_dsn()["user"],
            password=_dsn()["password"], database=_dsn()["db"],
            charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
            autocommit=False, connect_timeout=8,
        )
        return conn
    path = CFG.SQLITE_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _sql(sql):
    return _PLACEHOLDER.sub("%s", sql) if IS_MYSQL else sql


def _rows_to_dicts(rows, cursor):
    if IS_MYSQL:
        return [dict(r) for r in rows]
    return [dict(r) for r in rows]


def query_all(sql, args=()):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(_sql(sql), tuple(args))
        return _rows_to_dicts(cur.fetchall(), cur)
    finally:
        conn.close()


def query_one(sql, args=()):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(_sql(sql), tuple(args))
        if IS_MYSQL:
            cur.fetchone()
            row = cur.fetchone()
        else:
            row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(sql, args=()):
    """写入；返回自增主键或影响行数。"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(_sql(sql), tuple(args))
        last_id = getattr(cur, "lastrowid", None)
        affected = getattr(cur, "rowcount", 0)
        conn.commit()
        return last_id if last_id else affected
    finally:
        conn.close()


def executemany(sql, seq):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.executemany(_sql(sql), [tuple(a) for a in seq])
        affected = getattr(cur, "rowcount", 0)
        conn.commit()
        return affected
    finally:
        conn.close()


def init_schema(schema_file=None):
    """执行 schema.sql 建表（幂等）。"""
    schema_file = schema_file or os.path.join(CFG.BASE_DIR, "schema.sql")
    with open(schema_file, "r", encoding="utf-8") as fh:
        sql = fh.read()
    if IS_MYSQL:
        sql = _mysqlify(sql)
    conn = get_conn()
    try:
        cur = conn.cursor()
        if IS_MYSQL:
            for stmt in _split_statements(sql):
                cur.execute(stmt)
        else:
            conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


def seed(schema_file=None, seeds_file=None):
    seeds_file = seeds_file or os.path.join(CFG.BASE_DIR, "seeds.sql")
    if not os.path.isfile(seeds_file):
        return 0
    with open(seeds_file, "r", encoding="utf-8") as fh:
        sql = fh.read()
    if IS_MYSQL:
        sql = _mysqlify(sql).replace("INSERT OR IGNORE", "INSERT IGNORE")
    conn = get_conn()
    n = 0
    try:
        cur = conn.cursor()
        for stmt in _split_statements(sql):
            if stmt.strip():
                cur.execute(stmt)
                n += 1
        conn.commit()
    finally:
        conn.close()
    return n


def tables():
    if IS_MYSQL:
        return [r["TABLE_NAME"] if "TABLE_NAME" in r else list(r.values())[0]
                for r in query_all("SELECT TABLE_NAME FROM information_schema.tables "
                                   "WHERE table_schema = DATABASE()")]
    rows = query_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [r["name"] for r in rows]


# --------------------------------------------------------------------------- #
# 通用小工具
# --------------------------------------------------------------------------- #
def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def ip_hash(ip):
    return hashlib.sha256(("dgbilei|%s" % (ip or "")).encode("utf-8")).hexdigest()[:32]


def _split_statements(sql):
    """按分号切语句（忽略注释行），用于 MySQL 逐句执行。"""
    out, buf = [], []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--") or not s:
            continue
        buf.append(line)
        if s.endswith(";"):
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out


def _mysqlify(sql):
    out = re.sub(r"\bINTEGER PRIMARY KEY AUTOINCREMENT\b", "INT PRIMARY KEY AUTO_INCREMENT", sql, flags=re.I)
    out = re.sub(r"\bAUTOINCREMENT\b", "AUTO_INCREMENT", out, flags=re.I)
    out = re.sub(r"DEFAULT \(datetime\('now','localtime'\)\)", "DEFAULT CURRENT_TIMESTAMP", out, flags=re.I)
    out = re.sub(r"CREATE INDEX IF NOT EXISTS (\w+) ON", r"CREATE INDEX \1 ON", out, flags=re.I)
    return out
