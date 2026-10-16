# -*- coding: utf-8 -*-
"""命令执行器：流式输出、超时、可取消。

runner 只负责「跑一条命令并把输出逐行喂给回调」，其余（任务注册、日志缓冲）
由 jobs 负责，便于单独测试。
"""
import os
import re
import shlex
import signal
import subprocess
import sys
import threading

from . import paths

# 日志/命令预览里需要打码的内容
_SECRET_PATTERNS = [
    re.compile(r"(?i)(token|password|passwd|secret|api[_-]?key)\s*[=:]\s*([^\s&'\"]+)"),
    re.compile(r"(?i)(authorization:\s*(?:bearer|token)\s+)(\S+)"),
    re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@"),
]


def mask(text):
    """命令与日志脱敏：密钥、token、URL 内嵌密码一律打码。"""
    if not text:
        return ""
    out = str(text)
    out = _SECRET_PATTERNS[0].sub(lambda m: "%s=%s" % (m.group(1), "********"), out)
    out = _SECRET_PATTERNS[1].sub(lambda m: "%s********" % m.group(1), out)
    out = _SECRET_PATTERNS[2].sub(lambda m: "%s%s:********@" % (m.group(1), m.group(2)), out)
    return out


def shell_of(cmd):
    """把命令列表/字符串统一成可直接交给 shell 的形式（仅用于展示）。"""
    if isinstance(cmd, (list, tuple)):
        return " ".join(_display_part(p) for p in cmd)
    return str(cmd)


def _display_part(p):
    p = str(p)
    if not p or any(c in p for c in ' \t"\'&|<>'):
        return '"%s"' % p.replace('"', '\\"')
    return p


class Result(object):
    def __init__(self, code, stdout, stderr, cancelled=False, timeout=False):
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.cancelled = cancelled
        self.timeout = timeout

    @property
    def ok(self):
        return self.code == 0 and not self.cancelled and not self.timeout

    def __repr__(self):
        return "<Result code=%s ok=%s>" % (self.code, self.ok)


class CancelToken(object):
    """跨线程取消信号 + 当前子进程句柄。"""

    def __init__(self):
        self._event = threading.Event()
        self._proc = None
        self._lock = threading.Lock()

    def cancel(self):
        self._event.set()
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                if paths.IS_WINDOWS:
                    proc.terminate()
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:
                    pass
        return True

    @property
    def cancelled(self):
        return self._event.is_set()

    def _attach(self, proc):
        with self._lock:
            self._proc = proc

    def _detach(self):
        with self._lock:
            self._proc = None


def popen_kwargs(cwd=None, extra_env=None, merge_stderr=True):
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    kwargs = dict(
        cwd=cwd or paths.WORKDIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=env,
        bufsize=0,
        universal_newlines=False,
    )
    if not paths.IS_WINDOWS:
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return kwargs


def run(cmd, cwd=None, on_line=None, timeout=None, token=None,
        extra_env=None, check_exists=None):
    """执行命令，逐行回调 on_line(line, stream)。

    cmd 可以是 list（推荐，避免注入）或 str（交给 shell）。
    check_exists: 传入命令名时先检查其是否存在，不存在直接返回 127，不抛异常。
    """
    if check_exists and not _exists(check_exists):
        msg = "未找到命令：%s" % check_exists
        if on_line:
            on_line(msg, "error")
        return Result(127, "", msg)

    use_shell = isinstance(cmd, str)
    proc = None
    stdout_lines = []
    try:
        if use_shell:
            if paths.IS_WINDOWS:
                proc = subprocess.Popen(cmd, shell=True, **popen_kwargs(cwd, extra_env))
            else:
                proc = subprocess.Popen(["/bin/sh", "-c", cmd], **popen_kwargs(cwd, extra_env))
        else:
            proc = subprocess.Popen(list(cmd), **popen_kwargs(cwd, extra_env))
    except FileNotFoundError:
        msg = "命令不存在：%s" % (cmd[0] if isinstance(cmd, (list, tuple)) else cmd)
        if on_line:
            on_line(msg, "error")
        return Result(127, "", msg)
    except Exception as exc:  # noqa: BLE001
        msg = "启动命令失败：%s" % exc
        if on_line:
            on_line(msg, "error")
        return Result(1, "", msg)

    if token:
        token._attach(proc)

    timer = None
    timed_out = {"v": False}

    def _on_timeout():
        timed_out["v"] = True
        try:
            proc.kill()
        except Exception:
            pass

    if timeout:
        timer = threading.Timer(timeout, _on_timeout)
        timer.daemon = True
        timer.start()

    def _reader(stream, name):
        if stream is None:
            return
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            stdout_lines.append(line)
            if on_line:
                on_line(mask(line), name)
        try:
            stream.close()
        except Exception:
            pass

    readers = []
    if proc.stdout:
        t = threading.Thread(target=_reader, args=(proc.stdout, "stdout"))
        t.daemon = True
        t.start()
        readers.append(t)

    code = proc.wait()
    for t in readers:
        t.join(timeout=5)
    if timer:
        timer.cancel()
    if token:
        token._detach()

    cancelled = bool(token and token.cancelled)
    if cancelled and on_line:
        on_line("任务已被用户取消", "warn")
    if timed_out["v"] and on_line:
        on_line("命令执行超时（%s 秒）" % timeout, "error")
    return Result(code, "\n".join(stdout_lines), "", cancelled=cancelled, timeout=timed_out["v"])


def _exists(name):
    from . import detect
    return bool(detect.which(name))


def background(cmd, cwd=None, log_path=None, extra_env=None):
    """后台启动一个长驻进程（用于本地测试环境的服务），返回 pid。

    输出重定向到 log_path，便于「查看实时日志」读取。
    """
    log_file = None
    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_file = open(log_path, "ab", buffering=0)

    kwargs = dict(cwd=cwd or paths.WORKDIR)
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    kwargs["env"] = env

    if log_file is not None:
        kwargs["stdout"] = log_file
        kwargs["stderr"] = subprocess.STDOUT
    else:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    kwargs["stdin"] = subprocess.DEVNULL

    if paths.IS_WINDOWS:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | 0x00000008  # DETACHED
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True

    if isinstance(cmd, str):
        cmd = ["/bin/sh", "-c", cmd] if not paths.IS_WINDOWS else cmd
        if paths.IS_WINDOWS:
            proc = subprocess.Popen(cmd, shell=True, **kwargs)
        else:
            proc = subprocess.Popen(cmd, **kwargs)
    else:
        proc = subprocess.Popen(list(cmd), **kwargs)
    return proc.pid


def kill_pid(pid, force=True):
    """按 pid 结束进程；返回是否成功。"""
    if not pid:
        return False
    import time
    if paths.IS_WINDOWS:
        args = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            args.append("/F")
        try:
            out = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
            return out.returncode == 0
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(int(pid), signal.SIGTERM if not force else signal.SIGKILL)
    except ProcessLookupError:
        return True
    except Exception:  # noqa: BLE001
        return False
    for _ in range(20):
        if not pid_alive(pid):
            return True
        time.sleep(0.2)
    try:
        os.kill(int(pid), signal.SIGKILL)
    except Exception:
        pass
    return not pid_alive(pid)


def pid_alive(pid):
    if not pid:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if paths.IS_WINDOWS:
        try:
            out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
            text = (out.stdout or b"").decode("utf-8", "replace")
            return str(pid) in text
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:  # noqa: BLE001
        return False


def split_command(text):
    """把用户输入的命令文本拆成 list（高级模式覆盖用）。"""
    if not text or not str(text).strip():
        return []
    try:
        return shlex.split(str(text), posix=not paths.IS_WINDOWS)
    except ValueError:
        return str(text).split()


def which_python():
    return sys.executable or ("python" if paths.IS_WINDOWS else "python3")
