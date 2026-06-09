import math

from flask import render_template

from services import SIZE_ORDER


ROWS_PER_PAGE = 18
EXTRA_BLANK_ROWS = 8


def _format_money(value, fallback=None):
    if value is None:
        return fallback or ""
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return fallback or ""


def _size_summary(variants):
    sizes = [
        str(v.get("value", "")).strip()
        for v in (variants or [])
        if v.get("type") == "size" and str(v.get("value", "")).strip()
    ]
    if not sizes:
        return ""
    ordered = sorted(
        dict.fromkeys(sizes),
        key=lambda s: SIZE_ORDER.index(s) if s in SIZE_ORDER else 99,
    )
    if len(ordered) == 1:
        return ordered[0]
    return f"{ordered[0]} - {ordered[-1]}"


def _color_swatches(variants):
    swatches = []
    for variant in variants or []:
        if variant.get("type") != "color":
            continue
        value = str(variant.get("value", "")).strip()
        if value.startswith("#") and len(value) in {4, 7}:
            swatches.append(value)
    return swatches[:8]


def _owed_pickles(item, pickle_value):
    pickles = item.get("pickles", 0) or 0
    try:
        chips = int(pickles)
    except (TypeError, ValueError):
        chips = 0
    try:
        value = int(pickle_value or 1)
    except (TypeError, ValueError):
        value = 1
    owed = chips * max(1, value)
    chip_note = f"{chips} chips" if value != 1 and chips else ""
    return owed, chip_note


def _item_rows(pages, per_pickle, pickle_value):
    rows = []
    for page in pages:
        if page.get("type") == "earn":
            continue
        section = page.get("section_label") or page.get("title") or "Items"
        for item in page.get("items") or []:
            if not item:
                continue
            pickles = item.get("pickles", 0) or 0
            price = item.get("price")
            cost = _format_money(price)
            if not cost and pickles:
                cost = "est. " + _format_money(float(pickles) * float(per_pickle or 0))
            owed, chip_note = _owed_pickles(item, pickle_value)
            variants = item.get("variants") or []
            rows.append({
                "section": section,
                "item": item.get("name", ""),
                "size_hint": _size_summary(variants),
                "color_swatches": _color_swatches(variants),
                "cost": cost,
                "owed": owed if owed else "",
                "chip_note": chip_note,
                "blank": False,
            })
    return rows


def _blank_row():
    return {
        "section": "",
        "item": "",
        "size_hint": "",
        "color_swatches": [],
        "cost": "",
        "owed": "",
        "chip_note": "",
        "blank": True,
    }


def render_order_tracker_html(pages, per_pickle, pickle_value, store_num):
    rows = _item_rows(pages, per_pickle, pickle_value)
    if not rows:
        rows = []
    rows.extend(_blank_row() for _ in range(EXTRA_BLANK_ROWS))

    total_pages = max(1, math.ceil(len(rows) / ROWS_PER_PAGE))
    while len(rows) < total_pages * ROWS_PER_PAGE:
        rows.append(_blank_row())

    page_rows = [
        rows[i * ROWS_PER_PAGE:(i + 1) * ROWS_PER_PAGE]
        for i in range(total_pages)
    ]
    return render_template(
        "order_tracker.html",
        page_rows=page_rows,
        total=total_pages,
        store_num=store_num,
    )
