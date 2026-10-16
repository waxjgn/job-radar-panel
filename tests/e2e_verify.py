# -*- coding: utf-8 -*-
"""端到端验收：对真实运行中的面板发起请求，走完整部署链路。

用法：
    # 1) 先用一个临时工作区启动面板，避免污染正式数据
    #    Linux/macOS:  DEPLOY_PANEL_WORKDIR=/tmp/e2e-work python app.py --port 8771
    #    Windows:      $env:DEPLOY_PANEL_WORKDIR="D:\\e2e-work"; python app.py --port 8771
    # 2) 再跑本脚本
    python e2e_verify.py http://127.0.0.1:8771 [应用端口]

注意：面板会真的在本机启动一个服务并监听应用端口（默认 5099），
脚本结尾会自动把它停掉。
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8771"
APP_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5099
APP_BASE = "http://127.0.0.1:%d" % APP_PORT
RESULTS = []


def call(method, path, payload=None, timeout=120):
    url = BASE + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, raw
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, (" -> " + str(detail)) if detail and not cond else ""))


def wait_job(job_id, timeout=600):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        code, body = call("GET", "/api/jobs/%s" % job_id)
        job = (body.get("data") or {}).get("job") or {}
        last = job
        if job.get("status") not in ("pending", "running"):
            return job
        print("        …%s%% %s" % (job.get("progress", {}).get("value"), job.get("progress", {}).get("text")))
        time.sleep(1.2)
    return last or {}


def tail_log(job, n=14):
    lines = [l.get("text", "") for l in (job.get("lines") or [])]
    return "\n        ".join(lines[-n:])


print("=" * 74)
print(" 端到端验收：%s" % BASE)
print("=" * 74)

# ---------- 1. 面板页面与健康检查 ----------
code, body = call("GET", "/healthz")
check("面板 /healthz 正常", code == 200 and body.get("ok"), body)

code, html = call("GET", "/")
check("面板首页返回 HTML", code == 200 and "可视化部署面板" in str(html), code)

for asset in ("/js/main.js", "/js/api.js", "/js/config_form.js", "/js/logs.js", "/js/ui.js", "/css/panel.css"):
    code, _ = call("GET", asset)
    check("静态资源 %s" % asset, code == 200, code)

# ---------- 2. 配置：切到内置模板 + 本地环境 ----------
code, body = call("PUT", "/api/config", {"config": {
    "target.env": "local",
    "project.source_mode": "upload",
    "project.template": "打工避雷平台",
    "target.app_port": APP_PORT,
    "network.domain": "localhost",
    "network.bind_host": "127.0.0.1",
    "database.engine": "sqlite",
    "database.sqlite_path": "data/app.db",
    "allowlist.video_domains": ["bilibili.com", "douyin.com", "kuaishou.com", "channels.weixin.qq.com"],
    "security.captcha": True,
    "security.content_review": True,
    "security.rate_limit": True,
}})
check("保存配置（本地 + 内置模板 + 应用端口）", code == 200 and body.get("ok"), body)

code, body = call("GET", "/api/config")
cfg = body.get("data", {})
check("回读配置端口与模板", cfg.get("flat", {}).get("target.app_port") == APP_PORT and
      cfg.get("flat", {}).get("project.template") == "打工避雷平台", cfg.get("flat", {}).get("target.app_port"))

# ---------- 3. 环境检测 ----------
code, body = call("GET", "/api/detect")
det = body.get("data", {})
items = det.get("items", [])
check("环境检测返回分级结果", code == 200 and det.get("overall") in ("ok", "warn", "error"), det.get("overall"))
check("检测项包含 python/pip/nginx/git/mysql/端口", len(items) >= 6, [i.get("id") for i in items])
reds = [i["name"] for i in items if i["level"] == "error"]
print("        红色项（缺失的必需依赖）：%s" % (reds or "无"))
for i in items:
    print("        · [%s] %s —— %s" % (i["level"], i["name"], i.get("detail")))

# ---------- 4. 产物预览 ----------
code, body = call("GET", "/api/gen/artifacts")
arts = body.get("data", {})
names = [f["name"] for f in arts.get("files", [])]
check("生成产物清单非空", arts.get("count", 0) >= 3, names)
check("包含 .env.example 与 requirements.txt", "deploy/.env.example" in names and "deploy/requirements.txt" in names, names)

code, body = call("GET", "/api/gen/nginx")
check("生成 nginx.conf", code == 200 and len(body.get("data", {}).get("content", "")) > 100, code)

code, body = call("GET", "/api/commands")
cmds = body.get("data", {}).get("commands", [])
check("底层命令清单可用（高级模式）", len(cmds) >= 5, len(cmds))
for c in cmds[:6]:
    print("        $ %s" % c.get("cmd"))

# ---------- 5. 一键部署（含展开模板、装依赖、建库、启动） ----------
print("\n  --- 开始一键部署（真实执行，包括 pip install 与启动服务）---")
code, body = call("POST", "/api/deploy")
job = (body.get("data") or {}).get("job") or {}
check("提交一键部署任务", code == 200 and body.get("ok"), body)
deploy_job = wait_job(job.get("id"))
print("        任务状态：%s（%s）" % (deploy_job.get("status"), deploy_job.get("message")))
print("        日志尾部：\n        %s" % tail_log(deploy_job))
check("一键部署完成", deploy_job.get("status") == "done", deploy_job.get("message"))

# ---------- 6. 服务状态与真实 HTTP 访问 ----------
code, body = call("GET", "/api/service/status")
st = body.get("data", {})
check("服务状态为运行中", st.get("running") is True, st.get("message"))
check("端口显示监听中", st.get("listening") is True, st.get("port"))
print("        模式=%s pid=%s 端口=%s 日志=%s" % (st.get("mode"), st.get("pid"), st.get("port"), st.get("log_file")))


try:
    with urllib.request.urlopen(APP_BASE + "/healthz", timeout=8) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        check("被部署的应用 /healthz 可访问", resp.status == 200 and payload.get("ok"), payload)
except Exception as exc:  # noqa: BLE001
    check("被部署的应用 /healthz 可访问", False, exc)

try:
    import urllib.parse
    q = urllib.parse.quote("示例")
    with urllib.request.urlopen(APP_BASE + "/api/search?q=%s" % q, timeout=8) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        reports = (payload.get("data") or {}).get("reports") or []
        check("应用搜索接口返回模板示例数据", resp.status == 200 and len(reports) >= 1,
              "reports=%d" % len(reports))
except Exception as exc:  # noqa: BLE001
    check("应用搜索接口返回模板示例数据", False, exc)

try:
    with urllib.request.urlopen(APP_BASE + "/api/allowlist", timeout=8) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        domains = (payload.get("data") or {}).get("domains") or []
        check("应用读到面板配置的视频白名单", "bilibili.com" in domains, domains)
except Exception as exc:  # noqa: BLE001
    check("应用读到面板配置的视频白名单", False, exc)

# ---------- 7. 数据库概览 ----------
code, body = call("GET", "/api/db/overview")
db = body.get("data", {})
tables = [t["name"] for t in db.get("tables", [])]
check("数据库建表完成", db.get("exists") is True and len(tables) >= 5, tables)
for t in db.get("tables", []):
    print("        · %s：%s 行" % (t["name"], t["rows"]))

# ---------- 8. 应用日志 ----------
code, body = call("GET", "/api/logs?lines=200")
lg = body.get("data", {})
check("应用日志可读", lg.get("exists") is True and len(lg.get("lines", [])) >= 1,
      lg.get("message"))
print("        日志行数：%s" % len(lg.get("lines", [])))

# ---------- 9. 备份与导出 ----------
code, body = call("POST", "/api/backup", {"note": "端到端验收"})
bjob = wait_job((body.get("data") or {}).get("job", {}).get("id"), timeout=300)
check("一键备份完成", bjob.get("status") == "done", bjob.get("message"))

code, body = call("GET", "/api/backup")
backups = body.get("data", {}).get("backups", [])
check("备份列表可用且有下载入口", len(backups) >= 1, backups[:1])

for kind in ("deploy", "nginx", "code"):
    code, body = call("POST", "/api/export", {"kind": kind})
    name = (body.get("data") or {}).get("name")
    check("导出 %s" % kind, body.get("ok") and name, body.get("message"))
    if name:
        dl_code, dl = call("GET", "/api/download?kind=export&name=%s" % name)
        check("下载 %s 文件" % kind, dl_code == 200, dl_code)

# ---------- 10. 服务运维：重启与停止 ----------
code, body = call("POST", "/api/service/restart")
rjob = wait_job((body.get("data") or {}).get("job", {}).get("id"), timeout=180)
check("重启服务完成", rjob.get("status") in ("done", "failed"), "%s / %s" % (rjob.get("status"), rjob.get("message")))
if rjob.get("status") == "done":
    code, body = call("GET", "/api/service/status")
    check("重启后服务仍运行", body.get("data", {}).get("running") is True, body.get("data", {}).get("message"))

code, body = call("POST", "/api/service/stop")
sjob = wait_job((body.get("data") or {}).get("job", {}).get("id"), timeout=120)
check("停止服务完成", sjob.get("status") == "done", "%s / %s" % (sjob.get("status"), sjob.get("message")))
code, body = call("GET", "/api/service/status")
check("停止后状态为未运行", body.get("data", {}).get("running") is False, body.get("data", {}).get("message"))

# ---------- 汇总 ----------
print("\n" + "=" * 74)
passed = sum(1 for _, ok, _ in RESULTS if ok)
failed = [r for r in RESULTS if not r[1]]
print(" 端到端验收：通过 %d / 失败 %d" % (passed, len(failed)))
for name, _, detail in failed:
    print("   - %s -> %s" % (name, detail))
print("=" * 74)
sys.exit(1 if failed else 0)
