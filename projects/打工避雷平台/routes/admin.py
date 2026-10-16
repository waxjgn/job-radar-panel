# -*- coding: utf-8 -*-
"""后台：只审核公司申诉，不审核上传内容（上传免审直发）。

- POST /api/appeal                       公司提交申诉（进待审核）
- GET  /api/admin/appeals                待审核申诉队列
- POST /api/admin/appeal/review          受理 / 驳回申诉
- GET/POST/DELETE /api/admin/allowlist   视频平台白名单维护

生产环境请自行接入登录鉴权（schema.sql 已预留 admin_user 表）。
"""
from flask import Blueprint, jsonify, render_template, request, session

from config import Config as CFG
from models import execute, ip_hash, now, query_all, query_one
from safety import make_captcha

bp = Blueprint("admin", __name__)


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or ""


def _guard():
    token = request.args.get("token") or request.headers.get("X-Admin-Token") or ""
    return token == (CFG.SECRET_KEY[:8] if CFG.SECRET_KEY else "")


@bp.route("/admin", methods=["GET"])
def admin_page():
    return render_template("admin.html", site=CFG.SITE_NAME, ok=_guard())


# --------------------------------------------------------------------------- #
# 公司申诉
# --------------------------------------------------------------------------- #
@bp.route("/api/appeal/captcha", methods=["GET"])
def api_appeal_captcha():
    q, a = make_captcha()
    session["appeal_captcha"] = a
    return jsonify({"ok": True, "data": {"question": q, "enabled": CFG.ENABLE_CAPTCHA}})


def _check_captcha(answer):
    if not CFG.ENABLE_CAPTCHA:
        return True, "人机验证已关闭"
    expect = session.get("appeal_captcha")
    if expect is None:
        return False, "验证码已过期，请点击刷新"
    try:
        got = int(str(answer).strip())
    except (TypeError, ValueError):
        return False, "请输入数字答案"
    session.pop("appeal_captcha", None)
    if got != int(expect):
        return False, "答案不正确，请重新作答"
    return True, "验证通过"


@bp.route("/api/appeal", methods=["POST"])
def api_appeal():
    form = request.get_json(silent=True) or request.form.to_dict() or {}

    ok_cap, cap_msg = _check_captcha(form.get("captcha"))
    if not ok_cap:
        return jsonify({"ok": False, "step": "人机验证", "message": cap_msg}), 400

    credit = (form.get("credit_code") or "").strip().upper()
    if len(credit) != 18:
        return jsonify({"ok": False, "step": "主体确认",
                        "message": "请填写 18 位统一社会信用代码，用于确认申诉主体身份"}), 400

    reason = (form.get("reason") or "").strip()
    if len(reason) < 10:
        return jsonify({"ok": False, "step": "申诉理由",
                        "message": "申诉理由至少 10 个字，并注明可核验的凭证类型"}), 400

    company = query_one("SELECT id, name FROM company WHERE credit_code=? OR name=?",
                        (credit, form.get("company", "")))
    appeal_id = execute(
        "INSERT INTO appeal (company_id, company_name, credit_code, reason, evidence, contact, "
        "status, ip_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (company["id"] if company else None, form.get("company", ""), credit, reason,
         form.get("evidence", ""), form.get("contact", ""), "pending", ip_hash(client_ip()), now()))

    if company:
        _sync_company_appeal(company["id"])
        return jsonify({"ok": True, "level": "ok", "data": {"id": appeal_id, "status": "pending"},
                        "message": "申诉已提交，平台会审核；结论将公示在「%s」详情页顶部" % company["name"]})
    return jsonify({"ok": True, "level": "warn", "data": {"id": appeal_id, "status": "pending"},
                    "message": "申诉已提交（未匹配到库内主体，进入待审核队列）"})


@bp.route("/api/appeal/<int:company_id>", methods=["GET"])
def api_appeal_list(company_id):
    rows = query_all("SELECT id, reason, status, review_note, created_at FROM appeal "
                     "WHERE company_id=? ORDER BY id DESC", (company_id,))
    return jsonify({"ok": True, "data": {"appeals": rows}})


# --------------------------------------------------------------------------- #
# 申诉审核（后台）
# --------------------------------------------------------------------------- #
@bp.route("/api/admin/appeals", methods=["GET"])
def api_admin_appeals():
    if not _guard():
        return jsonify({"ok": False, "message": "需要管理凭据（?token=SECRET_KEY前8位）"}), 403
    pending = query_all("SELECT * FROM appeal WHERE status='pending' ORDER BY id DESC LIMIT 200")
    done = query_all("SELECT * FROM appeal WHERE status<>'pending' ORDER BY id DESC LIMIT 100")
    return jsonify({"ok": True, "data": {"pending": pending, "reviewed": done}})


@bp.route("/api/admin/appeal/review", methods=["POST"])
def api_admin_appeal_review():
    if not _guard():
        return jsonify({"ok": False, "message": "需要管理凭据"}), 403
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    action = (payload.get("action") or "").strip()
    if action not in ("accept", "reject"):
        return jsonify({"ok": False, "message": "action 只能是 accept 或 reject"}), 400
    try:
        appeal_id = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "id 不合法"}), 400

    row = query_one("SELECT * FROM appeal WHERE id=?", (appeal_id,))
    if not row:
        return jsonify({"ok": False, "message": "申诉不存在"}), 404

    status = "accepted" if action == "accept" else "rejected"
    execute("UPDATE appeal SET status=?, review_note=?, reviewed_at=? WHERE id=?",
            (status, (payload.get("note") or "").strip(), now(), appeal_id))
    if row["company_id"]:
        _sync_company_appeal(row["company_id"])
    return jsonify({"ok": True, "data": {"id": appeal_id, "status": status},
                    "message": "申诉已%s" % ("受理" if action == "accept" else "驳回")})


def _sync_company_appeal(company_id):
    """把申诉结果同步到 company 表，供前台公示。"""
    row = query_one("SELECT COUNT(*) AS n FROM appeal WHERE company_id=?", (company_id,))
    latest = query_one("SELECT status, reason, review_note FROM appeal "
                       "WHERE company_id=? ORDER BY id DESC LIMIT 1", (company_id,))
    status = (latest["status"] if latest else "none") or "none"
    note = ((latest["review_note"] or latest["reason"]) if latest else "") or ""
    execute("UPDATE company SET appeal_status=?, appeal_count=?, appeal_note=? WHERE id=?",
            (status, row["n"] if row else 0, note[:200], company_id))


# --------------------------------------------------------------------------- #
# 白名单维护（只允许四大平台链接）
# --------------------------------------------------------------------------- #
@bp.route("/api/admin/allowlist", methods=["GET", "POST", "DELETE"])
def api_admin_allowlist():
    if not _guard():
        return jsonify({"ok": False, "message": "需要管理凭据"}), 403
    if request.method == "GET":
        return jsonify({"ok": True, "data": query_all(
            "SELECT id, domain, enabled FROM video_allowlist ORDER BY id")})
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    domain = (payload.get("domain") or "").strip().lower()
    if not domain:
        return jsonify({"ok": False, "message": "缺少 domain"}), 400
    if request.method == "DELETE":
        execute("DELETE FROM video_allowlist WHERE domain=?", (domain,))
        return jsonify({"ok": True, "message": "已删除 %s" % domain})
    execute("INSERT INTO video_allowlist (domain, enabled, created_at) VALUES (?,1,?)", (domain, now()))
    return jsonify({"ok": True, "message": "已添加 %s" % domain})


@bp.route("/api/admin/review", methods=["POST"])
def api_admin_review_deprecated():
    return jsonify({"ok": False, "level": "warn",
                    "message": "站点不设人工审核：上传免审直发；后台只审核公司申诉，"
                               "请改用 /api/admin/appeal/review"}), 410
