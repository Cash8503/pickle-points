import os
import threading

from flask import Flask

from api import register_routes
from services import warm_cache

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
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = _get_secret_key()

    @app.after_request
    def _cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    register_routes(app)
    return app


app = create_app()


def main():
    print("=" * 60)
    print("  Pickle Points Web Editor")
    print("  http://localhost:5001")
    print("=" * 60)
    threading.Thread(target=warm_cache, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
