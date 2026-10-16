# -*- coding: utf-8 -*-
"""举报接口：人机验证 + 内容审核 + 白名单 + 防刷。"""
from flask import Blueprint, jsonify, request, session

from config import Config as CFG
from models import execute, ip_hash, now, query_one
from safety import log_review, make_captcha, pre_submit

bp = Blueprint("report", __name__)


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or ""


@bp.route("/api/captcha", methods=["GET"])
def api_captcha():
    question, answer = make_captcha()
    session["captcha_answer"] = answer
    return jsonify({"ok": True, "data": {"question": question,
                                         "enabled": CFG.ENABLE_CAPTCHA,
                                         "provider": CFG.CAPTCHA_PROVIDER}})


@bp.route("/api/report", methods=["POST"])
def api_report():
    form = request.get_json(silent=True) or request.form.to_dict() or {}
    ip = client_ip()

    # 1) 防刷
    if CFG.ENABLE_RATE_LIMIT:
        from safety import rate_limit_check
        ok_rl, rl_msg, hits = rate_limit_check(ip)
        if not ok_rl:
            return jsonify({"ok": False, "level": "error", "step": "防刷限制",
                            "message": rl_msg, "hits": hits}), 429

    # 2) 校验公司
    company_id = form.get("company_id")
    company_name = (form.get("company") or form.get("company_name") or "").strip()
    if not company_id and company_name:
        row = query_one("SELECT id FROM company WHERE name=?", (company_name,))
        if row:
            company_id = row["id"]
        else:
            company_id = execute("INSERT INTO company (name, city, industry, risk_level, created_at, updated_at) "
                                 "VALUES (?,?,?,0,?,?)",
                                 (company_name, form.get("city", ""), form.get("industry", ""),
                                  now(), now()))
    if not company_id:
        return jsonify({"ok": False, "step": "公司信息", "message": "请填写或选择公司"}), 400

    # 3) 内容与白名单检查
    ok_flag, extra, messages = pre_submit(session, ip, form)
    if not ok_flag:
        return jsonify({"ok": False, "step": "校验未通过", "message": messages[-1]["detail"],
                        "checks": messages, "level": "error"}), 400

    title = (form.get("title") or "").strip()[:120]
    content = (form.get("content") or "").strip()
    if len(content) < 10:
        return jsonify({"ok": False, "step": "内容审核",
                        "message": "正文至少 10 个字，便于他人核实"}), 400

    report_id = execute(
        "INSERT INTO report (company_id, category, title, content, video_url, city, job, contact, "
        "status, ip_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (company_id, form.get("category", "其他"), title, content,
         (form.get("video_url") or "").strip(), form.get("city", ""), form.get("job", ""),
         form.get("contact", ""), extra.get("status", "pending"), ip_hash(ip), now()))

    log_review(report_id, "pre_submit", "hold" if extra.get("status") == "pending" else "pass",
               extra.get("review", ""))

    if extra.get("status") == "pending":
        return jsonify({"ok": True, "level": "warn", "data": {"id": report_id, "status": "pending"},
                        "checks": messages,
                        "message": "已提交，等待人工审核（%s）" % extra.get("review", "")})
    return jsonify({"ok": True, "level": "ok", "data": {"id": report_id, "status": "approved"},
                    "checks": messages, "message": "提交成功，已发布"})


@bp.route("/api/report/<int:report_id>", methods=["GET"])
def api_report_detail(report_id):
    row = query_one("SELECT r.*, c.name AS company_name FROM report r "
                    "LEFT JOIN company c ON c.id=r.company_id WHERE r.id=?", (report_id,))
    if not row:
        return jsonify({"ok": False, "message": "记录不存在"}), 404
    return jsonify({"ok": True, "data": row})
