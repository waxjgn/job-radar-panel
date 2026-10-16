# -*- coding: utf-8 -*-
"""备份与导出。

备份：项目源码 + 数据库 + 配置 + 生成产物 -> backups/xxx.zip
导出：部署脚本与配置 / nginx.conf / 项目代码包 -> exports/
"""
import os
import shutil
import time
import zipfile

from . import config_schema as schema
from . import config_store
from . import paths
from . import templates_gen

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache",
             ".mypy_cache", ".idea", ".vscode", ".workdir"}


def _add_tree(zf, root, prefix=""):
    """把目录树加进 zip，跳过缓存与虚拟环境目录。"""
    count = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            full = os.path.join(dirpath, name)
            arc = os.path.join(prefix, os.path.relpath(full, root)).replace(os.sep, "/")
            try:
                zf.write(full, arc)
                count += 1
            except (OSError, ValueError):
                continue
    return count


def create_backup(cfg=None, note=""):
    """打包备份，返回 {ok, path, size, files}。"""
    cfg = cfg or config_store.load()
    flat = schema.flatten(cfg)
    paths.ensure_runtime_dirs()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = "backup-%s.zip" % stamp
    out = os.path.join(paths.BACKUP_DIR, name)

    source_dir = templates_gen._source_path(flat)
    db_file = None
    if flat.get("database.engine") == "sqlite":
        rel = (flat.get("database.sqlite_path") or "data/app.db").replace("\\", "/").lstrip("/")
        candidate = paths.safe_join(source_dir, *rel.split("/"))
        if os.path.isfile(candidate):
            db_file = candidate

    files = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        if os.path.isdir(source_dir):
            files += _add_tree(zf, source_dir, "project")
        else:
            zf.writestr("project/EMPTY.txt", "源码目录不存在，备份时是空的\n")
        if db_file:
            zf.write(db_file, "database/" + os.path.basename(db_file))
        if os.path.isfile(paths.CONFIG_FILE):
            zf.write(paths.CONFIG_FILE, "config/config.json")
        zf.writestr("config/.env.example", config_store.to_env(flat))
        zf.writestr("config/env-check.txt",
                    "备份时间：%s\n备份说明：%s\n部署环境：%s\n数据库：%s\n" % (
                        time.strftime("%Y-%m-%d %H:%M:%S"), note or "手动备份",
                        flat.get("target.env"), flat.get("database.engine")))
        for rel_path, content in templates_gen.artifacts(cfg).items():
            arc = rel_path if rel_path.startswith("deploy/") else ("deploy/" + os.path.basename(rel_path))
            zf.writestr(arc, content)
            files += 1
    size = os.path.getsize(out)
    _prune(cfg)
    return {"ok": True, "path": out, "name": name, "size": size, "files": files,
            "db_included": bool(db_file), "created_at": time.time(),
            "message": "备份完成：%s（%.2f MB）" % (name, size / 1048576.0)}


def _prune(cfg):
    """保留最近 N 份备份。"""
    keep = schema.flatten(cfg).get("advanced.keep_backups", 5)
    try:
        keep = int(keep)
    except (TypeError, ValueError):
        keep = 5
    if keep <= 0 or not os.path.isdir(paths.BACKUP_DIR):
        return
    items = [(os.path.join(paths.BACKUP_DIR, n), os.path.getmtime(os.path.join(paths.BACKUP_DIR, n)))
             for n in os.listdir(paths.BACKUP_DIR) if n.endswith(".zip")]
    items.sort(key=lambda x: x[1], reverse=True)
    for p, _ in items[keep:]:
        try:
            os.remove(p)
        except OSError:
            pass


def list_backups():
    out = []
    if os.path.isdir(paths.BACKUP_DIR):
        for name in os.listdir(paths.BACKUP_DIR):
            if not name.endswith(".zip"):
                continue
            p = os.path.join(paths.BACKUP_DIR, name)
            out.append({
                "name": name,
                "path": p,
                "size": os.path.getsize(p),
                "created_at": os.path.getmtime(p),
            })
    return sorted(out, key=lambda x: x["created_at"], reverse=True)


# --------------------------------------------------------------------------- #
# 导出
# --------------------------------------------------------------------------- #
def export_deploy_scripts(cfg=None):
    """导出整套部署脚本与配置。"""
    cfg = cfg or config_store.load()
    flat = schema.flatten(cfg)
    paths.ensure_runtime_dirs()
    name = "deploy-scripts-%s.zip" % time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(paths.EXPORT_DIR, name)
    arts = templates_gen.artifacts(cfg)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in arts.items():
            zf.writestr(rel_path, content)
        zf.writestr("deploy/merge-deploy.sh",
                    "#!/usr/bin/env bash\n"
                    "# 把本包内容解压到项目根目录，然后执行 deploy/deploy.sh 即可。\n"
                    "set -e\n"
                    "mkdir -p deploy\n"
                    "cp -r deploy/* ./deploy/ 2>/dev/null || true\n"
                    "echo '现在可以执行: sudo bash deploy/deploy.sh'\n")
    return {"ok": True, "path": out, "name": name, "size": os.path.getsize(out),
            "items": list(arts.keys()),
            "message": "已导出 %d 个部署文件" % len(arts)}


def export_nginx(cfg=None):
    """单独导出 nginx.conf。"""
    cfg = cfg or config_store.load()
    paths.ensure_runtime_dirs()
    name = "nginx-%s.conf" % time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(paths.EXPORT_DIR, name)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(templates_gen.nginx_conf(cfg))
    return {"ok": True, "path": out, "name": name, "size": os.path.getsize(out),
            "message": "已导出 Nginx 配置"}


def export_project_code(cfg=None):
    """导出当前源码目录为代码包。"""
    cfg = cfg or config_store.load()
    flat = schema.flatten(cfg)
    source_dir = templates_gen._source_path(flat)
    if not os.path.isdir(source_dir):
        return {"ok": False, "message": "源码目录不存在，请先上传或拉取代码"}
    paths.ensure_runtime_dirs()
    name = "project-code-%s.zip" % time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(paths.EXPORT_DIR, name)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        files = _add_tree(zf, source_dir)
    return {"ok": True, "path": out, "name": name, "size": os.path.getsize(out),
            "files": files, "message": "已导出项目代码（%d 个文件）" % files}


EXPORTERS = {
    "deploy": export_deploy_scripts,
    "nginx": export_nginx,
    "code": export_project_code,
}


def export(kind, cfg=None):
    fn = EXPORTERS.get(kind)
    if not fn:
        return {"ok": False, "message": "不支持的导出类型：%s" % kind}
    return fn(cfg)


def export_preview(cfg=None):
    """给前端展示的导出清单（不落盘）。"""
    cfg = cfg or config_store.load()
    arts = templates_gen.artifacts(cfg)
    return {
        "deploy_files": [{"name": k, "size": len(v.encode("utf-8"))} for k, v in arts.items()],
        "kinds": [
            {"id": "deploy", "name": "部署脚本与配置包", "desc": "nginx/systemd/gunicorn/平台配置与部署脚本"},
            {"id": "nginx", "name": "Nginx 配置", "desc": "单独的 nginx.conf，方便直接替换"},
            {"id": "code", "name": "项目代码包", "desc": "当前源码目录整体打包"},
        ],
    }


def cleanup_exports(keep=20):
    if not os.path.isdir(paths.EXPORT_DIR):
        return 0
    items = [(os.path.join(paths.EXPORT_DIR, n), os.path.getmtime(os.path.join(paths.EXPORT_DIR, n)))
             for n in os.listdir(paths.EXPORT_DIR)]
    items.sort(key=lambda x: x[1], reverse=True)
    n = 0
    for p, _ in items[keep:]:
        try:
            os.remove(p)
            n += 1
        except OSError:
            pass
    return n
