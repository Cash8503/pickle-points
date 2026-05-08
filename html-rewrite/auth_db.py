import hashlib
import hmac
import logging
import os
import sqlite3
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "appdata.db")

logger = logging.getLogger(__name__)
_PBKDF2_ITERS = 100_000


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    _legacy = os.path.join(APP_DIR, "users.db")
    if os.path.exists(_legacy) and not os.path.exists(DB_PATH):
        os.rename(_legacy, DB_PATH)
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL COLLATE NOCASE,
                real_name     TEXT    NOT NULL,
                password_hash TEXT,
                is_admin      INTEGER NOT NULL DEFAULT 0,
                created_at    REAL    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_stores (
                user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                store_num TEXT    NOT NULL,
                PRIMARY KEY (user_id, store_num)
            );
            CREATE TABLE IF NOT EXISTS store_configs (
                store_num      TEXT PRIMARY KEY,
                config_json    TEXT NOT NULL,
                last_edited_at REAL,
                last_edited_by TEXT,
                created_at     REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS store_config_backups (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                store_num    TEXT    NOT NULL,
                config_json  TEXT    NOT NULL,
                backed_up_at REAL    NOT NULL
            );
        """)


def has_any_admin():
    with _db() as conn:
        return conn.execute(
            "SELECT 1 FROM users WHERE is_admin=1 LIMIT 1"
        ).fetchone() is not None


def create_user(username, real_name, is_admin=False, store_nums=None):
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, real_name, is_admin, created_at) VALUES (?,?,?,?)",
            (username.strip(), real_name.strip(), 1 if is_admin else 0, time.time()),
        )
        uid = cur.lastrowid
        if store_nums:
            conn.executemany(
                "INSERT OR IGNORE INTO user_stores (user_id, store_num) VALUES (?,?)",
                [(uid, s) for s in store_nums],
            )
        return uid


def get_user(username=None, user_id=None):
    with _db() as conn:
        if username is not None:
            row = conn.execute(
                "SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_stores(user_id):
    with _db() as conn:
        rows = conn.execute(
            "SELECT store_num FROM user_stores WHERE user_id=? ORDER BY store_num",
            (user_id,),
        ).fetchall()
        return [r["store_num"] for r in rows]


def set_password(user_id, password):
    with _db() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?", (_hash(password), user_id)
        )


def check_password(user_id, password):
    with _db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id=?", (user_id,)
        ).fetchone()
    if not row or not row["password_hash"]:
        return False
    return _verify(password, row["password_hash"])


def clear_password(user_id):
    with _db() as conn:
        conn.execute("UPDATE users SET password_hash=NULL WHERE id=?", (user_id,))


def update_user(user_id, real_name=None, username=None, is_admin=None, store_nums=None):
    with _db() as conn:
        if real_name is not None:
            conn.execute(
                "UPDATE users SET real_name=? WHERE id=?", (real_name.strip(), user_id)
            )
        if username is not None:
            conn.execute(
                "UPDATE users SET username=? WHERE id=?", (username.strip(), user_id)
            )
        if is_admin is not None:
            conn.execute(
                "UPDATE users SET is_admin=? WHERE id=?", (1 if is_admin else 0, user_id)
            )
        if store_nums is not None:
            conn.execute("DELETE FROM user_stores WHERE user_id=?", (user_id,))
            if store_nums:
                conn.executemany(
                    "INSERT OR IGNORE INTO user_stores (user_id, store_num) VALUES (?,?)",
                    [(user_id, s) for s in store_nums],
                )


def delete_user(user_id):
    with _db() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))


def admin_count():
    with _db() as conn:
        row = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()
        return row[0]


def list_users():
    with _db() as conn:
        users = conn.execute(
            "SELECT * FROM users ORDER BY real_name COLLATE NOCASE"
        ).fetchall()
        result = []
        for u in users:
            stores = conn.execute(
                "SELECT store_num FROM user_stores WHERE user_id=? ORDER BY store_num",
                (u["id"],),
            ).fetchall()
            d = dict(u)
            d["stores"] = [s["store_num"] for s in stores]
            result.append(d)
        return result


def _hash(password):
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return salt.hex() + ":" + key.hex()


def _verify(password, stored):
    try:
        salt_hex, key_hex = stored.strip().split(":", 1)
    except ValueError:
        return False
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), _PBKDF2_ITERS
    )
    return hmac.compare_digest(key.hex(), key_hex)
