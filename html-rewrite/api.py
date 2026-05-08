import threading

from flask import jsonify, render_template, request

from config import load_config, save_config
from preview_render import render_preview_html
from services import fetch_smilemakers_product, prefetch_new_urls, resolve_items_for_preview


def register_routes(app):
    @app.route("/")
    def editor():
        return render_template("editor.html")

    @app.route("/api/config", methods=["GET"])
    def api_get_config():
        return jsonify(load_config())

    @app.route("/api/config", methods=["POST", "OPTIONS"])
    def api_post_config():
        if request.method == "OPTIONS":
            return "", 204
        try:
            cfg = request.get_json(force=True)
            save_config(cfg)
            threading.Thread(target=prefetch_new_urls, args=(cfg,), daemon=True).start()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/fetch-product", methods=["POST", "OPTIONS"])
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
            return jsonify(
                {
                    "name": name,
                    "desc": desc,
                    "image": image,
                    "price": price,
                    "sizes": sizes,
                }
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/preview")
    def preview():
        cfg = load_config()
        try:
            pages, per_pickle, pickle_value = resolve_items_for_preview(cfg)
        except Exception as exc:
            return f"<pre>Error resolving items:\n{exc}</pre>", 500
        return render_preview_html(
            pages,
            per_pickle,
            pickle_value,
            cfg.get("tag_colors", {}),
        )

    @app.route("/preview-frame")
    def preview_frame():
        cfg = load_config()
        try:
            pages, per_pickle, pickle_value = resolve_items_for_preview(cfg)
        except Exception as exc:
            return f"<pre>Error: {exc}</pre>", 500
        return render_preview_html(
            pages,
            per_pickle,
            pickle_value,
            cfg.get("tag_colors", {}),
        )
