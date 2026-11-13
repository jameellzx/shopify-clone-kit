#!/usr/bin/env python3
"""Save a finished clone as a reusable template in the user's قوالب library, with an HTML copy.

Usage:
    python save_template.py <theme_dir> <name> --title "..." [--images DIR] [--previews a.jpg b.jpg]
                            [--source-url URL] [--store x.myshopify.com --theme-id N] [--library DIR]
    python save_template.py --gallery [--library DIR]      # only rebuild <library>/index.html

Writes <library>/<name>/:
    template.json, sections/ck-*.liquid, templates/index.json, templates/footer-section.json,
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
    a = ap.parse_args()
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

    subprocess.run([sys.executable, os.path.join(HERE, "export_html.py"), dst], check=True)
    html_preview(dst)
    build_gallery(a.library)
    print(f"saved template: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
