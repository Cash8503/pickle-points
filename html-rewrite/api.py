import hmac
import io
import json
import logging
import secrets
import threading
import time
import zipfile
from collections import defaultdict
from functools import wraps

from flask import (flash, get_flashed_messages, jsonify, redirect,
                   render_template, request, Response, session, url_for)

from auth_db import (admin_count, check_password, clear_password, create_user,
                     delete_user, get_user, get_user_stores, has_any_admin,
                     list_users, set_password, set_user_dark_mode, update_user)
from config import (audit_log, backup_config, delete_store_config,
                    get_store_metadata, list_store_nums, load_config,
                    sanitize_store_num, save_config, set_store_notes,
                    store_config_exists)
from config_schema import validate_config
from order_render import render_order_tracker_html
from preview_render import render_preview_html
from services import (cache_entries, cache_entries_for_urls, clear_cache,
                      fetch_smilemakers_product, get_cache_warm_status,
                      prefetch_new_urls, resolve_items_for_preview,
                      start_cache_refetch_urls, start_cache_warm)

logger = logging.getLogger(__name__)


def _smilemakers_urls(cfg):
    urls = []
    for page in cfg.get("pages", []):
        for item in page.get("items", []):
            if item.get("type") != "smilemakers":
                continue
            for url in item.get("urls") or []:
                if url:
                    urls.append(url)
    return urls

# ── Rate limiting ─────────────────────────────────────────────────
_failed_logins: dict  = defaultdict(list)   # ip -> [timestamp, ...]
_rate_lock             = threading.Lock()
_RATE_WINDOW           = 300   # 5-minute sliding window
_RATE_MAX              = 10    # max failures before lockout
_RATE_LOCKOUT          = 900   # 15-minute lockout


def _is_rate_limited(ip: str) -> bool:
    with _rate_lock:
        now    = time.time()
        recent = [t for t in _failed_logins[ip] if now - t < _RATE_LOCKOUT]
        _failed_logins[ip] = recent
        return sum(1 for t in recent if now - t < _RATE_WINDOW) >= _RATE_MAX


def _record_failed_login(ip: str):
    with _rate_lock:
        _failed_logins[ip].append(time.time())


def _clear_failed_logins(ip: str):
    with _rate_lock:
        _failed_logins.pop(ip, None)


def _brief_list(items, limit=5):
    values = [str(item) for item in items if str(item)]
    if len(values) <= limit:
        return ", ".join(values)
    return ", ".join(values[:limit]) + f", +{len(values) - limit} more"


def _json_error(exc):
    if isinstance(exc, json.JSONDecodeError):
        return f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    if isinstance(exc, UnicodeDecodeError):
        return "file must be UTF-8 encoded JSON"
    return str(exc)


# ── Decorators ────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return f(*args, **kwargs)
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not logged in"}), 401
            return redirect(url_for("login"))
        if "store" not in session:
            stores = get_user_stores(session["user_id"])
            if len(stores) == 1:
                session["store"] = stores[0]
            elif len(stores) > 1:
                return redirect(url_for("pick_store"))
            elif session.get("is_admin"):
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session or not session.get("is_admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def _do_login(user_id):
    user = get_user(user_id=user_id)
    stores = get_user_stores(user_id)
    session.clear()
    session["user_id"]   = user_id
    session["username"]  = user["username"]
    session["real_name"] = user["real_name"]
    session["is_admin"]  = bool(user["is_admin"])
    session["dark_mode"] = bool(user.get("dark_mode"))
    if len(stores) == 1:
        session["store"] = stores[0]
        return redirect(url_for("editor"))
    if len(stores) > 1:
        return redirect(url_for("pick_store"))
    if user["is_admin"]:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("login"))


def register_routes(app):

    # ── CSRF ──────────────────────────────────────────────────────
    @app.before_request
    def _ensure_csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)

    @app.before_request
    def _enforce_csrf():
        if request.method != "POST" or request.path.startswith("/api/"):
            return
        token    = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not hmac.compare_digest(token, expected):
            logger.warning("CSRF check failed: path=%s ip=%s", request.path, request.remote_addr)
            flash("Your session expired. Please try again.", "err")
            return redirect(request.referrer or url_for("login"))

    app.jinja_env.globals["csrf_token"] = lambda: session.get("csrf_token", "")

    # ── Auth ──────────────────────────────────────────────────────
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "user_id" in session:
            if session.get("store"):
                return redirect(url_for("editor"))
            if session.get("is_admin"):
                return redirect(url_for("admin_dashboard"))

        # First-run: no admin exists yet
        if not has_any_admin():
            error = None
            if request.method == "POST" and request.form.get("action") == "setup_admin":
                username  = request.form.get("username", "").strip()
                real_name = request.form.get("real_name", "").strip()
                password  = request.form.get("password", "")
                confirm   = request.form.get("confirm", "")
                if not username or not real_name:
                    error = "Username and name are required."
                elif len(password) < 6:
                    error = "Password must be at least 6 characters."
                elif password != confirm:
                    error = "Passwords do not match."
                else:
                    uid = create_user(username, real_name, is_admin=True)
                    set_password(uid, password)
                    audit_log("setup_admin", f"username={username}")
                    return _do_login(uid)
            return render_template("login.html", step="first_run", error=error)

        error = None
        step     = "username"
        user_id  = None
        username = None

        if request.method == "POST":
            ip     = request.remote_addr
            action = request.form.get("action", "check_username")

            if _is_rate_limited(ip):
                error = "Too many failed attempts. Please wait a few minutes and try again."
                return render_template("login.html", step=step, user_id=user_id,
                                       username=username, error=error)

            if action == "check_username":
                uname = request.form.get("username", "").strip()
                user  = get_user(username=uname)
                if not user:
                    _record_failed_login(ip)
                    error = "Username not found."
                elif not user["password_hash"]:
                    step     = "set_password"
                    user_id  = user["id"]
                    username = user["username"]
                else:
                    step     = "password"
                    user_id  = user["id"]
                    username = user["username"]

            elif action == "set_password":
                user_id  = int(request.form.get("user_id", 0))
                password = request.form.get("password", "")
                confirm  = request.form.get("confirm", "")
                user     = get_user(user_id=user_id)
                if not user:
                    error = "Invalid session. Please start over."
                elif user["password_hash"]:
                    error = "This account already has a password. Please log in normally."
                    step  = "password"
                elif len(password) < 6:
                    error   = "Password must be at least 6 characters."
                    step    = "set_password"
                elif password != confirm:
                    error   = "Passwords do not match."
                    step    = "set_password"
                else:
                    username = user["username"]
                    set_password(user_id, password)
                    audit_log("password_set", f"user_id={user_id}")
                    _clear_failed_logins(ip)
                    return _do_login(user_id)

            elif action == "login":
                user_id  = int(request.form.get("user_id", 0))
                password = request.form.get("password", "")
                user     = get_user(user_id=user_id)
                if user:
                    username = user["username"]
                if check_password(user_id, password):
                    _clear_failed_logins(ip)
                    return _do_login(user_id)
                _record_failed_login(ip)
                error = "Incorrect password."
                step  = "password"

        return render_template("login.html", step=step, user_id=user_id,
                               username=username, error=error)

    @app.route("/logout")
    def logout():
        was_admin = session.get("is_admin") and session.get("admin_editing")
        session.pop("store", None)
        session.pop("admin_editing", None)
        if was_admin:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("login"))

    @app.route("/signout")
    def signout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/user/dark-mode", methods=["POST"])
    def user_dark_mode():
        if "user_id" not in session:
            if request.headers.get("Accept") == "application/json":
                return jsonify({"ok": False, "error": "Not logged in"}), 401
            return redirect(url_for("login"))
        raw = request.form.get("dark_mode")
        if raw is None and request.is_json:
            raw = (request.get_json(silent=True) or {}).get("dark_mode")
        enabled = str(raw).lower() in {"1", "true", "on", "yes"}
        set_user_dark_mode(session["user_id"], enabled)
        session["dark_mode"] = enabled
        if request.headers.get("Accept") == "application/json" or request.form.get("ajax") == "1":
            return jsonify({"ok": True, "dark_mode": enabled})
        return redirect(request.referrer or url_for("editor"))

    @app.route("/pick-store", methods=["GET", "POST"])
    def pick_store():
        if "user_id" not in session:
            return redirect(url_for("login"))
        stores = get_user_stores(session["user_id"]) if not session.get("is_admin") else list_store_nums()
        if request.method == "POST":
            chosen = sanitize_store_num(request.form.get("store", ""))
            if chosen and (session.get("is_admin") or chosen in stores):
                session["store"] = chosen
                return redirect(url_for("editor"))
        return render_template("login.html", step="pick_store", stores=sorted(stores))

    # ── Admin compat redirect ────────────────────────────────────
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        return redirect(url_for("login"))

    @app.route("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect(url_for("login"))

    # ── Editor ────────────────────────────────────────────────────
    @app.route("/")
    @login_required
    def editor():
        if session.get("is_admin"):
            switch_stores = sorted(list_store_nums())
        else:
            switch_stores = get_user_stores(session["user_id"])
        user = get_user(user_id=session["user_id"])
        dark_mode = bool(user and user.get("dark_mode"))
        session["dark_mode"] = dark_mode
        return render_template("editor.html",
                               store_num=session["store"],
                               admin_editing=session.get("admin_editing", False),
                               is_admin=session.get("is_admin", False),
                               dark_mode=dark_mode,
                               switch_stores=switch_stores)

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
            cfg    = request.get_json(force=True)
            validate_config(cfg)
            editor = session.get("real_name", "unknown")
            if session.get("admin_editing"):
                editor += " (Admin)"
            save_config(cfg, session["store"], editor=editor)
            threading.Thread(target=prefetch_new_urls, args=(cfg,), daemon=True).start()
            return jsonify({"ok": True})
        except ValueError as exc:
            logger.warning("Config validation failed for store %s: %s", session.get("store"), exc)
            return jsonify({"ok": False, "error": str(exc)}), 400
        except OSError as exc:
            logger.error("Config save failed for store %s: %s", session.get("store"), exc)
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/fetch-product", methods=["POST", "OPTIONS"])
    @login_required
    def api_fetch_product():
        if request.method == "OPTIONS":
            return "", 204
        data = request.get_json(force=True)
        url  = (data or {}).get("url", "").strip()
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        try:
            name, desc, image, price, size_variants = fetch_smilemakers_product(url)
            if not name and not image:
                return jsonify({"error": "No product info found. Check the URL or try again."}), 502
            sizes = [v["value"] for v in size_variants if v.get("type") == "size"]
            return jsonify({"name": name, "desc": desc, "image": image,
                            "price": price, "sizes": sizes})
        except Exception as exc:
            logger.error("Product fetch failed for %s: %s", url, exc)
            return jsonify({"error": str(exc)}), 500

    # ── Preview ───────────────────────────────────────────────────
    @app.route("/preview")
    @login_required
    def preview():
        cfg = load_config(session["store"])
        try:
            pages, per_pickle, pickle_value = resolve_items_for_preview(cfg)
        except Exception as exc:
            logger.error("Preview render failed for store %s: %s", session.get("store"), exc)
            return f"<pre>Error resolving items:\n{exc}</pre>", 500
        page_idx = request.args.get("page", type=int)
        if page_idx is not None and 0 <= page_idx < len(pages):
            pages = [pages[page_idx]]
        return render_preview_html(pages, per_pickle, pickle_value, cfg.get("tag_colors", {}))

    @app.route("/preview-frame")
    @login_required
    def preview_frame():
        cfg = load_config(session["store"])
        try:
            pages, per_pickle, pickle_value = resolve_items_for_preview(cfg)
        except Exception as exc:
            logger.error("Preview frame render failed for store %s: %s", session.get("store"), exc)
            return f"<pre>Error: {exc}</pre>", 500
        page_idx = request.args.get("page", type=int)
        if page_idx is not None and 0 <= page_idx < len(pages):
            pages = [pages[page_idx]]
        return render_preview_html(pages, per_pickle, pickle_value, cfg.get("tag_colors", {}))

    @app.route("/order-tracker")
    @login_required
    def order_tracker():
        cfg = load_config(session["store"])
        try:
            pages, per_pickle, pickle_value = resolve_items_for_preview(cfg)
        except Exception as exc:
            logger.error("Order tracker render failed for store %s: %s", session.get("store"), exc)
            return f"<pre>Error resolving items:\n{exc}</pre>", 500
        return render_order_tracker_html(pages, per_pickle, pickle_value, session["store"])

    @app.route("/order-tracker-frame")
    @login_required
    def order_tracker_frame():
        cfg = load_config(session["store"])
        try:
            pages, per_pickle, pickle_value = resolve_items_for_preview(cfg)
        except Exception as exc:
            logger.error("Order tracker frame render failed for store %s: %s", session.get("store"), exc)
            return f"<pre>Error: {exc}</pre>", 500
        return render_order_tracker_html(pages, per_pickle, pickle_value, session["store"])

    # ── Admin dashboard ───────────────────────────────────────────
    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        stores = []
        store_nums = sorted(list_store_nums())
        cfgs = []
        for num in store_nums:
            meta = get_store_metadata(num)
            stores.append({"num": num, **meta})
            cfgs.append(load_config(num))
        smilemakers_urls = []
        for cfg in cfgs:
            smilemakers_urls.extend(_smilemakers_urls(cfg))
        users = list_users()
        msgs  = get_flashed_messages(with_categories=True)
        user = get_user(user_id=session["user_id"])
        dark_mode = bool(user and user.get("dark_mode"))
        session["dark_mode"] = dark_mode
        return render_template(
            "admin.html",
            stores=stores,
            users=users,
            messages=msgs,
            cache_entries=cache_entries_for_urls(smilemakers_urls),
            cache_warm_status=get_cache_warm_status(),
            dark_mode=dark_mode,
        )

    @app.route("/admin/store/<store_num>/edit")
    @admin_required
    def admin_edit_store(store_num):
        store_num = sanitize_store_num(store_num)
        session["store"]         = store_num
        session["admin_editing"] = True
        return redirect(url_for("editor"))

    @app.route("/admin/store/back")
    @admin_required
    def admin_back():
        session.pop("store", None)
        session.pop("admin_editing", None)
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/cache/clear-url", methods=["POST"])
    @admin_required
    def admin_cache_clear_url():
        url = request.form.get("url", "").strip()
        if not url:
            if request.headers.get("X-Pickle-Ajax") == "1":
                return jsonify({"ok": False, "error": "No URL provided."})
            flash("No cache URL provided.", "err")
        else:
            clear_cache(url)
            audit_log("clear_cache_url", f"by={session.get('username')} url={url}")
            if request.headers.get("X-Pickle-Ajax") == "1":
                return jsonify({"ok": True})
            flash("Cached URL cleared.", "ok")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/cache/refetch-url", methods=["POST"])
    @admin_required
    def admin_cache_refetch_url():
        url = request.form.get("url", "").strip()
        if not url:
            if request.headers.get("X-Pickle-Ajax") == "1":
                return jsonify({"ok": False, "error": "No URL provided."})
            flash("No cache URL provided.", "err")
        else:
            clear_cache(url)
            name, _, image, _, _ = fetch_smilemakers_product(url)
            audit_log("refetch_cache_url", f"by={session.get('username')} url={url}")
            if request.headers.get("X-Pickle-Ajax") == "1":
                return jsonify({"ok": bool(name or image)})
            flash("Cached URL refreshed." if (name or image) else "URL refetch returned no product data.", "ok" if (name or image) else "err")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/cache/clear-all", methods=["POST"])
    @admin_required
    def admin_cache_clear_all():
        count = len(cache_entries())
        clear_cache()
        audit_log("clear_cache_all", f"by={session.get('username')} count={count}")
        if request.headers.get("X-Pickle-Ajax") == "1":
            return jsonify({"ok": True, "count": count})
        flash(f"Cleared {count} cache entr{'y' if count == 1 else 'ies'}.", "ok")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/cache/status")
    @admin_required
    def admin_cache_status():
        store_nums = sorted(list_store_nums())
        cfgs = [load_config(num) for num in store_nums]
        urls = []
        for cfg in cfgs:
            urls.extend(_smilemakers_urls(cfg))
        entries = cache_entries_for_urls(urls)
        warm = get_cache_warm_status()
        def _fmt(e):
            return {
                "url": e["url"],
                "status": e.get("status", "missing"),
                "configured": e.get("configured", False),
                "name": e.get("name") or "",
                "image": e.get("image") or "",
                "price": e.get("price"),
                "fetched_at": e.get("fetched_at"),
                "failed_at": e.get("failed_at"),
                "error": e.get("error") or "",
            }
        return jsonify({
            "warm_status": warm,
            "entries": [_fmt(e) for e in entries],
            "count": len(entries),
        })

    @app.route("/admin/cache/warm-all", methods=["POST"])
    @admin_required
    def admin_cache_warm_all():
        store_nums = list_store_nums()
        cfgs = [load_config(num) for num in store_nums]
        started, state = start_cache_warm(cfgs, include_cached=False, label="Warm all stores")
        audit_log("warm_cache_all", f"by={session.get('username')} stores={len(store_nums)}")
        if request.headers.get("X-Pickle-Ajax") == "1":
            return jsonify({"ok": True, "started": started})
        if started:
            flash(f"Started cache warming for {len(store_nums)} store{'' if len(store_nums) == 1 else 's'}; {state['total']} URL{'' if state['total'] == 1 else 's'} queued.", "ok")
        else:
            flash(f"Cache warming is already running: {state['done']}/{state['total']} URL{'' if state['total'] == 1 else 's'} checked.", "err")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/cache/refetch-needed", methods=["POST"])
    @admin_required
    def admin_cache_refetch_needed():
        store_nums = list_store_nums()
        cfgs = [load_config(num) for num in store_nums]
        urls = []
        for cfg in cfgs:
            urls.extend(_smilemakers_urls(cfg))
        rows = cache_entries_for_urls(urls)
        targets = [row["url"] for row in rows if row.get("configured") and row.get("status") in {"failed", "missing"}]
        if not targets:
            if request.headers.get("X-Pickle-Ajax") == "1":
                return jsonify({"ok": True, "started": False, "message": "Nothing to refetch."})
            flash("No failed or uncached SmileMakers URLs need refetching.", "ok")
            return redirect(url_for("admin_dashboard"))
        started, state = start_cache_refetch_urls(targets, label="Refetch needed URLs")
        audit_log("refetch_needed_cache", f"by={session.get('username')} count={len(targets)}")
        if request.headers.get("X-Pickle-Ajax") == "1":
            return jsonify({"ok": True, "started": started})
        if started:
            flash(f"Started refetch for {len(targets)} failed or uncached URL{'' if len(targets) == 1 else 's'}.", "ok")
        else:
            flash(f"Cache warming is already running: {state['done']}/{state['total']} URL{'' if state['total'] == 1 else 's'} checked.", "err")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/store/<store_num>/copy-config", methods=["POST"])
    @admin_required
    def admin_copy_config(store_num):
        store_num = sanitize_store_num(store_num)
        source    = sanitize_store_num(request.form.get("source", ""))
        if not source:
            flash("No source store specified.", "err")
        elif source == store_num:
            flash("Source and destination are the same store.", "err")
        else:
            backup_config(store_num)
            cfg = load_config(source)
            save_config(cfg, store_num, editor=f"{session.get('real_name', 'Admin')} (Admin)")
            audit_log("copy_config", f"by={session.get('username')} source={source} dest={store_num}")
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
                limit = 10 * 1024 * 1024
                data = f.read(limit + 1)
                if len(data) > limit:
                    raise ValueError("JSON file is too large; max size is 10 MB")
                cfg  = json.loads(data.decode("utf-8"))
                validate_config(cfg)
                backup_config(store_num)
                save_config(cfg, store_num, editor=f"{session.get('real_name', 'Admin')} (Admin)")
                audit_log("upload_config", f"by={session.get('username')} store={store_num}")
                flash(f"Uploaded config for Store #{store_num}; backup saved first.", "ok")
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                flash(f"Upload rejected for Store #{store_num}: {_json_error(exc)}", "err")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/store/<store_num>/delete", methods=["POST"])
    @admin_required
    def admin_delete_store(store_num):
        store_num = sanitize_store_num(store_num)
        confirm   = request.form.get("confirm_store_num", "").strip()
        if confirm != store_num:
            flash(f"Store number did not match. Deletion cancelled.", "err")
            return redirect(url_for("admin_dashboard"))
        backup_config(store_num)
        delete_store_config(store_num)
        if session.get("store") == store_num:
            session.pop("store", None)
            session.pop("admin_editing", None)
        audit_log("delete_store", f"by={session.get('username')} store={store_num}")
        flash(f"Store #{store_num} deleted (backup saved).", "ok")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/stores/create", methods=["POST"])
    @admin_required
    def admin_create_store():
        store_num = sanitize_store_num(request.form.get("store_num", ""))
        if not store_num:
            flash("Store number is required.", "err")
            return redirect(url_for("admin_dashboard"))
        if store_config_exists(store_num):
            flash(f"Store #{store_num} already exists.", "err")
            return redirect(url_for("admin_dashboard"))
        load_config(store_num)
        audit_log("create_store", f"by={session.get('username')} store={store_num}")
        flash(f"Store #{store_num} created.", "ok")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/stores/export.zip")
    @admin_required
    def admin_export_stores_zip():
        buf = io.BytesIO()
        store_nums = list_store_nums()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            manifest = {"stores": store_nums, "exported_at": time.time()}
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            for store_num in store_nums:
                cfg = load_config(store_num)
                zf.writestr(f"stores/store_{store_num}.json", json.dumps(cfg, indent=2))
        buf.seek(0)
        audit_log("export_all_stores", f"by={session.get('username')} count={len(store_nums)}")
        return Response(
            buf.getvalue(),
            mimetype="application/zip",
            headers={"Content-Disposition": "attachment; filename=pickle_points_stores.zip"},
        )

    @app.route("/admin/stores/import", methods=["POST"])
    @admin_required
    def admin_import_stores_zip():
        f = request.files.get("stores_zip")
        if not f:
            flash("No zip file selected.", "err")
            return redirect(url_for("admin_dashboard"))
        try:
            limit = 25 * 1024 * 1024
            data = f.read(limit + 1)
            if len(data) > limit:
                raise ValueError("zip file is too large; max size is 25 MB")
            validated = []
            skipped = []
            failed = []
            seen = set()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename
                    base = name.rsplit("/", 1)[-1]
                    if not (base.startswith("store_") and base.endswith(".json")):
                        continue
                    raw_store_num = base[6:-5]
                    store_num = sanitize_store_num(raw_store_num)
                    if not store_num:
                        skipped.append(f"{base} (invalid store number)")
                        continue
                    if store_num in seen:
                        skipped.append(f"Store #{store_num} duplicate")
                        continue
                    seen.add(store_num)
                    try:
                        cfg = json.loads(zf.read(info).decode("utf-8"))
                        validate_config(cfg)
                        validated.append((store_num, cfg))
                    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                        failed.append(f"Store #{store_num}: {_json_error(exc)}")

            if failed:
                msg = "Import rejected before writing any configs. Failed: " + _brief_list(failed, limit=3)
                if skipped:
                    msg += ". Skipped: " + _brief_list(skipped, limit=3)
                flash(msg, "err")
                return redirect(url_for("admin_dashboard"))
            if not validated:
                msg = "Import rejected: no store_*.json config files found."
                if skipped:
                    msg += " Skipped: " + _brief_list(skipped, limit=3)
                flash(msg, "err")
                return redirect(url_for("admin_dashboard"))

            imported = []
            backed_up = []
            for store_num, cfg in validated:
                if store_config_exists(store_num):
                    backup_config(store_num)
                    backed_up.append(f"#{store_num}")
                save_config(cfg, store_num, editor=f"{session.get('real_name', 'Admin')} (Admin import)")
                imported.append(f"#{store_num}")

            audit_log(
                "import_all_stores",
                f"by={session.get('username')} imported={len(imported)} skipped={len(skipped)} backups={len(backed_up)}",
            )
            msg = f"Imported {len(imported)} store config{'' if len(imported) == 1 else 's'}: {_brief_list(imported)}."
            if backed_up:
                msg += f" Backups saved for existing stores: {_brief_list(backed_up)}."
            if skipped:
                msg += f" Skipped: {_brief_list(skipped, limit=3)}."
            flash(msg, "ok")
        except (zipfile.BadZipFile, ValueError, OSError) as exc:
            flash(f"Import rejected before writing any configs: {exc}", "err")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/store/<store_num>/notes", methods=["POST"])
    @admin_required
    def admin_save_store_notes(store_num):
        store_num = sanitize_store_num(store_num)
        notes     = request.form.get("notes", "")
        set_store_notes(store_num, notes)
        audit_log("save_notes", f"by={session.get('username')} store={store_num}")
        flash(f"Notes saved for Store #{store_num}.", "ok")
        return redirect(url_for("admin_dashboard"))

    # ── Admin user management ─────────────────────────────────────
    @app.route("/admin/users/create", methods=["POST"])
    @admin_required
    def admin_create_user():
        username  = request.form.get("username", "").strip()
        real_name = request.form.get("real_name", "").strip()
        is_admin   = bool(request.form.get("is_admin"))
        store_nums = [sanitize_store_num(s) for s in request.form.getlist("stores") if s.strip()]
        store_nums = [s for s in store_nums if s]

        if not username or not real_name:
            flash("Username and name are required.", "err")
            return redirect(url_for("admin_dashboard"))
        if get_user(username=username):
            flash(f"Username '{username}' is already taken.", "err")
            return redirect(url_for("admin_dashboard"))
        try:
            create_user(username, real_name, is_admin=is_admin, store_nums=store_nums)
            audit_log("create_user", f"by={session.get('username')} new={username}")
            flash(f"User '{username}' created. They can set their password on first login.", "ok")
        except Exception as exc:
            logger.error("create_user failed: %s", exc)
            flash(f"Could not create user: {exc}", "err")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_edit_user(user_id):
        user   = get_user(user_id=user_id)
        stores = get_user_stores(user_id)
        if not user:
            flash("User not found.", "err")
            return redirect(url_for("admin_dashboard"))

        error = None
        if request.method == "POST":
            new_username  = request.form.get("username", "").strip()
            new_real_name = request.form.get("real_name", "").strip()
            new_is_admin  = bool(request.form.get("is_admin"))
            new_stores    = [sanitize_store_num(s) for s in request.form.getlist("stores") if s.strip()]
            new_stores    = [s for s in new_stores if s]

            if not new_username or not new_real_name:
                error = "Username and name are required."
            elif not new_is_admin and user["is_admin"] and admin_count() <= 1:
                error = "Cannot remove admin from the last admin account."
            else:
                try:
                    update_user(user_id,
                                username=new_username,
                                real_name=new_real_name,
                                is_admin=new_is_admin,
                                store_nums=new_stores)
                    audit_log("edit_user", f"by={session.get('username')} user_id={user_id}")
                    if user_id == session.get("user_id"):
                        session["username"]  = new_username
                        session["real_name"] = new_real_name
                        session["is_admin"]  = new_is_admin
                    flash(f"User '{new_username}' updated.", "ok")
                    return redirect(url_for("admin_dashboard"))
                except Exception as exc:
                    error = str(exc)

        all_stores = sorted(list_store_nums())
        current_user = get_user(user_id=session["user_id"])
        dark_mode = bool(current_user and current_user.get("dark_mode"))
        session["dark_mode"] = dark_mode
        return render_template("admin_edit_user.html",
                               user=user, stores=stores, all_stores=all_stores,
                               error=error, dark_mode=dark_mode)

    @app.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
    @admin_required
    def admin_reset_user_password(user_id):
        user = get_user(user_id=user_id)
        if not user:
            flash("User not found.", "err")
            return redirect(url_for("admin_dashboard"))
        clear_password(user_id)
        audit_log("reset_password", f"by={session.get('username')} user_id={user_id}")
        flash(f"Password cleared for '{user['username']}'. They will set a new one on next login.", "ok")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_user(user_id):
        if user_id == session.get("user_id"):
            flash("You cannot delete your own account.", "err")
            return redirect(url_for("admin_dashboard"))
        user = get_user(user_id=user_id)
        if not user:
            flash("User not found.", "err")
            return redirect(url_for("admin_dashboard"))
        if user["is_admin"] and admin_count() <= 1:
            flash("Cannot delete the last admin account.", "err")
            return redirect(url_for("admin_dashboard"))
        delete_user(user_id)
        audit_log("delete_user", f"by={session.get('username')} deleted={user['username']}")
        flash(f"User '{user['username']}' deleted.", "ok")
        return redirect(url_for("admin_dashboard"))
