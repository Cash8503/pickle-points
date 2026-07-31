import math
import random

from flask import render_template
from markupsafe import Markup

from services import SIZE_ORDER

PICKLE_SVG_PATH1 = (
    "M 65 -0.5 L 56 3.5 L 36 4.5 L 24 17.5 L 16 20.5 L 11.5 24 L 8.5 32 L 8.5 38 "
    "L -0.5 53 L -0.5 60 L 3.5 69 L 3.5 86 L 5.5 90 L 16.5 100 L 21.5 110 L 26 114.5 "
    "L 39 116.5 L 54 125.5 L 59 125.5 L 72 120.5 L 86 121.5 L 92.5 117 L 98 109.5 "
    "L 111 102.5 L 115.5 96 L 117.5 83 L 125.5 71 L 125.5 66 L 120.5 54 L 121.5 39 "
    "L 119.5 35 L 107.5 24 L 103.5 15 L 99 10.5 L 84 7.5 L 71 -0.5 L 65 -0.5 z "
    "M 64 10.5 L 71 10.5 L 81 17.5 L 92 18.5 L 95 20.5 L 101.5 33 L 110.5 40 L 110.5 56 "
    "L 115.5 68 L 114.5 72 L 107.5 80 L 105 94.5 L 94 99.5 L 85 110.5 L 69 110.5 "
    "L 58 115.5 L 52 113.5 L 44 107.5 L 33 106.5 L 29.5 104 L 22.5 91 L 13.5 84 "
    "L 13.5 67 L 10.5 62 L 9.5 55 L 17.5 44 L 18.5 32 L 22 28.5 L 33 23.5 L 40 14.5 "
    "L 57 13.5 L 64 10.5 z"
)
PICKLE_SVG_PATH2 = (
    "M 64 10.5 L 57 13.5 L 40 14.5 L 33 23.5 L 22 28.5 L 18.5 32 L 17.5 44 L 9.5 55 "
    "L 10.5 62 L 13.5 67 L 13.5 84 L 22.5 91 L 29.5 104 L 33 106.5 L 44 107.5 L 52 113.5 "
    "L 58 115.5 L 69 110.5 L 85 110.5 L 94 99.5 L 105 94.5 L 107.5 80 L 114.5 72 "
    "L 115.5 68 L 110.5 56 L 110.5 40 L 101.5 33 L 95 20.5 L 92 18.5 L 81 17.5 "
    "L 71 10.5 L 64 10.5 z "
    "M 67 34.5 L 72 35.5 L 73.5 38 L 69 42.5 L 65 44.5 L 60 43.5 L 58.5 42 L 58.5 39 "
    "L 62 35.5 L 67 34.5 z M 85 41.5 L 87 41.5 L 89.5 46 L 89.5 53 L 87 55.5 L 84 54.5 "
    "L 82.5 52 L 82.5 47 L 85 41.5 z M 75 42.5 L 78 42.5 L 78.5 48 L 77.5 51 L 74.5 56 "
    "L 72 57.5 L 68 57.5 L 66.5 56 L 66.5 51 L 75 42.5 z M 40 44.5 L 44 44.5 L 45.5 46 "
    "L 45.5 50 L 39 53.5 L 35 53.5 L 33.5 52 L 34.5 49 L 40 44.5 z M 43 56.5 L 51 56.5 "
    "L 55.5 60 L 55.5 63 L 53 65.5 L 43 64.5 L 39 62.5 L 37.5 60 L 43 56.5 z "
    "M 32 62.5 L 36 62.5 L 40 64.5 L 44.5 69 L 45.5 73 L 43 75.5 L 38 74.5 L 34.5 71 "
    "L 31.5 66 L 32 62.5 z M 66 67.5 L 71.5 71 L 73.5 77 L 73.5 83 L 72 84.5 L 68.5 83 "
    "L 62.5 75 L 62.5 70 L 66 67.5 z M 79 70.5 L 81 70.5 L 84.5 74 L 83.5 82 L 80 86.5 "
    "L 76.5 85 L 75.5 81 L 75.5 76 L 79 70.5 z M 57 80.5 L 61 81.5 L 66.5 87 L 67.5 89 "
    "L 66 90.5 L 59 89.5 L 55.5 86 L 54.5 83 L 57 80.5 z"
)

PICKLE_SVG_INLINE = f'''<svg viewBox="0 0 126 126" xmlns="http://www.w3.org/2000/svg">
  <path d="{PICKLE_SVG_PATH1}" fill="#64a077"/>
  <path d="{PICKLE_SVG_PATH2}" fill="#99b179"/>
</svg>'''

def _bubble_positions(page_idx, seed_extra=0):
    """Generate deterministic bubble positions for a page header."""
    rng = random.Random(page_idx * 31337 + seed_extra)
    bubbles = []
    count = rng.randint(3, 5)
    min_r, max_r = 28, 100
    attempts = 200
    while len(bubbles) < count and attempts > 0:
        attempts -= 1
        r = rng.randint(min_r, max_r)
        cx = rng.randint(r + 10, 612 - r - 10)
        cy = rng.randint(-r // 2, 130 + r // 2)
        ok = True
        for ox, oy, orad in bubbles:
            if math.hypot(cx - ox, cy - oy) < r + orad + 4:
                ok = False; break
        if ok:
            bubbles.append((cx, cy, r))
    return bubbles

def _variant_swatches_html(variants):
    """Render variant swatches as HTML elements."""
    style_vs = [v for v in variants if v.get('type') != 'size']
    size_vs  = [v for v in variants if v.get('type') == 'size']
    parts = []
    if style_vs:
        dots = ''.join(
            f'<span style="flex-shrink:0;display:block;width:7pt;height:7pt;border-radius:50%;'
            f'background:{v["value"]};border:0.4pt solid #bbb"></span>'
            if v.get('type') == 'color' else
            f'<span style="flex-shrink:0;display:flex;align-items:center;justify-content:center;'
            f'width:7pt;height:7pt;border-radius:50%;'
            f'background:#f8f8f8;border:0.4pt solid #bbb;font-size:4.5pt;'
            f'font-weight:700">{v.get("value","")}</span>'
            for v in style_vs[:8]
        )
        parts.append(
            f'<div style="display:flex;flex-direction:row;align-items:center;'
            f'gap:1.5pt;flex-wrap:wrap;flex-shrink:0">{dots}</div>'
        )
    if size_vs:
        ordered = sorted(
            [v["value"] for v in size_vs],
            key=lambda s: SIZE_ORDER.index(s) if s in SIZE_ORDER else 99
        )
        label = f'{ordered[0]} &ndash; {ordered[-1]}' if len(ordered) > 1 else ordered[0]
        parts.append(
            f'<span style="flex-shrink:0;background:#f8f8f8;border:0.4pt solid #bbb;'
            f'border-radius:4pt;padding:0.5pt 4pt;font-size:5pt;font-weight:700;'
            f'white-space:nowrap;color:#444">{label}</span>'
        )
    return ''.join(parts)

def _tag_badge_html(tag, tag_colors):
    if not tag or tag not in tag_colors:
        return ''
    cols = tag_colors[tag]
    return (f'<span style="background:{cols["bg"]};color:{cols["text"]};'
            f'font-size:5pt;font-weight:700;padding:1pt 3pt;border-radius:4pt;'
            f'white-space:nowrap">{tag}</span>')

def _uniform_approved_marker_html(size=12, label=False, approved=True):
    if approved == 'weekend':
        bg, border, color, symbol = '#FFF9C4', '#C8A800', '#7D5A00', '~'
        label_text = 'WEEKENDS ONLY'
    elif approved:
        bg, border, color, symbol = '#E2F0CE', '#6B7F2A', '#3D6010', '&#10003;'
        label_text = 'UNIFORM APPROVED'
    else:
        bg, border, color, symbol = '#F8D7DA', '#C62828', '#9F1D1D', '&#10005;'
        label_text = 'NOT UNIFORM APPROVED'
    text = (
        f'<span style="font-size:6.2pt;font-weight:700;color:{color};white-space:nowrap">'
        f'{label_text}</span>'
        if label else ''
    )
    return (
        f'<span style="display:inline-flex;align-items:center;gap:3pt;flex-shrink:0">'
        f'<span style="width:{size}pt;height:{size}pt;border-radius:50%;'
        f'background:{bg};border:1pt solid {border};color:{color};'
        f'display:inline-flex;align-items:center;justify-content:center;'
        f'font-size:{max(6, size - 4)}pt;font-weight:900;line-height:1">'
        f'{symbol}</span>{text}</span>'
    )

def _chip_svg(size=14, fill1='#64a077', fill2='#99b179'):
    """Return a tiny inline SVG of the pickle chip."""
    return (f'<svg viewBox="0 0 126 126" width="{size}" height="{size}" '
            f'xmlns="http://www.w3.org/2000/svg" style="display:inline-block;vertical-align:middle">'
            f'<path d="{PICKLE_SVG_PATH1}" fill="{fill1}"/>'
            f'<path d="{PICKLE_SVG_PATH2}" fill="{fill2}"/>'
            f'</svg>')

_EARN_MARGIN = 90  # pt — image column width on each side


def _build_earn_page_div(page, pi, total, pickle_value, accent, title, subtitle, chips_row, bubbles_svg, all_pages):
    reasons  = page.get('reasons', [])
    notes    = page.get('notes', [])
    headline = page.get('earn_headline', 'EARN PICKLES FOR FREE MERCH')
    M = _EARN_MARGIN  # shorthand

    # Collect item images from all non-earn pages
    all_images = []
    for p in all_pages:
        if p.get('type') == 'earn':
            continue
        for item in (p.get('items') or []):
            if item and not item.get('_unavailable') and item.get('image'):
                all_images.append(item['image'])

    rng = random.Random(pi * 99991 + 13)
    rng.shuffle(all_images)
    left_imgs  = all_images[:4]
    right_imgs = all_images[4:8]

    IMG_SIZE = 74
    IMG_TOP  = 144
    IMG_BOT  = 752

    def _side_imgs(images, cx):
        if not images: return ''
        n    = len(images)
        step = (IMG_BOT - IMG_TOP) / (n + 1)
        out  = ''
        for i, url in enumerate(images):
            cy = IMG_TOP + step * (i + 1)
            x  = int(cx - IMG_SIZE / 2)
            y  = int(cy - IMG_SIZE / 2)
            out += (
                f'<img class="earn-filler-image" src="{url}" '
                f'style="position:absolute;left:{x}pt;top:{y}pt;'
                f'width:{IMG_SIZE}pt;height:{IMG_SIZE}pt;object-fit:contain;'
                f'border-radius:8pt;border:0.8pt solid #E8DFC8;'
                f'box-shadow:1pt 2pt 5pt rgba(0,0,0,.07)">'
            )
        return out

    margin_imgs_html = (
        _side_imgs(left_imgs,  M // 2) +
        _side_imgs(right_imgs, 612 - M // 2)
    )

    HEADLINE_BOTTOM = 184  # approximate bottom edge of the headline divider row
    if pickle_value != 1:
        reasons_top    = 238
        pill_top       = (HEADLINE_BOTTOM + reasons_top) // 2 - 14  # vertically center ~28pt pill
        chip_note_html = (
            f'<div style="position:absolute;top:{pill_top}pt;left:{M}pt;right:{M}pt;'
            f'display:flex;justify-content:center">'
            f'<div style="background:#FFFBF0;border:1.5pt solid #FFC72C;border-radius:20pt;'
            f'padding:5pt 18pt;display:flex;align-items:center;gap:7pt">'
            f'{_chip_svg(15)}'
            f'<span style="font-size:10.5pt;font-weight:700;color:#1A1A1A">'
            f'1 CHIP = {pickle_value} POINTS</span>'
            f'</div></div>'
        )
    else:
        chip_note_html = ''
        reasons_top    = 208

    reason_rows_html = ''
    for i, r in enumerate(reasons):
        label   = r.get('label', '')
        value   = r.get('value', 0)
        r_type  = r.get('type', 'add')
        scope   = (r.get('scope') or '').strip()
        row_bg  = '#F9F5EE' if i % 2 == 0 else '#FFFFFF'
        top     = reasons_top + i * 28

        if r_type == 'multiply':
            if isinstance(value, (int, float)) and value > 0:
                top_text = f'&times;{int(value)}'
            else:
                top_text = f'&times;{value} POINTS' if value else '&times;?'
            top_size  = '13pt'
            bot_text  = scope or 'EVERYBODY WINS!'
            val_color = accent
        else:
            if isinstance(value, (int, float)):
                top_text  = f'+{int(value)} POINTS!' if value > 0 else f'{int(value)} POINTS!'
                val_color = accent if value >= 0 else '#C0392B'
            else:
                top_text  = f'{value} POINTS!'
                val_color = accent
            top_size = '10pt'
            bot_text = scope or '(1 chip)'

        reason_rows_html += (
            f'<div style="position:absolute;top:{top}pt;left:{M}pt;right:{M}pt;height:26pt;'
            f'background:{row_bg};border-radius:4pt;'
            f'display:flex;align-items:center;padding:0 10pt;gap:8pt">'
            f'{_chip_svg(11)}'
            f'<span style="flex:1;font-size:9.5pt;font-weight:600;color:#1A1A1A"'
            f' contenteditable spellcheck="false">{label}</span>'
            f'<div style="display:flex;flex-direction:column;align-items:flex-end;line-height:1.2">'
            f'<span style="font-size:{top_size};font-weight:700;color:{val_color}"'
            f' contenteditable spellcheck="false">{top_text}</span>'
            f'<span style="font-size:6.5pt;font-weight:600;color:#9A8A76">{bot_text}</span>'
            f'</div>'
            f'</div>'
        )

    after_reasons = reasons_top + len(reasons) * 28 + 16
    cta_html = (
        f'<div style="position:absolute;top:{after_reasons}pt;left:{M}pt;right:{M}pt;'
        f'text-align:center">'
        f'<span style="font-size:11pt;font-weight:700;color:{accent};letter-spacing:1pt">'
        f'ASK HOW TO EARN MORE!</span>'
        f'</div>'
    )

    notes_top = after_reasons + 24
    notes_html = ''.join(
        f'<div style="position:absolute;top:{notes_top + i * 16}pt;left:{M}pt;right:{M}pt;'
        f'font-size:7.5pt;color:#9A8A76">&bull; {note}</div>'
        for i, note in enumerate(notes)
    )

    # Extra merch images below content if there's room
    content_bottom = notes_top + max(len(notes), 0) * 16 + 12
    FOOTER_TOP     = 754
    available      = FOOTER_TOP - content_bottom
    EX_SIZE        = 64
    EX_GAP         = 10
    EX_ROW_PAD     = 14
    CENTER_W       = 612 - 2 * M
    n_per_row      = int((CENTER_W + EX_GAP) / (EX_SIZE + EX_GAP))
    row_total_w    = n_per_row * EX_SIZE + (n_per_row - 1) * EX_GAP
    row_start_x    = M + (CENTER_W - row_total_w) // 2
    rows_fit       = min(3, max(0, (available - EX_ROW_PAD) // (EX_SIZE + EX_ROW_PAD)))
    extra_pool     = all_images[8:] or all_images  # prefer images not already in the side columns
    extra_imgs_html = ''
    for row_idx in range(rows_fit):
        row_imgs = extra_pool[row_idx * n_per_row : (row_idx + 1) * n_per_row]
        if not row_imgs:
            break
        row_top = int(content_bottom + EX_ROW_PAD + row_idx * (EX_SIZE + EX_ROW_PAD))
        for j, url in enumerate(row_imgs):
            x = int(row_start_x + j * (EX_SIZE + EX_GAP))
            extra_imgs_html += (
                f'<img class="earn-filler-image" src="{url}" '
                f'style="position:absolute;left:{x}pt;top:{row_top}pt;'
                f'width:{EX_SIZE}pt;height:{EX_SIZE}pt;object-fit:contain;'
                f'border-radius:6pt;border:0.8pt solid #E8DFC8;'
                f'box-shadow:1pt 2pt 5pt rgba(0,0,0,.07)">'
            )

    footer_label = "PICKLE" if pickle_value == 1 else "PICKLES"

    return f'''
<div class="page" style="position:relative;width:612pt;height:792pt;
     background:#fff;overflow:hidden;flex-shrink:0">
  <div style="position:absolute;top:0;left:0;width:612pt;height:130pt;
              background:{accent};overflow:hidden">
    {bubbles_svg}
    <div style="position:absolute;top:8pt;left:10pt;width:108pt;height:108pt;
                display:flex;align-items:center;justify-content:center">
      <svg viewBox="0 0 126 126" width="104" height="104" xmlns="http://www.w3.org/2000/svg">
        <path d="{PICKLE_SVG_PATH1}" fill="#64a077"/>
        <path d="{PICKLE_SVG_PATH2}" fill="#99b179"/>
      </svg>
    </div>
    <div style="position:absolute;top:16pt;left:122pt;
                font-size:34pt;font-weight:700;color:#fff;
                font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                white-space:nowrap;line-height:1">PICKLE POINTS</div>
    <div style="position:absolute;top:58pt;left:124pt;
                font-size:11pt;font-weight:700;color:rgba(255,255,255,.8);
                letter-spacing:.5pt;white-space:nowrap"
         contenteditable spellcheck="false">{subtitle.upper()}</div>
    <div style="position:absolute;top:42pt;right:28pt;
                font-size:13pt;font-weight:700;color:#fff;
                text-align:right;white-space:nowrap"
         contenteditable spellcheck="false">{title.upper()}</div>
    <div style="position:absolute;top:16pt;right:28pt;
                font-size:7.5pt;color:rgba(255,255,255,.7)">
      PAGE {pi+1} OF {total}
    </div>
    <div style="position:absolute;top:82pt;right:28pt;
                display:flex;gap:8pt;align-items:center">
      {chips_row}
    </div>
  </div>
  <div style="position:absolute;top:128pt;left:0;width:612pt;height:8pt;
              background:#FFC72C"></div>
  <div style="position:absolute;top:136pt;left:0;width:612pt;height:28pt;
              background:#1A1A1A;display:flex;align-items:center;justify-content:flex-end;
              padding-right:28pt">
    <span class="print-on-dark" style="font-size:6.5pt;color:rgba(255,255,255,.5);font-weight:600">
      PRICES SUBJECT TO CHANGE &nbsp;&bull;&nbsp; ORDERS WILL BE SUBMITTED ON THE LAST DAY OF EACH MONTH
    </span>
  </div>
  {margin_imgs_html}
  <div style="position:absolute;top:172pt;left:{M}pt;right:{M}pt;
              display:flex;align-items:center;gap:10pt">
    <div style="flex:1;height:0.5pt;background:#E8DFC8"></div>
    <span style="font-size:8pt;font-weight:700;color:#9A8A76;white-space:nowrap"
          contenteditable spellcheck="false">{headline.upper()}</span>
    <div style="flex:1;height:0.5pt;background:#E8DFC8"></div>
  </div>
  {chip_note_html}
  {reason_rows_html}
  {cta_html}
  {notes_html}
  {extra_imgs_html}
  <div style="position:absolute;bottom:0;left:0;width:612pt;height:38pt;
              background:#1A1A1A;display:flex;align-items:center;padding:0 28pt">
    <div style="flex:1">
      <div class="print-on-dark" style="font-size:7pt;font-weight:700;color:rgba(255,255,255,.45)">
        EACH CHIP = {pickle_value} {footer_label} &nbsp;&bull;&nbsp; SEE CARMEN TO REDEEM &nbsp;&bull;&nbsp; {_uniform_approved_marker_html(9, True, True)} &nbsp;&bull;&nbsp; {_uniform_approved_marker_html(9, True, 'weekend')} &nbsp;&bull;&nbsp; {_uniform_approved_marker_html(9, True, False)}
      </div>
      <div class="print-on-dark-secondary" style="font-size:7pt;font-weight:700;color:rgba(255,255,255,.35);margin-top:2pt">
        NOT EVERY ITEM IS DRESS CODE APPROVED &mdash; USE DISCRETION
      </div>
    </div>
    <div style="font-size:11pt;font-weight:700;color:#FFC72C">I'M LOVIN' IT</div>
  </div>
</div>'''


def render_preview_html(pages, per_pickle, pickle_value, tag_colors):
    total = len(pages)
    page_divs = []

    for pi, page in enumerate(pages):
        accent  = page.get('accent', '#DA291C')
        title   = page.get('title', '')
        subtitle= page.get('subtitle', '')
        section = page.get('section_label', '')
        lay     = page.get('layout', {})
        cols    = int(lay.get('cols', 4))
        card_h  = int(lay.get('card_h', 126))
        gutter  = int(lay.get('gutter', 12))
        items   = page.get('items') or []

        # Bubbles (SVG circles)
        bubble_svg_parts = []
        for bx, by, br in _bubble_positions(pi):
            bubble_svg_parts.append(
                f'<circle cx="{bx}" cy="{by}" r="{br}" fill="rgba(0,0,0,0.08)"/>'
            )
        bubbles_svg = (
            f'<svg viewBox="0 0 612 130" preserveAspectRatio="none" '
            f'style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none">'
            + ''.join(bubble_svg_parts) +
            f'</svg>'
        )

        # 5-pickle chips row
        chips_row = ''.join(_chip_svg(14) for _ in range(5))

        if page.get('type') == 'earn':
            page_divs.append(_build_earn_page_div(
                page, pi, total, pickle_value, accent, title, subtitle, chips_row, bubbles_svg, pages
            ))
            continue

        # Card grid
        card_cells = []
        for item in items:
            if item is None: continue
            name     = item.get('name', '')
            desc     = item.get('desc', '')
            pickles  = item.get('pickles', 0) or 0
            tag      = item.get('tag')
            image    = item.get('image', '')
            variants = item.get('variants', [])
            approved = item.get('uniform_approved', False)
            unavailable = bool(item.get('_unavailable', False))

            pickles_str = str(pickles)

            tag_html  = _tag_badge_html(tag, tag_colors)
            swatch_html = _variant_swatches_html(variants)
            approved_html = '' if unavailable else _uniform_approved_marker_html(10, approved=approved)
            bottom_approved_html = '' if image else approved_html
            image_approved_html = (
                f'<span class="uniform-marker-overlay" style="position:absolute;right:1pt;bottom:1pt;'
                f'display:flex;align-items:center;justify-content:center;'
                f'filter:drop-shadow(0 0.8pt 1.2pt rgba(0,0,0,.24))">'
                f'{approved_html}</span>'
                if image else ''
            )
            img_html = (
                f'<img class="reward-image" src="{image}" alt="" '
                f'style="width:48pt;height:48pt;object-fit:contain;'
                f'border-radius:4pt;display:block">'
                if image else ''
            )
            floating_img_html = (
                f'<span style="float:right;width:48pt;height:48pt;margin:0 0 4pt 7pt;'
                f'display:flex;align-items:flex-start;justify-content:center;position:relative">'
                f'{img_html}{image_approved_html}</span>'
                if image else ''
            )
            unavailable_html = (
                '<div class="unavailable-card-label" '
                'style="position:absolute;z-index:20;left:-20%;top:50%;width:140%;'
                'transform:translateY(-50%) rotate(-16deg);background:#C62828;color:#fff;'
                'border-top:1.5pt solid rgba(255,255,255,.8);'
                'border-bottom:1.5pt solid rgba(255,255,255,.8);'
                'box-shadow:0 2pt 5pt rgba(0,0,0,.28);padding:6pt 2pt;'
                'font-size:9pt;font-weight:800;line-height:1;text-align:center;'
                'letter-spacing:.2pt;pointer-events:none">Not currently available.</div>'
                if unavailable else ''
            )

            if pickle_value != 1:
                points = pickles * pickle_value
                price_content = (
                    f'<div style="display:flex;align-items:baseline;gap:3pt;line-height:1">'
                    f'<span style="font-size:19pt;font-weight:700;color:{accent};line-height:1"'
                    f' contenteditable spellcheck="false">{pickles_str}</span>'
                    f'<span style="font-size:6.5pt;font-weight:700;color:#9A8A76">CHIPS</span>'
                    f'</div>'
                    f'<div style="font-size:6.5pt;font-weight:700;color:#9A8A76;line-height:1.05"'
                    f' contenteditable spellcheck="false">{points} PTS</div>'
                )
            else:
                price_content = (
                    f'<div style="display:flex;align-items:baseline;gap:3pt;line-height:1">'
                    f'<span style="font-size:20pt;font-weight:700;color:{accent};line-height:1"'
                    f' contenteditable spellcheck="false">{pickles_str}</span>'
                    f'<span style="font-size:7pt;font-weight:700;color:#9A8A76">CHIPS</span>'
                    f'</div>'
                )
            metadata_html = (
                '<div class="reward-meta" style="min-width:0;display:grid;'
                'grid-template-rows:12pt 12pt;row-gap:2pt;align-content:start;padding-top:1pt">'
                f'<div class="reward-variants" style="min-width:0;display:flex;align-items:center;'
                f'gap:3pt;overflow:hidden">{bottom_approved_html}{swatch_html}</div>'
                f'<div class="reward-tag" style="display:flex;align-items:center;justify-content:center;overflow:hidden">'
                f'{tag_html}</div>'
                '</div>'
            )
            footer_html = '' if unavailable else (
                '<div class="reward-footer" style="position:absolute;bottom:0;left:8pt;right:8pt;'
                'height:44pt;display:grid;grid-template-columns:max-content minmax(0,1fr);'
                'column-gap:7pt;align-items:start;padding-top:6pt;overflow:hidden">'
                f'<div class="reward-price" style="display:flex;flex-direction:column;'
                f'align-items:flex-start;gap:1pt">{price_content}</div>'
                f'{metadata_html}'
                '</div>'
            )

            divider_html = '' if unavailable else (
                f'<div class="reward-divider" style="position:absolute;bottom:{card_h - (card_h - 44)}pt;'
                f'left:8pt;right:8pt;border-top:0.7pt dashed #E8DFC8"></div>'
            )

            cell_html = f'''
<div class="reward-card" style="position:relative;background:#fff;border-radius:8pt;
     border:0.8pt solid #E8DFC8;box-shadow:2pt 2pt 6pt rgba(0,0,0,.08);
     height:{card_h}pt;overflow:hidden;break-inside:avoid;page-break-inside:avoid">
  <div style="position:absolute;top:0;left:0;right:0;height:8pt;
              background:{accent};border-radius:8pt 8pt 0 0"></div>
  <div class="reward-copy" style="position:absolute;top:11pt;left:8pt;right:8pt;bottom:48pt;
              overflow:hidden;overflow-wrap:anywhere;word-break:break-word">
    {floating_img_html}
    <div class="reward-name" style="font-size:9pt;font-weight:700;color:#1A1A1A;line-height:1.16;
                margin-bottom:2pt"
         contenteditable spellcheck="false">{name}</div>
    <div class="reward-desc" style="font-size:6.5pt;color:#9A8A76;line-height:1.25"
         contenteditable spellcheck="false">{desc}</div>
  </div>
  {divider_html}
  {footer_html}
  {unavailable_html}
</div>'''
            card_cells.append(cell_html)

        # "Coming soon" if needed
        if card_cells and len(card_cells) % cols != 0:
            card_cells.append(f'''
<div class="reward-card coming-soon-card" style="background:#F2F2F2;border-radius:8pt;
     border:1.5pt dashed #7AAD35;height:{card_h}pt;
     display:flex;flex-direction:column;align-items:center;
     justify-content:center;break-inside:avoid;page-break-inside:avoid">
  <div style="font-size:9pt;font-weight:700;color:#9A8A76">MORE COMING SOON</div>
  <div style="font-size:7pt;color:#9A8A76;margin-top:4pt">Check back later!</div>
</div>''')

        footer_label = "POINT" if pickle_value == 1 else "POINTS"

        page_div = f'''
<div class="page" style="position:relative;width:612pt;height:792pt;
     background:#fff;overflow:hidden;flex-shrink:0">

  <!-- Header -->
  <div style="position:absolute;top:0;left:0;width:612pt;height:130pt;
              background:{accent};overflow:hidden">
    {bubbles_svg}
    <!-- Big pickle icon -->
    <div style="position:absolute;top:8pt;left:10pt;width:108pt;height:108pt;
                display:flex;align-items:center;justify-content:center">
      <svg viewBox="0 0 126 126" width="104" height="104" xmlns="http://www.w3.org/2000/svg">
        <path d="{PICKLE_SVG_PATH1}" fill="#64a077"/>
        <path d="{PICKLE_SVG_PATH2}" fill="#99b179"/>
      </svg>
    </div>
    <!-- Brand name -->
    <div style="position:absolute;top:16pt;left:122pt;
                font-size:34pt;font-weight:700;color:#fff;
                font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                white-space:nowrap;line-height:1">PICKLE POINTS</div>
    <!-- Subtitle -->
    <div style="position:absolute;top:58pt;left:124pt;
                font-size:11pt;font-weight:700;color:rgba(255,255,255,.8);
                letter-spacing:.5pt;white-space:nowrap"
         contenteditable spellcheck="false">{subtitle.upper()}</div>
    <!-- Page title -->
    <div style="position:absolute;top:42pt;right:28pt;
                font-size:13pt;font-weight:700;color:#fff;
                text-align:right;white-space:nowrap"
         contenteditable spellcheck="false">{title.upper()}</div>
    <!-- Page N of M -->
    <div style="position:absolute;top:16pt;right:28pt;
                font-size:7.5pt;color:rgba(255,255,255,.7)">
      PAGE {pi+1} OF {total}
    </div>
    <!-- 5 pickle chips -->
    <div style="position:absolute;top:82pt;right:28pt;
                display:flex;gap:8pt;align-items:center">
      {chips_row}
    </div>
  </div>

  <!-- Yellow stripe -->
  <div style="position:absolute;top:128pt;left:0;width:612pt;height:8pt;
              background:#FFC72C"></div>

  <!-- Legend bar -->
  <div style="position:absolute;top:136pt;left:0;width:612pt;height:28pt;
              background:#1A1A1A;display:flex;align-items:center;justify-content:flex-end;
              padding-right:28pt">
    <span class="print-on-dark" style="font-size:6.5pt;color:rgba(255,255,255,.5);font-weight:600">
      PRICES SUBJECT TO CHANGE &nbsp;&bull;&nbsp; ORDERS WILL BE SUBMITTED ON THE LAST DAY OF EACH MONTH
    </span>
  </div>

  <!-- Section label -->
  <div style="position:absolute;top:172pt;left:28pt;right:28pt;
              display:flex;align-items:center;gap:10pt">
    <span style="font-size:8pt;font-weight:700;color:#9A8A76;white-space:nowrap"
          contenteditable spellcheck="false">{section.upper()}</span>
    <div style="flex:1;height:0.5pt;background:#E8DFC8"></div>
  </div>

  <!-- Card grid -->
  <div style="position:absolute;top:188pt;left:28pt;right:28pt;bottom:42pt;
              display:grid;grid-template-columns:repeat({cols},1fr);
              gap:{gutter}pt;align-content:start;overflow:hidden">
    {''.join(card_cells)}
  </div>

  <!-- Footer -->
  <div style="position:absolute;bottom:0;left:0;width:612pt;height:38pt;
              background:#1A1A1A;display:flex;align-items:center;padding:0 28pt">
    <div style="flex:1">
      <div class="print-on-dark" style="font-size:7pt;font-weight:700;color:rgba(255,255,255,.45)">
        EACH CHIP = {pickle_value} {footer_label} &nbsp;&bull;&nbsp; SEE CARMEN TO REDEEM &nbsp;&bull;&nbsp; {_uniform_approved_marker_html(9, True, True)} &nbsp;&bull;&nbsp; {_uniform_approved_marker_html(9, True, 'weekend')} &nbsp;&bull;&nbsp; {_uniform_approved_marker_html(9, True, False)}
      </div>
      <div class="print-on-dark-secondary" style="font-size:7pt;font-weight:700;color:rgba(255,255,255,.35);margin-top:2pt">
        NOT EVERY ITEM IS DRESS CODE APPROVED &mdash; USE DISCRETION
      </div>
    </div>
    <div style="font-size:11pt;font-weight:700;color:#FFC72C">I'M LOVIN' IT</div>
  </div>
</div>'''
        page_divs.append(page_div)

    pages_html = '\n<div class="page-screen-gap"></div>\n'.join(page_divs)
    return render_template(
        "preview.html",
        pages_html=Markup(pages_html),
        total=total,
    )
