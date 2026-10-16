# -*- coding: utf-8 -*-
"""路径解析：所有运行期目录都收敛到这里，避免各模块各写一份相对路径。"""
import os
import sys

IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
IS_MAC = sys.platform == "darwin"
PLATFORM_NAME = "windows" if IS_WINDOWS else ("macos" if IS_MAC else "linux")

# tools/deploy_panel/
PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WEB_DIR = os.path.join(PANEL_DIR, "web")
PROJECTS_DIR = os.path.join(PANEL_DIR, "projects")
BUILTIN_TEMPLATE = os.path.join(PROJECTS_DIR, "打工避雷平台")

# 运行期工作区（可整体删除，已在 .gitignore 中忽略）
WORKDIR = os.environ.get("DEPLOY_PANEL_WORKDIR") or os.path.join(PANEL_DIR, ".workdir")
STATE_FILE = os.path.join(WORKDIR, "state.json")
CONFIG_FILE = os.path.join(WORKDIR, "config.json")
SOURCE_DIR = os.path.join(WORKDIR, "source")          # 解压/拉取后的项目源码
UPLOAD_DIR = os.path.join(WORKDIR, "uploads")          # 上传的 zip 暂存
BUILD_DIR = os.path.join(WORKDIR, "build")             # 生成的部署产物
LOG_DIR = os.path.join(WORKDIR, "logs")                # 运行日志
BACKUP_DIR = os.path.join(WORKDIR, "backups")          # 备份压缩包
DB_DIR = os.path.join(WORKDIR, "db")                   # SQLite 文件
EXPORT_DIR = os.path.join(WORKDIR, "exports")          # 导出的脚本/配置/代码包
TMP_DIR = os.path.join(WORKDIR, "tmp")

RUNTIME_DIRS = (
    WORKDIR, UPLOAD_DIR, BUILD_DIR, LOG_DIR,
    BACKUP_DIR, DB_DIR, EXPORT_DIR, TMP_DIR,
)

DEFAULT_PANEL_HOST = "127.0.0.1"
DEFAULT_PANEL_PORT = 8765


def abs_path(*parts):
    return os.path.abspath(os.path.join(*parts))


def ensure_runtime_dirs():
    """幂等创建运行期目录。"""
    for d in RUNTIME_DIRS:
        os.makedirs(d, exist_ok=True)
    return list(RUNTIME_DIRS)


def safe_join(base, *parts):
    """把 *parts 拼到 base 下，并保证结果没有逃出 base。

    用于所有来自用户输入（zip 条目名、仓库子目录、文件名）的路径拼接。
    """
    base = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base, *parts))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("路径越界：%s" % target)
    return target


def rel(path, base=None):
    """相对 base（默认工作区）的展示用路径；跨盘时退回绝对路径。"""
    base = os.path.abspath(base or WORKDIR)
    try:
        r = os.path.relpath(os.path.abspath(path), base)
    except ValueError:
        return os.path.abspath(path)
    return r.replace(os.sep, "/")
