"""
Smoke tests for the Pickle Points Flask app.

Run from html-rewrite while the server may be running or stopped:
    python smoke_test.py
"""

from contextlib import contextmanager
import re
import sys

import api
import services
from config import normalize_automatic_items
from main import app
from preview_render import render_preview_html


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

        automatic_config = {
            **TEST_CONFIG,
            "settings": {**TEST_CONFIG["settings"], "show_unavailable_cards": True},
            "pages": [{"items": [{"type": "automatic", "urls": ["https://www.freshfashionsandmore.com/Big-Mac-McDonalds-T-Shirt"]}]}],
        }
        response = client.post("/api/config", json=automatic_config)
        assert response.status_code == 200

        # Existing saved configs remain valid while the editor migrates them to automatic.
        legacy_config = {
            **TEST_CONFIG,
            "pages": [{"items": [{"type": "waytobe", "urls": ["https://waytobe.com/product/example"]}]}],
        }
        response = client.post("/api/config", json=legacy_config)
        assert response.status_code == 200

        invalid_setting = {
            **TEST_CONFIG,
            "settings": {**TEST_CONFIG["settings"], "show_unavailable_cards": "yes"},
        }
        response = client.post("/api/config", json=invalid_setting)
        assert response.status_code == 400
        assert "settings.show_unavailable_cards" in response.get_json()["error"]

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
    assert b"+ Automatic" in response.data
    assert b"+ SmileMakers" not in response.data
    assert b"+ WayToBe" not in response.data
    assert b"Show unavailable cards" in response.data
    assert b"editor.js?v=" in response.data

    script = client.get("/static/editor.js?v=test")
    assert script.status_code == 200
    assert b"function addAutomaticItem()" in script.data
    assert b"Add a product URL to finish this item" in script.data
    assert b"await saveConfig({ reloadPreview: false })" in script.data
    assert b"await fetchAndApplyUrl(item, u, 'Checking product')" in script.data
    assert b"Product fetch failed (HTTP ${r.status})" in script.data


def test_legacy_item_migration():
    cfg = {
        "pages": [{"items": [
            {"type": "smilemakers", "urls": ["https://smilemakersonline.com/item"]},
            {"type": "waytobe", "urls": ["https://www.freshfashionsandmore.com/item"]},
            {"type": "manual", "name": "Manual"},
        ]}],
    }
    assert normalize_automatic_items(cfg) == 2
    assert [item["type"] for item in cfg["pages"][0]["items"]] == [
        "automatic", "automatic", "manual",
    ]
    assert cfg["pages"][0]["items"][1]["urls"] == [
        "https://www.freshfashionsandmore.com/item",
    ]
    assert normalize_automatic_items(cfg) == 0


def test_automatic_page_parsing():
    url = "https://www.freshfashionsandmore.com/Pixel-Print-Long-Sleeve-T-Shirt"
    html = """
    <html><head>
      <meta property="og:description" content="DetailsPixel Print Long Sleeve T-Shirt" />
      <script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"Product","name":"Pixel Print Long Sleeve T-Shirt",
           "description":"Super soft 50/50 cotton/poly blend long sleeve T-shirt Screened logos on left chest and down left sleeve. Unisex sizes S-3X",
           "image":"/Images/Product Images/1PIX_01.jpg","offers":{"priceSpecification":
             {"price":12.99,"minPrice":12.99,"maxPrice":15.99}}}
        ]}
      </script>
    </head><body></body></html>
    """

    class FakeResponse:
        def __init__(self, text, response_url):
            self.text = text
            self.url = response_url

        @staticmethod
        def raise_for_status():
            return None

    original_get = services.requests.get
    original_load = services.load_disk_cache
    original_persist = services._persist_entry
    request_options = {}

    def fake_get(request_url, **kwargs):
        request_options.update(kwargs)
        return FakeResponse(html, url)

    try:
        services._SMILEMAKERS_CACHE.pop(url, None)
        services.requests.get = fake_get
        services.load_disk_cache = lambda: None
        services._persist_entry = lambda *args, **kwargs: None
        name, desc, image, price, sizes = services.fetch_vendor_product(url)
    finally:
        services.requests.get = original_get
        services.load_disk_cache = original_load
        services._persist_entry = original_persist
        services._SMILEMAKERS_CACHE.pop(url, None)

    assert name == "Pixel Print Long Sleeve T-Shirt"
    assert desc == "Super soft 50/50 cotton/poly blend long sleeve T-shirt Screened logos on left chest and down left sleeve."
    assert image == "https://www.freshfashionsandmore.com/Images/Product Images/1PIX_01.jpg"
    assert price == 12.99
    assert [variant["value"] for variant in sizes] == ["SM", "M", "L", "XL", "2XL", "3XL"]
    assert request_options["headers"]["User-Agent"] == "Mozilla/5.0"
    assert request_options["timeout"] == (5, 12)


def test_unavailable_automatic_cards():
    cfg = {
        **TEST_CONFIG,
        "settings": {**TEST_CONFIG["settings"], "show_unavailable_cards": False},
        "pages": [{
            "title": "Automatic",
            "items": [{"type": "automatic", "urls": ["https://shop.example.test/missing"]}],
            "layout": {"cols": 4},
        }],
    }
    original_fetch = services.fetch_vendor_product
    try:
        services.fetch_vendor_product = lambda url: ("", "", "", None, [])
        hidden_pages, per_pickle, pickle_value = services.resolve_items_for_preview(cfg)
        assert hidden_pages[0]["items"] == []

        cfg["settings"]["show_unavailable_cards"] = True
        shown_pages, per_pickle, pickle_value = services.resolve_items_for_preview(cfg)

        cfg["settings"]["show_unavailable_cards"] = False
        services.fetch_vendor_product = lambda url: (
            "Fresh Product", "Available now.", "https://shop.example.test/product.png", 6.99, [],
        )
        available_pages, _, _ = services.resolve_items_for_preview(cfg)
    finally:
        services.fetch_vendor_product = original_fetch

    assert len(shown_pages[0]["items"]) == 1
    assert shown_pages[0]["items"][0]["_unavailable"] is True
    with app.app_context():
        rendered = render_preview_html(shown_pages, per_pickle, pickle_value, {})
    assert "Not currently available." in rendered
    assert "unavailable-card-label" in rendered
    assert len(available_pages[0]["items"]) == 1
    assert available_pages[0]["items"][0]["name"] == "Fresh Product"
    assert available_pages[0]["items"][0]["_unavailable"] is False


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
    assert b'class="reward-footer"' in response.data
    assert b'class="reward-price"' in response.data
    assert b'class="reward-meta"' in response.data
    assert b'class="reward-variants"' in response.data
    assert b'class="reward-tag"' in response.data
    assert response.data.find(b'class="reward-price"') < response.data.find(b'class="reward-meta"')
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
    assert b"Other Orders" in response.data
    assert b"extra-orders" in response.data
    assert b"order-color-swatch" in response.data
    assert b"50 pts" in response.data
    assert re.search(
        rb'class="number-cell"\s+rowspan="3"[^>]*>\s*10\s*'
        rb'<span class="chip-note"\s*>\s*50 pts</span\s*>',
        response.data,
    )
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
    runner.check("legacy vendor items migrate to automatic", test_legacy_item_migration)
    runner.check("automatic item parses product JSON-LD", test_automatic_page_parsing)
    runner.check("unavailable automatic cards hide or show", test_unavailable_automatic_cards)
    runner.check("preview-frame renders a test config", lambda: test_preview_frame_renders(client))
    runner.check("order tracker renders printable order sheet", lambda: test_order_tracker_renders(client))

    return runner.result()


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
