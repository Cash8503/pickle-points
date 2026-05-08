import datetime
import logging
import os
import threading

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from api import register_routes
from auth_db import init_db
from config import migrate_json_to_db
from services import start_cache_maintenance, warm_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_SECRET_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")


def _get_secret_key():
    if os.path.exists(_SECRET_KEY_FILE):
        with open(_SECRET_KEY_FILE, "rb") as f:
            return f.read()
    key = os.urandom(32)
    with open(_SECRET_KEY_FILE, "wb") as f:
        f.write(key)
    return key


def create_app():
    init_db()
    migrate_json_to_db()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = _get_secret_key()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    @app.after_request
    def _add_charset(response):
        ct = response.headers.get("Content-Type", "")
        if ct and "charset" not in ct and any(t in ct for t in ("text/", "javascript", "json")):
            response.headers["Content-Type"] = ct + "; charset=utf-8"
        return response

    @app.template_filter("timestamp_to_str")
    def _timestamp_to_str(ts):
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

    register_routes(app)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    return app


app = create_app()


def main():
    print("=" * 60)
    print("  Pickle Points Web Editor")
    print("  http://localhost:5001")
    print("=" * 60)
    threading.Thread(target=warm_cache, daemon=True).start()
    start_cache_maintenance()
    app.run(host="0.0.0.0", port=5001, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
