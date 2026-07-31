import datetime
import json
import logging
import os
import sqlite3
import time

from auth_db import DB_PATH
from config_schema import (DEFAULT_FETCH_CONCURRENCY, DEFAULT_PICKLE_VALUE,
                           DEFAULT_PRICE_PER_PICKLE, default_config)

APP_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
CONFIGS_DIR = os.path.join(APP_DIR, "configs")  # kept for audit log + migration scan
AUDIT_LOG_PATH = os.path.join(CONFIGS_DIR, "audit.log")

# Legacy JSON directory — scanned once during migration
_LEGACY_JSON_DIR = CONFIGS_DIR

logger = logging.getLogger(__name__)
LEGACY_AUTOMATIC_ITEM_TYPES = {"smilemakers", "waytobe"}


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
            "SELECT config_json, last_edited_at, last_edited_by, notes FROM store_configs WHERE store_num=?",
            (store_num,),
        ).fetchone()
    if not row:
        return {"last_modified": None, "last_edited_by": None, "item_count": 0, "page_count": 0, "notes": ""}
    try:
        cfg   = json.loads(row["config_json"])
        pages = cfg.get("pages", [])
        return {
            "last_modified":  row["last_edited_at"],
            "last_edited_by": row["last_edited_by"],
            "item_count":     sum(len(p.get("items", [])) for p in pages),
            "page_count":     len(pages),
            "notes":          row["notes"] or "",
        }
    except (json.JSONDecodeError, KeyError):
        return {
            "last_modified":  row["last_edited_at"],
            "last_edited_by": row["last_edited_by"],
            "item_count": 0, "page_count": 0,
            "notes":      row["notes"] or "",
        }


def set_store_notes(store_num, notes):
    with _db() as conn:
        conn.execute(
            "UPDATE store_configs SET notes=? WHERE store_num=?",
            (notes.strip() or None, store_num),
        )


# ── Config load / save ────────────────────────────────────────
def _default_config():
    return default_config(APP_DIR)


def normalize_automatic_items(cfg):
    """Normalize automatic items and remove obsolete manual variant selection."""
    changed = 0
    if not isinstance(cfg, dict):
        return changed
    for page in cfg.get("pages", []):
        if not isinstance(page, dict):
            continue
        for item in page.get("items", []):
            if not isinstance(item, dict):
                continue
            item_changed = False
            if item.get("type") in LEGACY_AUTOMATIC_ITEM_TYPES:
                item["type"] = "automatic"
                item_changed = True
            if item.get("type") == "automatic" and "variant_type" in item:
                del item["variant_type"]
                item_changed = True
            if item_changed:
                changed += 1
    return changed


def migrate_vendor_items_to_automatic():
    """Migrate every stored config, retaining a rollback copy before each change."""
    migrated_items = 0
    migrated_stores = 0
    with _db() as conn:
        rows = conn.execute("SELECT store_num, config_json FROM store_configs").fetchall()
        for row in rows:
            try:
                cfg = json.loads(row["config_json"])
            except (TypeError, json.JSONDecodeError):
                logger.warning("Could not migrate invalid config for store %s", row["store_num"])
                continue
            changed = normalize_automatic_items(cfg)
            if not changed:
                continue
            conn.execute(
                "INSERT INTO store_config_backups (store_num, config_json, backed_up_at) VALUES (?,?,?)",
                (row["store_num"], row["config_json"], time.time()),
            )
            conn.execute(
                "UPDATE store_configs SET config_json=? WHERE store_num=?",
                (json.dumps(cfg, ensure_ascii=False), row["store_num"]),
            )
            migrated_items += changed
            migrated_stores += 1
    if migrated_items:
        logger.info(
            "Normalized %d automatic item(s) across %d store(s)",
            migrated_items,
            migrated_stores,
        )
    return migrated_items


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
        cfg = json.loads(row["config_json"])
        # Covers configs imported after application startup.
        if normalize_automatic_items(cfg):
            backup_config(store_num)
            with _db() as conn:
                conn.execute(
                    "UPDATE store_configs SET config_json=? WHERE store_num=?",
                    (json.dumps(cfg, ensure_ascii=False), store_num),
                )
        return cfg
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
    normalize_automatic_items(cfg)
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
