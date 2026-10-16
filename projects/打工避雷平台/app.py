# -*- coding: utf-8 -*-
"""打工避雷平台 —— 应用入口。

本地运行：
    pip install -r requirements.txt
    python manage.py init-db
    python app.py
访问 http://127.0.0.1:5000
"""
import os
import sys

from flask import Flask, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import Config as CFG, get_config      # noqa: E402


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(get_config())
    app.secret_key = CFG.SECRET_KEY

    from routes.admin import bp as admin_bp
    from routes.query import bp as query_bp
    from routes.report import bp as report_bp
    app.register_blueprint(query_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(admin_bp)

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    @app.errorhandler(404)
    def _404(exc):  # noqa: ANN001
        return jsonify({"ok": False, "message": "接口不存在"}), 404

    @app.errorhandler(429)
    def _429(exc):  # noqa: ANN001
        return jsonify({"ok": False, "message": "提交过于频繁，请稍后再试"}), 429

    @app.errorhandler(500)
    def _500(exc):  # noqa: ANN001
        return jsonify({"ok": False, "message": "服务内部错误"}), 500

    return app


app = create_app()


if __name__ == "__main__":
    host = CFG.APP_BIND
    port = int(os.environ.get("APP_PORT") or CFG.APP_PORT)
    print("%s 启动中：http://%s:%s  (数据库：%s)" % (CFG.SITE_NAME, host, port, CFG.DB_ENGINE))
    print("首次运行请先执行：python manage.py init-db")
    app.run(host=host, port=port, debug=CFG.DEBUG)
