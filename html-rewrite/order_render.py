from flask import render_template

from services import SIZE_ORDER


# Printed order sheet layout knobs.
ORDER_LINES_PER_ITEM = 3
ITEMS_PER_PAGE = 9
EXTRA_ORDER_LINES = 6


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
    owed = chips
    chip_note = f"{chips * max(1, value)} pts" if value != 1 and chips else ""
    return owed, chip_note


def _item_sheets(pages, per_pickle, pickle_value):
    sheets = []
    for page in pages:
        if page.get("type") == "earn":
            continue
        section = page.get("section_label") or page.get("title") or "Items"
        for item in page.get("items") or []:
            if not item or item.get("_unavailable"):
                continue
            pickles = item.get("pickles", 0) or 0
            price = item.get("price")
            cost = _format_money(price)
            if not cost and pickles:
                cost = "est. " + _format_money(float(pickles) * float(per_pickle or 0))
            owed, chip_note = _owed_pickles(item, pickle_value)
            variants = item.get("variants") or []
            sheets.append({
                "section": section,
                "item": item.get("name", ""),
                "size_hint": _size_summary(variants),
                "color_swatches": _color_swatches(variants),
                "cost": cost,
                "owed": owed if owed else "",
                "chip_note": chip_note,
                "line_count": ORDER_LINES_PER_ITEM,
            })
    return sheets


def _blank_sheet():
    return {
        "section": "",
        "item": "",
        "size_hint": "",
        "color_swatches": [],
        "cost": "",
        "owed": "",
        "chip_note": "",
        "line_count": ORDER_LINES_PER_ITEM,
    }


def render_order_tracker_html(pages, per_pickle, pickle_value, store_num):
    item_sheets = _item_sheets(pages, per_pickle, pickle_value)
    if not item_sheets:
        item_sheets = [_blank_sheet()]
    page_sheets = [
        item_sheets[i:i + ITEMS_PER_PAGE]
        for i in range(0, len(item_sheets), ITEMS_PER_PAGE)
    ]
    return render_template(
        "order_tracker.html",
        page_sheets=page_sheets,
        line_numbers=list(range(1, ORDER_LINES_PER_ITEM + 1)),
        extra_order_lines=list(range(EXTRA_ORDER_LINES)),
        total=len(page_sheets),
        store_num=store_num,
    )
