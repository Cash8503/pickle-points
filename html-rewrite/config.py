import datetime
import json
import logging
import os
import sqlite3
import time

from auth_db import DB_PATH

APP_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
CONFIGS_DIR = os.path.join(APP_DIR, "configs")  # kept for audit log + migration scan
AUDIT_LOG_PATH = os.path.join(CONFIGS_DIR, "audit.log")

# Legacy JSON directory — scanned once during migration
_LEGACY_JSON_DIR = CONFIGS_DIR

DEFAULT_FETCH_CONCURRENCY = 5
DEFAULT_PRICE_PER_PICKLE  = 0.50
DEFAULT_PICKLE_VALUE      = 1

logger = logging.getLogger(__name__)


# ── DB helpers ────────────────────────────────────────────────
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Store number helpers ──────────────────────────────────────
def sanitize_store_num(s):
    import re
    return re.sub(r"[^a-zA-Z0-9]", "", str(s))[:20]


def list_store_nums():
    with _db() as conn:
        rows = conn.execute(
            "SELECT store_num FROM store_configs ORDER BY store_num"
        ).fetchall()
        return [r["store_num"] for r in rows]


def store_config_exists(store_num):
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM store_configs WHERE store_num=?", (store_num,)
        ).fetchone()
        return row is not None


def get_store_metadata(store_num):
    with _db() as conn:
        row = conn.execute(
            "SELECT config_json, last_edited_at, last_edited_by FROM store_configs WHERE store_num=?",
            (store_num,),
        ).fetchone()
    if not row:
        return {"last_modified": None, "last_edited_by": None, "item_count": 0, "page_count": 0}
    try:
        cfg   = json.loads(row["config_json"])
        pages = cfg.get("pages", [])
        return {
            "last_modified":  row["last_edited_at"],
            "last_edited_by": row["last_edited_by"],
            "item_count":     sum(len(p.get("items", [])) for p in pages),
            "page_count":     len(pages),
        }
    except (json.JSONDecodeError, KeyError):
        return {
            "last_modified":  row["last_edited_at"],
            "last_edited_by": row["last_edited_by"],
            "item_count": 0, "page_count": 0,
        }


# ── Config load / save ────────────────────────────────────────
def _default_config():
    return {
        "output_path": os.path.join(APP_DIR, "pickle-points-chart.pdf"),
        "pdf_title": "Pickle Points - Crew Merch Chart",
        "settings": {
            "fetch_concurrency": DEFAULT_FETCH_CONCURRENCY,
            "price_per_pickle":  DEFAULT_PRICE_PER_PICKLE,
            "pickle_chip_value": DEFAULT_PICKLE_VALUE,
        },
        "tag_colors": {
            "POPULAR": {"bg": "#FFF0B2", "text": "#A07800"},
            "NEW":     {"bg": "#D6F0FF", "text": "#0066A0"},
            "LIMITED": {"bg": "#E2F0CE", "text": "#3D6010"},
        },
        "pages": [{
            "title":         "Always Available",
            "subtitle":      "Redeem your pickles for crew gear!",
            "section_label": "Classic Merch - Always Available",
            "accent":        "#DA291C",
            "items":         [],
            "layout":        {"cols": 4},
        }],
    }


def _db_upsert(store_num, cfg):
    with _db() as conn:
        conn.execute(
            """INSERT INTO store_configs
                   (store_num, config_json, last_edited_at, last_edited_by, created_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(store_num) DO UPDATE SET
                   config_json    = excluded.config_json,
                   last_edited_at = excluded.last_edited_at,
                   last_edited_by = excluded.last_edited_by""",
            (
                store_num,
                json.dumps(cfg, ensure_ascii=False),
                cfg.get("last_edited_at"),
                cfg.get("last_edited_by"),
                time.time(),
            ),
        )


def load_config(store_num):
    with _db() as conn:
        row = conn.execute(
            "SELECT config_json FROM store_configs WHERE store_num=?", (store_num,)
        ).fetchone()
    if row:
        return json.loads(row["config_json"])
    cfg = _default_config()
    _db_upsert(store_num, cfg)
    return cfg


def backup_config(store_num):
    with _db() as conn:
        row = conn.execute(
            "SELECT config_json FROM store_configs WHERE store_num=?", (store_num,)
        ).fetchone()
        if row:
            conn.execute(
                "INSERT INTO store_config_backups (store_num, config_json, backed_up_at) VALUES (?,?,?)",
                (store_num, row["config_json"], time.time()),
            )


def save_config(cfg, store_num, editor=None):
    cfg["last_edited_at"] = time.time()
    if editor:
        cfg["last_edited_by"] = editor
    _db_upsert(store_num, cfg)
    logger.info("Config saved for store %s by %s", store_num, editor or "unknown")


def delete_store_config(store_num):
    with _db() as conn:
        conn.execute("DELETE FROM store_configs WHERE store_num=?", (store_num,))


# ── One-time JSON → DB migration ──────────────────────────────
def migrate_json_to_db():
    migrated = 0
    if os.path.isdir(_LEGACY_JSON_DIR):
        for fname in os.listdir(_LEGACY_JSON_DIR):
            if not (fname.startswith("store_") and fname.endswith(".json")):
                continue
            store_num = fname[6:-5]
            if store_config_exists(store_num):
                continue
            path = os.path.join(_LEGACY_JSON_DIR, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    cfg = json.load(f)
                _db_upsert(store_num, cfg)
                migrated += 1
                logger.info("Migrated store %s from JSON to DB", store_num)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Migration failed for %s: %s", fname, exc)
    if migrated:
        logger.info("Migrated %d store config(s) from JSON files to DB", migrated)


# ── Audit log ─────────────────────────────────────────────────
def audit_log(action, detail=""):
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {action} | {detail}\n"
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
        logger.info("AUDIT: %s | %s", action, detail)
    except OSError as exc:
        logger.error("Failed to write audit log: %s", exc)
