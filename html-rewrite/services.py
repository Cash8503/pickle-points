import io
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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

_SMILEMAKERS_CACHE: dict = {}

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

def fetch_smilemakers_product(url):
    if url in _SMILEMAKERS_CACHE:
        return _SMILEMAKERS_CACHE[url]
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
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            def og(prop):
                tag = soup.find("meta", property=prop)
                return tag["content"].strip() if tag and tag.get("content") else ""

            name = og("og:title") or (soup.find("h1") or {}).get_text("").strip()
            desc = og("og:description")
            if not desc:
                m = soup.find("meta", attrs={"name":"description"})
                desc = m["content"].strip() if m and m.get("content") else ""
            desc, size_variants = extract_size_variants(desc)
            desc = _first_sentence(desc)
            image_url = og("og:image")

            price = og("product:price:amount") or og("og:price:amount") or og("price")
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
            if not price:
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string or "{}")
                    except Exception:
                        continue
                    if isinstance(data, dict) and "offers" in data:
                        offers = data["offers"]
                        if isinstance(offers, dict) and "price" in offers:
                            price = str(offers["price"]); break
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "offers" in item:
                                offers = item["offers"]
                                if isinstance(offers, dict) and "price" in offers:
                                    price = str(offers["price"]); break
                        if price: break

            if price:
                price = re.sub(r"[^0-9.]", "", str(price))
            price = float(price) if price else None
            result = (name, desc, image_url, price, size_variants)
            break
        except requests.exceptions.Timeout:
            if attempt < 3:
                time.sleep(1); continue
        except Exception:
            break

    _SMILEMAKERS_CACHE[url] = result
    return result

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
    except Exception:
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
    """Fetch all SmileMakers items and return fully resolved page data.

    NOTE: _SMILEMAKERS_CACHE stores only raw product data (name, desc, image,
    price, size_variants) — never resolved pickle counts.  per_pickle is read
    fresh from cfg on every call so changing price_per_pickle in Settings
    immediately affects pickle counts on the next render without re-fetching.
    """
    s            = cfg.get("settings", {})
    concurrency  = s.get("fetch_concurrency", DEFAULT_FETCH_CONCURRENCY)
    # Read fresh from config every render — do NOT use a module-level constant here.
    per_pickle   = float(s.get("price_per_pickle", s.get("price_per_point", DEFAULT_PRICE_PER_PICKLE)))
    pickle_value = int(s.get("pickle_pickle_value", s.get("pickle_point_value", DEFAULT_PICKLE_VALUE)))

    resolved_pages = []
    for page in cfg.get("pages", []):
        if page.get("type") == "earn":
            resolved_pages.append(page)
            continue
        resolved_items = []
        pending = []  # (index, item_cfg)
        for i, item in enumerate(page.get("items", [])):
            if item.get("type") == "smilemakers":
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
                })

        if pending:
            def _fetch_item(idx_item):
                idx, item = idx_item
                urls = item.get("urls", [])
                if not urls:
                    return idx, {
                        "name":"","desc":"","pickles":0,
                        "tag":item.get("tag"),"image":"","variants":[],"price":None
                    }
                fn, fd, fi, fp, fetched_size_variants = fetch_smilemakers_product(urls[0])
                variant_type = item.get("variant_type", "color")
                image_url = item.get("image") or fi
                page_price = item.get("price") or fp

                if variant_type == "sex":
                    variants = []
                    cleaned = strip_sex_words(fn)
                    if cleaned: fn = cleaned
                    for vurl in urls:
                        vn, _, _, _, _ = fetch_smilemakers_product(vurl)
                        sex_label = _detect_sex_label(vn)
                        if sex_label:
                            variants.append({"type":"sex","value":sex_label})
                elif len(urls) > 1:
                    variants = []
                    for vurl in urls:
                        _, _, vimg, _, _ = fetch_smilemakers_product(vurl)
                        if vimg:
                            cols = extract_dominant_colors(vimg, 1)
                            if cols:
                                variants.append({"type":"color","value":cols[0]})
                else:
                    variants = []

                if variant_type == "color" and len(urls) > 1:
                    fn = strip_color_words(fn)
                    fd = strip_color_words(fd)

                desc_override = item.get("desc")
                desc = desc_override if desc_override is not None else fd
                desc, override_size_variants = extract_size_variants(desc or "")
                variants = _merge_variants(variants, fetched_size_variants, override_size_variants)

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
                }

            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {pool.submit(_fetch_item, p): p for p in pending}
                for future in as_completed(futures):
                    idx, resolved = future.result()
                    resolved_items[idx] = resolved

        resolved_pages.append({**page, "items": resolved_items})

    return resolved_pages, per_pickle, pickle_value

SIZE_ORDER = _SIZE_ORDER

def warm_cache():

    """Pre-fetch every SmileMakers URL in the config so /preview-frame is instant."""
    cfg = load_config()
    urls = []
    for page in cfg.get("pages", []):
        for item in page.get("items", []):
            if item.get("type") == "smilemakers":
                for u in item.get("urls", []):
                    if u not in _SMILEMAKERS_CACHE:
                        urls.append(u)
    if not urls:
        print("  Cache already warm.")
        return
    concurrency = cfg.get("settings", {}).get("fetch_concurrency", DEFAULT_FETCH_CONCURRENCY)
    print(f"  Warming cache: {len(urls)} product URL(s)…")
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(fetch_smilemakers_product, urls))
    print(f"  Cache warm — preview will now load instantly.")
