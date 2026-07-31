import datetime
import logging
import os
import threading

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from api import register_routes
from auth_db import init_db
from config import migrate_json_to_db, migrate_vendor_items_to_automatic
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
    migrate_vendor_items_to_automatic()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = _get_secret_key()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    def static_asset_version(filename):
        """Use the file timestamp to prevent mixed old/new editor assets."""
        try:
            return os.stat(os.path.join(app.static_folder, filename)).st_mtime_ns
        except OSError:
            return 0

    app.jinja_env.globals["static_asset_version"] = static_asset_version

    @app.after_request
    def _add_charset(response):
        ct = response.headers.get("Content-Type", "")
        if ct and "charset" not in ct and any(t in ct for t in ("text/", "javascript", "json")):
            response.headers["Content-Type"] = ct + "; charset=utf-8"
        return response

    @app.template_filter("timestamp_to_str")
    def _timestamp_to_str(ts):
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

    @app.template_filter("relative_time")
    def _relative_time(ts):
        if not ts:
            return "Never"
        seconds = max(0, int(datetime.datetime.now().timestamp() - float(ts)))
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} min ago"
        hours = minutes // 60
        if hours < 48:
            return f"{hours} hr ago"
        days = hours // 24
        return f"{days} days ago"

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
