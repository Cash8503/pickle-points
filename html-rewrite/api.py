import threading
from functools import wraps

from flask import jsonify, redirect, render_template, request, session, url_for

from config import (load_config, sanitize_store_num, save_config,
                    set_codeword, store_has_codeword, verify_codeword)
from preview_render import render_preview_html
from services import fetch_smilemakers_product, prefetch_new_urls, resolve_items_for_preview


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return f(*args, **kwargs)
        if "store" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not logged in"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def register_routes(app):

    # ── Auth ──────────────────────────────────────────────────────
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "store" in session:
            return redirect(url_for("editor"))

        step = 1
        store_num = None
        is_new = False
        error = None

        if request.method == "POST":
            action = request.form.get("action", "check_store")

            if action == "check_store":
                store_num = sanitize_store_num(request.form.get("store_num", ""))
                if not store_num:
                    error = "Please enter a valid store number."
                    step = 1
                else:
                    is_new = not store_has_codeword(store_num)
                    step = 2

            elif action == "setup_codeword":
                store_num = sanitize_store_num(request.form.get("store_num", ""))
                codeword = request.form.get("codeword", "").strip()
                if not codeword:
                    error = "Please choose a codeword."
                    step = 2
                    is_new = True
                else:
                    set_codeword(store_num, codeword)
                    session["store"] = store_num
                    return redirect(url_for("editor"))

            elif action == "verify_codeword":
                store_num = sanitize_store_num(request.form.get("store_num", ""))
                codeword = request.form.get("codeword", "").strip()
                if verify_codeword(store_num, codeword):
                    session["store"] = store_num
                    return redirect(url_for("editor"))
                error = "Incorrect codeword. Please try again."
                step = 2
                is_new = False

        return render_template("login.html", step=step, store_num=store_num,
                               is_new=is_new, error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ── Editor ────────────────────────────────────────────────────
    @app.route("/")
    @login_required
    def editor():
        return render_template("editor.html", store_num=session["store"])

    # ── Config API ────────────────────────────────────────────────
    @app.route("/api/config", methods=["GET"])
    @login_required
    def api_get_config():
        return jsonify(load_config(session["store"]))

    @app.route("/api/config", methods=["POST", "OPTIONS"])
    @login_required
    def api_post_config():
        if request.method == "OPTIONS":
            return "", 204
        try:
            cfg = request.get_json(force=True)
            save_config(cfg, session["store"])
            threading.Thread(target=prefetch_new_urls, args=(cfg,), daemon=True).start()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/fetch-product", methods=["POST", "OPTIONS"])
    @login_required
    def api_fetch_product():
        if request.method == "OPTIONS":
            return "", 204
        data = request.get_json(force=True)
        url = (data or {}).get("url", "").strip()
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        try:
            name, desc, image, price, size_variants = fetch_smilemakers_product(url)
            sizes = [v["value"] for v in size_variants if v.get("type") == "size"]
            return jsonify({"name": name, "desc": desc, "image": image, "price": price, "sizes": sizes})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ── Preview ───────────────────────────────────────────────────
    @app.route("/preview")
    @login_required
    def preview():
        cfg = load_config(session["store"])
        try:
            pages, per_pickle, pickle_value = resolve_items_for_preview(cfg)
        except Exception as exc:
            return f"<pre>Error resolving items:\n{exc}</pre>", 500
        return render_preview_html(pages, per_pickle, pickle_value, cfg.get("tag_colors", {}))

    @app.route("/preview-frame")
    @login_required
    def preview_frame():
        cfg = load_config(session["store"])
        try:
            pages, per_pickle, pickle_value = resolve_items_for_preview(cfg)
        except Exception as exc:
            return f"<pre>Error: {exc}</pre>", 500
        return render_preview_html(pages, per_pickle, pickle_value, cfg.get("tag_colors", {}))
