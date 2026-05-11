import os

DEFAULT_FETCH_CONCURRENCY = 5
DEFAULT_PRICE_PER_PICKLE = 0.50
DEFAULT_PICKLE_VALUE = 1


def default_config(app_dir):
    return {
        "output_path": os.path.join(app_dir, "pickle-points-chart.pdf"),
        "pdf_title": "Pickle Points - Crew Merch Chart",
        "settings": {
            "fetch_concurrency": DEFAULT_FETCH_CONCURRENCY,
            "price_per_pickle": DEFAULT_PRICE_PER_PICKLE,
            "pickle_chip_value": DEFAULT_PICKLE_VALUE,
        },
        "tag_colors": {
            "POPULAR": {"bg": "#FFF0B2", "text": "#A07800"},
            "NEW": {"bg": "#D6F0FF", "text": "#0066A0"},
            "LIMITED": {"bg": "#E2F0CE", "text": "#3D6010"},
        },
        "pages": [{
            "title": "Always Available",
            "subtitle": "Redeem your pickles for crew gear!",
            "section_label": "Classic Merch - Always Available",
            "accent": "#DA291C",
            "items": [],
            "layout": {"cols": 4},
        }],
    }


def _fail(path, message):
    raise ValueError(f"{path}: {message}")


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_config(cfg):
    if not isinstance(cfg, dict):
        _fail("$", "config must be a JSON object")
    if not isinstance(cfg.get("pages"), list):
        _fail("pages", "must be an array")

    settings = cfg.get("settings", {})
    if "settings" in cfg and not isinstance(settings, dict):
        _fail("settings", "must be an object")
    if isinstance(settings, dict):
        if "fetch_concurrency" in settings:
            value = settings["fetch_concurrency"]
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                _fail("settings.fetch_concurrency", "must be an integer of 1 or greater")
        if "price_per_pickle" in settings:
            value = settings["price_per_pickle"]
            if not _is_number(value) or value <= 0:
                _fail("settings.price_per_pickle", "must be a number greater than 0")
        if "pickle_chip_value" in settings:
            value = settings["pickle_chip_value"]
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                _fail("settings.pickle_chip_value", "must be an integer of 1 or greater")

    tag_colors = cfg.get("tag_colors", {})
    if "tag_colors" in cfg and not isinstance(tag_colors, dict):
        _fail("tag_colors", "must be an object")
    if isinstance(tag_colors, dict):
        for tag, colors in tag_colors.items():
            path = f"tag_colors.{tag}"
            if not isinstance(colors, dict):
                _fail(path, "must be an object with bg/text colors")
            for key in ("bg", "text"):
                if key in colors and not isinstance(colors[key], str):
                    _fail(f"{path}.{key}", "must be a color string")

    for i, page in enumerate(cfg["pages"]):
        page_path = f"pages[{i}]"
        if not isinstance(page, dict):
            _fail(page_path, "must be an object")
        if "title" in page and not isinstance(page["title"], str):
            _fail(f"{page_path}.title", "must be text")
        if "subtitle" in page and not isinstance(page["subtitle"], str):
            _fail(f"{page_path}.subtitle", "must be text")
        layout = page.get("layout", {})
        if "layout" in page and not isinstance(layout, dict):
            _fail(f"{page_path}.layout", "must be an object")
        if isinstance(layout, dict) and "cols" in layout:
            cols = layout["cols"]
            if not isinstance(cols, int) or isinstance(cols, bool) or not 1 <= cols <= 6:
                _fail(f"{page_path}.layout.cols", "must be an integer from 1 to 6")

        items = page.get("items", [])
        if not isinstance(items, list):
            _fail(f"{page_path}.items", "must be an array")
        for j, item in enumerate(items):
            item_path = f"{page_path}.items[{j}]"
            if not isinstance(item, dict):
                _fail(item_path, "must be an object")
            item_type = item.get("type", "manual")
            if item_type not in {"manual", "smilemakers"}:
                _fail(f"{item_path}.type", "must be 'manual' or 'smilemakers'")
            if item_type == "smilemakers":
                urls = item.get("urls", [])
                if not isinstance(urls, list):
                    _fail(f"{item_path}.urls", "must be an array")
                if not urls:
                    _fail(f"{item_path}.urls", "must include at least one SmileMakers URL")
                for k, url in enumerate(urls):
                    if not isinstance(url, str) or not url.strip():
                        _fail(f"{item_path}.urls[{k}]", "must be a non-empty URL")
            else:
                if "name" in item and not isinstance(item["name"], str):
                    _fail(f"{item_path}.name", "must be text")
                if "pickles" in item:
                    pickles = item["pickles"]
                    if not isinstance(pickles, int) or isinstance(pickles, bool) or pickles < 0:
                        _fail(f"{item_path}.pickles", "must be an integer of 0 or greater")
