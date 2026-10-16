# -*- coding: utf-8 -*-
"""项目来源：本地 zip 上传解压 / GitHub 仓库拉取 / 定时同步。

安全要点（上传与拉取共用同一套校验）：
- 逐条校验规范化后的解压路径必须落在目标目录内（拒绝 ../ 穿越）；
- 拒绝符号链接与硬链接条目；
- 限制单文件大小与解压总量，防止压缩炸弹；
- 拒绝绝对路径与盘符路径。
"""
import io
import json
import os
import re
import shutil
import tarfile
import threading
import time
import zipfile

from . import config_schema as schema
from . import paths

MAX_SINGLE_FILE = 200 * 1024 * 1024      # 单文件 200MB
MAX_TOTAL_SIZE = 800 * 1024 * 1024       # 解压总量 800MB
MAX_ENTRIES = 20000
ALLOWED_EXT = None                        # None 表示不限制扩展名

_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[\w.\-]+)/(?P<repo>[\w.\-]+?)(?:\.git)?/?$", re.I)


class SourceError(Exception):
    pass


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def parse_github_url(url):
    m = _URL_RE.match((url or "").strip())
    if not m:
        raise SourceError("GitHub 地址格式应为 https://github.com/owner/repo(.git)")
    return m.group("owner"), m.group("repo")


def _check_relpath(name):
    """校验压缩包内的条目名，返回规范化的相对路径。"""
    if not name or name.endswith("/"):
        return None
    norm = name.replace("\\", "/")
    if norm.startswith("/") or re.match(r"^[a-zA-Z]:", norm):
        raise SourceError("压缩包内含绝对路径条目：%s" % name)
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise SourceError("压缩包内含路径穿越条目：%s" % name)
    return "/".join(parts)


def _prepare_target(target):
    if os.path.exists(target):
        shutil.rmtree(target, ignore_errors=True)
    os.makedirs(target, exist_ok=True)


def _strip_single_root(target):
    """如果解压后只有一个顶层目录，把它内部内容上提到 target。"""
    entries = [e for e in os.listdir(target) if not e.startswith("__MACOSX")]
    if len(entries) != 1:
        return None
    only = os.path.join(target, entries[0])
    if not os.path.isdir(only):
        return None
    tmp = target + "__flat"
    if os.path.exists(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    os.rename(only, tmp)
    for item in os.listdir(tmp):
        shutil.move(os.path.join(tmp, item), os.path.join(target, item))
    shutil.rmtree(tmp, ignore_errors=True)
    return entries[0]


# --------------------------------------------------------------------------- #
# 上传 zip
# --------------------------------------------------------------------------- #
def extract_zip(zip_path, target=None):
    target = target or paths.SOURCE_DIR
    if not zipfile.is_zipfile(zip_path):
        raise SourceError("不是有效的 zip 文件")
    _prepare_target(target)
    total = 0
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            rel = _check_relpath(info.filename)
            if rel is None:
                continue
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and (mode & 0o170000) == 0o120000:
                raise SourceError("压缩包内含符号链接：%s" % info.filename)
            if info.file_size > MAX_SINGLE_FILE:
                raise SourceError("单个文件过大（>200MB）：%s" % info.filename)
            total += info.file_size
            if total > MAX_TOTAL_SIZE:
                raise SourceError("解压后总量超过 800MB，已中止")
            count += 1
            if count > MAX_ENTRIES:
                raise SourceError("压缩包条目数量超过 20000，已中止")
            dest = paths.safe_join(target, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 256)
    stripped = _strip_single_root(target)
    files = _count_files(target)
    return {
        "target": target,
        "files": files,
        "entries": count,
        "stripped_root": stripped,
        "log": "解压完成：%d 个文件" % files,
    }


# --------------------------------------------------------------------------- #
# GitHub 拉取（HTTPS 归档接口，不依赖系统 git）
# --------------------------------------------------------------------------- #
def _http_get(url, token=None, timeout=120):
    """返回 (status, bytes)；requests 可用时优先用它。"""
    headers = {"User-Agent": "deploy-panel/1.0", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "token %s" % token
    try:
        import requests  # type: ignore
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True,
                            allow_redirects=True)
        chunks = []
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            if chunk:
                chunks.append(chunk)
        return resp.status_code, b"".join(chunks)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        raise SourceError("网络请求失败：%s" % exc)

    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:
            pass
        return exc.code, body
    except Exception as exc:  # noqa: BLE001
        raise SourceError("网络请求失败：%s" % exc)


def test_connection(url, branch="main", token=""):
    owner, repo = parse_github_url(url)
    api = "https://api.github.com/repos/%s/%s" % (owner, repo)
    code, body = _http_get(api, token, timeout=30)
    if code == 401:
        return {"ok": False, "level": "error", "message": "认证失败：Token 无效或已过期"}
    if code == 404:
        return {"ok": False, "level": "error",
                "message": "仓库不存在或为私有仓库（私有仓库请填写 Token）"}
    if code != 200:
        return {"ok": False, "level": "error", "message": "GitHub 返回状态码 %s" % code}
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return {"ok": False, "level": "warn", "message": "仓库可访问，但响应解析失败"}
    branches = []
    bcode, bbody = _http_get(api + "/branches?per_page=100", token, timeout=30)
    if bcode == 200:
        try:
            branches = [b.get("name") for b in json.loads(bbody.decode("utf-8", "replace"))]
        except Exception:
            branches = []
    branch_ok = (branch in branches) if branches else True
    return {
        "ok": True,
        "level": "ok" if branch_ok else "warn",
        "message": "已连通：%s（默认分支 %s）" % (data.get("full_name", repo),
                                                data.get("default_branch", "?")),
        "data": {
            "full_name": data.get("full_name"),
            "private": bool(data.get("private")),
            "default_branch": data.get("default_branch"),
            "branches": branches[:50],
            "branch_exists": branch_ok,
            "pushed_at": data.get("pushed_at"),
        },
    }


def fetch_repo(url, branch="main", token="", target=None, subdir=""):
    """下载仓库 tar.gz 并解压到 target/subdir。"""
    owner, repo = parse_github_url(url)
    target = target or paths.SOURCE_DIR
    branch = (branch or "main").strip()
    code, body = _http_get(
        "https://codeload.github.com/%s/%s/tar.gz/%s" % (owner, repo, branch),
        token, timeout=300)
    if code == 404:
        raise SourceError("分支 %s 不存在，或仓库不是公开的（私有请填 Token）" % branch)
    if code in (401, 403):
        raise SourceError("认证失败：检查 Token 是否有效、是否有该仓库读权限")
    if code != 200:
        raise SourceError("下载失败，状态码 %s" % code)
    if not body:
        raise SourceError("下载结果为空")

    workdir = os.path.join(paths.TMP_DIR, "repo_%d" % int(time.time()))
    _prepare_target(workdir)
    try:
        total = 0
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tf:
            members = tf.getmembers()
            for m in members:
                if m.issym() or m.islnk():
                    raise SourceError("仓库内含链接条目，已中止：%s" % m.name)
                rel = _check_relpath(m.name)
                if rel is None:
                    continue
                if m.isfile():
                    total += m.size
                    if m.size > MAX_SINGLE_FILE or total > MAX_TOTAL_SIZE:
                        raise SourceError("仓库体积超过面板限制（单文件 200MB / 总量 800MB）")
                dest = paths.safe_join(workdir, *rel.split("/"))
                if m.isdir():
                    os.makedirs(dest, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                src = tf.extractfile(m)
                if src is None:
                    continue
                with src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 256)
    finally:
        pass

    # tar.gz 的顶层目录是 repo-branch/
    inner = _strip_single_root(workdir)
    sub = (subdir or "").strip().strip("/")
    src_root = paths.safe_join(workdir, *sub.split("/")) if sub else workdir
    if not os.path.isdir(src_root):
        shutil.rmtree(workdir, ignore_errors=True)
        raise SourceError("子目录不存在：%s" % subdir)

    _prepare_target(target)
    for item in os.listdir(src_root):
        shutil.move(os.path.join(src_root, item), os.path.join(target, item))
    shutil.rmtree(workdir, ignore_errors=True)
    return {
        "target": target,
        "files": _count_files(target),
        "root": inner,
        "subdir": sub,
        "branch": branch,
        "bytes": len(body),
        "log": "已拉取 %s@%s（%.1f MB）" % (repo, branch, len(body) / 1048576.0),
    }


def _count_files(root):
    n = 0
    for _, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        n += len(files)
    return n


def copy_template(template_id, target=None):
    """把内置模板复制到源码目录。"""
    tpl = schema.find_template(template_id)
    if not tpl:
        raise SourceError("内置模板不存在：%s" % template_id)
    target = target or paths.SOURCE_DIR
    _prepare_target(target)
    for item in os.listdir(tpl["path"]):
        if item == "manifest.json":
            continue
        src = os.path.join(tpl["path"], item)
        dst = os.path.join(target, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    return {"target": target, "template": tpl["id"], "files": _count_files(target),
            "log": "已展开内置模板：%s" % tpl["name"]}


def inspect_source(target=None):
    """查看当前源码目录概况，用于面板展示。"""
    target = target or paths.SOURCE_DIR
    if not os.path.isdir(target):
        return {"exists": False, "files": 0, "entries": []}
    top = sorted(os.listdir(target))[:40]
    return {
        "exists": True,
        "files": _count_files(target),
        "entries": top,
        "has_app": os.path.isfile(os.path.join(target, "app.py")),
        "has_requirements": os.path.isfile(os.path.join(target, "requirements.txt")),
        "target": target,
    }


# --------------------------------------------------------------------------- #
# 定时同步
# --------------------------------------------------------------------------- #
class SyncScheduler(object):
    """简单的间隔轮询同步器（进程内，面板关闭即停止）。"""

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self.last_run = None
        self.last_result = None
        self.next_run = None

    def start(self, interval_min, cfg_provider):
        self.stop()
        self._stop = threading.Event()

        def _loop():
            interval = max(60, int(interval_min) * 60)
            while not self._stop.wait(5):
                self.next_run = time.time() + interval
                if self._stop.wait(interval):
                    return
                cfg = cfg_provider()
                flat = schema.flatten(cfg)
                if flat.get("project.source_mode") != "github":
                    continue
                try:
                    self.last_run = time.time()
                    self.last_result = self._pull(cfg)
                except Exception as exc:  # noqa: BLE001
                    self.last_result = {"ok": False, "message": str(exc)}

        self._thread = threading.Thread(target=_loop, name="sync-scheduler")
        self._thread.daemon = True
        self._thread.start()
        self.next_run = time.time() + max(60, int(interval_min) * 60)
        return {"running": True, "interval_min": interval_min, "next_run": self.next_run}

    def _pull(self, cfg):
        flat = schema.flatten(cfg)
        before = _count_files(paths.SOURCE_DIR)
        info = fetch_repo(flat.get("project.github_url", ""),
                          flat.get("project.branch", "main"),
                          _real_token(flat),
                          paths.SOURCE_DIR,
                          flat.get("project.subdir", ""))
        return {"ok": True, "message": info["log"], "files_before": before,
                "files": info["files"]}

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        self.next_run = None
        return {"running": False}

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def status(self):
        return {
            "running": self.running,
            "last_run": self.last_run,
            "last_result": self.last_result,
            "next_run": self.next_run,
        }


def _real_token(flat):
    from . import config_store
    return config_store.secret_value("project.token")


scheduler = SyncScheduler()
