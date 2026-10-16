# -*- coding: utf-8 -*-
"""后台接口：待审核队列 + 通过/驳回。

仅作骨架演示：生产环境请自行接入登录鉴权（schema.sql 里已预留 admin_user 表）。
"""
from flask import Blueprint, jsonify, render_template, request

from config import Config as CFG
from models import execute, now, query_all

bp = Blueprint("admin", __name__)


def _guard():
    """极简保护：演示用；正式上线请换成登录态校验。"""
    token = request.args.get("token") or request.headers.get("X-Admin-Token") or ""
    return token == (CFG.SECRET_KEY[:8] if CFG.SECRET_KEY else "")


@bp.route("/admin", methods=["GET"])
def admin_page():
    return render_template("admin.html", site=CFG.SITE_NAME, ok=_guard())


@bp.route("/api/admin/queue", methods=["GET"])
def api_queue():
    if not _guard():
        return jsonify({"ok": False, "message": "需要管理凭据（?token=SECRET_KEY前8位）"}), 403
    rows = query_all(
        "SELECT r.id, r.title, r.category, r.content, r.video_url, r.city, r.job, r.status, "
        "       r.created_at, c.name AS company_name "
        "FROM report r LEFT JOIN company c ON c.id=r.company_id "
        "WHERE r.status='pending' ORDER BY r.id DESC LIMIT 200")
    rejected = query_all("SELECT id, title FROM report WHERE status='rejected' ORDER BY id DESC LIMIT 50")
    logs = query_all("SELECT report_id, rule, action, detail, created_at FROM review_log "
                     "ORDER BY id DESC LIMIT 100")
    return jsonify({"ok": True, "data": {"pending": rows, "rejected": rejected, "logs": logs}})


@bp.route("/api/admin/review", methods=["POST"])
def api_review():
    if not _guard():
        return jsonify({"ok": False, "message": "需要管理凭据"}), 403
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    report_id = payload.get("id")
    action = (payload.get("action") or "").strip()
    if action not in ("approve", "reject"):
        return jsonify({"ok": False, "message": "action 只能是 approve 或 reject"}), 400
    try:
        report_id = int(report_id)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "id 不合法"}), 400
    status = "approved" if action == "approve" else "rejected"
    execute("UPDATE report SET status=?, reviewed_at=? WHERE id=?", (status, now(), report_id))
    execute("INSERT INTO review_log (report_id, rule, action, detail, created_at) VALUES (?,?,?,?,?)",
            (report_id, "manual", action, payload.get("note", ""), now()))
    return jsonify({"ok": True, "data": {"id": report_id, "status": status},
                    "message": "已%s" % ("发布" if action == "approve" else "驳回")})


@bp.route("/api/admin/allowlist", methods=["GET", "POST", "DELETE"])
def api_allowlist_admin():
    if not _guard():
        return jsonify({"ok": False, "message": "需要管理凭据"}), 403
    if request.method == "GET":
        return jsonify({"ok": True, "data": query_all(
            "SELECT id, domain, enabled FROM video_allowlist ORDER BY id")})
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    domain = (payload.get("domain") or "").strip().lower()
    if request.method == "DELETE":
        if not domain:
            return jsonify({"ok": False, "message": "缺少 domain"}), 400
        execute("DELETE FROM video_allowlist WHERE domain=?", (domain,))
        return jsonify({"ok": True, "message": "已删除 %s" % domain})
    if not domain:
        return jsonify({"ok": False, "message": "缺少 domain"}), 400
    execute("INSERT INTO video_allowlist (domain, enabled, created_at) VALUES (?,1,?)", (domain, now()))
    return jsonify({"ok": True, "message": "已添加 %s" % domain})
