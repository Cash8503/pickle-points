"""
Smoke tests for the Pickle Points Flask app.

Run from html-rewrite while the server may be running or stopped:
    python smoke_test.py
"""

from contextlib import contextmanager
import re
import sys

import api
from main import app


TEST_CONFIG = {
    "output_path": "",
    "pdf_title": "Smoke Test Chart",
    "settings": {
        "fetch_concurrency": 1,
        "price_per_pickle": 0.5,
        "pickle_chip_value": 5,
    },
    "tag_colors": {},
    "pages": [{
        "title": "Always Available",
        "subtitle": "Smoke test page",
        "section_label": "Smoke",
        "accent": "#DA291C",
        "items": [{
            "type": "manual",
            "name": "Test Prize",
            "desc": "A test reward.",
            "pickles": 10,
            "image": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'%3E%3Crect width='10' height='10' fill='red'/%3E%3C/svg%3E",
            "uniform_approved": True,
            "variants": [
                {"type": "color", "value": "#DA291C"},
                {"type": "color", "value": "#4A6B1F"},
            ],
        }],
        "layout": {"cols": 4},
    }],
}


@contextmanager
def patched(**replacements):
    originals = {}
    for name, value in replacements.items():
        originals[name] = getattr(api, name)
        setattr(api, name, value)
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(api, name, value)


def set_session(client, **values):
    with client.session_transaction() as session:
        session.clear()
        session.update(values)


def seed_session(client, **values):
    with client.session_transaction() as session:
        session.clear()
        session.update({
            "csrf_token": "token",
            "user_id": 1,
            "username": "admin",
            "real_name": "Admin User",
            "is_admin": True,
            "store": "1001",
        })
        session.update(values)


class SmokeRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def check(self, name, fn):
        try:
            fn()
        except Exception as exc:
            self.failed += 1
            print(f"  FAIL  {name}: {exc}")
        else:
            self.passed += 1
            print(f"  PASS  {name}")

    def result(self):
        print()
        print(f"Results: {self.passed} passed, {self.failed} failed")
        return self.failed == 0


def test_login_loads(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("Content-Type", "")
    assert "charset=utf-8" in response.headers.get("Content-Type", "").lower()


def test_unauthenticated_routes(client):
    response = client.get("/api/config")
    assert response.status_code == 401

    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_first_admin_setup(client):
    created = {}
    set_session(client, csrf_token="token")

    def create_user(username, real_name, is_admin=False, store_nums=None):
        created["username"] = username
        created["real_name"] = real_name
        created["is_admin"] = is_admin
        return 1

    def set_password(user_id, password):
        created["password_user_id"] = user_id
        created["password"] = password

    with patched(
        has_any_admin=lambda: False,
        create_user=create_user,
        set_password=set_password,
        audit_log=lambda action, detail="": None,
        get_user=lambda username=None, user_id=None: {
            "id": 1,
            "username": "admin",
            "real_name": "Admin User",
            "is_admin": 1,
            "dark_mode": 0,
            "password_hash": "set",
        },
        get_user_stores=lambda user_id: [],
    ):
        response = client.post("/login", data={
            "csrf_token": "token",
            "action": "setup_admin",
            "username": "admin",
            "real_name": "Admin User",
            "password": "secret1",
            "confirm": "secret1",
        }, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")
    assert created == {
        "username": "admin",
        "real_name": "Admin User",
        "is_admin": True,
        "password_user_id": 1,
        "password": "secret1",
    }


def test_login_logout_and_password_creation(client):
    set_session(client, csrf_token="token")
    users = {
        1: {
            "id": 1,
            "username": "crew",
            "real_name": "Crew User",
            "is_admin": 0,
            "dark_mode": 0,
            "password_hash": "set",
        },
        2: {
            "id": 2,
            "username": "newcrew",
            "real_name": "New Crew",
            "is_admin": 0,
            "dark_mode": 0,
            "password_hash": None,
        },
    }
    password_sets = []

    def get_user(username=None, user_id=None):
        if user_id is not None:
            return users.get(int(user_id))
        return next((u for u in users.values() if u["username"] == username), None)

    with patched(
        has_any_admin=lambda: True,
        get_user=get_user,
        get_user_stores=lambda user_id: ["1001"],
        check_password=lambda user_id, password: user_id == 1 and password == "secret1",
        set_password=lambda user_id, password: password_sets.append((user_id, password)),
        audit_log=lambda action, detail="": None,
    ):
        response = client.post("/login", data={
            "csrf_token": "token",
            "action": "check_username",
            "username": "crew",
        })
        assert response.status_code == 200
        assert b"Enter Password" in response.data

        response = client.post("/login", data={
            "csrf_token": "token",
            "action": "login",
            "user_id": "1",
            "password": "secret1",
        }, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")

        response = client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")

        set_session(client, csrf_token="token")
        response = client.post("/login", data={
            "csrf_token": "token",
            "action": "set_password",
            "user_id": "2",
            "password": "secret2",
            "confirm": "secret2",
        }, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")
        assert password_sets == [(2, "secret2")]


def test_config_api(client):
    saved = []
    seed_session(client)
    with patched(
        load_config=lambda store_num: TEST_CONFIG,
        save_config=lambda cfg, store_num, editor=None: saved.append((store_num, cfg, editor)),
        prefetch_new_urls=lambda cfg: None,
    ):
        response = client.get("/api/config")
        assert response.status_code == 200
        assert response.get_json()["pdf_title"] == "Smoke Test Chart"

        response = client.post("/api/config", json=TEST_CONFIG)
        assert response.status_code == 200
        assert response.get_json() == {"ok": True}
        assert saved and saved[0][0] == "1001"

        bad_config = {**TEST_CONFIG, "pages": [{"items": [{"type": "smilemakers", "urls": [""]}]}]}
        response = client.post("/api/config", json=bad_config)
        assert response.status_code == 400
        assert "pages[0].items[0].urls[0]" in response.get_json()["error"]


def test_admin_only_routes_reject_normal_users(client):
    seed_session(client, is_admin=False)
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_editor_has_no_admin_cache_controls(client):
    seed_session(client, is_admin=True)
    with patched(
        list_store_nums=lambda: ["1001"],
        get_user=lambda user_id=None, username=None: {
            "id": 1,
            "username": "admin",
            "real_name": "Admin User",
            "is_admin": 1,
            "dark_mode": 0,
        },
    ):
        response = client.get("/")
    assert response.status_code == 200
    assert b"/admin/cache/" not in response.data
    assert b"Warm All Stores" not in response.data
    assert b"Clear All Cache" not in response.data


def test_preview_frame_renders(client):
    seed_session(client)
    with patched(load_config=lambda store_num: TEST_CONFIG):
        response = client.get("/preview-frame")
    assert response.status_code == 200
    assert b"<!doctype html>" in response.data
    assert b"Test Prize" in response.data
    assert b"UNIFORM APPROVED" in response.data
    assert b"NOT UNIFORM APPROVED" in response.data
    assert b"#C62828" in response.data
    assert b"uniform-marker-overlay" in response.data
    assert b"10</span><span style=\"font-size:6.5pt;font-weight:700;color:#9A8A76\">CHIPS" in response.data
    assert b"50 PTS" in response.data


def test_order_tracker_renders(client):
    seed_session(client)
    with patched(load_config=lambda store_num: TEST_CONFIG):
        response = client.get("/order-tracker")
    assert response.status_code == 200
    assert b"Order Tracker" in response.data
    assert b"Test Prize" in response.data
    assert b"est. $5.00" in response.data
    assert b"Pickles Owed" in response.data
    assert b"paid-box" in response.data
    assert b"Received" in response.data
    assert b"received-box" in response.data
    assert b"/static/pickle.svg" in response.data
    assert b'rowspan="3"' in response.data
    assert b"Each item has 3 blank crew order lines" in response.data
    assert b"Extra Orders" in response.data
    assert b"extra-orders" in response.data
    assert b"order-color-swatch" in response.data
    assert b"50 pts" in response.data
    assert re.search(rb'class="number-cell"[^>]*rowspan="3"[^>]*>\s*10\s*<span class="chip-note">50 pts</span>', response.data)
    assert b">Qty<" not in response.data
    assert b"col-qty" not in response.data
    assert b'<td class="line-num">32</td>' not in response.data


def run_tests():
    app.config["TESTING"] = True
    client = app.test_client()
    runner = SmokeRunner()

    runner.check("/login loads with charset", lambda: test_login_loads(client))
    runner.check("unauthenticated routes reject correctly", lambda: test_unauthenticated_routes(client))
    runner.check("first-admin setup creates admin and password", lambda: test_first_admin_setup(client))
    runner.check("login, logout, and first password creation", lambda: test_login_logout_and_password_creation(client))
    runner.check("/api/config GET and POST with session", lambda: test_config_api(client))
    runner.check("admin-only routes reject normal users", lambda: test_admin_only_routes_reject_normal_users(client))
    runner.check("editor has no admin cache controls", lambda: test_editor_has_no_admin_cache_controls(client))
    runner.check("preview-frame renders a test config", lambda: test_preview_frame_renders(client))
    runner.check("order tracker renders printable order sheet", lambda: test_order_tracker_renders(client))

    return runner.result()


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
