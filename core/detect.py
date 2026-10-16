# -*- coding: utf-8 -*-
"""环境探测：python / pip / nginx / git / mysql / sqlite / 端口占用。

探测结果统一是 level：ok(绿) / warn(黄) / error(红)，前端直接着色。
"""
import os
import shutil
import socket
import subprocess
import sys

from . import paths
from . import presets

TIMEOUT = 8


def which(name):
    """找可执行文件；Windows 上补 .exe/.cmd 后缀。"""
    p = shutil.which(name)
    if p:
        return p
    if paths.IS_WINDOWS:
        for ext in (".exe", ".cmd", ".bat"):
            p = shutil.which(name + ext)
            if p:
                return p
    return None


def _run(cmd, timeout=TIMEOUT):
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, shell=isinstance(cmd, str),
        )
        out = (proc.stdout or b"").decode("utf-8", "replace").strip()
        return proc.returncode, out
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _first_line(text):
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def check_python():
    exe = sys.executable
    ver = "%d.%d.%d" % sys.version_info[:3]
    level = "ok" if sys.version_info >= (3, 8) else "warn"
    return {
        "id": "python", "name": "Python", "required": True, "level": level,
        "found": bool(exe), "path": exe, "version": ver,
        "detail": "解释器：%s" % exe,
        "fix": "" if level == "ok" else "建议升级到 Python 3.8 以上。",
        "install_cmd": "",
    }


def check_pip():
    exe = which("pip") or which("pip3")
    if not exe:
        code, out = _run([sys.executable, "-m", "pip", "--version"])
        if code == 0:
            return {
                "id": "pip", "name": "pip", "required": True, "level": "ok",
                "found": True, "path": sys.executable, "version": _first_line(out),
                "detail": "通过 python -m pip 调用", "fix": "", "install_cmd": "",
            }
        return {
            "id": "pip", "name": "pip", "required": True, "level": "error",
            "found": False, "path": "", "version": "",
            "detail": "未找到 pip",
            "fix": "执行 python -m ensurepip --upgrade 可安装 pip。",
            "install_cmd": "%s -m ensurepip --upgrade" % _q(sys.executable),
        }
    code, out = _run([exe, "--version"])
    return {
        "id": "pip", "name": "pip", "required": True, "level": "ok",
        "found": True, "path": exe, "version": _first_line(out),
        "detail": "安装依赖用它执行", "fix": "", "install_cmd": "",
    }


def check_nginx(required):
    exe = which("nginx")
    if exe:
        code, out = _run([exe, "-v"])
        return {
            "id": "nginx", "name": "Nginx", "required": required, "level": "ok",
            "found": True, "path": exe, "version": _first_line(out) or "installed",
            "detail": "用于反向代理", "fix": "", "install_cmd": _install_hint("nginx"),
        }
    level = "error" if required else "warn"
    return {
        "id": "nginx", "name": "Nginx", "required": required, "level": level,
        "found": False, "path": "", "version": "",
        "detail": "未安装" if required else "未安装（当前环境不需要）",
        "fix": "Ubuntu：sudo apt install -y nginx" if required else "本地测试环境无需 Nginx。",
        "install_cmd": _install_hint("nginx"),
    }


def check_git(required):
    exe = which("git")
    if exe:
        code, out = _run([exe, "--version"])
        return {
            "id": "git", "name": "Git", "required": required, "level": "ok",
            "found": True, "path": exe, "version": _first_line(out),
            "detail": "命令行拉取代码用", "fix": "", "install_cmd": _install_hint("git"),
        }
    level = "error" if required else "warn"
    return {
        "id": "git", "name": "Git", "required": required, "level": level,
        "found": False, "path": "", "version": "",
        "detail": "未安装" if required else "未安装（面板改用 HTTPS 归档接口拉取，不影响使用）",
        "fix": "Ubuntu：sudo apt install -y git" if required else "面板不依赖 git 也能拉取 GitHub 代码。",
        "install_cmd": _install_hint("git"),
    }


def check_mysql():
    exe = which("mysql") or which("mysqld")
    if exe:
        code, out = _run([exe, "--version"])
        return {
            "id": "mysql", "name": "MySQL 客户端", "required": False, "level": "ok",
            "found": True, "path": exe, "version": _first_line(out),
            "detail": "可用于导入建表脚本", "fix": "", "install_cmd": _install_hint("mysql"),
        }
    return {
        "id": "mysql", "name": "MySQL 客户端", "required": False, "level": "warn",
        "found": False, "path": "", "version": "",
        "detail": "未安装（选择 SQLite 时不需要）",
        "fix": "选择 MySQL 时需要在服务器上安装并建库。",
        "install_cmd": _install_hint("mysql"),
    }


def check_db_driver(engine):
    """检查项目侧数据库驱动是否可导入。"""
    mod = "pymysql" if engine == "mysql" else "sqlite3"
    try:
        __import__(mod)
        return {
            "id": "db_driver", "name": "数据库驱动 (%s)" % mod, "required": True,
            "level": "ok", "found": True, "path": "", "version": "importable",
            "detail": "%s 可导入" % mod, "fix": "", "install_cmd": "",
        }
    except Exception:
        pkg = "pymysql" if engine == "mysql" else ""
        return {
            "id": "db_driver", "name": "数据库驱动 (%s)" % mod, "required": engine == "mysql",
            "level": "error" if engine == "mysql" else "warn",
            "found": False, "path": "", "version": "",
            "detail": "%s 不可导入" % mod,
            "fix": "安装：pip install pymysql" if engine == "mysql" else "标准库缺失，检查 Python 安装。",
            "install_cmd": "pip install %s" % pkg if pkg else "",
        }


def check_port(port, host="127.0.0.1"):
    """端口占用检测。返回 level/占用进程提示。"""
    if not port:
        return None
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        rc = sock.connect_ex((host if host not in ("0.0.0.0", "") else "127.0.0.1", int(port)))
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "port_%s" % port, "name": "端口 %s" % port, "required": True,
            "level": "warn", "found": False, "path": "", "version": "",
            "detail": "检测失败：%s" % exc, "fix": "检查端口号是否正确。", "install_cmd": "",
        }
    finally:
        sock.close()
    if rc == 0:
        return {
            "id": "port_%s" % port, "name": "端口 %s" % port, "required": True,
            "level": "error", "found": True, "path": "", "version": "occupied",
            "detail": "端口已被占用",
            "fix": "换一个应用端口，或先停掉占用该端口的进程。",
            "install_cmd": _port_kill_hint(port),
        }
    return {
        "id": "port_%s" % port, "name": "端口 %s" % port, "required": True,
        "level": "ok", "found": False, "path": "", "version": "free",
        "detail": "端口空闲，可以使用", "fix": "", "install_cmd": "",
    }


def _port_kill_hint(port):
    if paths.IS_WINDOWS:
        return 'netstat -ano | findstr :%s  然后  taskkill /F /PID <PID>' % port
    return "lsof -i :%s  或  ss -lptn 'sport = :%s'" % (port, port)


def _install_hint(pkg):
    if paths.IS_WINDOWS:
        return "choco install %s  或手动下载安装" % pkg
    if paths.IS_MAC:
        return "brew install %s" % pkg
    return "sudo apt update && sudo apt install -y %s" % pkg


def _q(s):
    return '"%s"' % s if " " in s else s


def check_python_packages(pkgs):
    """检查 Python 包是否已安装。"""
    results = []
    for name in pkgs:
        mod = {"flask": "flask", "requests": "requests", "gunicorn": "gunicorn",
               "pymysql": "pymysql", "python-dotenv": "dotenv"}.get(name, name.replace("-", "_"))
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "installed")
            results.append({
                "id": "pkg_%s" % name, "name": "依赖包 %s" % name, "required": True,
                "level": "ok", "found": True, "path": "", "version": str(ver),
                "detail": "已安装", "fix": "", "install_cmd": "",
            })
        except Exception:
            results.append({
                "id": "pkg_%s" % name, "name": "依赖包 %s" % name, "required": True,
                "level": "error", "found": False, "path": "", "version": "",
                "detail": "未安装", "fix": "点击「安装依赖」自动安装，或手动 pip install %s" % name,
                "install_cmd": "%s -m pip install %s" % (_q(sys.executable), name),
            })
    return results


def environment_report(cfg):
    """汇总探测结果：items + 总状态 level + needs_install 列表。"""
    from . import config_schema as schema
    flat = schema.flatten(cfg)
    env = flat.get("target.env", "local")
    engine = flat.get("database.engine", "sqlite")
    cap = presets.caps(env)

    items = [check_python(), check_pip()]
    items.append(check_git(required=presets.supports(env, "auto_sync") and env == "ubuntu"))
    items.append(check_nginx(required=bool(cap["nginx"])))
    items.append(check_mysql())
    items.append(check_db_driver(engine))

    if not cap["static_only"]:
        items.append(check_port(flat.get("target.app_port")))

    needs_install = [i["install_cmd"] for i in items
                     if i["level"] == "error" and i.get("install_cmd")]

    if any(i["level"] == "error" for i in items):
        overall = "error"
    elif any(i["level"] == "warn" for i in items):
        overall = "warn"
    else:
        overall = "ok"

    return {
        "env": env,
        "env_name": presets.get_env(env)["name"],
        "platform": presets.platform_summary(),
        "overall": overall,
        "items": items,
        "needs_install": needs_install,
        "capabilities": cap,
        "deps": presets.deps_for(env),
    }
