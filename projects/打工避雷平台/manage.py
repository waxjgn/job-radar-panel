#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""命令行运维脚本（部署面板也会调用它）。

    python manage.py init-db     # 建表 + 写入示例数据
    python manage.py tables      # 列出表与行数
    python manage.py allowlist   # 查看视频域名白名单
    python manage.py run         # 先建表再启动
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import models  # noqa: E402
from config import Config as CFG  # noqa: E402


def cmd_init_db(_args):
    models.init_schema()
    print("[ok] 建表完成，共 %d 张表：%s" % (len(models.tables()), ", ".join(models.tables())))
    n = models.seed()
    print("[ok] 示例数据写入 %d 条语句" % n)
    return 0


def cmd_tables(_args):
    names = models.tables()
    if not names:
        print("还没有表，先执行 python manage.py init-db")
        return 1
    for name in names:
        try:
            row = models.query_one("SELECT COUNT(*) AS c FROM %s" % name)
            count = list(row.values())[0] if row else 0
        except Exception as exc:  # noqa: BLE001
            count = "?（%s）" % exc
        print("  %-20s %s 行" % (name, count))
    return 0


def cmd_allowlist(_args):
    for d in CFG.load_allowlist_from_db():
        print("  " + d)
    return 0


def cmd_run(_args):
    cmd_init_db(_args)
    from app import app
    host = CFG.APP_BIND
    port = int(os.environ.get("APP_PORT") or CFG.APP_PORT)
    print("启动：http://%s:%s" % (host, port))
    app.run(host=host, port=port, debug=CFG.DEBUG)
    return 0


COMMANDS = {
    "init-db": cmd_init_db,
    "tables": cmd_tables,
    "allowlist": cmd_allowlist,
    "run": cmd_run,
}


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "init-db"
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    fn = COMMANDS.get(cmd)
    if not fn:
        print("未知命令：%s\n%s" % (cmd, __doc__))
        return 2
    return fn(argv[2:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
