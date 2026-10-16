# -*- coding: utf-8 -*-
"""查询接口：搜索公司 / 查看详情 / 首页数据。"""
from flask import Blueprint, jsonify, render_template, request

from config import Config as CFG
from models import query_all, query_one

bp = Blueprint("query", __name__)


@bp.route("/", methods=["GET"])
def index():
    keyword = request.args.get("q", "").strip()
    payload = search_payload(keyword)
    return render_template("index.html", site=CFG.SITE_NAME, keyword=keyword, **payload)


@bp.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"ok": True, "site": CFG.SITE_NAME, "engine": CFG.DB_ENGINE})


@bp.route("/api/search", methods=["GET"])
def api_search():
    keyword = request.args.get("q", "").strip()
    return jsonify({"ok": True, "data": search_payload(keyword)})


def search_payload(keyword):
    params = []
    where = "WHERE r.status='approved'"
    if keyword:
        where += " AND (c.name LIKE ? OR c.city LIKE ? OR c.industry LIKE ? OR r.title LIKE ?)"
        like = "%" + keyword + "%"
        params = [like, like, like, like]
    reports = query_all(
        "SELECT r.id, r.title, r.category, r.content, r.video_url, r.city, r.job, r.created_at, "
        "       c.id AS company_id, c.name AS company_name, c.risk_level, c.tags "
        "FROM report r JOIN company c ON c.id = r.company_id "
        "%s ORDER BY r.id DESC LIMIT 50" % where, params)
    companies = query_all(
        "SELECT c.id, c.name, c.industry, c.city, c.risk_level, c.tags, "
        "       (SELECT COUNT(*) FROM report r WHERE r.company_id=c.id AND r.status='approved') AS report_count "
        "FROM company c ORDER BY c.risk_level DESC, report_count DESC LIMIT 20")
    stats = query_one("SELECT "
                      "(SELECT COUNT(*) FROM company) AS companies, "
                      "(SELECT COUNT(*) FROM report WHERE status='approved') AS reports, "
                      "(SELECT COUNT(*) FROM report WHERE status='pending') AS pending") or {}
    return {"reports": reports, "companies": companies, "stats": stats,
            "allowlist": CFG.load_allowlist_from_db()}


@bp.route("/api/company/<int:company_id>", methods=["GET"])
def api_company(company_id):
    company = query_one("SELECT * FROM company WHERE id=?", (company_id,))
    if not company:
        return jsonify({"ok": False, "message": "公司不存在"}), 404
    reports = query_all(
        "SELECT id, title, category, content, video_url, city, job, status, created_at "
        "FROM report WHERE company_id=? AND status='approved' ORDER BY id DESC", (company_id,))
    return jsonify({"ok": True, "data": {"company": company, "reports": reports}})


@bp.route("/api/allowlist", methods=["GET"])
def api_allowlist():
    return jsonify({"ok": True, "data": {"domains": CFG.load_allowlist_from_db(),
                                         "proxy_images": CFG.PROXY_IMAGES}})
