import json
import os
import threading
from functools import wraps

from flask import (flash, get_flashed_messages, jsonify, redirect,
                   render_template, request, Response, session, url_for)

from config import (admin_has_password, clear_codeword, get_auth_path,
                    get_store_config_path, get_store_metadata,
                    list_store_nums, load_config, sanitize_store_num,
                    save_config, set_admin_password, set_codeword,
                    store_has_codeword, verify_admin_password, verify_codeword)
from preview_render import render_preview_html
from services import fetch_smilemakers_product, prefetch_new_urls, resolve_items_for_preview


# ── Decorators ────────────────────────────────────────────────────
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


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin" not in session:
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


def register_routes(app):

    # ── Store auth ────────────────────────────────────────────────
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

        return render_template("login.html", step=step, store_num=store_num,
                               is_new=is_new, error=error)

    @app.route("/logout")
    def logout():
        # If admin was editing, go back to admin panel; otherwise go to login
        was_admin = "admin" in session
        session.pop("store", None)
        session.pop("admin_editing", None)
        if was_admin:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("login"))

    # ── Editor ────────────────────────────────────────────────────
    @app.route("/")
    @login_required
    def editor():
        return render_template("editor.html",
                               store_num=session["store"],
                               admin_editing=session.get("admin_editing", False))

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
            return jsonify({"name": name, "desc": desc, "image": image,
                            "price": price, "sizes": sizes})
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

    # ── Admin auth ────────────────────────────────────────────────
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if "admin" in session:
            return redirect(url_for("admin_dashboard"))
        is_setup = not admin_has_password()
        error = None
        if request.method == "POST":
            password = request.form.get("password", "").strip()
            if is_setup:
                if not password:
                    error = "Please choose an admin password."
                else:
                    set_admin_password(password)
                    session["admin"] = True
                    return redirect(url_for("admin_dashboard"))
            else:
                if verify_admin_password(password):
                    session["admin"] = True
                    return redirect(url_for("admin_dashboard"))
                error = "Incorrect password."
        return render_template("admin_login.html", is_setup=is_setup, error=error)

    @app.route("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect(url_for("admin_login"))

    # ── Admin dashboard ───────────────────────────────────────────
    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        stores = []
        for num in sorted(list_store_nums()):
            meta = get_store_metadata(num)
            stores.append({
                "num": num,
                "has_codeword": store_has_codeword(num),
                **meta,
            })
        msgs = get_flashed_messages(with_categories=True)
        return render_template("admin.html", stores=stores, messages=msgs)

    @app.route("/admin/store/<store_num>/edit")
    @admin_required
    def admin_edit_store(store_num):
        store_num = sanitize_store_num(store_num)
        session["store"] = store_num
        session["admin_editing"] = True
        return redirect(url_for("editor"))

    @app.route("/admin/store/back")
    @admin_required
    def admin_back():
        session.pop("store", None)
        session.pop("admin_editing", None)
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/store/<store_num>/reset-codeword", methods=["POST"])
    @admin_required
    def admin_reset_codeword(store_num):
        store_num = sanitize_store_num(store_num)
        new_codeword = request.form.get("codeword", "").strip()
        if new_codeword:
            set_codeword(store_num, new_codeword)
            flash(f"Codeword updated for Store #{store_num}.", "ok")
        else:
            clear_codeword(store_num)
            flash(f"Codeword cleared for Store #{store_num} — they will set a new one on next login.", "ok")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/store/<store_num>/copy-config", methods=["POST"])
    @admin_required
    def admin_copy_config(store_num):
        store_num = sanitize_store_num(store_num)
        source = sanitize_store_num(request.form.get("source", ""))
        if not source:
            flash("No source store specified.", "err")
        elif source == store_num:
            flash("Source and destination are the same store.", "err")
        else:
            cfg = load_config(source)
            save_config(cfg, store_num)
            flash(f"Config copied from Store #{source} to Store #{store_num}.", "ok")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/store/<store_num>/download")
    @admin_required
    def admin_download_config(store_num):
        store_num = sanitize_store_num(store_num)
        cfg = load_config(store_num)
        return Response(
            json.dumps(cfg, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename=store_{store_num}.json"},
        )

    @app.route("/admin/store/<store_num>/upload", methods=["POST"])
    @admin_required
    def admin_upload_config(store_num):
        store_num = sanitize_store_num(store_num)
        f = request.files.get("config_file")
        if not f:
            flash("No file selected.", "err")
        else:
            try:
                cfg = json.loads(f.read().decode("utf-8"))
                save_config(cfg, store_num)
                flash(f"Config replaced for Store #{store_num}.", "ok")
            except Exception as exc:
                flash(f"Invalid JSON: {exc}", "err")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/store/<store_num>/delete", methods=["POST"])
    @admin_required
    def admin_delete_store(store_num):
        store_num = sanitize_store_num(store_num)
        for path in (get_store_config_path(store_num), get_auth_path(store_num)):
            if os.path.exists(path):
                os.remove(path)
        # If admin was editing this store, clear it from session
        if session.get("store") == store_num:
            session.pop("store", None)
            session.pop("admin_editing", None)
        flash(f"Store #{store_num} deleted.", "ok")
        return redirect(url_for("admin_dashboard"))
