import hashlib
import hmac
import json
import os
import re

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
CONFIGS_DIR = os.path.join(APP_DIR, "configs")
CONFIG_PATH = os.path.join(APP_DIR, "pickle_points_config.json")  # legacy single-store
LEGACY_CONFIG_PATH = os.path.join(PROJECT_DIR, "pickle_points_config.json")

DEFAULT_FETCH_CONCURRENCY = 5
DEFAULT_PRICE_PER_PICKLE  = 0.50
DEFAULT_PICKLE_VALUE      = 1

_PBKDF2_ITERS = 100_000


# ── Store number helpers ───────────────────────────────────────────
def sanitize_store_num(s):
    """Allow only alphanumeric characters, max 20 chars (prevents path traversal)."""
    return re.sub(r"[^a-zA-Z0-9]", "", str(s))[:20]


def get_store_config_path(store_num):
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    return os.path.join(CONFIGS_DIR, f"store_{store_num}.json")


def _get_auth_path(store_num):
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    return os.path.join(CONFIGS_DIR, f"store_{store_num}.auth")


def list_store_nums():
    """Return every store number that already has a saved config file."""
    if not os.path.isdir(CONFIGS_DIR):
        return []
    nums = []
    for f in os.listdir(CONFIGS_DIR):
        if f.startswith("store_") and f.endswith(".json"):
            nums.append(f[6:-5])
    return nums


# ── Codeword auth ──────────────────────────────────────────────────
def store_has_codeword(store_num):
    return os.path.exists(_get_auth_path(store_num))


def set_codeword(store_num, codeword):
    """Hash codeword with PBKDF2-HMAC-SHA256 and persist it."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", codeword.encode("utf-8"), salt, _PBKDF2_ITERS)
    with open(_get_auth_path(store_num), "w") as f:
        f.write(salt.hex() + ":" + key.hex())


def verify_codeword(store_num, codeword):
    """Return True if codeword matches the stored hash."""
    path = _get_auth_path(store_num)
    if not os.path.exists(path):
        return False
    with open(path) as f:
        stored = f.read().strip()
    try:
        salt_hex, key_hex = stored.split(":", 1)
    except ValueError:
        return False
    key = hashlib.pbkdf2_hmac("sha256", codeword.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERS)
    return hmac.compare_digest(key.hex(), key_hex)


# ── Config load / save ─────────────────────────────────────────────
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


def load_config(store_num=None):
    if store_num:
        path = get_store_config_path(store_num)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        cfg = _default_config()
        _write_config(path, cfg)
        return cfg

    # Legacy single-store fallback
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


def save_config(cfg, store_num=None):
    if store_num:
        _write_config(get_store_config_path(store_num), cfg)
    else:
        _write_config(CONFIG_PATH, cfg)


def _get_setting(cfg, *keys, default=None):
    s = cfg.get("settings", {})
    for k in keys:
        if k in s: return s[k]
    return default
