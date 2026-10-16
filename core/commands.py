# -*- coding: utf-8 -*-
"""底层 shell 命令生成（高级模式展示 / 可覆盖）。

每个命令有唯一 id、标题、说明与生成函数；实际执行也走这里，保证
「高级模式里看到的」就是「真正跑的」。
"""
import os
import sys

from . import config_schema as schema
from . import paths
from . import presets
from . import runner


class CommandSpec(object):
    def __init__(self, cid, title, desc, argv, cwd=None, timeout=None, env=None):
        self.id = cid
        self.title = title
        self.desc = desc
        self.argv = argv
        self.cwd = cwd
        self.timeout = timeout
        self.env = env or {}

    def display(self):
        return runner.mask(runner.shell_of(self.argv))

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "desc": self.desc,
            "cmd": self.display(),
            "cwd": self.cwd or "",
            "timeout": self.timeout,
            "override": "",
        }


def build_all(cfg, source_dir=None):
    """返回当前配置下的全部命令，键为 id。"""
    flat = schema.flatten(cfg)
    env = flat.get("target.env", "local")
    source_dir = source_dir or _source_dir(flat)
    cap = presets.caps(env)
    py = runner.which_python()
    cmds = {}

    # ---- 环境检测 ----
    cmds["check_python"] = CommandSpec(
        "check_python", "检测 Python", "确认解释器版本可用",
        [py, "--version"], cwd=source_dir)
    cmds["check_pip"] = CommandSpec(
        "check_pip", "检测 pip", "确认 pip 可用",
        [py, "-m", "pip", "--version"], cwd=source_dir)
    cmds["check_nginx"] = CommandSpec(
        "check_nginx", "检测 Nginx", "确认 nginx 已安装",
        ["nginx", "-v"], cwd=source_dir, timeout=10)
    cmds["check_git"] = CommandSpec(
        "check_git", "检测 Git", "确认 git 已安装",
        ["git", "--version"], cwd=source_dir, timeout=10)
    cmds["check_mysql"] = CommandSpec(
        "check_mysql", "检测 MySQL 客户端", "确认 mysql 命令可用",
        ["mysql", "--version"], cwd=source_dir, timeout=10)

    # ---- 依赖安装 ----
    req = os.path.join(source_dir, "requirements.txt")
    cmds["install_deps"] = CommandSpec(
        "install_deps", "安装项目依赖", "按 requirements.txt 安装",
        [py, "-m", "pip", "install", "-r", req], cwd=source_dir, timeout=1800)
    cmds["install_deps_fallback"] = CommandSpec(
        "install_deps_fallback", "依赖清单缺失时的兜底安装", "没有 requirements.txt 时安装核心依赖",
        [py, "-m", "pip", "install", "flask"], cwd=source_dir, timeout=900)
    if flat.get("database.engine") == "mysql":
        cmds["install_mysql_driver"] = CommandSpec(
            "install_mysql_driver", "安装 MySQL 驱动", "pip install pymysql",
            [py, "-m", "pip", "install", "pymysql"], cwd=source_dir, timeout=600)
    if env == "ubuntu":
        cmds["install_gunicorn"] = CommandSpec(
            "install_gunicorn", "安装 gunicorn", "生产环境 WSGI 服务器",
            [py, "-m", "pip", "install", "gunicorn"], cwd=source_dir, timeout=600)

    # ---- 数据库初始化 ----
    cmds["init_db"] = CommandSpec(
        "init_db", "初始化数据库", "建表 + 写入基础数据",
        [py, "manage.py", "init-db"], cwd=source_dir, timeout=300)
    cmds["list_tables"] = CommandSpec(
        "list_tables", "查看表结构", "列出已建表与行数",
        [py, "manage.py", "tables"], cwd=source_dir, timeout=120)
    if flat.get("database.engine") == "mysql":
        cmds["mysql_import"] = CommandSpec(
            "mysql_import", "导入 MySQL 建库脚本", "执行 deploy/mysql.sql",
            ["mysql", "-u", flat.get("database.mysql_user", "root"), "-p",
             "-e", "source deploy/mysql.sql"],
            cwd=source_dir, timeout=300)

    # ---- 启动 / 停止 ----
    app_port = flat.get("target.app_port", 5000)
    bind = flat.get("network.bind_host", "127.0.0.1")
    if env == "local":
        cmds["start_service"] = CommandSpec(
            "start_service", "启动服务（本地）", "用 Flask 内置服务器跑起来",
            [py, "app.py"], cwd=source_dir, timeout=None,
            env={"APP_PORT": app_port, "APP_BIND": bind})
    elif env == "ubuntu":
        if cap["systemd"]:
            cmds["start_service"] = CommandSpec(
                "start_service", "启动服务（systemd）", "通过 systemd 守护启动",
                ["sudo", "systemctl", "start", "%s.service" % _svc(flat)], cwd=source_dir)
            cmds["stop_service"] = CommandSpec(
                "stop_service", "停止服务（systemd）", "停止并确认状态",
                ["sudo", "systemctl", "stop", "%s.service" % _svc(flat)], cwd=source_dir)
            cmds["restart_service"] = CommandSpec(
                "restart_service", "重启服务（systemd）", "改完配置后重启",
                ["sudo", "systemctl", "restart", "%s.service" % _svc(flat)], cwd=source_dir)
            cmds["status_service"] = CommandSpec(
                "status_service", "查看服务状态（systemd）", "systemctl status",
                ["sudo", "systemctl", "status", "--no-pager", "%s.service" % _svc(flat)],
                cwd=source_dir)
        else:
            cmds["start_service"] = CommandSpec(
                "start_service", "启动服务（nohup）", "无 systemd 时用 nohup 常驻",
                ["gunicorn", "-w", str(flat.get("network.workers", 2)),
                 "-b", "%s:%s" % (bind, app_port), "app:app", "--daemon"],
                cwd=source_dir)
    else:
        cmds["release_hint"] = CommandSpec(
            "release_hint", "云端发布指引", "该环境由平台侧构建，面板只导出配置",
            ["echo", "见 deploy/ 目录下的平台配置文件与使用说明.md"], cwd=source_dir)

    cmds["stop_service_local"] = CommandSpec(
        "stop_service_local", "停止服务（按 pid）", "结束面板启动的进程",
        ["kill", "<PID>"], cwd=source_dir)

    # ---- 日志 ----
    if env == "ubuntu" and cap["systemd"]:
        cmds["tail_log"] = CommandSpec(
            "tail_log", "查看日志（journalctl）", "实时跟随服务日志",
            ["sudo", "journalctl", "-u", "%s.service" % _svc(flat), "-f", "-n", "200"],
            cwd=source_dir)
    else:
        cmds["tail_log"] = CommandSpec(
            "tail_log", "查看日志（文件）", "读取面板记录的应用日志",
            _tail_argv(os.path.join(paths.LOG_DIR, "app.log")), cwd=source_dir)

    # ---- 备份 ----
    cmds["backup"] = CommandSpec(
        "backup", "打包备份", "项目 + 数据库 + 配置",
        ["tar", "-czf", os.path.join(paths.BACKUP_DIR, "backup.tar.gz"), "."],
        cwd=source_dir, timeout=600)

    # ---- 拉取代码 ----
    if flat.get("project.source_mode") == "github":
        cmds["pull_code"] = CommandSpec(
            "pull_code", "拉取仓库代码", "面板内部用 HTTPS 归档接口拉取（无需 git）",
            ["<panel>", "fetch", flat.get("project.github_url", ""), flat.get("project.branch", "main")],
            cwd=source_dir, timeout=600)

    # 应用高级模式的命令覆盖
    overrides = flat.get("advanced.command_overrides") or {}
    if isinstance(overrides, dict):
        for cid, text in overrides.items():
            if cid in cmds and str(text).strip():
                cmds[cid].argv = runner.split_command(text)
                cmds[cid].desc = (cmds[cid].desc + "（已由高级模式覆盖）").strip()

    return cmds


def get_command(cfg, cid, source_dir=None):
    return build_all(cfg, source_dir).get(cid)


def list_commands(cfg, source_dir=None):
    cmds = build_all(cfg, source_dir)
    out = []
    for cid in sorted(cmds):
        d = cmds[cid].to_dict()
        overrides = schema.flatten(cfg).get("advanced.command_overrides") or {}
        d["override"] = str(overrides.get(cid, "")) if isinstance(overrides, dict) else ""
        out.append(d)
    return out


def _source_dir(flat):
    sub = flat.get("project.subdir") or ""
    return paths.safe_join(paths.SOURCE_DIR, sub) if sub else paths.SOURCE_DIR


def _svc(flat):
    return flat.get("service_name") or "dgbilei"


def _tail_argv(path):
    if paths.IS_WINDOWS:
        return ["powershell", "-NoProfile", "-Command", "Get-Content -Tail 200 -Wait '%s'" % path]
    return ["tail", "-n", "200", "-f", path]
