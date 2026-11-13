#!/usr/bin/env python3
"""Save a finished clone as a reusable template in the user's قوالب library, with an HTML copy.

Usage:
    python save_template.py <theme_dir> <name> --title "..." [--images DIR] [--previews a.jpg b.jpg]
                            [--source-url URL] [--store x.myshopify.com --theme-id N] [--library DIR]
    python save_template.py --gallery [--library DIR]      # only rebuild <library>/index.html
    python save_template.py --slots-only <template_dir>    # only (re)write <template>/slots.json

Writes <library>/<name>/:
    template.json, slots.json (fillable settings map for demo builders), sections/ck-*.liquid, templates/index.json, templates/footer-section.json,
    images/ (+ photo-credits.json when given), preview-*.jpg, source/ (gen.py, clone-manifest.json
    when found in <theme>/.clone/), html/index.html (standalone HTML version), README.md
and refreshes <library>/index.html (gallery), <library>/README.md table and <library>/install.py.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
def default_library():
    """CK_TEMPLATES_DIR if set, else a folder named قوالب in the current directory."""
    return os.environ.get("CK_TEMPLATES_DIR") or os.path.join(os.getcwd(), "قوالب")


DEFAULT_LIBRARY = default_library()
SCHEMA_RE = re.compile(r"\{%-?\s*schema\s*-?%\}(.*?)\{%-?\s*endschema\s*-?%\}", re.S)


def load_json(path):
    text = open(path, encoding="utf-8-sig").read()
    if text.lstrip().startswith("/*"):
        text = text[text.index("*/") + 2:]
    return json.loads(text)


def write_json(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


FILLABLE = {"text", "textarea", "richtext", "inline_richtext", "html", "image_picker", "url", "color",
            "color_background", "font_picker", "range", "number", "checkbox", "select", "video_url"}
TEXT_TYPES = {"text", "textarea", "richtext", "inline_richtext", "html"}
FACT_RE = re.compile(r"price|rating|review|count|quote|testimonial|guarantee|number|stat|award|press|"
                     r"customers|sold|years|percent", re.I)
FACT_BLOCKS = re.compile(r"review|testimonial|logo|press|stat|award|badge", re.I)
NOT_FACT_RE = re.compile(r"size|repeat|speed|padding|margin|width|height|columns|opacity|radius|gap|label$", re.I)
TAG_RE = re.compile(r"<[^>]+>")
CONTENT_TYPES = TEXT_TYPES | {"image_picker", "url", "video_url"}
BRAND_TYPES = {"color", "color_background", "font_picker"}


def is_grey(hex_color):
    h = hex_color.lstrip("#")
    return len(h) == 6 and h[0:2] == h[2:4] == h[4:6]


def build_slots(template_dir):
    """Write <template>/slots.json: every fillable setting of the template, so a demo builder can
    fill the template with a client's content (new values in a copy of index.json, then export_html.py).

    Each slot: path, file, section, section_type, block (key or null), block_type, setting_id, type,
    group (content = text/images/links, brand = colours/fonts, layout = sizes/toggles), label, value (current value, or the schema default), fact (must come from a real client source).
    Sections: can_hide, blocks (type -> can_repeat, max). leftovers: the template's own text, image
    file names and colours; none of them may remain in a filled demo."""
    sec_dir = os.path.join(template_dir, "sections")
    schemas = {}
    for path in glob.glob(os.path.join(sec_dir, "*.liquid")):
        m = SCHEMA_RE.search(open(path, encoding="utf-8").read())
        if m:
            schemas[os.path.basename(path)[:-7]] = json.loads(m.group(1))

    slots, sections, texts, images, colors = [], [], set(), set(), set()

    def add(file, key, stype, bkey, btype, sdefs, values):
        for s in sdefs or []:
            sid, t = s.get("id"), s.get("type")
            if not sid or t not in FILLABLE:
                continue
            val = values.get(sid, s.get("default"))
            label = s.get("label", sid)
            fact = bool(FACT_RE.search(sid) or FACT_RE.search(str(label)) or (btype and FACT_BLOCKS.search(btype)))
            if (t not in TEXT_TYPES and t not in ("range", "number")) or NOT_FACT_RE.search(sid):
                fact = False
            group = "content" if t in CONTENT_TYPES else "brand" if t in BRAND_TYPES else "layout"
            loc = f"{file}:{key}" + (f"/{bkey}" if bkey else "") + f"/{sid}"
            slots.append({"path": loc, "file": file, "section": key, "section_type": stype, "block": bkey,
                          "block_type": btype, "setting_id": sid, "type": t, "group": group, "label": label,
                          "value": val, "fact": fact})
            if val in (None, ""):
                continue
            if t in TEXT_TYPES:
                plain = html.unescape(TAG_RE.sub(" ", str(val))).strip()
                if len(plain) >= 4:
                    texts.add(" ".join(plain.split()))
            elif t == "image_picker":
                images.add(str(val).rsplit("/", 1)[-1])
            elif t in ("color", "color_background") and str(val).startswith("#") and not is_grey(str(val)):
                colors.add(str(val).upper())

    for file in ("index", "footer-section"):
        path = os.path.join(template_dir, "templates", file + ".json")
        if not os.path.exists(path):
            continue
        data = load_json(path)
        secs = data.get("sections", data)
        for key in data.get("order", list(secs.keys())):
            sec = secs[key]
            schema = schemas.get(sec.get("type"), {})
            add(file, key, sec["type"], None, None, schema.get("settings"), sec.get("settings") or {})
            bdefs = {b["type"]: b for b in schema.get("blocks", []) if b.get("type")}
            for bkey in sec.get("block_order", list((sec.get("blocks") or {}).keys())):
                b = sec["blocks"][bkey]
                add(file, key, sec["type"], bkey, b["type"], bdefs.get(b["type"], {}).get("settings"),
                    b.get("settings") or {})
            sections.append({
                "file": file, "section": key, "type": sec["type"], "can_hide": True,
                "disabled": bool(sec.get("disabled")),
                "block_order": sec.get("block_order", list((sec.get("blocks") or {}).keys())),
                "blocks": {t: {"can_repeat": True, "limit": d.get("limit")} for t, d in bdefs.items()},
                "max_blocks": schema.get("max_blocks"),
            })

    out = {
        "template": os.path.basename(os.path.abspath(template_dir)),
        "how_to_fill": "Copy templates/*.json, set new values at each slot path (file:section[/block]/setting), "
                       "clone a block of the same type to add items, set \"disabled\": true to hide a section, "
                       "then run export_html.py --index <new index.json> --images <new images dir>.",
        "slots": slots,
        "sections": sections,
        "leftovers": {"texts": sorted(texts), "images": sorted(images), "colors": sorted(colors)},
    }
    write_json(os.path.join(template_dir, "slots.json"), out)
    groups = {g: sum(s["group"] == g for s in slots) for g in ("content", "brand", "layout")}
    print(f"slots: {len(slots)} settings {groups}, {len(sections)} sections, "
          f"{sum(s['fact'] for s in slots)} fact slots -> {os.path.join(template_dir, 'slots.json')}")
    return out


def templates(library):
    out = []
    for name in sorted(os.listdir(library)):
        meta = os.path.join(library, name, "template.json")
        if os.path.isfile(meta):
            out.append((name, load_json(meta)))
    return out


def html_preview(template_dir):
    """Screenshot html/index.html (1440x900, top of page) into preview-0-html.jpg."""
    page = os.path.join(template_dir, "html", "index.html")
    if not os.path.exists(page):
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright missing: no HTML preview image")
        return
    from pathlib import Path
    out = os.path.join(template_dir, "preview-0-html.jpg")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(Path(page).as_uri(), wait_until="networkidle")
        pg.wait_for_timeout(800)
        pg.screenshot(path=out, type="jpeg", quality=85)
        b.close()
    print(f"preview: {out}")


def build_gallery(library):
    cards = []
    rows = []
    for name, meta in templates(library):
        previews = sorted(glob.glob(os.path.join(library, name, "preview-*.jpg")))
        thumb = f"{name}/{os.path.basename(previews[0])}" if previews else ""
        sections = meta.get("sections", [])
        cards.append(f"""
  <article class="card">
    <a href="{name}/html/index.html" class="thumb">{f'<img src="{html.escape(thumb)}" alt="">' if thumb else ''}</a>
    <div class="body">
      <h2>{html.escape(name)}</h2>
      <p>{html.escape(meta.get('title', ''))}</p>
      <p class="meta">{len(sections)} sections · {html.escape(meta.get('made', ''))} · {html.escape(meta.get('fonts', ''))}</p>
      <div class="swatches">{''.join(f'<span title="{html.escape(k)} {v}" style="background:{v}"></span>' for k, v in (meta.get('colors') or {}).items())}</div>
      <div class="links"><a href="{name}/html/index.html">Open HTML</a><a href="{name}/README.md">README</a></div>
      <code>python install.py {html.escape(name)} "theme" --store x.myshopify.com --theme-id N</code>
    </div>
  </article>""")
        rows.append(f"| [{name}]({name}/README.md) | {meta.get('title', '')} | {len(sections)} | [HTML]({name}/html/index.html) |")

    page = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>قوالب</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, "Segoe UI", Tahoma, sans-serif; background: #f6f5f2; color: #1d1d1b; }}
  header {{ padding: 40px 6% 16px; }}
  h1 {{ margin: 0 0 6px; font-size: 34px; }}
  header p {{ margin: 0; color: #666; }}
  main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 24px; padding: 24px 6% 60px; }}
  .card {{ background: #fff; border-radius: 14px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08); display: flex; flex-direction: column; }}
  .thumb {{ display: block; aspect-ratio: 16 / 10; background: #eee; overflow: hidden; }}
  .thumb img {{ width: 100%; height: 100%; object-fit: cover; object-position: top; display: block; }}
  .body {{ padding: 18px 20px 20px; direction: ltr; text-align: left; }}
  h2 {{ margin: 0 0 4px; font-size: 20px; }}
  .body p {{ margin: 0 0 6px; font-size: 14px; }}
  .meta {{ color: #777; font-size: 12px !important; }}
  .swatches {{ display: flex; gap: 6px; margin: 10px 0; }}
  .swatches span {{ width: 22px; height: 22px; border-radius: 50%; border: 1px solid rgba(0,0,0,.1); }}
  .links {{ display: flex; gap: 10px; margin: 10px 0; }}
  .links a {{ background: #1d1d1b; color: #fff; padding: 8px 14px; border-radius: 8px; text-decoration: none; font-size: 13px; }}
  .links a + a {{ background: #ecebe6; color: #1d1d1b; }}
  code {{ display: block; font-size: 11px; background: #f3f2ee; padding: 8px; border-radius: 6px; word-break: break-all; }}
</style>
</head>
<body>
<header><h1>قوالب</h1><p>{len(cards)} قالب جاهز · اضغط على الصورة عشان تفتح نسخة الـ HTML</p></header>
<main>{''.join(cards)}
</main>
</body>
</html>
"""
    with open(os.path.join(library, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page)

    readme = os.path.join(library, "README.md")
    if os.path.exists(readme):
        text = open(readme, encoding="utf-8").read()
        table = "| القالب | شو هو | الأقسام | HTML |\n|---|---|---|---|\n" + "\n".join(rows) + "\n"
        text = re.sub(r"\| القالب \|.*?\n(?:\|.*\n)+", table, text, count=1, flags=re.S)
        open(readme, "w", encoding="utf-8", newline="\n").write(text)
    shutil.copy(os.path.join(HERE, "install.py"), os.path.join(library, "install.py"))
    print(f"gallery: {os.path.join(library, 'index.html')} ({len(cards)} templates)")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("theme", nargs="?")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--title", default="")
    ap.add_argument("--images")
    ap.add_argument("--credits")
    ap.add_argument("--previews", nargs="*", default=[])
    ap.add_argument("--source-url", default="")
    ap.add_argument("--store", default="")
    ap.add_argument("--theme-id", default="")
    ap.add_argument("--library", default=DEFAULT_LIBRARY)
    ap.add_argument("--gallery", action="store_true")
    ap.add_argument("--slots-only", metavar="TEMPLATE_DIR", help="only (re)write <template>/slots.json")
    a = ap.parse_args()
    if a.slots_only:
        build_slots(a.slots_only)
        return 0
    os.makedirs(a.library, exist_ok=True)

    if a.gallery:
        for name, _ in templates(a.library):
            if not os.path.exists(os.path.join(a.library, name, "preview-0-html.jpg")):
                html_preview(os.path.join(a.library, name))
        build_gallery(a.library)
        return 0
    if not (a.theme and a.name):
        ap.error("theme and name are required (or use --gallery)")

    theme = os.path.abspath(a.theme)
    dst = os.path.join(a.library, a.name)
    for sub in ("sections", "templates", "images", "source"):
        os.makedirs(os.path.join(dst, sub), exist_ok=True)

    sections = sorted(glob.glob(os.path.join(theme, "sections", "ck-*.liquid")))
    for s in sections:
        shutil.copy(s, os.path.join(dst, "sections"))
    index = load_json(os.path.join(theme, "templates", "index.json"))
    write_json(os.path.join(dst, "templates", "index.json"), index)
    group = os.path.join(theme, "sections", "footer-group.json")
    if os.path.exists(group):
        fg = load_json(group)
        ck = {k: v for k, v in fg["sections"].items() if v.get("type", "").startswith("ck-") and not v.get("disabled")}
        if ck:
            write_json(os.path.join(dst, "templates", "footer-section.json"), ck)

    if a.images:
        for f in glob.glob(os.path.join(a.images, "*")):
            if os.path.isfile(f):
                shutil.copy(f, os.path.join(dst, "images"))
    if a.credits:
        shutil.copy(a.credits, os.path.join(dst, "images", "photo-credits.json"))
    for i, p in enumerate(a.previews, 1):
        shutil.copy(p, os.path.join(dst, f"preview-{i}.jpg"))
    for found in glob.glob(os.path.join(theme, ".clone", "*", "clone-manifest.json"))[:1]:
        shutil.copy(found, os.path.join(dst, "source"))

    # Colors and fonts from the sections' defaults, for the gallery card.
    colors, fonts = {}, set()
    for s in sections:
        schema = json.loads(SCHEMA_RE.search(open(s, encoding="utf-8").read()).group(1))
        for st in schema.get("settings", []):
            if st.get("id") == "background_color" and st.get("default") not in colors.values():
                colors[os.path.basename(s)[3:-7]] = st["default"]
            if st.get("type") == "font_picker":
                fonts.add(st.get("default", ""))
    meta = {
        "name": a.name,
        "title": a.title or a.name,
        "made": datetime.date.today().isoformat(),
        "source_url": a.source_url,
        "first_store": f"{a.store} theme #{a.theme_id}".strip(),
        "sections": [os.path.basename(s)[:-7] for s in sections],
        "page_order": index.get("order", []),
        "colors": dict(list(colors.items())[:8]),
        "fonts": ", ".join(sorted(fonts)),
    }
    old = os.path.join(dst, "template.json")
    if os.path.exists(old):
        meta = {**meta, **{k: v for k, v in load_json(old).items() if k in ("title", "colors", "fonts", "images", "copy")}}
    write_json(old, meta)
    build_slots(dst)

    subprocess.run([sys.executable, os.path.join(HERE, "export_html.py"), dst], check=True)
    html_preview(dst)
    build_gallery(a.library)
    print(f"saved template: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
