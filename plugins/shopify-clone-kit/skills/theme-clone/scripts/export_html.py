#!/usr/bin/env python3
"""Render a saved template (sections/*.liquid + templates/index.json) to one static HTML page.

The page uses the template's own section CSS and JS, real images from <template>/images/,
and Google Fonts for the heading/body fonts, so it opens in any browser without Shopify.

Usage:
    python export_html.py <template_dir> [--out <template_dir>/html/index.html] [--title "..."]

Demo builders (fill a template with someone else's content, see slots.json) can also pass:
    --index FILE --footer FILE   use these instead of templates/index.json / footer-section.json
    --images DIR                 image folder (default <template_dir>/images)
    --shop-name NAME --logo FILE --nav "Home|Shop|Contact"   header text, logo image, menu labels
    --lang ar --dir rtl          <html lang/dir>
    --noindex                    <meta name="robots" content="noindex,nofollow">
    --head-html FILE --body-end-html FILE   extra HTML at the end of <head> / <body>
With none of these the output is the same as before.

Needs: pip install python-liquid
Covers the tags and filters clone sections use. Shopify-only pieces render as a plain
stand-in: {% form %} -> <form>, {% render %} -> nothing, video_tag -> nothing,
collection pickers -> empty (demo blocks show instead).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

try:
    from liquid import Environment
except ImportError:
    sys.exit("python-liquid missing: python -m pip install python-liquid")

SCHEMA_RE = re.compile(r"\{%-?\s*schema\s*-?%\}(.*?)\{%-?\s*endschema\s*-?%\}", re.S)
CSS_RE = re.compile(r"\{%-?\s*stylesheet\s*-?%\}(.*?)\{%-?\s*endstylesheet\s*-?%\}", re.S)
JS_RE = re.compile(r"\{%-?\s*javascript\s*-?%\}(.*?)\{%-?\s*endjavascript\s*-?%\}", re.S)
FORM_OPEN_RE = re.compile(r"\{%-?\s*form\s+'[^']*'[^%]*?(?:class:\s*'([^']*)')?[^%]*-?%\}")
FORM_CLOSE_RE = re.compile(r"\{%-?\s*endform\s*-?%\}")
RENDER_RE = re.compile(r"\{%-?\s*render\s[^%]*-?%\}")

# Shopify font handles -> Google Fonts family names (extend when a template uses another font).
FONT_NAMES = {
    "nunito": "Nunito", "nunito_sans": "Nunito Sans", "assistant": "Assistant", "montserrat": "Montserrat",
    "poppins": "Poppins", "lato": "Lato", "open_sans": "Open Sans", "roboto": "Roboto", "inter": "Inter",
    "dm_sans": "DM Sans", "work_sans": "Work Sans", "rubik": "Rubik", "karla": "Karla", "playfair_display": "Playfair Display",
    # Arabic
    "tajawal": "Tajawal", "cairo": "Cairo", "almarai": "Almarai", "ibm_plex_sans_arabic": "IBM Plex Sans Arabic",
    "noto_kufi_arabic": "Noto Kufi Arabic", "noto_naskh_arabic": "Noto Naskh Arabic", "readex_pro": "Readex Pro",
}

PLACEHOLDER = ('<svg class="{cls}" viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" '
               'xmlns="http://www.w3.org/2000/svg"><rect width="400" height="300" fill="#e9e9e9"/>'
               '<text x="200" y="155" text-anchor="middle" font-family="sans-serif" font-size="18" fill="#999">{name}</text></svg>')


class Font(dict):
    """Stands in for a Shopify font object."""

    def __init__(self, handle: str):
        base, _, variant = handle.rpartition("_")
        if not base:
            base, variant = handle, "n4"
        family = FONT_NAMES.get(base, base.replace("_", " ").title())
        super().__init__(family=family, fallback_families="sans-serif",
                         weight=int(variant[1:] or 4) * 100 if variant[1:].isdigit() else 400,
                         style="italic" if variant.startswith("i") else "normal")
        self.handle = handle

    def __str__(self):
        return self["family"]


def image_path(value, images_rel):
    if not value:
        return ""
    name = str(value).rsplit("/", 1)[-1]
    return f"{images_rel}/{name}"


def build_env(images_rel: str, currency: str) -> Environment:
    env = Environment()
    f = env.filters
    f["image_url"] = lambda v, **kw: image_path(v, images_rel)
    def image_tag(src, **kw):
        attrs = {"src": src, "alt": "", "loading": kw.get("loading") or "lazy"}
        if kw.get("class"):
            attrs["class"] = kw["class"]
        return "<img " + " ".join(f'{k}="{html.escape(str(v), quote=True)}"' for k, v in attrs.items()) + ">"
    f["image_tag"] = image_tag
    f["placeholder_svg_tag"] = lambda name, cls="": PLACEHOLDER.format(cls=cls, name=html.escape(str(name)))
    f["font_face"] = lambda font, **kw: ""
    f["video_tag"] = lambda v, **kw: ""
    f["money"] = lambda v: f"{currency}{(float(v or 0) / 100):,.2f}"
    f["t"] = lambda v, **kw: str(v).rsplit(".", 1)[-1].replace("_", " ")
    f["link_to"] = lambda text, url: f'<a href="{url}">{text}</a>'
    return env


def preprocess(src: str) -> str:
    src = SCHEMA_RE.sub("", src)
    src = CSS_RE.sub("", src)
    src = JS_RE.sub("", src)
    src = FORM_OPEN_RE.sub(lambda m: f'<form onsubmit="return false" class="{m.group(1) or ""}">', src)
    src = FORM_CLOSE_RE.sub("</form>", src)
    src = RENDER_RE.sub("", src)
    return src


def settings_with_defaults(schema_settings, values, images_rel):
    out = {}
    for s in schema_settings or []:
        sid = s.get("id")
        if not sid:
            continue
        val = values.get(sid, s.get("default", ""))
        t = s.get("type")
        if t == "font_picker":
            val = Font(val or "assistant_n4")
        elif t in ("image_picker", "video", "collection", "product", "link_list") and val is None:
            val = ""
        if t in ("collection", "product", "link_list", "video"):
            # Store resources do not exist offline: render as empty (demo blocks / fallbacks show).
            val = ""
        out[sid] = val
    for k, v in values.items():
        out.setdefault(k, v)
    return out


def render_section(env, sec_dir, key, data, images_rel, stylesheets, scripts, fonts, shop_name="My Store"):
    path = os.path.join(sec_dir, data["type"] + ".liquid")
    if not os.path.exists(path):
        return f"<!-- section type {data['type']} not in template -->"
    src = open(path, encoding="utf-8").read()
    schema = json.loads(SCHEMA_RE.search(src).group(1))
    if data["type"] not in stylesheets:
        stylesheets[data["type"]] = "\n".join(CSS_RE.findall(src))
        scripts[data["type"]] = "\n".join(JS_RE.findall(src))
    settings = settings_with_defaults(schema.get("settings"), data.get("settings", {}), images_rel)
    for v in settings.values():
        if isinstance(v, Font):
            fonts.add((v["family"], v["weight"]))
    block_defs = {b["type"]: b for b in schema.get("blocks", [])}
    blocks = []
    for bkey in data.get("block_order", list((data.get("blocks") or {}).keys())):
        b = data["blocks"][bkey]
        if b.get("disabled"):
            continue
        bdef = block_defs.get(b["type"], {})
        blocks.append({"id": bkey, "type": b["type"], "shopify_attributes": "",
                       "settings": settings_with_defaults(bdef.get("settings"), b.get("settings", {}), images_rel)})
    ctx = {
        "section": {"id": key, "settings": settings, "blocks": blocks},
        "shop": {"name": shop_name, "policies": []},
        "routes": {"root_url": "#", "all_products_collection_url": "#", "cart_url": "#", "search_url": "#"},
        "settings": {},
        "request": {"design_mode": False},
    }
    body = env.from_string(preprocess(src)).render(**ctx)
    return f'<div id="shopify-section-{key}" class="shopify-section">{body}</div>'


BASE_CSS = """
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { -webkit-font-smoothing: antialiased; }
img, svg { max-width: 100%; }
a { color: inherit; }
button { font: inherit; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.ck-demo-header { display: flex; align-items: center; justify-content: space-between; padding: 18px 5%; font-family: var(--ck-demo-font, sans-serif); border-bottom: 1px solid #eee; background: #fff; position: sticky; top: 0; z-index: 10; }
.ck-demo-header strong { font-size: 22px; font-weight: 800; }
.ck-demo-header nav { display: flex; gap: 24px; font-size: 14px; }
.ck-demo-header nav a { text-decoration: none; }
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("--out")
    ap.add_argument("--title")
    ap.add_argument("--currency", default="$")
    ap.add_argument("--index")
    ap.add_argument("--footer")
    ap.add_argument("--images")
    ap.add_argument("--shop-name", default="My Store")
    ap.add_argument("--logo")
    ap.add_argument("--nav", default="Home|Catalog|Contact")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--dir", choices=["ltr", "rtl"])
    ap.add_argument("--noindex", action="store_true")
    ap.add_argument("--head-html")
    ap.add_argument("--body-end-html")
    a = ap.parse_args()

    tdir = os.path.abspath(a.template)
    out = os.path.abspath(a.out or os.path.join(tdir, "html", "index.html"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    images_dir = os.path.abspath(a.images) if a.images else os.path.join(tdir, "images")
    images_rel = os.path.relpath(images_dir, os.path.dirname(out)).replace("\\", "/")
    meta = {}
    if os.path.exists(os.path.join(tdir, "template.json")):
        meta = json.load(open(os.path.join(tdir, "template.json"), encoding="utf-8"))
    title = a.title or meta.get("title") or os.path.basename(tdir)

    env = build_env(images_rel, a.currency)
    sec_dir = os.path.join(tdir, "sections")
    stylesheets, scripts, fonts = {}, {}, set()
    parts = []
    overrides = {"index.json": a.index, "footer-section.json": a.footer}
    for fname in ("index.json", "footer-section.json"):
        path = overrides[fname] or os.path.join(tdir, "templates", fname)
        if not os.path.exists(path):
            continue
        data = json.load(open(path, encoding="utf-8-sig"))
        sections = data.get("sections", data)
        order = data.get("order", list(sections.keys()))
        for key in order:
            sec = sections[key]
            if sec.get("disabled"):
                continue
            parts.append(render_section(env, sec_dir, key, sec, images_rel, stylesheets, scripts, fonts, a.shop_name))

    families = {}
    for fam, w in fonts:
        families.setdefault(fam, set()).add(w)
    gf = "&".join(f"family={fam.replace(' ', '+')}:wght@{';'.join(str(w) for w in sorted(ws | {400, 700}))}"
                  for fam, ws in sorted(families.items()))
    first_font = sorted(families)[0] if families else "sans-serif"

    def read(path):
        return open(path, encoding="utf-8").read() if path else ""
    html_attrs = f'lang="{html.escape(a.lang)}"' + (f' dir="{a.dir}"' if a.dir else "")
    head_extra = ('<meta name="robots" content="noindex,nofollow">\n' if a.noindex else "") + read(a.head_html)
    brand = html.escape(a.shop_name)
    if a.logo:
        logo_rel = os.path.relpath(os.path.abspath(a.logo), os.path.dirname(out)).replace("\\", "/")
        brand = f'<img src="{html.escape(logo_rel)}" alt="{brand}" class="ck-demo-logo"> <span>{brand}</span>'
        head_extra += ("<style>.ck-demo-header strong { display: flex; align-items: center; gap: 10px; }"
                       " .ck-demo-logo { height: 40px; width: 40px; border-radius: 50%; object-fit: cover; }</style>")
    nav = "".join(f'<a href="#">{html.escape(x)}</a>' for x in a.nav.split("|") if x)

    doc = f"""<!DOCTYPE html>
<html {html_attrs}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?{gf}&display=swap">' if gf else ''}
<style>
{BASE_CSS}
:root {{ --ck-demo-font: '{first_font}', sans-serif; }}
{''.join(stylesheets.values())}
</style>
{head_extra}</head>
<body>
<header class="ck-demo-header"><strong>{brand}</strong><nav>{nav}</nav></header>
{''.join(parts)}
<script>
{''.join(scripts.values())}
</script>
{read(a.body_end_html)}</body>
</html>
"""
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)
    print(f"wrote {out} ({len(parts)} sections, fonts: {', '.join(sorted(families)) or 'none'})")


if __name__ == "__main__":
    main()
