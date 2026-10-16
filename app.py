# -*- coding: utf-8 -*-
"""打工避雷平台 · 可视化一键部署面板 —— Flask 入口。

启动：
    python app.py                 # 默认 http://127.0.0.1:8765
    python app.py --port 9000     # 换端口
    python app.py --no-browser    # 不自动打开浏览器
"""
import argparse
import io
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import backup as backup_mod          # noqa: E402
from core import commands as commands_mod      # noqa: E402
from core import config_schema as schema       # noqa: E402
from core import config_store                  # noqa: E402
from core import db as db_mod                  # noqa: E402
from core import detect                        # noqa: E402
from core import jobs                          # noqa: E402
from core import logs as logs_mod              # noqa: E402
from core import paths                         # noqa: E402
from core import presets                       # noqa: E402
from core import project_source                # noqa: E402
from core import runner                        # noqa: E402
from core import service                       # noqa: E402
from core import templates_gen                 # noqa: E402

try:
    from werkzeug.exceptions import HTTPException
    from flask import Flask, Response, jsonify, request, send_file, send_from_directory
except ImportError:  # pragma: no cover - 仅用于给出可读提示
    sys.stderr.write(
        "\n[!] 缺少 Flask，部署面板无法启动。\n"
        "    请先安装依赖：%s -m pip install -r %s\n\n"
        % (sys.executable, os.path.join(paths.PANEL_DIR, "requirements.txt"))
    )
    raise SystemExit(2)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024     # 上传上限 300MB
app.config["JSON_AS_ASCII"] = False


# --------------------------------------------------------------------------- #
# 统一响应
# --------------------------------------------------------------------------- #
def ok(data=None, message="", level="ok"):
    return jsonify({"ok": True, "data": data if data is not None else {},
                    "message": message, "level": level})


def fail(message, level="error", data=None, code=200):
    return jsonify({"ok": False, "data": data if data is not None else {},
                    "message": message, "level": level}), code


class BadRequest(Exception):
    pass


@app.errorhandler(HTTPException)
def _on_http_error(exc):  # noqa: ANN001
    return fail("%s %s" % (exc.code, exc.name), "error", code=exc.code or 500)


@app.errorhandler(413)
def _too_large(exc):  # noqa: ANN001
    return fail("上传文件超过 300MB 限制", "error", code=413)


@app.errorhandler(BadRequest)
def _on_bad_request(exc):  # noqa: ANN001
    return fail("请求不合法：%s" % exc, "error", code=400)


@app.errorhandler(Exception)
def _on_error(exc):  # noqa: ANN001
    traceback.print_exc()
    return fail("服务端错误：%s" % exc, "error", code=500)


def body():
    return request.get_json(silent=True) or {}


# --------------------------------------------------------------------------- #
# 静态页面
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return send_from_directory(paths.WEB_DIR, "index.html")


@app.route("/favicon.ico")
def favicon():
    p = os.path.join(paths.WEB_DIR, "favicon.ico")
    if os.path.isfile(p):
        return send_from_directory(paths.WEB_DIR, "favicon.ico")
    return ("", 204)


@app.route("/<path:filename>")
def web_assets(filename):
    full = os.path.join(paths.WEB_DIR, filename)
    if os.path.isfile(full):
        return send_from_directory(paths.WEB_DIR, filename)
    return fail("文件不存在：%s" % filename, "error", code=404)


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
@app.route("/api/config", methods=["GET"])
def api_config_get():
    cfg = config_store.load()
    flat = schema.flatten(cfg)
    return ok({
        "config": config_store.masked(cfg),
        "flat": {k: (config_store.MASK if k in config_store.SECRET_KEYS else v)
                 for k, v in flat.items()},
        "ui": schema.ui_model(),
        "preset": presets.preset_for(flat.get("target.env", "local")),
        "source": project_source.inspect_source(),
        "platform": presets.platform_summary(),
    })


@app.route("/api/config", methods=["PUT", "POST"])
def api_config_put():
    payload = body()
    incoming = payload.get("config") or payload
    flat = schema.flatten(incoming)
    if not flat:
        return fail("没有收到配置内容")
    current = schema.flatten(config_store.load())
    current.update(flat)          # 支持局部更新
    okflag, errors, warnings = config_store.save(schema.expand(current))
    if not okflag:
        return fail("配置校验未通过", "error", {"errors": errors, "warnings": warnings})
    cfg = config_store.load()
    flat_now = schema.flatten(cfg)
    sync = {}
    try:
        sync = service.start_sync_if_needed(cfg)
    except Exception as exc:  # noqa: BLE001
        sync = {"running": False, "error": str(exc)}
    return ok({
        "config": config_store.masked(cfg),
        "warnings": warnings,
        "preset": presets.preset_for(flat_now.get("target.env", "local")),
        "sync": sync,
    }, "配置已保存" + ("（%d 条提示）" % len(warnings) if warnings else ""))


@app.route("/api/config/validate", methods=["POST"])
def api_config_validate():
    payload = body()
    incoming = payload.get("config") or payload
    flat = schema.flatten(config_store.load())
    flat.update(schema.flatten(incoming))
    okflag, errors, warnings = config_store.validate(dict(flat))
    return ok({"valid": okflag, "errors": errors, "warnings": warnings},
              "校验通过" if okflag else "校验未通过", "ok" if okflag else "error")


@app.route("/api/schema", methods=["GET"])
def api_schema():
    return ok(schema.ui_model())


@app.route("/api/presets", methods=["GET"])
def api_presets():
    env = request.args.get("env") or schema.flatten(config_store.load()).get("target.env", "local")
    preset = presets.preset_for(env)
    cfg = config_store.load()
    flat = schema.flatten(cfg)
    if env != flat.get("target.env"):
        flat = dict(flat, **{"target.env": env})
    return ok({
        "envs": presets.all_presets(),
        "current": preset,
        "artifacts": artifacts_preview(env, flat),
        "deps": presets.deps_for(env),
        "capabilities": presets.caps(env),
        "fields": [
            {"key": f["key"], "label": f.get("label", f["key"]),
             "help": f.get("help", ""), "type": f["type"],
             "options": f.get("options")}
            for f in schema.visible_fields(flat)
        ],
    })


def artifacts_preview(env, flat):
    cfg = schema.expand(flat)
    try:
        names = list(templates_gen.artifacts(cfg).keys())
    except Exception as exc:  # noqa: BLE001
        names = ["（生成失败：%s）" % exc]
    return names


@app.route("/api/templates", methods=["GET"])
def api_templates():
    return ok({"templates": [
        {"id": t["id"], "name": t["name"], "desc": t["desc"],
         "tables": t["manifest"].get("tables", []),
         "routes": t["manifest"].get("routes", []),
         "pages": t["manifest"].get("pages", [])}
        for t in schema.available_templates()
    ]})


@app.route("/api/template/<template_id>/inspector", methods=["GET"])
def api_template_inspector(template_id):
    tpl = schema.find_template(template_id)
    if not tpl:
        return fail("模板不存在：%s" % template_id, "error", code=404)
    return ok({"manifest": tpl["manifest"],
               "files": project_source.inspect_source(tpl["path"])})


# --------------------------------------------------------------------------- #
# 环境检测 / 依赖
# --------------------------------------------------------------------------- #
@app.route("/api/detect", methods=["GET"])
def api_detect():
    cfg = config_store.load()
    report = detect.environment_report(cfg)
    return ok(report, "检测完成", report["overall"])


@app.route("/api/detect/install", methods=["POST"])
def api_detect_install():
    cfg = config_store.load()
    report = detect.environment_report(cfg)
    cmds = [c for c in report["needs_install"] if c]
    if not cmds and not body().get("force"):
        return ok({"commands": [], "report": report}, "没有缺失的必需依赖", "ok")

    def _work(job):
        job.log("待安装：%s" % ("; ".join(cmds) or "requirements.txt"))
        job.set_progress(5, "准备安装")
        if cmds:
            total = len(cmds)
            for idx, c in enumerate(cmds, 1):
                jobs.cancelled(job)
                job.set_progress(int(idx / total * 60), "执行第 %d/%d 条" % (idx, total))
                jobs.run_step(job, runner.split_command(c), cwd=paths.WORKDIR, timeout=1800)
        # 再装项目依赖
        req = os.path.join(paths.SOURCE_DIR, "requirements.txt")
        jobs.cancelled(job)
        job.set_progress(70, "安装项目依赖")
        if os.path.isfile(req):
            res = jobs.run_step(job, [runner.which_python(), "-m", "pip", "install", "-r", req],
                                cwd=paths.SOURCE_DIR, timeout=3600)
        else:
            job.log("源码目录没有 requirements.txt，改为安装面板核心依赖 flask", "warn")
            res = jobs.run_step(job, [runner.which_python(), "-m", "pip", "install", "flask"],
                                cwd=paths.WORKDIR, timeout=1800)
        job.set_progress(95, "复检")
        report2 = detect.environment_report(config_store.load())
        job.log("复检结果：%s" % report2["overall"], "ok" if report2["overall"] == "ok" else "warn")
        for item in report2["items"]:
            if item["level"] != "ok":
                job.log("[%s] %s —— %s" % (item["level"], item["name"], item["detail"]),
                        "warn" if item["level"] == "warn" else "error")
        if not res.ok and not os.path.isfile(req):
            job.finish("failed", "error", "依赖安装失败，请查看日志")
        else:
            job.finish("done", "ok", "依赖安装流程结束，请重新点「检测环境」确认")

    job = jobs.manager.start("install", "安装依赖", _work)
    return ok({"job": job.snapshot()}, "已开始安装依赖")


# --------------------------------------------------------------------------- #
# 项目源
# --------------------------------------------------------------------------- #
@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if f is None:
        return fail("没有收到文件（字段名应为 file）")
    name = (f.filename or "").strip()
    if not name.lower().endswith(".zip"):
        return fail("只支持 .zip 压缩包，当前文件：%s" % name)
    paths.ensure_runtime_dirs()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    saved = os.path.join(paths.UPLOAD_DIR, "%s-%s" % (stamp, os.path.basename(name)))
    f.save(saved)
    size = os.path.getsize(saved)

    payload = body()
    use_template = request.form.get("template") or ""
    target = None
    if request.form.get("subdir"):
        flat = schema.flatten(config_store.load())
        flat["project.subdir"] = request.form.get("subdir")
        target = commands_mod._source_dir(flat)

    def _work(job):
        job.set_progress(10, "校验压缩包")
        job.log("已接收：%s（%.2f MB）" % (os.path.basename(saved), size / 1048576.0))
        jobs.cancelled(job)
        job.set_progress(35, "解压中")
        info = project_source.extract_zip(saved, target)
        job.log(info["log"], "ok")
        if info.get("stripped_root"):
            job.log("已自动剥离顶层目录：%s" % info["stripped_root"], "info")
        jobs.cancelled(job)
        if use_template:
            job.set_progress(70, "展开内置模板")
            tinfo = project_source.copy_template(use_template, target)
            job.log(tinfo["log"], "ok")
        job.set_progress(90, "写入配置产物")
        try:
            templates_gen.write_artifacts(config_store.load(), target)
            job.log("已生成 deploy/ 配置", "ok")
        except Exception as exc:  # noqa: BLE001
            job.log("生成配置失败：%s" % exc, "warn")
        job.set_progress(100, "完成")
        job.log("源码目录：%s" % (target or paths.SOURCE_DIR), "ok")

    job = jobs.manager.start("upload", "解压上传的项目", _work)
    return ok({"job": job.snapshot(), "saved": saved, "size": size},
              "已接收压缩包，正在解压")


@app.route("/api/github/test", methods=["POST"])
def api_github_test():
    payload = body()
    cfg = config_store.load()
    flat = schema.flatten(cfg)
    url = payload.get("url") or flat.get("project.github_url") or ""
    branch = payload.get("branch") or flat.get("project.branch") or "main"
    token = payload.get("token") or config_store.secret_value("project.token")
    if payload.get("token") == config_store.MASK:
        token = config_store.secret_value("project.token")
    if not url:
        return fail("请先填写 GitHub 仓库地址")
    try:
        result = project_source.test_connection(url, branch, token or "")
    except project_source.SourceError as exc:
        return fail(str(exc), "error")
    except Exception as exc:  # noqa: BLE001
        return fail("测试连接失败：%s" % exc, "error")
    if not result["ok"]:
        return fail(result["message"], result.get("level", "error"))
    return ok(result.get("data", {}), result["message"], result.get("level", "ok"))


@app.route("/api/github/pull", methods=["POST"])
def api_github_pull():
    cfg = config_store.load()
    flat = schema.flatten(cfg)
    payload = body()
    url = payload.get("url") or flat.get("project.github_url") or ""
    branch = payload.get("branch") or flat.get("project.branch") or "main"
    subdir = payload.get("subdir", flat.get("project.subdir") or "")
    if payload.get("token") and payload["token"] != config_store.MASK:
        token = payload["token"]
    else:
        token = config_store.secret_value("project.token")

    def _work(job):
        job.log("仓库：%s 分支：%s" % (url, branch))
        job.set_progress(15, "下载代码归档")
        jobs.cancelled(job)
        info = project_source.fetch_repo(url, branch, token or "", paths.SOURCE_DIR, subdir)
        job.set_progress(80, "写入配置产物")
        job.log(info["log"], "ok")
        try:
            templates_gen.write_artifacts(cfg, paths.SOURCE_DIR)
            job.log("已生成 deploy/ 配置", "ok")
        except Exception as exc:  # noqa: BLE001
            job.log("生成配置失败：%s" % exc, "warn")
        job.set_progress(100, "完成")

    job = jobs.manager.start("pull", "拉取 GitHub 代码", _work)
    return ok({"job": job.snapshot()}, "已开始拉取代码")


@app.route("/api/github/sync", methods=["GET", "POST"])
def api_github_sync():
    cfg = config_store.load()
    if request.method == "POST":
        payload = body()
        action = payload.get("action", "auto")
        flat = schema.flatten(cfg)
        if action == "start":
            state = project_source.scheduler.start(
                payload.get("interval_min") or flat.get("project.sync_interval_min", 30),
                lambda: config_store.load())
            return ok(state, "定时同步已开启")
        if action == "stop":
            return ok(project_source.scheduler.stop(), "定时同步已关闭")
        return ok(service.start_sync_if_needed(cfg), "已按配置同步定时任务状态")
    return ok(project_source.scheduler.status())


# --------------------------------------------------------------------------- #
# 命令预览 / 产物生成
# --------------------------------------------------------------------------- #
@app.route("/api/commands", methods=["GET"])
def api_commands():
    cfg = config_store.load()
    return ok({"commands": commands_mod.list_commands(cfg),
               "source_dir": commands_mod._source_dir(schema.flatten(cfg))})


@app.route("/api/commands/preview", methods=["POST"])
def api_commands_preview():
    """保存高级模式的命令覆盖，并返回覆盖后的命令列表。"""
    payload = body()
    overrides = payload.get("overrides")
    cfg = schema.flatten(config_store.load())
    if isinstance(overrides, dict):
        cfg["advanced.command_overrides"] = {k: v for k, v in overrides.items() if str(v).strip()}
        okflag, errors, _ = config_store.save(schema.expand(cfg))
        if not okflag:
            return fail("命令覆盖保存失败", "error", {"errors": errors})
    cfg = config_store.load()
    return ok({"commands": commands_mod.list_commands(cfg)}, "命令预览已更新")


@app.route("/api/gen/nginx", methods=["GET", "POST"])
def api_gen_nginx():
    cfg = config_store.load()
    if request.method == "POST":
        payload = body()
        flat = schema.flatten(cfg)
        flat.update(schema.flatten(payload.get("config") or {}))
        cfg = schema.expand(flat)
    content = templates_gen.nginx_conf(cfg)
    if request.args.get("download") == "1":
        return Response(content, mimetype="text/plain",
                        headers={"Content-Disposition": "attachment; filename=nginx.conf"})
    return ok({"content": content, "path": "deploy/nginx.conf"})


@app.route("/api/gen/artifacts", methods=["GET", "POST"])
def api_gen_artifacts():
    cfg = config_store.load()
    if request.method == "POST":
        if bool(body().get("write")):
            cfg = config_store.load()
            src_files, build_files = templates_gen.write_all(
                cfg, commands_mod._source_dir(schema.flatten(cfg)))
            return ok({"written": len(src_files),
                       "files": [paths.rel(p, paths.WORKDIR) for p in src_files],
                       "build": [paths.rel(p, paths.WORKDIR) for p in build_files]},
                      "已生成并写入 deploy/ 目录")
    arts = templates_gen.artifacts(cfg)
    return ok({
        "files": [{"name": k, "size": len(v.encode("utf-8")),
                   "preview": v[:4000], "truncated": len(v) > 4000}
                  for k, v in arts.items()],
        "count": len(arts),
    })


@app.route("/api/gen/artifact", methods=["GET"])
def api_gen_artifact():
    name = request.args.get("name") or ""
    if not name or ".." in name:
        return fail("文件名不合法")
    cfg = config_store.load()
    arts = templates_gen.artifacts(cfg)
    if name not in arts:
        return fail("未生成该文件：%s" % name, "error", code=404)
    content = arts[name]
    return Response(content, mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition":
                             "attachment; filename=%s" % os.path.basename(name)})


# --------------------------------------------------------------------------- #
# 数据库
# --------------------------------------------------------------------------- #
@app.route("/api/db/init", methods=["POST"])
def api_db_init():
    cfg = config_store.load()
    flat = schema.flatten(cfg)

    def _work(job):
        job.set_progress(20, "读取建表脚本")
        if flat.get("database.engine") == "mysql":
            job.log("MySQL 模式：面板生成建库脚本，请用 mysql 客户端导入", "warn")
            job.log(db_mod.mysql_apply_hint(cfg), "info")
            path = os.path.join(paths.SOURCE_DIR, "deploy", "mysql.sql")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(db_mod.mysql_script(cfg))
            job.log("已写出：%s" % path, "ok")
            job.set_progress(100, "完成")
            return
        job.set_progress(50, "建表中")
        okflag, msgs = db_mod.init_sqlite(cfg)
        for m in msgs:
            job.log(m, "ok" if okflag else "error")
        if not okflag:
            job.finish("failed", "error", "数据库初始化失败")
            return
        job.set_progress(100, "完成")

    job = jobs.manager.start("db", "初始化数据库", _work)
    return ok({"job": job.snapshot()}, "已开始初始化数据库")


@app.route("/api/db/overview", methods=["GET"])
def api_db_overview():
    cfg = config_store.load()
    data = db_mod.table_overview(cfg)
    data["hint"] = db_mod.mysql_apply_hint(cfg) if data.get("engine") == "mysql" else ""
    return ok(data)


# --------------------------------------------------------------------------- #
# 部署 / 服务 / 日志
# --------------------------------------------------------------------------- #
@app.route("/api/deploy", methods=["POST"])
def api_deploy():
    payload = body()
    cfg = config_store.load()

    def _work(job):
        flat = schema.flatten(cfg)
        env = flat.get("target.env", "local")
        source_dir = commands_mod._source_dir(flat)
        preset = presets.get_env(env)

        job.set_progress(5, "检查源码目录")
        empty = (not os.path.isdir(source_dir)) or (not os.listdir(source_dir))
        if empty and flat.get("project.template"):
            job.log("源码目录为空，先展开内置模板：%s" % flat.get("project.template"), "info")
            try:
                tinfo = project_source.copy_template(flat.get("project.template"), source_dir)
                job.log(tinfo["log"], "ok")
                empty = False
            except Exception as exc:  # noqa: BLE001
                job.log("展开内置模板失败：%s" % exc, "error")
        if empty:
            job.log("源码目录为空：%s" % source_dir, "error")
            job.log("请先在「1. 项目源」上传 zip、拉取 GitHub 或选择内置模板", "warn")
            job.finish("failed", "error", "没有可部署的代码")
            return
        job.log("源码目录：%s" % source_dir, "ok")
        job.log("目标环境：%s" % preset["name"], "info")

        job.set_progress(15, "生成部署产物")
        try:
            written = templates_gen.write_artifacts(cfg, source_dir)
            job.log("已写入 %d 个配置文件到 deploy/" % len(written), "ok")
        except Exception as exc:  # noqa: BLE001
            job.log("生成产物失败：%s" % exc, "error")
            job.finish("failed", "error", "生成部署产物失败")
            return

        job.set_progress(30, "写 .env")
        with open(os.path.join(source_dir, ".env"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(config_store.to_env(flat))
        job.log("已写 .env", "ok")

        job.set_progress(45, "环境检测")
        report = detect.environment_report(cfg)
        for item in report["items"]:
            job.log("[%s] %s：%s" % (item["level"], item["name"], item["detail"]),
                    "ok" if item["level"] == "ok" else ("warn" if item["level"] == "warn" else "error"))

        job.set_progress(60, "安装依赖")
        req = os.path.join(source_dir, "requirements.txt")
        if os.path.isfile(req):
            py = runner.which_python()
            res = jobs.run_step(job, [py, "-m", "pip", "install", "-r", req],
                                cwd=source_dir, timeout=3600,
                                progress=72, progress_text="pip 安装中")
            if not res.ok:
                job.log("依赖安装未成功，继续尝试启动（可能依赖已在环境中）", "warn")
        else:
            job.log("未找到 requirements.txt，跳过 pip 安装", "warn")

        if flat.get("database.engine") == "sqlite":
            job.set_progress(80, "初始化数据库")
            okflag, msgs = db_mod.init_sqlite(cfg)
            for m in msgs:
                job.log(m, "ok" if okflag else "warn")

        job.set_progress(88, "启动服务")
        jobs.cancelled(job)
        if presets.supports(env, "static_only"):
            job.log("Vercel 环境不运行后端；已完成静态导出准备", "warn")
            job.log("请把 static/ 目录交给 Vercel，接口地址指向另一个后端域名", "info")
            job.set_progress(100, "完成")
            return

        service._do_start(job, cfg)   # 内部会 finish 任务

    job = jobs.manager.start("deploy", "一键部署", _work)
    return ok({"job": job.snapshot()}, "部署已开始，请在日志窗口查看进度")


@app.route("/api/service/<action>", methods=["POST"])
def api_service(action):
    cfg = config_store.load()
    if action == "start":
        job = service.start_job(cfg)
    elif action == "stop":
        job = service.stop_job(cfg)
    elif action == "restart":
        job = service.restart_job(cfg)
    elif action == "status":
        return ok(service.status(cfg), service.status(cfg)["message"], service.status(cfg)["level"])
    else:
        return fail("不支持的操作：%s" % action, "error", code=404)
    return ok({"job": job.snapshot()}, "已提交：%s" % action)


@app.route("/api/service/status", methods=["GET"])
def api_service_status():
    st = service.status(config_store.load())
    return ok(st, st["message"], st["level"])


@app.route("/api/logs", methods=["GET"])
def api_logs():
    cfg = config_store.load()
    lines = int(request.args.get("lines", 300))
    level = request.args.get("level", "all")
    return ok(logs_mod.tail(cfg, lines=lines, level=level))


@app.route("/api/logs/follow")
def api_logs_follow():
    cfg = config_store.load()
    return Response(logs_mod.follow(cfg), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                             "Connection": "keep-alive"})


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    return ok(logs_mod.clear(config_store.load()), "日志已清空")


@app.route("/api/logs/files", methods=["GET"])
def api_logs_files():
    return ok({"files": logs_mod.list_logs(config_store.load())})


# --------------------------------------------------------------------------- #
# 任务
# --------------------------------------------------------------------------- #
@app.route("/api/jobs", methods=["GET"])
def api_jobs():
    return ok({"jobs": jobs.manager.list(limit=int(request.args.get("limit", 20)))})


@app.route("/api/jobs/<job_id>", methods=["GET"])
def api_job(job_id):
    job = jobs.manager.get(job_id)
    if not job:
        return fail("任务不存在", "error", code=404)
    since = float(request.args.get("since", 0) or 0)
    return ok({"job": job.snapshot(since=since)})


@app.route("/api/jobs/<job_id>/stream")
def api_job_stream(job_id):
    return Response(jobs.manager.sse_stream(job_id), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                             "Connection": "keep-alive"})


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def api_job_cancel(job_id):
    okflag, message = jobs.manager.cancel(job_id)
    return ok({"cancelled": okflag}, message, "ok" if okflag else "warn")


# --------------------------------------------------------------------------- #
# 备份 / 导出
# --------------------------------------------------------------------------- #
@app.route("/api/backup", methods=["GET", "POST"])
def api_backup():
    cfg = config_store.load()
    if request.method == "GET":
        return ok({"backups": backup_mod.list_backups()})

    note = (body() or {}).get("note", "")

    def _work(job):
        job.set_progress(10, "收集项目文件")
        job.log("开始打包：项目源码 + 数据库 + 配置 + 生成产物")
        jobs.cancelled(job)
        job.set_progress(45, "压缩中")
        info = backup_mod.create_backup(cfg, note=note)
        job.log(info["message"], "ok" if info["ok"] else "error")
        job.log("备份路径：%s" % info.get("path"), "info")
        job.log("数据库是否包含：%s" % ("是" if info.get("db_included") else "否"), "info")
        job.set_progress(100, "完成")
        job.result = {"name": info.get("name"), "size": info.get("size")}
        if not info["ok"]:
            job.finish("failed", "error", info.get("message", "备份失败"))

    job = jobs.manager.start("backup", "一键备份", _work)
    return ok({"job": job.snapshot()}, "已开始备份")


@app.route("/api/export", methods=["GET", "POST"])
def api_export():
    cfg = config_store.load()
    if request.method == "GET":
        return ok(backup_mod.export_preview(cfg))
    payload = body()
    kind = payload.get("kind") or "deploy"
    result = backup_mod.export(kind, cfg)
    if not result.get("ok"):
        return fail(result.get("message", "导出失败"))
    return ok(result, result.get("message", "导出完成"))


@app.route("/api/download", methods=["GET"])
def api_download():
    kind = request.args.get("kind") or ""
    name = request.args.get("name") or ""
    roots = {"backup": paths.BACKUP_DIR, "export": paths.EXPORT_DIR}
    root = roots.get(kind)
    if not root:
        return fail("下载类型不支持：%s（可用 backup / export）" % kind)
    if not name:
        return fail("请提供 name 参数")
    safe = os.path.basename(name)
    full = os.path.join(root, safe)
    if not os.path.isfile(full):
        return fail("文件不存在：%s" % safe, "error", code=404)
    return send_file(full, as_attachment=True, download_name=safe)


# --------------------------------------------------------------------------- #
# 健康检查 / 信息
# --------------------------------------------------------------------------- #
@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "app": "deploy-panel",
                    "time": time.strftime("%Y-%m-%d %H:%M:%S")})


@app.route("/api/info", methods=["GET"])
def api_info():
    return ok({
        "panel": {"name": "打工避雷平台 · 可视化部署面板", "version": "1.0.0",
                  "workdir": paths.WORKDIR, "platform": presets.platform_summary(),
                  "python": sys.version.split()[0], "pid": os.getpid()},
        "service": service.status(config_store.load()),
        "source": project_source.inspect_source(),
        "sync": project_source.scheduler.status(),
    })


# --------------------------------------------------------------------------- #
# 启动
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(description="打工避雷平台 · 可视化部署面板")
    p.add_argument("--host", default=paths.DEFAULT_PANEL_HOST, help="面板监听地址")
    p.add_argument("--port", type=int, default=paths.DEFAULT_PANEL_PORT, help="面板监听端口")
    p.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    p.add_argument("--debug", action="store_true", help="开启 Flask 调试模式")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    paths.ensure_runtime_dirs()
    cfg = config_store.load()
    if not os.path.isfile(paths.CONFIG_FILE):
        config_store.save(cfg)
    try:
        service.start_sync_if_needed(cfg)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[warn] 定时同步启动失败：%s\n" % exc)

    url = "http://%s:%s" % (args.host if args.host != "0.0.0.0" else "127.0.0.1", args.port)
    print("=" * 66)
    print(" 打工避雷平台 · 可视化部署面板")
    print(" 面板地址：%s" % url)
    print(" 工作目录：%s" % paths.WORKDIR)
    print(" 按 Ctrl+C 停止面板")
    print("=" * 66)

    if not args.no_browser and os.environ.get("DEPLOY_PANEL_NO_BROWSER") != "1":
        try:
            import threading
            import webbrowser
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        except Exception:  # noqa: BLE001
            pass

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True,
            use_reloader=False)


if __name__ == "__main__":
    main()
