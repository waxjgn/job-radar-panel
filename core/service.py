# -*- coding: utf-8 -*-
"""服务控制：启动 / 停止 / 重启 / 状态。

两种模式：
- systemd 模式（Ubuntu 且有 sudo）：交给 systemctl 管理；
- 进程模式（本地测试 / 无 systemd）：面板用独立进程启动并记录 pid，
  停止时按 pid 结束，因此 Windows 与 Linux 都能用。
"""
import json
import os
import socket
import time

from . import commands
from . import config_schema as schema
from . import config_store
from . import jobs
from . import paths
from . import presets
from . import runner

STATE_LOCK_TIMEOUT = 5


# --------------------------------------------------------------------------- #
# 状态文件
# --------------------------------------------------------------------------- #
def _read_state():
    if not os.path.isfile(paths.STATE_FILE):
        return {}
    try:
        with open(paths.STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_state(state):
    paths.ensure_runtime_dirs()
    tmp = paths.STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, paths.STATE_FILE)


def update_state(**kw):
    state = _read_state()
    state.update(kw)
    _write_state(state)
    return state


def clear_state(*keys):
    state = _read_state()
    for k in keys:
        state.pop(k, None)
    _write_state(state)
    return state


# --------------------------------------------------------------------------- #
# 端口 / 健康检查
# --------------------------------------------------------------------------- #
def port_open(port, host="127.0.0.1", timeout=1.5):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False


def health_check(port, host="127.0.0.1", path="/healthz"):
    """优先请求 /healthz，失败则退回端口探测。"""
    try:
        import urllib.request
        url = "http://%s:%s%s" % (host, port, path)
        with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310
            return {"ok": True, "code": resp.status, "url": url}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "url": "http://%s:%s%s" % (host, port, path)}


def status(cfg=None):
    cfg = cfg or config_store.load()
    flat = schema.flatten(cfg)
    env = flat.get("target.env", "local")
    port = int(flat.get("target.app_port") or 5000)
    bind = flat.get("network.bind_host") or "127.0.0.1"
    probe_host = "127.0.0.1"
    state = _read_state()
    pid = state.get("pid")
    caps = presets.caps(env)
    running_pid = bool(pid and runner.pid_alive(pid))
    listening = port_open(port, probe_host)

    result = {
        "env": env,
        "env_name": presets.get_env(env)["name"],
        "mode": "systemd" if (caps["systemd"] and env == "ubuntu") else "process",
        "pid": pid if running_pid else None,
        "raw_pid": pid,
        "port": port,
        "bind": bind,
        "listening": listening,
        "running": bool(running_pid or listening),
        "started_at": state.get("started_at"),
        "stopped_at": state.get("stopped_at"),
        "source": state.get("source"),
        "last_action": state.get("last_action"),
        "log_file": state.get("log_file") or os.path.join(paths.LOG_DIR, "app.log"),
        "systemd_supported": bool(caps["systemd"]),
        "static_only": bool(caps["static_only"]),
        "can_control": bool(caps["service"]),
    }
    if result["running"]:
        result["level"] = "ok"
        result["message"] = "服务运行中（端口 %s 可访问）" % port
    elif caps["static_only"]:
        result["level"] = "warn"
        result["message"] = "当前环境只发布静态页面，后端服务不在本机运行"
    else:
        result["level"] = "warn"
        result["message"] = "服务未运行"
    return result


# --------------------------------------------------------------------------- #
# 启动 / 停止 / 重启
# --------------------------------------------------------------------------- #
def start_job(cfg=None, title="启动服务"):
    cfg = cfg or config_store.load()
    return jobs.manager.start("start", title, lambda job: _do_start(job, cfg))


def stop_job(cfg=None):
    cfg = cfg or config_store.load()
    return jobs.manager.start("stop", "停止服务", lambda job: _do_stop(job, cfg))


def restart_job(cfg=None):
    cfg = cfg or config_store.load()
    return jobs.manager.start("restart", "重启服务", lambda job: _do_restart(job, cfg))


def _sysd_name(flat):
    return flat.get("service_name") or "dgbilei"


def _do_start(job, cfg):
    flat = schema.flatten(cfg)
    env = flat.get("target.env", "local")
    caps = presets.caps(env)
    source_dir = commands._source_dir(flat)

    if caps["static_only"]:
        job.finish("failed", "error", "当前环境（Vercel）只发布静态页面，不运行后端服务")
        return
    if not os.path.isdir(source_dir):
        job.finish("failed", "error", "源码目录不存在，请先上传或拉取代码")
        return

    port = int(flat.get("target.app_port") or 5000)
    if port_open(port):
        job.log("端口 %s 已被占用，服务可能已在运行" % port, "warn")
        job.finish("done", "warn", "端口已在监听，未重复启动")
        return

    # 写产物与 .env，保证启动时配置是最新的
    from . import templates_gen
    job.set_progress(10, "写入配置文件")
    try:
        templates_gen.write_artifacts(cfg, source_dir)
        env_text = config_store.to_env(flat)
        with open(os.path.join(source_dir, ".env"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(env_text)
        job.log("已写入 .env 与 deploy/ 配置", "ok")
    except Exception as exc:  # noqa: BLE001
        job.log("写配置失败：%s" % exc, "warn")

    if caps["systemd"] and env == "ubuntu":
        _start_systemd(job, flat, source_dir)
        return

    _start_process(job, flat, source_dir)


def _start_systemd(job, flat, source_dir):
    svc = _sysd_name(flat)
    step = commands.get_command(flat, "start_service", source_dir)
    job.set_progress(40, "systemd 启动中")
    res = jobs.run_step(job, step.argv, cwd=source_dir)
    if not res.ok:
        job.log("systemctl 启动失败；如果服务器上没有配置 systemd，请改用「本地进程模式」运行", "warn")
        job.finish("failed", "error", "systemd 启动失败")
        return
    job.set_progress(80, "确认状态")
    jobs.run_step(job, ["sudo", "systemctl", "is-active", "%s.service" % svc], cwd=source_dir)
    update_state(pid=None, started_at=time.time(), env=flat.get("target.env"),
                 port=flat.get("target.app_port"), mode="systemd", last_action="start")
    job.finish("done", "ok", "systemd 服务已启动")


def _start_process(job, flat, source_dir):
    log_file = os.path.join(paths.LOG_DIR, "app.log")
    os.makedirs(paths.LOG_DIR, exist_ok=True)
    py = runner.which_python()
    env = {
        "APP_PORT": flat.get("target.app_port") or 5000,
        "APP_BIND": flat.get("network.bind_host") or "127.0.0.1",
        "FLASK_ENV": "production" if flat.get("target.env") != "local" else "development",
        "DEPLOY_PANEL": "1",
    }
    job.set_progress(30, "初始化数据库")
    try:
        from . import db
        ok, msgs = db.init_sqlite(flat)
        for m in msgs:
            job.log(m, "ok" if ok else "error")
    except Exception as exc:  # noqa: BLE001
        job.log("初始化数据库跳过：%s" % exc, "warn")

    job.set_progress(60, "启动进程")
    try:
        pid = runner.background([py, "app.py"], cwd=source_dir, log_path=log_file, extra_env=env)
    except Exception as exc:  # noqa: BLE001
        job.log("启动失败：%s" % exc, "error")
        job.finish("failed", "error", "启动进程失败")
        return
    job.log("已启动进程 pid=%s" % pid, "ok")
    job.log("日志文件：%s" % log_file, "info")

    port = int(flat.get("target.app_port") or 5000)
    job.set_progress(80, "等待端口就绪")
    ready = False
    for _ in range(20):
        if job.token.cancelled:
            job.log("用户取消，正在停止刚启动的进程", "warn")
            runner.kill_pid(pid)
            raise jobs._Cancelled()
        if not runner.pid_alive(pid):
            job.log("进程已退出，请查看下面的日志", "error")
            break
        if port_open(port):
            ready = True
            break
        time.sleep(0.6)

    update_state(pid=pid, started_at=time.time(), env=flat.get("target.env"),
                 port=port, mode="process", log_file=log_file, last_action="start",
                 source=source_dir)
    if ready:
        job.set_progress(100, "启动成功")
        job.log("服务已就绪：http://127.0.0.1:%s" % port, "ok")
        job.finish("done", "ok", "服务已启动")
    else:
        job.log("端口 %s 尚未就绪，请检查日志窗口里的报错" % port, "warn")
        job.finish("failed", "error", "启动后端口未就绪")


def _do_stop(job, cfg):
    flat = schema.flatten(cfg)
    env = flat.get("target.env", "local")
    caps = presets.caps(env)
    state = _read_state()
    source_dir = commands._source_dir(flat)

    if caps["systemd"] and env == "ubuntu" and state.get("mode") == "systemd":
        svc = _sysd_name(flat)
        job.set_progress(40, "systemd 停止中")
        res = jobs.run_step(job, ["sudo", "systemctl", "stop", "%s.service" % svc], cwd=source_dir)
        update_state(stopped_at=time.time(), pid=None, last_action="stop")
        job.finish("done" if res.ok else "failed", "ok" if res.ok else "error",
                   "服务已停止" if res.ok else "停止失败")
        return

    pid = state.get("pid")
    if not pid:
        job.set_progress(50, "没有记录到进程")
        job.log("状态文件里没有 pid，可能服务本来就没启动", "warn")
        port = int(flat.get("target.app_port") or 5000)
        if port_open(port):
            job.log("但端口 %s 仍在监听，可能有其他进程占用" % port, "warn")
            job.log("可用命令排查：%s" % runner.mask(_port_hint(port)), "info")
            job.finish("failed", "warn", "未找到面板启动的进程，端口被其他程序占用")
        else:
            job.finish("done", "ok", "服务未在运行")
        return

    job.set_progress(40, "结束进程 pid=%s" % pid)
    ok = runner.kill_pid(pid, force=True)
    time.sleep(0.5)
    alive = runner.pid_alive(pid)
    if ok or not alive:
        job.log("已结束进程 %s" % pid, "ok")
        clear_state("pid")
        update_state(stopped_at=time.time(), last_action="stop")
        job.finish("done", "ok", "服务已停止")
    else:
        job.log("结束进程失败，请手动执行：%s" % runner.mask(_kill_hint(pid)), "error")
        job.finish("failed", "error", "停止失败")


def _do_restart(job, cfg):
    flat = schema.flatten(cfg)
    state = _read_state()
    env = flat.get("target.env", "local")
    caps = presets.caps(env)
    source_dir = commands._source_dir(flat)
    if caps["systemd"] and env == "ubuntu" and state.get("mode") == "systemd":
        svc = _sysd_name(flat)
        job.set_progress(40, "systemd 重启中")
        res = jobs.run_step(job, ["sudo", "systemctl", "restart", "%s.service" % svc], cwd=source_dir)
        update_state(last_action="restart", started_at=time.time())
        job.finish("done" if res.ok else "failed", "ok" if res.ok else "error",
                   "服务已重启" if res.ok else "重启失败")
        return
    # 进程模式：先停再起
    job.set_progress(20, "停止旧进程")
    stop_job_result = _stop_via_pid(job, flat)
    if job.token.cancelled:
        raise jobs._Cancelled()
    if not stop_job_result:
        job.log("旧进程未正常结束，继续尝试启动", "warn")
    _do_start(job, cfg)


def _stop_via_pid(job, flat):
    state = _read_state()
    pid = state.get("pid")
    if not pid:
        job.log("没有记录到旧进程", "warn")
        return True
    ok = runner.kill_pid(pid, force=True)
    clear_state("pid")
    return ok or not runner.pid_alive(pid)


def _port_hint(port):
    if paths.IS_WINDOWS:
        return "netstat -ano | findstr :%s" % port
    return "ss -lptn 'sport = :%s'" % port


def _kill_hint(pid):
    if paths.IS_WINDOWS:
        return "taskkill /F /PID %s" % pid
    return "kill -9 %s" % pid


def start_sync_if_needed(cfg):
    """配置开启定时同步且是 GitHub 模式时启动调度器。"""
    flat = schema.flatten(cfg)
    from . import project_source
    if flat.get("project.source_mode") == "github" and flat.get("project.auto_sync"):
        return project_source.scheduler.start(
            flat.get("project.sync_interval_min", 30),
            lambda: config_store.load(),
        )
    project_source.scheduler.stop()
    return {"running": False}
