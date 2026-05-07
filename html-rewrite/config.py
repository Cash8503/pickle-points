import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
CONFIG_PATH = os.path.join(APP_DIR, "pickle_points_config.json")
LEGACY_CONFIG_PATH = os.path.join(PROJECT_DIR, "pickle_points_config.json")

DEFAULT_FETCH_CONCURRENCY = 5
DEFAULT_PRICE_PER_PICKLE  = 0.50
DEFAULT_PICKLE_VALUE      = 1

def _default_config():
    return {
        "output_path": os.path.join(APP_DIR, "pickle-points-chart.pdf"),
        "pdf_title": "Pickle Points - Crew Merch Chart",
        "settings": {
            "fetch_concurrency": DEFAULT_FETCH_CONCURRENCY,
            "price_per_pickle": DEFAULT_PRICE_PER_PICKLE,
            "pickle_pickle_value": DEFAULT_PICKLE_VALUE,
        },
        "tag_colors": {
            "POPULAR": {"bg":"#FFF0B2","text":"#A07800"},
            "NEW":     {"bg":"#D6F0FF","text":"#0066A0"},
            "LIMITED": {"bg":"#E2F0CE","text":"#3D6010"},
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

def _write_config(path, cfg):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)

    if os.path.exists(LEGACY_CONFIG_PATH):
        with open(LEGACY_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        _write_config(CONFIG_PATH, cfg)
        return cfg

    cfg = _default_config()
    _write_config(CONFIG_PATH, cfg)
    return cfg

def save_config(cfg):
    _write_config(CONFIG_PATH, cfg)

def _get_setting(cfg, *keys, default=None):
    s = cfg.get("settings", {})
    for k in keys:
        if k in s: return s[k]
    return default
