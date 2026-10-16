# -*- coding: utf-8 -*-
"""部署面板自测（离线可跑，不依赖网络与外部服务器）。

运行：
    python tools/deploy_panel/tests/smoke_test.py

覆盖：配置读写与校验 / 预设 / 命令生成 / 产物生成 / 上传解压安全校验 /
模板完整性 / 服务状态机 / 备份包内容 / Flask 接口（装了 Flask 时自动加测）。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.dirname(HERE)
sys.path.insert(0, PANEL)

def _pick_tmp_root():
    """选一个真正可写的临时根目录：系统临时目录 -> 面板工作区内的 testtmp。"""
    candidates = [os.path.join(PANEL, ".workdir", "testtmp"),
                  os.environ.get("TEMP"), os.environ.get("TMP"), tempfile.gettempdir()]
    for c in candidates:
        if not c:
            continue
        try:
            os.makedirs(c, exist_ok=True)
            probe = os.path.join(c, "write-probe.tmp")
            with open(probe, "wb") as fh:
                fh.write(b"x")
            os.remove(probe)
            return os.path.abspath(c)
        except OSError:
            continue
    raise SystemExit("找不到可写的临时目录，请手动设置 TEMP 环境变量")


# 用临时工作区跑测试，避免污染真实 .workdir
tempfile.tempdir = _pick_tmp_root()
TMP_WORK = tempfile.mkdtemp(prefix="deploy-panel-test-")
os.environ["DEPLOY_PANEL_WORKDIR"] = TMP_WORK

from core import backup as backup_mod        # noqa: E402
from core import commands as commands_mod    # noqa: E402
from core import config_schema as schema     # noqa: E402
from core import config_store                # noqa: E402
from core import db as db_mod                # noqa: E402
from core import detect                      # noqa: E402
from core import jobs                        # noqa: E402
from core import logs as logs_mod            # noqa: E402
from core import paths                       # noqa: E402
from core import presets                     # noqa: E402
from core import project_source              # noqa: E402
from core import runner                      # noqa: E402
from core import service                     # noqa: E402
from core import templates_gen               # noqa: E402

PASSED = []
FAILED = []


def case(name):
    def deco(fn):
        try:
            fn()
            PASSED.append(name)
            print("  [PASS] %s" % name)
        except Exception as exc:  # noqa: BLE001
            FAILED.append((name, exc))
            print("  [FAIL] %s -> %s" % (name, exc))
            traceback.print_exc()
        return fn
    return deco


def eq(a, b, msg=""):
    if a != b:
        raise AssertionError("%s期望 %r，实际 %r" % (msg + "：" if msg else "", b, a))


def truthy(v, msg=""):
    if not v:
        raise AssertionError(msg or "期望为真")


def section(title):
    print("\n== %s ==" % title)


def reset_source():
    """清空工作区源码目录并返回它，保证每个用例从干净状态开始。"""
    target = paths.SOURCE_DIR
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
    os.makedirs(target, exist_ok=True)
    return target


def template_snapshot():
    """记录内置模板目录的当前文件清单，用于结尾检查模板未被测试污染。"""
    tpl = schema.find_template("打工避雷平台")
    if not tpl:
        return set()
    out = set()
    for dirpath, dirs, files in os.walk(tpl["path"]):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            out.add(os.path.relpath(os.path.join(dirpath, name), tpl["path"]))
    return out


# 记录内置模板目录的基线（结尾会对比，确保测试没污染模板）
TEMPLATE_BASELINE = template_snapshot()


# --------------------------------------------------------------------------- #
section("配置层")
# --------------------------------------------------------------------------- #
@case("默认配置包含全部字段且可展开")
def _():
    cfg = schema.default_config()
    eq(len(cfg), len(schema.FIELDS), "字段数量")
    nested = schema.expand(cfg)
    truthy("project" in nested and "target" in nested and "nginx" in nested)


@case("配置保存与读取（含密钥打码）")
def _():
    paths.ensure_runtime_dirs()
    cfg = schema.default_config()
    cfg["network.domain"] = "example.com"
    cfg["project.token"] = "ghp_secret_value"
    okflag, errors, _ = config_store.save(cfg)
    truthy(okflag, "保存失败：%s" % errors)
    loaded = config_store.load()
    eq(schema.flatten(loaded)["network.domain"], "example.com")
    eq(config_store.secret_value("project.token"), "ghp_secret_value")
    masked = config_store.masked(loaded)
    eq(masked["project"]["token"], config_store.MASK, "密钥应被打码")


@case("保存掩码值不会覆盖真实密钥")
def _():
    cfg = schema.flatten(config_store.load())
    cfg["project.token"] = config_store.MASK
    config_store.save(schema.expand(cfg))
    eq(config_store.secret_value("project.token"), "ghp_secret_value", "掩码不应写回")


@case("配置校验：捕获非法端口与非法域名")
def _():
    flat = schema.flatten(config_store.load())
    flat["target.app_port"] = 99999
    flat["network.domain"] = "bad domain!"
    okflag, errors, _ = config_store.validate(dict(flat))
    truthy(not okflag, "非法配置应校验失败")
    truthy(any("端口" in e for e in errors), "应报端口错误")
    truthy(any("域名" in e for e in errors), "应报域名错误")


@case("配置校验：GitHub 模式必须填仓库地址与分支")
def _():
    flat = schema.flatten(config_store.load())
    flat["project.source_mode"] = "github"
    flat["project.github_url"] = "https://example.com/notgithub"
    flat["project.branch"] = ""
    okflag, errors, _ = config_store.validate(dict(flat))
    truthy(not okflag)
    truthy(any("GitHub" in e for e in errors))


@case("白名单归一化（去协议、去路径、去重）")
def _():
    flat = schema.flatten(config_store.load())
    flat["allowlist.video_domains"] = ["https://www.bilibili.com/video/x", "BILIBILI.COM", "bad_domain!"]
    okflag, errors, _ = config_store.validate(flat)      # validate 会把归一化结果写回传入的字典
    truthy(not okflag, "非法域名应报错")
    eq(flat["allowlist.video_domains"], ["bilibili.com"], "归一化结果")


@case("生成 .env 内容覆盖开关与数据库")
def _():
    flat = schema.flatten(config_store.load())
    flat["database.engine"] = "mysql"
    flat["security.captcha"] = True
    text = config_store.to_env(flat)
    truthy("DB_ENGINE=mysql" in text)
    truthy("MYSQL_HOST=" in text)
    truthy("ENABLE_CAPTCHA=true" in text)
    truthy("VIDEO_ALLOWLIST=" in text)


@case("字段可见性随环境与开关变化")
def _():
    flat = schema.flatten(config_store.load())
    flat["target.env"] = "vercel"
    flat["database.engine"] = "sqlite"
    vis = {f["key"] for f in schema.visible_fields(flat)}
    truthy("network.listen_port" not in vis, "Vercel 不应显示对外端口")
    truthy("nginx.ssl" not in vis, "Vercel 不应显示 Nginx")
    flat["target.env"] = "ubuntu"
    flat["nginx.ssl"] = True
    vis2 = {f["key"] for f in schema.visible_fields(flat)}
    truthy("nginx.ssl_cert" in vis2, "开启 HTTPS 后应显示证书字段")
    flat["security.captcha"] = False
    vis3 = {f["key"] for f in schema.visible_fields(flat)}
    truthy("security.captcha_provider" not in vis3, "关闭验证码后不应显示验证方式")


# --------------------------------------------------------------------------- #
section("预设与命令")
# --------------------------------------------------------------------------- #
@case("5 个部署环境预设完整")
def _():
    ids = [e[0] for e in presets.env_options()]
    eq(ids, ["local", "ubuntu", "pythonanywhere", "render", "vercel"])
    for e in presets.all_presets():
        truthy(e.get("name") and e.get("summary") and e.get("caps") is not None, "预设字段")
        truthy(presets.deps_for(e["id"])["required"] is not None)


@case("能力矩阵与产物清单随环境变化")
def _():
    truthy(presets.supports("ubuntu", "nginx"))
    truthy(not presets.supports("vercel", "nginx"))
    truthy(presets.supports("vercel", "static_only"))
    truthy("nginx" in presets.artifacts_for("ubuntu"))
    truthy("render_yaml" in presets.artifacts_for("render"))


@case("命令生成：本地与 Ubuntu 的启动方式不同")
def _():
    local = schema.flatten(config_store.load())
    local["target.env"] = "local"
    cmds = commands_mod.build_all(schema.expand(local))
    truthy("local" == local["target.env"])
    truthy(any("app.py" in c.display() for c in cmds.values()), "本地应直接跑 app.py")

    ubuntu = dict(local, **{"target.env": "ubuntu"})
    cmds2 = commands_mod.build_all(schema.expand(ubuntu))
    truthy(any("systemctl" in c.display() for c in cmds2.values()), "Ubuntu 应出现 systemctl")


@case("高级模式命令覆盖生效")
def _():
    flat = schema.flatten(config_store.load())
    flat["advanced.command_overrides"] = {"check_python": "echo CUSTOM_PY_CHECK"}
    cmds = commands_mod.build_all(schema.expand(flat))
    truthy("CUSTOM_PY_CHECK" in cmds["check_python"].display(), "覆盖命令应生效")
    flat["advanced.command_overrides"] = {}


@case("命令与日志脱敏")
def _():
    text = runner.mask("git clone https://user:secretpw@github.com/a/b.git --token=abc123")
    truthy("secretpw" not in text, "URL 密码应打码")
    truthy("abc123" not in text, "token 应打码")
    truthy("********" in text)


# --------------------------------------------------------------------------- #
section("部署产物生成")
# --------------------------------------------------------------------------- #
@case("本地环境生成 nginx 参考 + 运行脚本")
def _():
    flat = schema.flatten(config_store.load())
    flat["target.env"] = "local"
    arts = templates_gen.artifacts(schema.expand(flat))
    truthy("deploy/nginx.conf" in arts)
    truthy(".env.example" in " ".join(arts.keys()))
    truthy(any(k.startswith("deploy/run_local") for k in arts), "应有本地运行脚本")


@case("Ubuntu 环境生成 nginx/systemd/gunicorn/deploy.sh")
def _():
    flat = schema.flatten(config_store.load())
    flat["target.env"] = "ubuntu"
    flat["nginx.enable"] = True
    flat["network.domain"] = "bilei.example.com"
    flat["target.app_port"] = 5000
    arts = templates_gen.artifacts(schema.expand(flat))
    keys = " ".join(arts.keys())
    for need in ("deploy/nginx.conf", "deploy/gunicorn.conf.py", "deploy/deploy.sh"):
        truthy(need in keys, "缺少 %s" % need)
    truthy(any(k.endswith(".service") for k in arts), "缺少 systemd unit")
    nginx = arts["deploy/nginx.conf"]
    truthy("proxy_pass         http://127.0.0.1:5000;" in nginx, "反代地址应使用应用端口")
    truthy("server_name bilei.example.com;" in nginx, "server_name 应使用域名")
    truthy("proxy_set_header   X-Real-IP" in nginx, "应带真实 IP 头")


@case("Nginx 端口与 HTTPS 配置正确")
def _():
    flat = schema.flatten(config_store.load())
    flat["target.env"] = "ubuntu"
    flat["network.listen_port"] = 8080
    flat["nginx.ssl"] = True
    flat["nginx.ssl_cert"] = "/etc/ssl/certs/a.pem"
    flat["nginx.ssl_key"] = "/etc/ssl/private/a.key"
    content = templates_gen.nginx_conf(schema.expand(flat))
    truthy("listen      8080;" in content, "应使用对外端口")
    truthy("return 301 https://$host$request_uri;" in content, "应跳转 HTTPS")
    truthy("ssl_certificate     /etc/ssl/certs/a.pem;" in content)


@case("Render / Vercel / PythonAnywhere 生成对应配置")
def _():
    base = schema.flatten(config_store.load())
    render_arts = templates_gen.artifacts(schema.expand(dict(base, **{"target.env": "render"})))
    truthy("deploy/render.yaml" in render_arts)
    truthy("startCommand" in render_arts["deploy/render.yaml"])
    vercel_arts = templates_gen.artifacts(schema.expand(dict(base, **{"target.env": "vercel"})))
    truthy("deploy/vercel.json" in vercel_arts)
    json.loads(vercel_arts["deploy/vercel.json"])          # 必须是合法 JSON
    pa_arts = templates_gen.artifacts(schema.expand(dict(base, **{"target.env": "pythonanywhere"})))
    truthy("deploy/pythonanywhere_wsgi.py" in pa_arts)
    truthy("application" in pa_arts["deploy/pythonanywhere_wsgi.py"])


@case("MySQL 模式生成 mysql.sql 且语句可执行")
def _():
    flat = schema.flatten(config_store.load())
    flat["database.engine"] = "mysql"
    flat["database.mysql_dbname"] = "dgbilei_test"
    arts = templates_gen.artifacts(schema.expand(flat))
    truthy("deploy/mysql.sql" in arts)
    sql = arts["deploy/mysql.sql"]
    truthy("CREATE DATABASE IF NOT EXISTS `dgbilei_test`" in sql)
    truthy("AUTO_INCREMENT" in sql, "应把 SQLite 自增语法转成 MySQL")
    truthy("AUTOINCREMENT" not in sql, "不应残留 SQLite 语法")


@case("产物可落盘且路径限定在工作区")
def _():
    files = templates_gen.write_artifacts(config_store.load(), paths.BUILD_DIR)
    truthy(len(files) >= 3)
    for f in files:
        truthy(os.path.abspath(f).startswith(os.path.abspath(TMP_WORK)))


# --------------------------------------------------------------------------- #
section("上传与解压安全")
# --------------------------------------------------------------------------- #
def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    buf.seek(0)
    return buf


_zip_seq = [0]


def save_zip(buf, name="case"):
    """把内存 zip 写到临时工作区里的固定目录，避免依赖系统临时目录。"""
    _zip_seq[0] += 1
    d = os.path.join(TMP_WORK, "zips")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "%02d-%s.zip" % (_zip_seq[0], name))
    with open(path, "wb") as fh:
        fh.write(buf.read())
    return path


@case("正常 zip 解压并自动剥离顶层目录")
def _():
    buf = make_zip({"proj/app.py": "print(1)", "proj/requirements.txt": "flask\n",
                    "proj/templates/index.html": "<h1>hi</h1>"})
    tmp = save_zip(buf, "normal")
    target = os.path.join(TMP_WORK, "src_normal")
    info = project_source.extract_zip(tmp, target)
    truthy(info["files"] >= 3, "应解压出文件")
    truthy(os.path.isfile(os.path.join(target, "app.py")), "顶层目录应被剥离")
    eq(info["stripped_root"], "proj")


@case("拒绝路径穿越条目")
def _():
    buf = make_zip({"../../evil.py": "x"})
    tmp = save_zip(buf, "traversal")
    try:
        project_source.extract_zip(tmp, os.path.join(TMP_WORK, "src_evil"))
    except project_source.SourceError as exc:
        truthy("越" in str(exc) or "穿越" in str(exc), "错误信息应指明穿越")
        return
    raise AssertionError("路径穿越应被拒绝")


@case("拒绝绝对路径条目")
def _():
    buf = make_zip({"/etc/passwd": "x"})
    tmp = save_zip(buf, "absolute")
    try:
        project_source.extract_zip(tmp, os.path.join(TMP_WORK, "src_abs"))
    except project_source.SourceError:
        return
    raise AssertionError("绝对路径应被拒绝")


@case("拒绝非 zip 文件")
def _():
    tmp = os.path.join(TMP_WORK, "not-a-zip.zip")
    with open(tmp, "wb") as fh:
        fh.write(b"this is not a zip")
    try:
        project_source.extract_zip(tmp, os.path.join(TMP_WORK, "src_bad"))
    except project_source.SourceError:
        return
    raise AssertionError("非 zip 应被拒绝")


@case("GitHub 地址解析与校验")
def _():
    owner, repo = project_source.parse_github_url("https://github.com/foo/bar.git")
    eq(owner, "foo"); eq(repo, "bar")
    owner2, repo2 = project_source.parse_github_url("https://github.com/foo/bar")
    eq(repo2, "bar")
    try:
        project_source.parse_github_url("https://gitlab.com/foo/bar")
    except project_source.SourceError:
        return
    raise AssertionError("非 GitHub 地址应被拒绝")


@case("safe_join 阻止目录逃逸")
def _():
    base = os.path.join(TMP_WORK, "base")
    os.makedirs(base, exist_ok=True)
    eq(paths.safe_join(base, "a", "b"), os.path.join(base, "a", "b"))
    try:
        paths.safe_join(base, "..", "outside")
    except ValueError:
        return
    raise AssertionError("应阻止 .. 逃逸")


# --------------------------------------------------------------------------- #
section("内置模板")
# --------------------------------------------------------------------------- #
@case("内置「打工避雷平台」模板存在且清单完整")
def _():
    tpl = schema.find_template("打工避雷平台")
    truthy(tpl, "应能找到内置模板")
    m = tpl["manifest"]
    truthy(len(m.get("tables", [])) >= 5, "至少 5 张表")
    truthy(len(m.get("routes", [])) >= 8, "至少 8 个接口")
    truthy(len(m.get("pages", [])) >= 2, "至少 2 个页面")
    for f in ("app.py", "config.py", "models.py", "safety.py", "manage.py",
              "schema.sql", "seeds.sql", "requirements.txt"):
        truthy(os.path.isfile(os.path.join(tpl["path"], f)), "缺少文件 %s" % f)
    for d in ("routes", "templates", "static", "deploy"):
        truthy(os.path.isdir(os.path.join(tpl["path"], d)), "缺少目录 %s" % d)


@case("模板展开到源码目录后可识别入口")
def _():
    target = reset_source()
    info = project_source.copy_template("打工避雷平台", target)
    truthy(info["files"] > 8, "应复制出多个文件")
    src = project_source.inspect_source(target)
    truthy(src["has_app"], "应有 app.py")
    truthy(src["has_requirements"], "应有 requirements.txt")
    truthy(not os.path.exists(os.path.join(target, "manifest.json")), "manifest 不应复制到项目里")


@case("模板 SQLite 建表 + 写入示例数据")
def _():
    target = reset_source()
    project_source.copy_template("打工避雷平台", target)
    flat = schema.flatten(config_store.load())
    flat["project.subdir"] = ""
    flat["database.engine"] = "sqlite"
    flat["database.sqlite_path"] = "data/app.db"
    okflag, msgs = db_mod.init_sqlite(schema.expand(flat))
    truthy(okflag, "建表失败：%s" % msgs)
    overview = db_mod.table_overview(schema.expand(flat))
    names = [t["name"] for t in overview["tables"]]
    for need in ("company", "report", "review_log", "rate_limit", "video_allowlist"):
        truthy(need in names, "缺少表 %s" % need)
    report_rows = [t for t in overview["tables"] if t["name"] == "report"][0]
    truthy(report_rows["rows"] >= 3, "示例数据应写入（实际 %d 行）" % report_rows["rows"])


@case("模板白名单校验逻辑（import safety）")
def _():
    tpl = schema.find_template("打工避雷平台")
    sys.path.insert(0, tpl["path"])
    try:
        for mod in ("config", "models", "safety"):
            if mod in sys.modules:
                del sys.modules[mod]
        os.environ["SQLITE_PATH"] = "data/app.db"
        import safety  # noqa: WPS433
        ok1, _, dom = safety.check_video_url("https://www.bilibili.com/video/BV1xx")
        truthy(ok1, "白名单内域名应通过")
        ok2, msg, _ = safety.check_video_url("https://evil.example.net/video")
        truthy(not ok2, "白名单外域名应拒绝")
        truthy("白名单" in msg)
        action, detail = safety.review_text("加微信 123456 刷单秒结")
        truthy(action == "reject", "高危词应直接拒绝：%s" % detail)
        action2, _ = safety.review_text("公司拖欠工资，试用期不缴社保，已持续两个月")
        truthy(action2 == "pass", "正常内容应通过")
        q, ans = safety.make_captcha()
        truthy(isinstance(ans, int) and "?" in q)
    finally:
        sys.path.remove(tpl["path"])


# --------------------------------------------------------------------------- #
section("备份与导出")
# --------------------------------------------------------------------------- #
@case("备份包含项目、数据库、配置与部署产物")
def _():
    reset_source()
    project_source.copy_template("打工避雷平台", paths.SOURCE_DIR)
    flat = schema.flatten(config_store.load())
    flat["project.subdir"] = ""
    config_store.save(schema.expand(flat))
    db_mod.init_sqlite(schema.expand(flat))     # 确保有 sqlite 文件
    for _ in range(3):
        info = backup_mod.create_backup(config_store.load(), note="自测备份")
        truthy(info["ok"] and os.path.isfile(info["path"]))
        truthy(info["size"] > 1000, "备份包不应为空")
        truthy(info["db_included"], "备份应包含数据库")
        with zipfile.ZipFile(info["path"]) as zf:
            names = zf.namelist()
        truthy(any(n.startswith("project/") for n in names), "应包含项目源码")
        truthy(any(n.startswith("database/") for n in names), "应包含数据库")
        truthy(any(n.startswith("config/") for n in names), "应包含配置")
        truthy(any(n.startswith("deploy/") for n in names), "应包含部署产物")


@case("备份保留份数生效")
def _():
    flat = schema.flatten(config_store.load())
    flat["advanced.keep_backups"] = 2
    config_store.save(schema.expand(flat))
    backup_mod.create_backup(config_store.load(), note="truncate-test")
    lists = backup_mod.list_backups()
    truthy(len(lists) <= 2, "应只保留 2 份，实际 %d" % len(lists))
    flat["advanced.keep_backups"] = 5
    config_store.save(schema.expand(flat))


@case("导出部署脚本 / nginx / 代码包")
def _():
    reset_source()
    project_source.copy_template("打工避雷平台", paths.SOURCE_DIR)
    flat = schema.flatten(config_store.load())
    flat["project.subdir"] = ""
    config_store.save(schema.expand(flat))
    d = backup_mod.export("deploy", config_store.load())
    truthy(d["ok"] and os.path.getsize(d["path"]) > 500, "部署脚本包应非空")
    n = backup_mod.export("nginx", config_store.load())
    truthy(n["ok"] and os.path.getsize(n["path"]) > 100, "nginx 配置应非空")
    c = backup_mod.export("code", config_store.load())
    truthy(c["ok"] and c["files"] > 5, "代码包应有多个文件（实际 %s）" % c.get("files"))
    bad = backup_mod.export("nope", config_store.load())
    truthy(not bad["ok"], "未知类型应失败")


# --------------------------------------------------------------------------- #
section("检测 / 服务 / 任务")
# --------------------------------------------------------------------------- #
@case("环境检测返回结构化结果与总状态")
def _():
    report = detect.environment_report(config_store.load())
    truthy(report["overall"] in ("ok", "warn", "error"))
    ids = [i["id"] for i in report["items"]]
    for need in ("python", "pip", "nginx", "git", "mysql"):
        truthy(need in ids, "缺少检测项 %s" % need)
    for item in report["items"]:
        truthy(item["level"] in ("ok", "warn", "error"), "非法等级：%s" % item["level"])


@case("端口检测能识别占用")
def _():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.listen(1)
    try:
        item = detect.check_port(port)
        eq(item["level"], "error", "已占用端口应报错")
        truthy(item["install_cmd"])
    finally:
        s.close()
    item2 = detect.check_port(port)
    eq(item2["level"], "ok", "释放后应正常")


@case("服务状态机：未启动时为 warn")
def _():
    st = service.status(config_store.load())
    truthy(st["level"] in ("ok", "warn"))
    truthy(st["port"])
    truthy(st["mode"] in ("process", "systemd"))


@case("任务管理器：创建、执行、完成、日志齐全")
def _():
    def _work(job):
        job.log("开始干活", "ok")
        job.set_progress(50, "一半")
        jobs.run_step(job, [runner.which_python(), "-c", "print('hello from job')"])
        job.log("收工", "ok")

    job = jobs.manager.start("test", "自测任务", _work)
    deadline = time.time() + 30
    while job.status in ("pending", "running") and time.time() < deadline:
        time.sleep(0.2)
    eq(job.status, "done", "任务应完成")
    snap = job.snapshot()
    text = "\n".join(l["text"] for l in snap["lines"])
    truthy("hello from job" in text, "应捕获子进程输出")
    truthy("开始干活" in text)
    truthy(snap["progress"]["value"] == 100, "完成时进度应为 100")


@case("任务管理器：同类任务互斥")
def _():
    import threading
    gate = threading.Event()

    def _slow(job):
        job.log("占用中")
        gate.wait(10)

    j1 = jobs.manager.start("deploy", "长任务", _slow)
    time.sleep(0.3)
    j2 = jobs.manager.start("deploy", "并发任务", lambda job: job.log("不该执行"))
    eq(j2.status, "failed", "互斥应拒绝并发任务")
    gate.set()
    deadline = time.time() + 10
    while j1.status in ("pending", "running") and time.time() < deadline:
        time.sleep(0.1)


@case("任务取消会终止子进程")
def _():
    def _long(job):
        job.log("开始长命令")
        jobs.run_step(job, [runner.which_python(), "-c", "import time; time.sleep(30)"], timeout=60)

    job = jobs.manager.start("pull", "可取消任务", _long)
    time.sleep(1.2)
    okflag, msg = jobs.manager.cancel(job.id)
    truthy(okflag, msg)
    deadline = time.time() + 20
    while job.status in ("pending", "running") and time.time() < deadline:
        time.sleep(0.2)
    truthy(job.status in ("cancelled", "failed"), "取消后状态应为 cancelled/failed，实际 %s" % job.status)


@case("日志脱敏与分级")
def _():
    job = jobs.manager.create("log", "日志测试")
    job.log("plain line")
    job.log("Error: something broke")
    job.log("警告：端口被占用")
    job.log("Success: started")
    levels = [l["level"] for l in job.snapshot()["lines"]]
    truthy("error" in levels and "warn" in levels and "ok" in levels, "应分级：%s" % levels)


@case("应用日志读取与清空")
def _():
    path = os.path.join(paths.LOG_DIR, "app.log")
    os.makedirs(paths.LOG_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("line1\nError: boom\nline3\n")
    service.update_state(log_file=path)
    res = logs_mod.tail(config_store.load(), lines=10)
    truthy(res["exists"] and len(res["lines"]) == 3, "应读到 3 行")
    errs = logs_mod.tail(config_store.load(), lines=10, level="error")
    eq(len(errs["lines"]), 1, "应筛出 1 行错误")
    logs_mod.clear(config_store.load())
    eq(logs_mod.tail(config_store.load(), lines=10)["lines_total"], 0)


# --------------------------------------------------------------------------- #
section("Flask 接口")
# --------------------------------------------------------------------------- #
HAVE_FLASK = False
try:
    import flask  # noqa: F401
    HAVE_FLASK = True
except ImportError:
    HAVE_FLASK = False

if not HAVE_FLASK:
    print("  [SKIP] 未安装 Flask，跳过接口测试（装了以后会自动加测）")
else:
    sys.path.insert(0, PANEL)
    import importlib
    app_mod = importlib.import_module("app")
    client = app_mod.app.test_client()

    def get_json(resp):
        return json.loads(resp.data.decode("utf-8"))

    @case("GET /api/config 返回配置、UI 模型与预设")
    def _():
        r = client.get("/api/config")
        eq(r.status_code, 200)
        d = get_json(r)["data"]
        truthy(d["ui"]["groups"], "应有分组模型")
        truthy(d["ui"]["envs"], "应有环境下拉")
        truthy("config" in d and "flat" in d)
        eq(d["flat"]["project.token"] if d["flat"].get("project.token") else config_store.MASK,
           config_store.MASK, "token 应打码")

    @case("PUT /api/config 保存与校验错误返回")
    def _():
        good = {"network.domain": "panel.example.com", "target.app_port": 5001}
        r = client.put("/api/config", json={"config": good})
        eq(r.status_code, 200)
        truthy(get_json(r)["ok"])
        r2 = client.put("/api/config", json={"config": {"target.app_port": 70000}})
        body = get_json(r2)
        truthy(not body["ok"], "非法端口应失败")
        truthy(body["data"]["errors"], "应返回错误列表")

    @case("GET /api/presets 按环境返回能力与产物")
    def _():
        d = get_json(client.get("/api/presets?env=ubuntu"))["data"]
        eq(d["current"]["id"], "ubuntu")
        truthy(d["capabilities"]["nginx"])
        truthy(d["artifacts"])
        d2 = get_json(client.get("/api/presets?env=vercel"))["data"]
        truthy(d2["capabilities"]["static_only"])

    @case("GET /api/templates 与模板巡检")
    def _():
        d = get_json(client.get("/api/templates"))["data"]
        truthy(len(d["templates"]) >= 1)
        tpl_id = d["templates"][0]["id"]
        d2 = get_json(client.get("/api/template/%s/inspector" % tpl_id))["data"]
        truthy(d2["manifest"]["tables"])

    @case("GET /api/detect 返回彩色分级结果")
    def _():
        d = get_json(client.get("/api/detect"))["data"]
        truthy(d["overall"] in ("ok", "warn", "error"))
        truthy(len(d["items"]) >= 5)
        for i in d["items"]:
            truthy(i["level"] in ("ok", "warn", "error"))

    @case("GET /api/commands 返回命令清单与覆盖位")
    def _():
        d = get_json(client.get("/api/commands"))["data"]
        truthy(len(d["commands"]) >= 5)
        truthy("cmd" in d["commands"][0])

    @case("POST /api/commands/preview 保存命令覆盖")
    def _():
        r = client.post("/api/commands/preview", json={"overrides": {"check_git": "echo NO_GIT"}})
        body = get_json(r)
        truthy(body["ok"])
        cmds = {c["id"]: c for c in body["data"]["commands"]}
        truthy("NO_GIT" in cmds["check_git"]["cmd"], "覆盖应体现在命令里")
        client.post("/api/commands/preview", json={"overrides": {}})

    @case("GET /api/gen/nginx 与产物预览")
    def _():
        d = get_json(client.get("/api/gen/nginx"))["data"]
        truthy("proxy_pass" in d["content"] or "参考" in d["content"])
        d2 = get_json(client.get("/api/gen/artifacts"))["data"]
        truthy(d2["count"] >= 3)
        names = [f["name"] for f in d2["files"]]
        truthy("deploy/nginx.conf" in names)

    @case("GET /api/gen/artifact 下载单文件 + 非法名拒绝")
    def _():
        r = client.get("/api/gen/artifact?name=deploy/nginx.conf")
        eq(r.status_code, 200)
        truthy(b"server" in r.data or len(r.data) > 20)
        r2 = client.get("/api/gen/artifact?name=../../etc/passwd")
        truthy(get_json(r2).get("ok") is False)

    @case("POST /api/upload 上传 zip 并解压（任务完成）")
    def _():
        buf = make_zip({"proj/app.py": "print('ok')", "proj/requirements.txt": "flask\n"})
        r = client.post("/api/upload", data={"file": (buf, "proj.zip")},
                        content_type="multipart/form-data")
        body = get_json(r)
        truthy(body["ok"], body.get("message"))
        job_id = body["data"]["job"]["id"]
        deadline = time.time() + 30
        status = "running"
        while time.time() < deadline:
            jd = get_json(client.get("/api/jobs/%s" % job_id))["data"]["job"]
            status = jd["status"]
            if status not in ("pending", "running"):
                break
            time.sleep(0.2)
        eq(status, "done", "上传解压任务应成功")

    @case("POST /api/upload 拒绝非 zip")
    def _():
        buf = io.BytesIO(b"not a zip at all")
        r = client.post("/api/upload", data={"file": (buf, "bad.txt")},
                        content_type="multipart/form-data")
        truthy(not get_json(r)["ok"])

    @case("POST /api/github/test 参数校验（不发网络请求）")
    def _():
        r = client.post("/api/github/test", json={"url": ""})
        truthy(not get_json(r)["ok"])
        r2 = client.post("/api/github/test", json={"url": "https://gitlab.com/a/b"})
        truthy(not get_json(r2)["ok"], "非 GitHub 地址应报错")

    @case("POST /api/db/init 建表任务完成")
    def _():
        body = get_json(client.post("/api/db/init"))
        truthy(body["ok"], body.get("message"))
        job_id = body["data"]["job"]["id"]
        deadline = time.time() + 40
        while time.time() < deadline:
            jd = get_json(client.get("/api/jobs/%s" % job_id))["data"]["job"]
            if jd["status"] not in ("pending", "running"):
                eq(jd["status"], "done", "建表任务应成功：%s" % jd["message"])
                break
            time.sleep(0.2)
        d = get_json(client.get("/api/db/overview"))["data"]
        truthy(d["engine"] in ("sqlite", "mysql"))

    @case("GET /api/service/status 返回结构化状态")
    def _():
        body = get_json(client.get("/api/service/status"))
        truthy(body["ok"])
        truthy("port" in body["data"] and "level" in body["data"])

    @case("POST /api/backup 生成可下载备份")
    def _():
        body = get_json(client.post("/api/backup", json={"note": "接口自测"}))
        truthy(body["ok"])
        job_id = body["data"]["job"]["id"]
        deadline = time.time() + 60
        while time.time() < deadline:
            jd = get_json(client.get("/api/jobs/%s" % job_id))["data"]["job"]
            if jd["status"] not in ("pending", "running"):
                eq(jd["status"], "done", "备份任务应成功：%s" % jd["message"])
                break
            time.sleep(0.3)
        lst = get_json(client.get("/api/backup"))["data"]["backups"]
        truthy(len(lst) >= 1, "应至少有一个备份")
        name = lst[0]["name"]
        dl = client.get("/api/download?kind=backup&name=%s" % name)
        eq(dl.status_code, 200)
        truthy(len(dl.data) > 500, "下载内容应非空")
        bad = client.get("/api/download?kind=backup&name=../config.json")
        truthy(not get_json(bad)["ok"], "应拒绝路径穿越下载")

    @case("POST /api/export 三种导出都成功")
    def _():
        for kind in ("deploy", "nginx", "code"):
            body = get_json(client.post("/api/export", json={"kind": kind}))
            truthy(body["ok"], "%s 导出失败：%s" % (kind, body.get("message")))
            dl = client.get("/api/download?kind=export&name=%s" % body["data"]["name"])
            eq(dl.status_code, 200)
        d = get_json(client.get("/api/export"))["data"]
        eq(len(d["kinds"]), 3)

    @case("GET /api/jobs 与 404 处理")
    def _():
        d = get_json(client.get("/api/jobs"))["data"]
        truthy("jobs" in d and len(d["jobs"]) >= 1)
        r = client.get("/api/jobs/not-exist")
        truthy(not get_json(r)["ok"])
        r2 = client.get("/no/such/file.js")
        eq(r2.status_code, 404)

    @case("GET /healthz 与 /api/info")
    def _():
        d = get_json(client.get("/healthz"))
        truthy(d["ok"])
        d2 = get_json(client.get("/api/info"))["data"]
        truthy(d2["panel"]["version"])
        truthy(d2["panel"]["workdir"] == TMP_WORK)

    @case("GET / 返回面板页面")
    def _():
        r = client.get("/")
        eq(r.status_code, 200)
        html = r.data.decode("utf-8")
        truthy("可视化部署面板" in html)
        for asset in ("/js/main.js", "/css/panel.css"):
            truthy(asset in html, "页面应引用 %s" % asset)


# --------------------------------------------------------------------------- #
def main():
    print("\n" + "=" * 70)
    print(" 打工避雷平台 · 可视化部署面板 —— 自测")
    print(" 工作区：%s" % TMP_WORK)
    print("=" * 70)

    # 结尾检查：测试不应在内置模板目录里留下任何新文件（例如误建数据库）
    after = template_snapshot()
    leaked = sorted(after - TEMPLATE_BASELINE)
    if leaked:
        FAILED.append(("内置模板目录被测试污染", AssertionError("新增文件：%s" % leaked)))
        print("\n  [FAIL] 内置模板目录被测试污染 -> %s" % leaked)
    else:
        PASSED.append("内置模板目录未被污染")
        print("\n  [PASS] 内置模板目录未被污染")

    print("\n通过 %d / 失败 %d" % (len(PASSED), len(FAILED)))
    if FAILED:
        print("\n失败明细：")
        for name, exc in FAILED:
            print("  - %s：%s" % (name, exc))
    else:
        print("\n全部通过 ✅")
    print("清理临时工作区…")
    shutil.rmtree(TMP_WORK, ignore_errors=True)
    # 模板里若被 python 生成了缓存，一并清掉
    tpl = schema.find_template("打工避雷平台")
    if tpl:
        shutil.rmtree(os.path.join(tpl["path"], "__pycache__"), ignore_errors=True)
        shutil.rmtree(os.path.join(tpl["path"], "routes", "__pycache__"), ignore_errors=True)
        shutil.rmtree(os.path.join(tpl["path"], "data"), ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
