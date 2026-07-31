import io
import json
import logging
import math
import os
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests

from config import (
    DEFAULT_FETCH_CONCURRENCY,
    DEFAULT_PICKLE_VALUE,
    DEFAULT_PRICE_PER_PICKLE,
    load_config,
)

try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

_APP_DIR       = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR     = os.path.join(_APP_DIR, "cache")
_MANIFEST_PATH = os.path.join(_CACHE_DIR, "smilemakers_manifest.json")
CACHE_MAX_AGE  = 86_400  # 1 day in seconds
AUTOMATIC_ITEM_TYPES = {"automatic", "smilemakers", "waytobe"}

_SMILEMAKERS_CACHE: dict = {}  # url -> (name, desc, image, price, variants)
_cache_times:       dict = {}  # url -> fetched_at timestamp
_cache_failures:    dict = {}  # url -> {"failed_at": timestamp, "error": message}
_manifest_lock            = threading.Lock()
_disk_cache_loaded        = False
_warm_lock                = threading.Lock()
_warm_state               = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "done": 0,
    "succeeded": 0,
    "failed": 0,
    "message": "Idle",
}


def load_disk_cache():
    """Populate the in-memory cache from the manifest file, evicting stale entries."""
    global _disk_cache_loaded
    if _disk_cache_loaded:
        return
    with _manifest_lock:
        if _disk_cache_loaded:
            return
        _disk_cache_loaded = True
        if not os.path.isfile(_MANIFEST_PATH):
            return
        try:
            with open(_MANIFEST_PATH, encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load cache manifest: %s", exc)
            return
        now   = time.time()
        fresh = {}
        stale = 0
        for url, entry in manifest.items():
            fetched_at = entry.get("fetched_at") or entry.get("failed_at") or 0
            if now - fetched_at >= CACHE_MAX_AGE:
                stale += 1
                continue
            if entry.get("status") == "failed":
                _cache_failures[url] = {
                    "failed_at": fetched_at,
                    "error": entry.get("error") or "Fetch returned no product data",
                }
                fresh[url] = entry
                continue
            result = entry.get("result")
            if not result or len(result) < 5:
                continue
            _SMILEMAKERS_CACHE[url] = (result[0], result[1], result[2], result[3], result[4])
            _cache_times[url]       = fetched_at
            fresh[url]              = entry
        if stale:
            _write_manifest(fresh)
        logger.info("Cache loaded: %d fresh, %d stale evicted", len(fresh), stale)


def _write_manifest(data: dict):
    """Atomically write manifest dict to disk. Call inside _manifest_lock."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    tmp = _MANIFEST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, _MANIFEST_PATH)


def _build_manifest(now=None):
    now = now or time.time()
    manifest = {
        u: {"status": "ok", "fetched_at": _cache_times.get(u, now), "result": list(r)}
        for u, r in _SMILEMAKERS_CACHE.items()
    }
    for u, failure in _cache_failures.items():
        if u in manifest:
            continue
        manifest[u] = {
            "status": "failed",
            "failed_at": failure.get("failed_at", now),
            "error": failure.get("error") or "Fetch returned no product data",
        }
    return manifest


def _persist_entry(url: str, result: tuple):
    """Append/update one URL in the on-disk manifest. Thread-safe."""
    with _manifest_lock:
        now = time.time()
        _cache_times[url] = now
        _cache_failures.pop(url, None)
        _write_manifest(_build_manifest(now))


def _persist_failure(url: str, error: str):
    with _manifest_lock:
        now = time.time()
        _SMILEMAKERS_CACHE.pop(url, None)
        _cache_times.pop(url, None)
        _cache_failures[url] = {"failed_at": now, "error": error or "Fetch returned no product data"}
        _write_manifest(_build_manifest(now))


def clear_cache(url: str = None):
    """Remove one URL from the cache, or clear everything if url is None."""
    with _manifest_lock:
        if url:
            _SMILEMAKERS_CACHE.pop(url, None)
            _cache_times.pop(url, None)
            _cache_failures.pop(url, None)
        else:
            _SMILEMAKERS_CACHE.clear()
            _cache_times.clear()
            _cache_failures.clear()
        _write_manifest(_build_manifest())


def cache_entries():
    """Return cached SmileMakers entries for the admin dashboard."""
    load_disk_cache()
    with _manifest_lock:
        entries = []
        for url, result in _SMILEMAKERS_CACHE.items():
            fetched_at = _cache_times.get(url)
            entries.append({
                "url": url,
                "status": "cached",
                "fetched_at": fetched_at,
                "failed_at": None,
                "last_seen": fetched_at,
                "error": "",
                "name": result[0] if len(result) > 0 else "",
                "image": result[2] if len(result) > 2 else "",
                "price": result[3] if len(result) > 3 else None,
            })
        for url, failure in _cache_failures.items():
            failed_at = failure.get("failed_at")
            entries.append({
                "url": url,
                "status": "failed",
                "fetched_at": None,
                "failed_at": failed_at,
                "last_seen": failed_at,
                "error": failure.get("error") or "Fetch returned no product data",
                "name": "",
                "image": "",
                "price": None,
            })
        return sorted(entries, key=lambda e: e.get("last_seen") or 0, reverse=True)


def cache_entries_for_urls(urls):
    """Return cache status rows for configured URLs, plus any orphaned cache rows."""
    known = []
    seen = set()
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            known.append(url)
    entries_by_url = {entry["url"]: entry for entry in cache_entries()}
    rows = []
    for url in known:
        entry = entries_by_url.pop(url, None)
        if entry:
            entry = {**entry, "configured": True}
        else:
            entry = {
                "url": url,
                "status": "missing",
                "configured": True,
                "fetched_at": None,
                "failed_at": None,
                "last_seen": None,
                "error": "",
                "name": "",
                "image": "",
                "price": None,
            }
        rows.append(entry)
    for entry in entries_by_url.values():
        rows.append({**entry, "configured": False})
    status_order = {"failed": 0, "missing": 1, "cached": 2}
    return sorted(
        rows,
        key=lambda e: (status_order.get(e.get("status"), 9), -(e.get("last_seen") or 0), e.get("url") or ""),
    )


def _evict_stale():
    """Drop cache entries older than CACHE_MAX_AGE from memory and the manifest."""
    with _manifest_lock:
        now    = time.time()
        stale  = [u for u, t in _cache_times.items() if now - t >= CACHE_MAX_AGE]
        stale_failures = [u for u, f in _cache_failures.items() if now - f.get("failed_at", 0) >= CACHE_MAX_AGE]
        if not stale and not stale_failures:
            return
        for u in stale:
            _SMILEMAKERS_CACHE.pop(u, None)
            _cache_times.pop(u, None)
        for u in stale_failures:
            _cache_failures.pop(u, None)
        _write_manifest(_build_manifest(now))
        logger.info("Cache eviction: removed %d stale entry/entries", len(stale) + len(stale_failures))


_EVICTION_INTERVAL = 3_600  # check every hour


def start_cache_maintenance():
    """Start a daemon thread that evicts stale cache entries once per hour."""
    import threading

    def _loop():
        while True:
            time.sleep(_EVICTION_INTERVAL)
            try:
                _evict_stale()
            except Exception as exc:
                logger.error("Cache eviction error: %s", exc)

    t = threading.Thread(target=_loop, name="cache-eviction", daemon=True)
    t.start()
    logger.info("Cache maintenance thread started (interval=%ds, max_age=%ds)",
                _EVICTION_INTERVAL, CACHE_MAX_AGE)

_COLOR_WORDS = {
    "black","white","gray","grey","charcoal","ivory","cream",
    "red","crimson","scarlet","burgundy","maroon","rose","pink",
    "coral","salmon","magenta",
    "orange","amber","peach","yellow","gold",
    "green","olive","lime","mint","teal","turquoise",
    "blue","navy","aqua","cyan","cobalt","indigo","violet",
    "purple","lavender","lilac","mauve",
    "brown","tan","beige","khaki",
    "silver","multicolor","multicolour","sand",
}
_COLOR_ALT = '|'.join(re.escape(w) for w in _COLOR_WORDS)
_COLOR_PATTERN = re.compile(
    r'\b(?:' + _COLOR_ALT + r')\b'
    r'(?:\s*(?:/|&|\band\b|\bor\b)\s*\b(?:' + _COLOR_ALT + r')\b)*',
    re.IGNORECASE,
)

_SEX_MALE_WORDS   = {"men's","mens","men","male","boy's","boys","boy"}
_SEX_FEMALE_WORDS = {"women's","womens","women","female","ladies'","ladies","lady's","lady","girl's","girls","girl"}
_SEX_STRIP_PATTERN = re.compile(
    r"\b(?:men(?:'s)?|mens|women(?:'s)?|womens|boy(?:'s)?|boys|girl(?:'s)?|girls|lady(?:'s)?|ladies(?:'s)?|male|female|unisex)\b",
    re.IGNORECASE,
)
_SEX_MALE_PATTERN = re.compile(
    r'\b(?:' + '|'.join(re.escape(w) for w in _SEX_MALE_WORDS) + r')\b', re.IGNORECASE
)
_SEX_FEMALE_PATTERN = re.compile(
    r'\b(?:' + '|'.join(re.escape(w) for w in _SEX_FEMALE_WORDS) + r')\b', re.IGNORECASE
)

_SIZE_ORDER = ["XXS","XS","SM","M","L","XL","2XL","3XL","4XL","5XL","6XL"]
_SIZE_ALIASES = {
    "XXS":"XXS","XS":"XS","SM":"SM","S":"SM","SMALL":"SM",
    "MD":"M","MED":"M","MEDIUM":"M","M":"M",
    "LG":"L","LARGE":"L","L":"L","XL":"XL",
    "XXL":"2XL","2X":"2XL","2XL":"2XL",
    "3X":"3XL","3XL":"3XL","4X":"4XL","4XL":"4XL",
    "5X":"5XL","5XL":"5XL","6X":"6XL","6XL":"6XL",
}
_SIZE_TOKEN_ALT = "|".join(re.escape(k) for k in sorted(_SIZE_ALIASES, key=len, reverse=True))
_SIZE_EXPR_RE = (
    rf"\b(?:{_SIZE_TOKEN_ALT})\b"
    rf"(?:\s*(?:-|–|—|to|through|thru|/|,|&|\band\b)\s*\b(?:{_SIZE_TOKEN_ALT})\b)+"
)
_SIZE_PREFIX_PATTERN = re.compile(
    rf"\b(?:available\s+in\s+)?sizes?\s*:?\s*(?P<expr>{_SIZE_EXPR_RE})(?:\s+only)?\.?",
    re.IGNORECASE,
)
_SIZE_BARE_PATTERN = re.compile(
    rf"(?P<prefix>(?:^|[,;(]\s*))(?P<expr>{_SIZE_EXPR_RE})(?:\s+only)?\.?",
    re.IGNORECASE,
)
_SIZE_TOKEN_PATTERN = re.compile(rf"\b(?:{_SIZE_TOKEN_ALT})\b", re.IGNORECASE)
_SIZE_RANGE_PATTERN = re.compile(r"(?:-|–|—|\bto\b|\bthrough\b|\bthru\b)", re.IGNORECASE)


def _tidy(text):
    text = re.sub(r'\s{2,}', ' ', text).strip()
    text = re.sub(r'\s+([,\-/])', r'\1', text)
    text = re.sub(r'^[,\-/\s]+|[,\-/\s]+$', '', text)
    return text

def strip_color_words(text):
    return _tidy(_COLOR_PATTERN.sub('', text))

def strip_sex_words(text):
    return _tidy(_SEX_STRIP_PATTERN.sub('', text))

def _detect_sex_label(name):
    if _SEX_MALE_PATTERN.search(name):
        return "M"
    if _SEX_FEMALE_PATTERN.search(name):
        return "F"
    return None

def _normalize_size_token(token):
    return _SIZE_ALIASES.get(token.upper())

def _sizes_from_expr(expr):
    tokens = [_normalize_size_token(t.group(0)) for t in _SIZE_TOKEN_PATTERN.finditer(expr)]
    tokens = [t for t in tokens if t]
    if not tokens:
        return []
    if len(tokens) == 2 and _SIZE_RANGE_PATTERN.search(expr):
        try:
            start = _SIZE_ORDER.index(tokens[0])
            end   = _SIZE_ORDER.index(tokens[1])
        except ValueError:
            return tokens
        lo, hi = sorted((start, end))
        return _SIZE_ORDER[lo:hi + 1]
    seen, sizes = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t); sizes.append(t)
    return sizes

def extract_size_variants(text):
    if not text:
        return text, []
    sizes = []
    def _collect(match):
        for s in _sizes_from_expr(match.group("expr")):
            if s not in sizes: sizes.append(s)
        return ""
    cleaned = _SIZE_PREFIX_PATTERN.sub(_collect, text)
    def _collect_bare(match):
        for s in _sizes_from_expr(match.group("expr")):
            if s not in sizes: sizes.append(s)
        return match.group("prefix").rstrip()
    cleaned = _SIZE_BARE_PATTERN.sub(_collect_bare, cleaned)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"(?:,\s*){2,}", ", ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;")
    return cleaned, [{"type":"size","value":s} for s in sizes]

def _merge_variants(*groups):
    merged, seen = [], set()
    for g in groups:
        for v in (g or []):
            k = (v.get("type"), v.get("value"))
            if k not in seen:
                seen.add(k); merged.append(v)
    return merged

def _first_sentence(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    m = re.search(r'[.!?](?:\s|$)', text)
    if m:
        return text[:m.start() + 1].strip()
    return text[:75] if len(text) > 75 else text


def _price_from_offers(offers):
    """Read regular, aggregate, and price-specification Schema.org offers."""
    if isinstance(offers, list):
        for offer in offers:
            value = _price_from_offers(offer)
            if value is not None:
                return value
        return None
    if not isinstance(offers, dict):
        return None
    for key in ("price", "lowPrice", "minPrice"):
        if offers.get(key) is not None:
            return offers[key]
    specifications = offers.get("priceSpecification")
    if isinstance(specifications, dict):
        specifications = [specifications]
    for specification in specifications or []:
        if not isinstance(specification, dict):
            continue
        for key in ("price", "lowPrice", "minPrice"):
            if specification.get(key) is not None:
                return specification[key]
    return None

def fetch_vendor_product(url):
    load_disk_cache()
    if url in _SMILEMAKERS_CACHE:
        return _SMILEMAKERS_CACHE[url]
    hostname = (urlparse(url).hostname or "").lower()
    is_fresh_fashions = (
        hostname == "freshfashionsandmore.com"
        or hostname.endswith(".freshfashionsandmore.com")
    )
    if is_fresh_fashions:
        # This storefront stalls requests that impersonate a full Chrome browser,
        # while its server-rendered product HTML responds normally to a minimal UA.
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*;q=0.8"}
    else:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ("", "", "", None, [])

    result = ("", "", "", None, [])
    failure_reason = "Fetch returned no product data"
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=(5, 12))
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            def meta_content(key):
                tag = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
                return tag["content"].strip() if tag and tag.get("content") else ""

            heading = soup.find("h1")
            name = meta_content("og:title") or meta_content("twitter:title")
            if not name and heading:
                name = heading.get_text(" ", strip=True)
            desc = meta_content("og:description") or meta_content("twitter:description")
            if not desc:
                m = soup.find("meta", attrs={"name":"description"})
                desc = m["content"].strip() if m and m.get("content") else ""
            size_variants = []
            image_url = meta_content("og:image") or meta_content("twitter:image")

            price = meta_content("product:price:amount") or meta_content("og:price:amount") or meta_content("price")
            if not price:
                m = soup.find("meta", attrs={"itemprop":"price"})
                if m and m.get("content"): price = m["content"].strip()
            if not price:
                m = soup.find("meta", attrs={"name":"price"})
                if m and m.get("content"): price = m["content"].strip()
            if not price:
                m = soup.find(attrs={"itemprop":"price"})
                if m:
                    price = m.get("content", m.get_text("")).strip()
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or script.get_text() or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                candidates = data if isinstance(data, list) else [data]
                expanded = []
                for candidate in candidates:
                    if isinstance(candidate, dict) and isinstance(candidate.get("@graph"), list):
                        expanded.extend(candidate["@graph"])
                    else:
                        expanded.append(candidate)
                for product in expanded:
                    if not isinstance(product, dict):
                        continue
                    product_type = product.get("@type", "")
                    if isinstance(product_type, list):
                        is_product = "Product" in product_type
                    else:
                        is_product = product_type == "Product"
                    if not is_product:
                        continue
                    structured_name = str(product.get("name") or "").strip()
                    structured_desc = str(product.get("description") or "").strip()
                    name = structured_name or name
                    desc = structured_desc or desc
                    product_image = product.get("image")
                    if isinstance(product_image, list):
                        product_image = product_image[0] if product_image else ""
                    if isinstance(product_image, dict):
                        product_image = product_image.get("url") or product_image.get("contentUrl")
                    image_url = str(product_image or "").strip() or image_url
                    offers = product.get("offers")
                    if not price:
                        price = _price_from_offers(offers)
                    break

            if not image_url:
                image_tag = soup.find(attrs={"itemprop": "image"})
                if image_tag:
                    image_url = image_tag.get("content") or image_tag.get("src") or ""
            if image_url:
                image_url = urljoin(getattr(resp, "url", url) or url, image_url)

            desc, size_variants = extract_size_variants(desc)
            desc = _first_sentence(desc)

            if price:
                price_match = re.search(r"\d[\d,]*(?:\.\d{1,2})?", str(price))
                price = float(price_match.group(0).replace(",", "")) if price_match else None
            else:
                price = None
            result = (name, desc, image_url, price, size_variants)
            break
        except requests.exceptions.Timeout:
            failure_reason = "Request timed out"
            if attempt < max_attempts:
                time.sleep(0.5); continue
        except requests.exceptions.RequestException as exc:
            failure_reason = str(exc)
            logger.error("Fetch failed for %s: %s", url, exc)
            break
        except Exception as exc:
            failure_reason = str(exc)
            logger.error("Unexpected fetch error for %s: %s", url, exc, exc_info=True)
            break

    # Only cache successful results — a failed/empty fetch must not poison the cache
    # so that the next preview load retries instead of returning blank forever.
    if result[0] or result[2]:  # name or image URL
        _SMILEMAKERS_CACHE[url] = result
        _persist_entry(url, result)
    else:
        _persist_failure(url, failure_reason)
    return result


# Backward-compatible name used by API imports and older callers.
fetch_smilemakers_product = fetch_vendor_product

def extract_dominant_colors(image_url, n=5):
    if not image_url or not _PIL_AVAILABLE:
        return []
    try:
        resp = requests.get(image_url, timeout=20)
        resp.raise_for_status()
        img = _PILImage.open(io.BytesIO(resp.content)).convert("RGB")
        img = img.resize((80, 80), _PILImage.LANCZOS)
        paletted = img.quantize(colors=n + 4, method=_PILImage.Quantize.MEDIANCUT)
        palette = paletted.getpalette()
        counts = [0] * (n + 4)
        for px in paletted.getdata():
            if px < len(counts): counts[px] += 1
        order = sorted(range(len(counts)), key=lambda k: -counts[k])
        colors, seen = [], set()
        for idx in order:
            r2, g2, b2 = palette[idx*3], palette[idx*3+1], palette[idx*3+2]
            brightness = (r2 + g2 + b2) / 3
            if brightness < 40 or brightness > 215: continue
            hex_col = f"#{r2:02X}{g2:02X}{b2:02X}"
            if hex_col not in seen:
                seen.add(hex_col); colors.append(hex_col)
            if len(colors) >= n: break
        return colors
    except Exception as exc:
        logger.warning("Color extraction failed for %s: %s", image_url, exc)
        return []

def price_to_pickles(price, per_pickle=None, round_up_to=None):
    if per_pickle is None:
        per_pickle = DEFAULT_PRICE_PER_PICKLE
    if price is None: return None
    try:
        value = float(price)
    except (TypeError, ValueError):
        return None
    if value < 0: return None
    pickles = math.ceil(value / per_pickle)
    if round_up_to and pickles % round_up_to:
        pickles = ((pickles + round_up_to - 1) // round_up_to) * round_up_to
    return pickles

def resolve_items_for_preview(cfg):
    """Fetch all vendor-backed items and return fully resolved page data.

    NOTE: _SMILEMAKERS_CACHE stores only raw product data (name, desc, image,
    price, size_variants) — never resolved pickle counts.  per_pickle is read
    fresh from cfg on every call so changing price_per_pickle in Settings
    immediately affects pickle counts on the next render without re-fetching.
    """
    s            = cfg.get("settings", {})
    concurrency  = s.get("fetch_concurrency", DEFAULT_FETCH_CONCURRENCY)
    show_unavailable = bool(s.get("show_unavailable_cards", False))
    # Read fresh from config every render — do NOT use a module-level constant here.
    per_pickle   = float(s.get("price_per_pickle", s.get("price_per_point", DEFAULT_PRICE_PER_PICKLE)))
    pickle_value = int(s.get("pickle_chip_value", s.get("pickle_pickle_value", s.get("pickle_point_value", DEFAULT_PICKLE_VALUE))))

    resolved_pages = []
    for page in cfg.get("pages", []):
        if page.get("type") == "earn":
            resolved_pages.append(page)
            continue
        resolved_items = []
        pending = []  # (index, item_cfg)
        for i, item in enumerate(page.get("items", [])):
            if item.get("type") in AUTOMATIC_ITEM_TYPES:
                pending.append((i, item))
                resolved_items.append(None)
            else:
                desc, size_variants = extract_size_variants(item.get("desc", "") or "")
                variants = _merge_variants(item.get("variants", []), size_variants)
                pickles = item.get("pickles", item.get("points"))
                price = item.get("price")
                if pickles is None and price is not None:
                    pickles = price_to_pickles(price, per_pickle=per_pickle, round_up_to=pickle_value)
                resolved_items.append({
                    "name":     item.get("name", ""),
                    "desc":     desc,
                    "pickles":  pickles or 0,
                    "tag":      item.get("tag"),
                    "image":    item.get("image", ""),
                    "variants": variants,
                    "price":    price,
                    "uniform_approved": item.get("uniform_approved", False),
                })

        if pending:
            def _fetch_item(idx_item):
                idx, item = idx_item
                urls = item.get("urls", [])
                if not urls:
                    return idx, {
                        "name":"","desc":"","pickles":0,
                        "tag":item.get("tag"),"image":"","variants":[],"price":None,
                        "uniform_approved": item.get("uniform_approved", False),
                        "_unavailable": True,
                    }
                primary_product = fetch_vendor_product(urls[0])
                fn, fd, fi, fp, _ = primary_product
                image_url = item.get("image") or fi
                page_price = item.get("price") or fp

                if not (fn or fi):
                    pickles = item.get("pickles", item.get("points"))
                    if pickles is None and page_price is not None:
                        pickles = price_to_pickles(page_price, per_pickle=per_pickle, round_up_to=pickle_value)
                    desc, size_variants = extract_size_variants(item.get("desc", "") or "")
                    return idx, {
                        "name": item.get("name") or "",
                        "desc": desc,
                        "pickles": pickles or 0,
                        "tag": item.get("tag"),
                        "image": image_url,
                        "variants": _merge_variants(item.get("variants", []), size_variants),
                        "price": page_price,
                        "uniform_approved": item.get("uniform_approved", False),
                        "_unavailable": True,
                    }

                fetched_products = [primary_product]
                fetched_products.extend(fetch_vendor_product(vurl) for vurl in urls[1:])
                sex_variants = []
                color_variants = []
                fetched_size_variants = []
                for vn, _, vimg, _, vsize_variants in fetched_products:
                    fetched_size_variants.extend(vsize_variants or [])
                    sex_label = _detect_sex_label(vn or "")
                    if sex_label:
                        sex_variants.append({"type": "sex", "value": sex_label})
                    if len(urls) > 1 and vimg:
                        colors = extract_dominant_colors(vimg, 1)
                        if colors:
                            color_variants.append({"type": "color", "value": colors[0]})

                if sex_variants:
                    cleaned = strip_sex_words(fn)
                    if cleaned:
                        fn = cleaned
                    fd = strip_sex_words(fd)
                if color_variants:
                    fn = strip_color_words(fn)
                    fd = strip_color_words(fd)

                desc_override = item.get("desc")
                desc = desc_override if desc_override is not None else fd
                desc, override_size_variants = extract_size_variants(desc or "")
                variants = _merge_variants(
                    item.get("variants", []),
                    sex_variants,
                    color_variants,
                    fetched_size_variants,
                    override_size_variants,
                )

                pickles = item.get("pickles", item.get("points"))
                if pickles is None and page_price is not None:
                    pickles = price_to_pickles(page_price, per_pickle=per_pickle, round_up_to=pickle_value)

                return idx, {
                    "name":     item.get("name") or fn,
                    "desc":     desc,
                    "pickles":  pickles or 0,
                    "tag":      item.get("tag"),
                    "image":    image_url,
                    "variants": variants,
                    "price":    page_price,
                    "uniform_approved": item.get("uniform_approved", False),
                    "_unavailable": False,
                }

            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {pool.submit(_fetch_item, p): p for p in pending}
                for future in as_completed(futures):
                    idx, resolved = future.result()
                    resolved_items[idx] = resolved

        if not show_unavailable:
            resolved_items = [
                item for item in resolved_items
                if item is not None and not item.get("_unavailable", False)
            ]

        resolved_pages.append({**page, "items": resolved_items})

    return resolved_pages, per_pickle, pickle_value

SIZE_ORDER = _SIZE_ORDER


def _collect_smilemakers_urls(cfgs, include_cached=False):
    load_disk_cache()
    seen, urls = set(), []
    with _manifest_lock:
        cached = set(_SMILEMAKERS_CACHE)
    for cfg in cfgs:
        for page in cfg.get("pages", []):
            for item in page.get("items", []):
                if item.get("type") not in AUTOMATIC_ITEM_TYPES:
                    continue
                for url in item.get("urls") or []:
                    if not url or url in seen:
                        continue
                    if not include_cached and url in cached:
                        continue
                    seen.add(url)
                    urls.append(url)
    return urls


def get_cache_warm_status():
    with _warm_lock:
        return dict(_warm_state)


def _set_warm_state(**updates):
    with _warm_lock:
        _warm_state.update(updates)


def _run_cache_warm(urls, concurrency, label):
    _set_warm_state(
        running=True,
        started_at=time.time(),
        finished_at=None,
        total=len(urls),
        done=0,
        succeeded=0,
        failed=0,
        message=f"{label}: warming {len(urls)} URL(s)",
    )
    if not urls:
        _set_warm_state(
            running=False,
            finished_at=time.time(),
            message=f"{label}: no URLs need warming",
        )
        return

    def _fetch(url):
        result = fetch_smilemakers_product(url)
        return bool(result[0] or result[2])

    workers = max(1, min(int(concurrency or DEFAULT_FETCH_CONCURRENCY), len(urls)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch, url): url for url in urls}
        for future in as_completed(futures):
            ok = False
            try:
                ok = bool(future.result())
            except Exception as exc:
                _persist_failure(futures[future], str(exc))
            with _warm_lock:
                _warm_state["done"] += 1
                if ok:
                    _warm_state["succeeded"] += 1
                else:
                    _warm_state["failed"] += 1
                _warm_state["message"] = (
                    f"{label}: {_warm_state['done']}/{_warm_state['total']} URL(s) checked"
                )

    with _warm_lock:
        _warm_state["running"] = False
        _warm_state["finished_at"] = time.time()
        _warm_state["message"] = (
            f"{label}: {_warm_state['succeeded']}/{_warm_state['total']} loaded, "
            f"{_warm_state['failed']} failed"
        )


def start_cache_warm(cfgs, include_cached=False, label="Warm all stores"):
    urls = _collect_smilemakers_urls(cfgs, include_cached=include_cached)
    concurrency = max(
        (c.get("settings", {}).get("fetch_concurrency", DEFAULT_FETCH_CONCURRENCY) for c in cfgs),
        default=DEFAULT_FETCH_CONCURRENCY,
    )
    with _warm_lock:
        if _warm_state.get("running"):
            return False, dict(_warm_state)
    _set_warm_state(
        running=True,
        started_at=time.time(),
        finished_at=None,
        total=len(urls),
        done=0,
        succeeded=0,
        failed=0,
        message=f"{label}: queued {len(urls)} URL(s)",
    )
    threading.Thread(
        target=_run_cache_warm,
        args=(urls, concurrency, label),
        name="smilemakers-cache-warm",
        daemon=True,
    ).start()
    return True, get_cache_warm_status()


def start_cache_refetch_urls(urls, concurrency=DEFAULT_FETCH_CONCURRENCY, label="Refetch cache"):
    unique = []
    seen = set()
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    with _warm_lock:
        if _warm_state.get("running"):
            return False, dict(_warm_state)
    for url in unique:
        clear_cache(url)
    _set_warm_state(
        running=True,
        started_at=time.time(),
        finished_at=None,
        total=len(unique),
        done=0,
        succeeded=0,
        failed=0,
        message=f"{label}: queued {len(unique)} URL(s)",
    )
    threading.Thread(
        target=_run_cache_warm,
        args=(unique, concurrency, label),
        name="smilemakers-cache-refetch",
        daemon=True,
    ).start()
    return True, get_cache_warm_status()


def prefetch_new_urls(cfg):
    """Fetch any SmileMakers URLs in cfg that are not yet cached.
    Intended to run in a background thread immediately after a config save so
    that new items are ready before the next preview reload arrives."""
    load_disk_cache()
    s = cfg.get("settings", {})
    concurrency = s.get("fetch_concurrency", DEFAULT_FETCH_CONCURRENCY)
    urls = []
    for page in cfg.get("pages", []):
        for item in page.get("items", []):
            if item.get("type") in AUTOMATIC_ITEM_TYPES:
                for u in (item.get("urls") or []):
                    if u and u not in _SMILEMAKERS_CACHE:
                        urls.append(u)
    if not urls:
        return
    with ThreadPoolExecutor(max_workers=min(concurrency, len(urls))) as pool:
        list(pool.map(fetch_smilemakers_product, urls))


def warm_cache():
    """Pre-fetch every SmileMakers URL across all store configs so /preview-frame is instant."""
    load_disk_cache()
    from config import list_store_nums, load_config as _load
    store_nums = list_store_nums()
    all_cfgs = [_load(s) for s in store_nums]
    urls = _collect_smilemakers_urls(all_cfgs)
    if not urls:
        print("  Cache already warm.")
        return
    concurrency = max(
        (c.get("settings", {}).get("fetch_concurrency", DEFAULT_FETCH_CONCURRENCY) for c in all_cfgs),
        default=DEFAULT_FETCH_CONCURRENCY,
    )
    n_stores = len(all_cfgs)
    print(f"  Warming {len(urls)} URL(s) across {n_stores} store(s) [{concurrency} workers]")

    id_pool = queue.Queue()
    for i in range(1, concurrency + 1):
        id_pool.put(i)

    def _fetch_logged(url):
        wid = id_pool.get()
        try:
            slug = url.rstrip("/").split("/")[-1] or url
            print(f"  worker {wid}: fetching  {slug}", flush=True)
            t0 = time.time()
            result = fetch_smilemakers_product(url)
            elapsed = time.time() - t0
            name = (result[0] or "").strip()
            ok = "✓" if (result[0] or result[2]) else "✗ empty"
            label = f" — {name[:50]}" if name else ""
            print(f"  worker {wid}: {ok} {elapsed:.1f}s{label}", flush=True)
            return result
        finally:
            id_pool.put(wid)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(_fetch_logged, urls))

    succeeded = sum(1 for r in results if r[0] or r[2])
    print(f"  Cache warm — {succeeded}/{len(urls)} loaded.")
