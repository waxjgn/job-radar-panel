# -*- coding: utf-8 -*-
"""运行日志：读取 / 实时跟随 / 清理。"""
import os
import time

from . import config_schema as schema
from . import paths
from . import service

MAX_READ = 400 * 1024     # 一次最多读 400KB
MAX_LINES = 1500


def log_file(cfg=None):
    state = service._read_state()
    return state.get("log_file") or os.path.join(paths.LOG_DIR, "app.log")


def tail(cfg=None, lines=300, level=None):
    """读取日志尾部若干行。"""
    path = log_file(cfg)
    if not os.path.isfile(path):
        return {"exists": False, "path": path, "lines": [],
                "message": "还没有日志文件（服务启动后会生成）"}
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        if size > MAX_READ:
            fh.seek(size - MAX_READ)
            fh.readline()   # 丢弃可能被截断的半行
        data = fh.read()
    text = data.decode("utf-8", "replace")
    all_lines = text.splitlines()[-max(1, int(lines)):]
    items = [_classify(l) for l in all_lines]
    if level and level != "all":
        items = [i for i in items if i["level"] == level]
    return {
        "exists": True,
        "path": path,
        "size": size,
        "lines": items,
        "lines_total": len(all_lines),
        "truncated": size > MAX_READ,
    }


def _classify(line):
    low = line.lower()
    level = "info"
    for token in ("error", "traceback", "exception", "失败", "critical"):
        if token in low:
            level = "error"
            break
    else:
        for token in ("warning", "warn", "警告"):
            if token in low:
                level = "warn"
                break
        else:
            for token in ("success", "成功", "started", "running on", "listening"):
                if token in low:
                    level = "ok"
                    break
    return {"level": level, "text": line}


def follow(cfg=None, poll=0.8, idle_limit=1800):
    """SSE 生成器：跟随日志文件追加内容。"""
    import json
    path = log_file(cfg)
    offset = 0
    if os.path.isfile(path):
        offset = max(0, os.path.getsize(path) - 8000)
    idle_start = time.time()
    last_beat = time.time()
    while True:
        if os.path.isfile(path):
            size = os.path.getsize(path)
            if size < offset:      # 日志被清理/轮转
                offset = 0
            if size > offset:
                with open(path, "rb") as fh:
                    fh.seek(offset)
                    data = fh.read()
                    offset = fh.tell()
                for line in data.decode("utf-8", "replace").splitlines():
                    yield _sse(_classify(line))
                idle_start = time.time()
        if time.time() - last_beat > 15:
            last_beat = time.time()
            yield ": keep-alive\n\n"
        if time.time() - idle_start > idle_limit:
            yield _sse({"level": "warn", "text": "日志跟随超时，请重新打开"})
            return
        time.sleep(poll)


def _sse(payload):
    import json
    return "data: %s\n\n" % json.dumps(payload, ensure_ascii=False)


def clear(cfg=None):
    path = log_file(cfg)
    if os.path.isfile(path):
        open(path, "w", encoding="utf-8").close()
        return {"ok": True, "path": path, "message": "日志已清空"}
    return {"ok": True, "path": path, "message": "日志文件不存在"}


def list_logs(cfg=None):
    out = []
    if os.path.isdir(paths.LOG_DIR):
        for name in sorted(os.listdir(paths.LOG_DIR)):
            p = os.path.join(paths.LOG_DIR, name)
            if os.path.isfile(p):
                out.append({
                    "name": name,
                    "path": p,
                    "size": os.path.getsize(p),
                    "mtime": os.path.getmtime(p),
                })
    return out
