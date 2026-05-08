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


def validate_config(cfg):
    if not isinstance(cfg, dict):
        raise ValueError("config must be a JSON object")
    if not isinstance(cfg.get("pages"), list):
        raise ValueError("missing or invalid 'pages' array")
    for i, page in enumerate(cfg["pages"]):
        if not isinstance(page, dict):
            raise ValueError(f"page {i} is not an object")
        if not isinstance(page.get("items", []), list):
            raise ValueError(f"page {i} has invalid 'items'")
    if "settings" in cfg and not isinstance(cfg["settings"], dict):
        raise ValueError("'settings' must be an object")
    if "tag_colors" in cfg and not isinstance(cfg["tag_colors"], dict):
        raise ValueError("'tag_colors' must be an object")
