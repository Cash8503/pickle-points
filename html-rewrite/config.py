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
_ADMIN_AUTH_FILE = os.path.join(APP_DIR, "admin.auth")

DEFAULT_FETCH_CONCURRENCY = 5
DEFAULT_PRICE_PER_PICKLE  = 0.50
DEFAULT_PICKLE_VALUE      = 1
_PBKDF2_ITERS = 100_000


# ── Store number helpers ───────────────────────────────────────────
def sanitize_store_num(s):
    return re.sub(r"[^a-zA-Z0-9]", "", str(s))[:20]


def get_store_config_path(store_num):
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    return os.path.join(CONFIGS_DIR, f"store_{store_num}.json")


def get_auth_path(store_num):
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    return os.path.join(CONFIGS_DIR, f"store_{store_num}.auth")


def list_store_nums():
    if not os.path.isdir(CONFIGS_DIR):
        return []
    nums = []
    for f in os.listdir(CONFIGS_DIR):
        if f.startswith("store_") and f.endswith(".json"):
            nums.append(f[6:-5])
    return nums


def get_store_metadata(store_num):
    """Return display metadata for the admin dashboard."""
    path = get_store_config_path(store_num)
    if not os.path.exists(path):
        return {"last_modified": None, "item_count": 0, "page_count": 0}
    mtime = os.path.getmtime(path)
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        pages = cfg.get("pages", [])
        item_count = sum(len(p.get("items", [])) for p in pages)
        return {"last_modified": mtime, "item_count": item_count, "page_count": len(pages)}
    except Exception:
        return {"last_modified": mtime, "item_count": 0, "page_count": 0}


# ── Store codeword auth ────────────────────────────────────────────
def store_has_codeword(store_num):
    return os.path.exists(get_auth_path(store_num))


def _hash_secret(secret):
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, _PBKDF2_ITERS)
    return salt.hex() + ":" + key.hex()


def _check_secret(secret, stored):
    try:
        salt_hex, key_hex = stored.strip().split(":", 1)
    except ValueError:
        return False
    key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERS)
    return hmac.compare_digest(key.hex(), key_hex)


def set_codeword(store_num, codeword):
    with open(get_auth_path(store_num), "w") as f:
        f.write(_hash_secret(codeword))


def verify_codeword(store_num, codeword):
    path = get_auth_path(store_num)
    if not os.path.exists(path):
        return False
    with open(path) as f:
        return _check_secret(codeword, f.read())


def clear_codeword(store_num):
    path = get_auth_path(store_num)
    if os.path.exists(path):
        os.remove(path)


# ── Admin password auth ────────────────────────────────────────────
def admin_has_password():
    return os.path.exists(_ADMIN_AUTH_FILE)


def set_admin_password(password):
    with open(_ADMIN_AUTH_FILE, "w") as f:
        f.write(_hash_secret(password))


def verify_admin_password(password):
    if not os.path.exists(_ADMIN_AUTH_FILE):
        return False
    with open(_ADMIN_AUTH_FILE) as f:
        return _check_secret(password, f.read())


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


