# -*- coding: utf-8 -*-
"""任务注册表：job_id、状态、进度、日志缓冲、SSE 订阅、取消。

设计：每个长任务单独一个守护线程，日志写入环形缓冲，前端可以用
SSE 订阅（/api/jobs/<id>/stream）也可以轮询（/api/jobs/<id>）。
"""
import json
import threading
import time
import uuid

from . import runner

MAX_JOBS = 60
MAX_LINES = 2000
DEFAULT_PROGRESS = {"value": 0, "text": "等待开始"}

_EXCLUSIVE = {
    "install": "deploy",
    "deploy": "deploy",
    "start": "service",
    "stop": "service",
    "restart": "service",
    "pull": "source",
}


class Job(object):
    def __init__(self, job_id, kind, title):
        self.id = job_id
        self.kind = kind
        self.title = title
        self.status = "pending"        # pending | running | done | failed | cancelled
        self.level = "info"            # info | ok | warn | error
        self.message = ""
        self.progress = dict(DEFAULT_PROGRESS)
        self.created_at = time.time()
        self.started_at = None
        self.finished_at = None
        self.lines = []
        self._rev = 0
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self.token = runner.CancelToken()
        self.result = None

    # ---------- 日志 ----------
    def log(self, text, stream="stdout"):
        text = str(text)
        with self._cond:
            for piece in text.splitlines() or [""]:
                level = _level_of(piece, stream)
                self.lines.append({
                    "t": time.time(),
                    "level": level,
                    "stream": stream,
                    "text": piece,
                })
            if len(self.lines) > MAX_LINES:
                self.lines = self.lines[-MAX_LINES:]
            self._rev += 1
            self._cond.notify_all()

    def set_progress(self, value=None, text=None):
        with self._cond:
            if value is not None:
                self.progress["value"] = max(0, min(100, int(value)))
            if text is not None:
                self.progress["text"] = text
            self._rev += 1
            self._cond.notify_all()

    def finish(self, status, level=None, message=""):
        with self._cond:
            self.status = status
            self.level = level or ("ok" if status == "done" else "error")
            self.message = message
            self.finished_at = time.time()
            if status == "done":
                self.progress["value"] = 100
                self.progress["text"] = self.progress.get("text") or "已完成"
            self._rev += 1
            self._cond.notify_all()

    # ---------- 查询 ----------
    def snapshot(self, since=0):
        with self._lock:
            lines = [l for l in self.lines if l["t"] > since] if since else list(self.lines)
            return {
                "id": self.id,
                "kind": self.kind,
                "title": self.title,
                "status": self.status,
                "level": self.level,
                "message": self.message,
                "progress": dict(self.progress),
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "rev": self._rev,
                "lines": lines,
                "line_count": len(self.lines),
                "result": self.result,
            }

    def wait_for_rev(self, rev, timeout=1.0):
        with self._cond:
            if self._rev > rev:
                return self._rev
            self._cond.wait(timeout)
            return self._rev


class JobManager(object):
    def __init__(self):
        self._jobs = {}
        self._order = []
        self._lock = threading.RLock()
        self._running_locks = {}

    # ---------- 生命周期 ----------
    def create(self, kind, title):
        job_id = uuid.uuid4().hex[:12]
        job = Job(job_id, kind, title)
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
            while len(self._order) > MAX_JOBS:
                old = self._order.pop(0)
                if self._jobs.get(old) and self._jobs[old].status in ("done", "failed", "cancelled"):
                    self._jobs.pop(old, None)
        return job

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit=20):
        with self._lock:
            ids = list(reversed(self._order))[:limit]
            return [self._jobs[i].snapshot(since=0) if i in self._jobs else None for i in ids]

    def cancel(self, job_id):
        job = self.get(job_id)
        if not job:
            return False, "任务不存在"
        if job.status in ("done", "failed", "cancelled"):
            return False, "任务已结束"
        job.log("收到取消请求，正在终止…", "warn")
        job.token.cancel()
        return True, "已发送取消请求"

    def start(self, kind, title, fn, exclusive=True):
        """创建并在线程里执行 fn(job)。返回 Job。

        exclusive=True 时按 kind 归入互斥组，避免同时跑两个部署/启动任务。
        """
        group = _EXCLUSIVE.get(kind, kind)
        with self._lock:
            if exclusive:
                lock = self._running_locks.setdefault(group, threading.Lock())
                already = lock.locked()
            else:
                lock = None
                already = False
        job = self.create(kind, title)
        if already:
            job.finish("failed", "error", "已有同类任务正在执行，请等它结束后再试")
            job.log("互斥组「%s」中已有任务在运行" % group, "error")
            return job

        def _target():
            if lock:
                lock.acquire()
            try:
                job.status = "running"
                job.started_at = time.time()
                job.log("任务开始：%s" % title)
                job.set_progress(1, "开始执行")
                fn(job)
                if job.status == "running":
                    job.finish("done", "ok", "执行完成")
            except _Cancelled:
                job.finish("cancelled", "warn", "任务已取消")
            except Exception as exc:  # noqa: BLE001
                import traceback
                job.log("执行出错：%s" % exc, "error")
                for line in traceback.format_exc().splitlines():
                    job.log(line, "stderr")
                job.finish("failed", "error", str(exc))
            finally:
                if lock:
                    try:
                        lock.release()
                    except RuntimeError:
                        pass

        t = threading.Thread(target=_target, name="job-%s" % job.id)
        t.daemon = True
        t.start()
        return job

    # ---------- SSE ----------
    def sse_stream(self, job_id, poll=0.5, idle_limit=1800):
        """生成 SSE 事件流；任务结束后发送一次 done 事件并收尾。"""
        job = self.get(job_id)
        if not job:
            yield _sse({"error": "任务不存在", "status": "failed"})
            return
        last_rev = 0
        last_beat = time.time()
        idle_start = time.time()
        while True:
            rev = job.wait_for_rev(last_rev, timeout=poll)
            if rev != last_rev:
                snap = job.snapshot(since=0)
                # 只推增量行，避免每帧重发全部日志
                lines = job.lines
                start = 0
                if last_rev:
                    start = max(0, len(lines) - max(1, rev - last_rev))
                snap["lines"] = [_line_without_time(l) for l in lines[start:]]
                last_rev = rev
                yield _sse(snap)
                idle_start = time.time()
            elif time.time() - last_beat > 15:
                last_beat = time.time()
                yield ": keep-alive\n\n"
            if job.status in ("done", "failed", "cancelled"):
                yield _sse({"id": job.id, "status": job.status, "level": job.level,
                            "message": job.message, "final": True, "progress": job.progress})
                return
            if time.time() - idle_start > idle_limit:
                yield _sse({"id": job.id, "status": job.status, "final": True,
                            "message": "日志流闲置超时，请刷新查看"})
                return


class _Cancelled(Exception):
    pass


def _line_without_time(line):
    return {"level": line["level"], "stream": line["stream"], "text": line["text"]}


def _level_of(piece, stream):
    if stream in ("error", "stderr"):
        return "error"
    low = piece.lower()
    for token in ("error", "traceback", "exception", "失败", "致命", "拒绝"):
        if token in low:
            return "error"
    for token in ("warning", "warn", "警告", "跳过", "提示"):
        if token in low:
            return "warn"
    for token in ("success", "成功", "已完成", "done", "listening", "running on"):
        if token in low:
            return "ok"
    return "info"


def _sse(payload):
    return "data: %s\n\n" % json.dumps(payload, ensure_ascii=False)


manager = JobManager()


def cancelled(job):
    """在任务体里检查取消：已取消则抛出，交给管理器收尾。"""
    if job.token.cancelled:
        raise _Cancelled()


def run_step(job, cmd, cwd=None, timeout=None, progress=None, progress_text=None,
             check_exists=None, on_line=None, extra_env=None):
    """在任务里跑一条命令，自动把输出写进 job 日志并检查取消。"""
    if progress is not None:
        job.set_progress(progress, progress_text)
    job.log("$ %s" % runner.mask(runner.shell_of(cmd)), "cmd")
    cancelled(job)

    def _emit(line, stream):
        job.log(line, stream)
        if on_line:
            on_line(line, stream)

    res = runner.run(cmd, cwd=cwd, on_line=_emit, timeout=timeout,
                     token=job.token, check_exists=check_exists, extra_env=extra_env)
    if res.cancelled:
        raise _Cancelled()
    if not res.ok:
        job.log("命令退出码：%s" % res.code, "error")
    return res
