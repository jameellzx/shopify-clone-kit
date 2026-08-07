#!/usr/bin/env python3
"""Capture a source page for cloning into Shopify Liquid.

Produces, in --out:

    desktop.png / tablet.png / mobile.png   full-page, animations frozen
    dom.json                                visible element tree + computed styles
    tokens.json                             frequency-ranked colors, fonts, spacing, radii, shadows
    assets.json                             every image/svg/font with role + dimensions
    assets/                                 the downloaded files (unless --no-assets)
    behaviors.json                          interactive mechanics + suspected third-party apps
    states/*.png                            a screenshot per interaction state

Two modes:
    --mode remote   (default) capture the source site
    --mode local    capture your own `shopify theme dev` render for diffing;
                    replays the states recorded by a previous remote run via
                    --replay <behaviors.json>

Usage:
    python capture.py https://example.com --out .clone/run
    python capture.py http://127.0.0.1:9292 --mode local --replay .clone/run/behaviors.json --out .clone/run/local
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter

VIEWPORTS = {
    "desktop": (1440, 900),
    "tablet": (768, 1024),
    "mobile": (390, 844),
}

# Elements smaller than this in either dimension are skipped in the DOM dump.
MIN_BOX = 4
MAX_ELEMENTS = 2500

# Known third-party Shopify apps, matched against script/network hosts. The
# value is the mechanic to recreate natively - see references/app-behavior-recreations.md
APP_SIGNATURES = {
    "judge.me": "product reviews",
    "loox": "product reviews (photo)",
    "yotpo": "product reviews",
    "okendo": "product reviews",
    "stamped.io": "product reviews",
    "reviews.io": "product reviews",
    "klaviyo": "email capture popup",
    "privy": "email capture popup",
    "omnisend": "email capture popup",
    "attentive": "sms capture popup",
    "rebuy": "upsell / cross-sell",
    "boldapps": "options / upsell",
    "zipify": "landing page builder",
    "pagefly": "landing page builder",
    "gempages": "landing page builder",
    "shogun": "landing page builder",
    "hextom": "urgency / free shipping bar",
    "vitals": "app bundle (multiple mechanics)",
    "tidio": "live chat",
    "gorgias": "live chat",
    "smile.io": "loyalty",
    "swym": "wishlist / back-in-stock",
    "back-in-stock": "back-in-stock notify",
    "recharge": "subscriptions",
    "wiser": "recommendations",
    "searchanise": "predictive search",
    "algolia": "predictive search",
    "instafeed": "instagram feed",
    "trustpilot": "reviews badge",
    "cookieyes": "cookie consent",
    "consentmo": "cookie consent",
    "gdpr": "cookie consent",
}

FREEZE_CSS = """
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  animation-iteration-count: 1 !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
}
video { visibility: hidden !important; }
"""

# Some themes - Shopify's Horizon among them - do not scroll the document.
# They pin html/body to the viewport height and scroll an inner wrapper instead
# (`html:has(.page-wrapper), html:has(.page-wrapper) body { height: 100dvh;
# overflow: hidden }`). A full-page screenshot then returns only the viewport.
# Releasing those containers is what makes the shot show the whole page.
RELEASE_SCROLL_JS = r"""
() => {
  const released = [];
  const free = (el, why) => {
    el.style.setProperty('height', 'auto', 'important');
    el.style.setProperty('max-height', 'none', 'important');
    el.style.setProperty('overflow', 'visible', 'important');
    released.push(why);
  };
  free(document.documentElement, 'html');
  free(document.body, 'body');
  document.querySelectorAll('body *').forEach((el) => {
    const cs = getComputedStyle(el);
    const scrolls = /auto|scroll|hidden|clip/.test(cs.overflowY);
    const tall = el.scrollHeight > el.clientHeight + 8;
    const wide = el.clientWidth >= window.innerWidth * 0.9;
    if (scrolls && tall && wide) {
      free(el, el.tagName.toLowerCase() + '.' + String(el.className || '').split(' ')[0]);
    }
  });
  return released;
}
"""

# --------------------------------------------------------------------------
# In-page JavaScript
# --------------------------------------------------------------------------

JS_DOM = r"""
(limits) => {
  const { minBox, maxElements } = limits;
  const PROPS = [
    'display','position','flexDirection','justifyContent','alignItems','gap','rowGap','columnGap',
    'gridTemplateColumns','gridTemplateRows','flexWrap','order',
    'width','height','maxWidth','minHeight',
    'marginTop','marginRight','marginBottom','marginLeft',
    'paddingTop','paddingRight','paddingBottom','paddingLeft',
    'color','backgroundColor','backgroundImage','backgroundSize','backgroundPosition',
    'fontFamily','fontSize','fontWeight','fontStyle','lineHeight','letterSpacing','textAlign',
    'textTransform','textDecorationLine','whiteSpace',
    'borderTopWidth','borderRightWidth','borderBottomWidth','borderLeftWidth',
    'borderTopLeftRadius','borderTopRightRadius','borderBottomLeftRadius','borderBottomRightRadius',
    'borderColor','borderStyle','boxShadow','opacity','overflow','overflowX','zIndex',
    'objectFit','aspectRatio','textShadow','backdropFilter','transform'
  ];
  const out = [];
  const walk = (el, depth, path) => {
    if (out.length >= maxElements) return;
    const rect = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const visible = cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';
    const bigEnough = rect.width >= minBox && rect.height >= minBox;
    if (visible && bigEnough) {
      const style = {};
      for (const p of PROPS) {
        const v = cs[p];
        if (v && v !== 'none' && v !== 'normal' && v !== 'auto' && v !== '0px' && v !== 'rgba(0, 0, 0, 0)') {
          style[p] = v;
        }
      }
      const ownText = Array.from(el.childNodes)
        .filter(n => n.nodeType === 3)
        .map(n => n.textContent.trim())
        .join(' ')
        .slice(0, 300);
      out.push({
        path,
        tag: el.tagName.toLowerCase(),
        id: el.id || undefined,
        cls: el.className && typeof el.className === 'string' ? el.className.slice(0, 200) : undefined,
        role: el.getAttribute('role') || undefined,
        href: el.tagName === 'A' ? el.getAttribute('href') : undefined,
        text: ownText || undefined,
        depth,
        box: {
          x: Math.round(rect.x + scrollX),
          y: Math.round(rect.y + scrollY),
          w: Math.round(rect.width),
          h: Math.round(rect.height)
        },
        style
      });
    }
    let i = 0;
    for (const child of el.children) walk(child, depth + 1, path + '/' + (i++));
  };
  walk(document.body, 0, '0');
  return {
    url: location.href,
    title: document.title,
    lang: document.documentElement.lang || null,
    scrollHeight: document.documentElement.scrollHeight,
    elements: out
  };
}
"""

JS_ASSETS = r"""
() => {
  const seen = new Map();
  const add = (url, info) => {
    if (!url || url.startsWith('data:')) return;
    const abs = new URL(url, location.href).href;
    if (!seen.has(abs)) seen.set(abs, { url: abs, ...info });
  };
  const roleOf = (el) => {
    const hay = ((el.className || '') + ' ' + (el.alt || '') + ' ' + (el.id || '')).toLowerCase();
    if (/logo|brand/.test(hay)) return 'logo';
    if (/icon|badge|payment|trust/.test(hay)) return 'icon';
    if (/hero|banner|slide/.test(hay)) return 'hero';
    if (/product|item|card/.test(hay)) return 'product';
    if (/avatar|author|testimonial/.test(hay)) return 'avatar';
    return 'content';
  };
  document.querySelectorAll('img').forEach(img => {
    const r = img.getBoundingClientRect();
    add(img.currentSrc || img.src, {
      kind: 'image',
      role: roleOf(img),
      alt: img.alt || null,
      natural: [img.naturalWidth, img.naturalHeight],
      rendered: [Math.round(r.width), Math.round(r.height)],
      srcset: img.getAttribute('srcset') || null,
      loading: img.getAttribute('loading') || null
    });
  });
  document.querySelectorAll('source[srcset]').forEach(s => {
    const first = s.getAttribute('srcset').split(',')[0].trim().split(/\s+/)[0];
    add(first, { kind: 'image', role: 'source', media: s.getAttribute('media') || null });
  });
  document.querySelectorAll('*').forEach(el => {
    const bg = getComputedStyle(el).backgroundImage;
    if (bg && bg !== 'none') {
      const m = bg.match(/url\(["']?(.*?)["']?\)/);
      if (m) {
        const r = el.getBoundingClientRect();
        add(m[1], { kind: 'background', role: 'background', rendered: [Math.round(r.width), Math.round(r.height)] });
      }
    }
  });
  const fonts = [];
  try {
    document.fonts.forEach(f => fonts.push({ family: f.family, weight: f.weight, style: f.style, status: f.status }));
  } catch (e) {}
  performance.getEntriesByType('resource').forEach(e => {
    if (/\.(woff2?|ttf|otf|eot)(\?|$)/i.test(e.name)) add(e.name, { kind: 'font', role: 'font' });
    if (/\.svg(\?|$)/i.test(e.name)) add(e.name, { kind: 'svg', role: 'icon' });
  });
  const inlineSvg = document.querySelectorAll('svg').length;
  return { assets: Array.from(seen.values()), fonts, inlineSvgCount: inlineSvg };
}
"""

JS_SCRIPT_HOSTS = r"""
() => {
  const hosts = new Set();
  document.querySelectorAll('script[src]').forEach(s => {
    try { hosts.add(new URL(s.src, location.href).host); } catch (e) {}
  });
  performance.getEntriesByType('resource').forEach(e => {
    try { hosts.add(new URL(e.name).host); } catch (err) {}
  });
  return Array.from(hosts);
}
"""

# Candidate interactive triggers, in priority order. Each entry is
# [label, selector, max instances to probe].
JS_TRIGGERS = r"""
(limit) => {
  const groups = [
    ['nav-item',      'nav li:has(ul) > a, nav li:has(.submenu) > a, [data-has-dropdown], header [aria-haspopup]', 6],
    ['disclosure',    '[aria-expanded], details > summary, .accordion__title, [data-accordion-trigger]', 8],
    ['tab',           '[role="tab"], [data-tab], .tabs__button', 6],
    ['carousel',      '[aria-label*="Next" i], .swiper-button-next, .slick-next, [data-slide-next], .flickity-button.next', 4],
    ['carousel-dot',  '.swiper-pagination-bullet, .slick-dots button, [data-slide-to]', 4],
    ['drawer',        '[href="/cart"], [data-cart-drawer], .cart-icon, [aria-label*="cart" i], [data-drawer-open]', 3],
    ['modal',         '[data-modal-open], [data-size-guide], [href="#size-guide"], [data-popup-trigger]', 3],
    ['variant',       '[name="options[]"], .product-form__input input, [data-variant-option], .swatch input', 6],
    ['search',        '[aria-label*="search" i], [data-search-toggle], .search-toggle', 2],
    ['menu-toggle',   '.menu-toggle, [data-mobile-menu], [aria-label*="menu" i], .hamburger', 2]
  ];
  const out = [];
  const seen = new Set();
  for (const [kind, selector, cap] of groups) {
    let els;
    try { els = document.querySelectorAll(selector); } catch (e) { continue; }
    let n = 0;
    for (const el of els) {
      if (n >= cap || out.length >= limit) break;
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      const key = kind + '|' + Math.round(r.x) + ',' + Math.round(r.y);
      if (seen.has(key)) continue;
      seen.add(key);
      el.setAttribute('data-clonekit-probe', String(out.length));
      out.push({
        index: out.length,
        kind,
        selector: `[data-clonekit-probe="${out.length}"]`,
        tag: el.tagName.toLowerCase(),
        label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 60),
        box: { x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY), w: Math.round(r.width), h: Math.round(r.height) }
      });
      n++;
    }
  }
  return out;
}
"""

JS_SIGNATURE = r"""
() => {
  let visible = 0;
  const texts = [];
  document.querySelectorAll('body *').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    visible++;
    if (texts.length < 400) {
      const t = el.getAttribute('aria-expanded');
      if (t !== null) texts.push(el.tagName + ':expanded=' + t);
    }
  });
  return {
    visible,
    expanded: texts.join('|'),
    height: document.documentElement.scrollHeight,
    openDialogs: document.querySelectorAll('dialog[open], [aria-modal="true"], .modal.is-open, .drawer.is-open').length,
    bodyClass: document.body.className.slice(0, 200)
  };
}
"""

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def slugify(text: str, fallback: str = "item") -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s or fallback)[:40]


def px(value: str) -> float | None:
    m = re.match(r"^(-?\d+(?:\.\d+)?)px$", value or "")
    return float(m.group(1)) if m else None


def build_tokens(dom: dict) -> dict:
    """Frequency-rank the design decisions so generated CSS looks intentional."""
    colors, bgs, families, sizes, weights, spacing = (Counter() for _ in range(6))
    radii, shadows, widths, line_heights, letter_spacings = (Counter() for _ in range(5))

    for el in dom["elements"]:
        st = el["style"]
        area = el["box"]["w"] * el["box"]["h"]
        if st.get("color"):
            colors[st["color"]] += 1
        if st.get("backgroundColor"):
            bgs[st["backgroundColor"]] += max(1, area // 10000)
        if st.get("fontFamily"):
            families[st["fontFamily"].split(",")[0].strip("\"' ")] += 1
        for key, counter in (
            ("fontSize", sizes),
            ("lineHeight", line_heights),
            ("letterSpacing", letter_spacings),
        ):
            v = px(st.get(key, ""))
            if v:
                counter[v] += 1
        if st.get("fontWeight"):
            weights[st["fontWeight"]] += 1
        for key in ("gap", "rowGap", "columnGap", "paddingTop", "paddingBottom", "marginBottom"):
            v = px(st.get(key, ""))
            if v and v > 0:
                spacing[v] += 1
        for key in ("borderTopLeftRadius", "borderTopRightRadius"):
            v = px(st.get(key, ""))
            if v and v > 0:
                radii[v] += 1
        if st.get("boxShadow"):
            shadows[st["boxShadow"]] += 1
        v = px(st.get("maxWidth", ""))
        if v and 600 <= v <= 1920:
            widths[v] += 1

    def top(counter: Counter, n: int = 12):
        return [{"value": v, "count": c} for v, c in counter.most_common(n)]

    return {
        "colors": {"text": top(colors), "background": top(bgs)},
        "typography": {
            "families": top(families, 6),
            "sizes": top(sizes, 14),
            "weights": top(weights, 8),
            "lineHeights": top(line_heights, 8),
            "letterSpacings": top(letter_spacings, 6),
        },
        "spacing": top(spacing, 16),
        "radii": top(radii, 8),
        "shadows": top(shadows, 6),
        "containerWidths": top(widths, 6),
    }


def download_assets(assets: list[dict], out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for asset in assets:
        url = asset["url"]
        try:
            name = os.path.basename(urllib.parse.urlparse(url).path) or "asset"
            name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:60]
            digest = hashlib.sha1(url.encode()).hexdigest()[:8]
            root, ext = os.path.splitext(name)
            if not ext:
                ext = {"font": ".woff2", "svg": ".svg"}.get(asset.get("kind"), ".jpg")
            filename = f"{slugify(root, asset.get('role', 'asset'))}-{digest}{ext}"
            path = os.path.join(out_dir, filename)
            if not os.path.exists(path):
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as resp, open(path, "wb") as fh:
                    fh.write(resp.read())
            asset["local"] = filename
            asset["bytes"] = os.path.getsize(path)
        except Exception as exc:  # noqa: BLE001 - a dead asset must not kill the run
            asset["error"] = str(exc)[:120]


def largest_from_srcset(srcset: str | None, current: str) -> str:
    if not srcset:
        return current
    best, best_w = current, 0
    for part in srcset.split(","):
        bits = part.strip().split()
        if len(bits) == 2 and bits[1].endswith("w"):
            try:
                w = int(bits[1][:-1])
            except ValueError:
                continue
            if w > best_w:
                best, best_w = bits[0], w
    return best


# --------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------


def prepare(page, freeze: bool = True) -> None:
    """Settle the page: lazy content loaded, animations frozen, scrolled home."""
    page.wait_for_load_state("domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    # Scroll whatever actually scrolls - the document on most sites, an inner
    # wrapper on Horizon-style themes - so lazy content loads either way.
    page.evaluate(
        """async () => {
            const candidates = [document.scrollingElement, document.documentElement, document.body]
              .concat(Array.from(document.querySelectorAll('body > *, body > * > *')));
            let scroller = document.scrollingElement;
            let best = scroller ? scroller.scrollHeight : 0;
            for (const el of candidates) {
                if (el && el.scrollHeight > best + 8 && el.clientHeight > 0) {
                    scroller = el;
                    best = el.scrollHeight;
                }
            }
            const step = Math.round(window.innerHeight * 0.8);
            for (let y = 0; y < best; y += step) {
                scroller.scrollTop = y;
                window.scrollTo(0, y);
                await new Promise(r => setTimeout(r, 120));
            }
            scroller.scrollTop = 0;
            window.scrollTo(0, 0);
            await new Promise(r => setTimeout(r, 400));
        }"""
    )
    if freeze:
        page.add_style_tag(content=FREEZE_CSS)
    page.wait_for_timeout(400)


def dismiss_overlays(page) -> list[str]:
    """Close consent walls and marketing popups so they do not sit on top of
    every screenshot. Klaviyo/Privy-style email captures are as common as cookie
    banners on Shopify and hide exactly the content worth cloning: the hero."""
    dismissed = []
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception:
        pass

    patterns = [
        # cookie / consent
        "#onetrust-accept-btn-handler",
        "button:has-text('Accept')", "button:has-text('Agree')",
        "button:has-text('Got it')", "button:has-text('Allow all')",
        ".cookie-banner button",
        # email capture popups - decline, never subscribe
        "button:has-text('No, thanks')", "button:has-text('No thanks')",
        "button:has-text('Maybe later')", "button:has-text('Not now')",
        "button:has-text('Dismiss')",
        ".klaviyo-close-form", "[class*='klaviyo'] [aria-label='Close']",
        # generic close controls
        "[aria-label='Close dialog']", "[aria-label='Close form']",
        "[aria-label='Close']", "dialog[open] button[class*='close' i]",
    ]
    for selector in patterns:
        try:
            el = page.locator(selector).first
            if el.count() and el.is_visible():
                el.click(timeout=1500)
                page.wait_for_timeout(400)
                dismissed.append(selector)
        except Exception:
            continue

    # Popups often mount late, on a timer. One more Escape after settling.
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception:
        pass
    return dismissed


def probe_behaviors(page, out_dir: str, limit: int = 24) -> list[dict]:
    """Drive every interactive control and record what changed.

    A control that navigates instead of mutating the page is not a behavior to
    recreate - it is a link. Those are recorded as such, and the probe restores
    the original page (which re-tags the triggers) before continuing.
    """
    states_dir = os.path.join(out_dir, "states")
    os.makedirs(states_dir, exist_ok=True)
    start_url = page.url
    triggers = page.evaluate(JS_TRIGGERS, limit)
    behaviors = []

    def restore() -> None:
        page.goto(start_url, wait_until="commit", timeout=60000)
        prepare(page)
        dismiss_overlays(page)
        page.evaluate(JS_TRIGGERS, limit)  # re-applies the data-clonekit-probe tags

    for trig in triggers:
        try:
            before = page.evaluate(JS_SIGNATURE)
            el = page.locator(trig["selector"]).first
            if not el.count():
                continue
            el.scroll_into_view_if_needed(timeout=3000)
            page.wait_for_timeout(150)
            if trig["kind"] == "nav-item":
                el.hover(timeout=3000)
            else:
                el.click(timeout=3000, force=True)
            page.wait_for_timeout(650)

            if page.url != start_url:
                behaviors.append({
                    "name": f"{trig['kind']}-{trig['index']}-{slugify(trig['label'], 'link')}",
                    "kind": "navigation",
                    "label": trig["label"],
                    "navigated_to": page.url,
                    "note": "plain link - no client-side mechanic to recreate",
                })
                restore()
                continue

            after = page.evaluate(JS_SIGNATURE)

            changed = (
                after["visible"] != before["visible"]
                or after["expanded"] != before["expanded"]
                or after["openDialogs"] != before["openDialogs"]
                or abs(after["height"] - before["height"]) > 4
                or after["bodyClass"] != before["bodyClass"]
            )
            if not changed:
                continue

            name = f"{trig['kind']}-{trig['index']}-{slugify(trig['label'], 'state')}"
            shot = os.path.join(states_dir, f"{name}.png")
            page.screenshot(path=shot)
            behaviors.append({
                "name": name,
                "kind": trig["kind"],
                "label": trig["label"],
                "trigger": {"action": "hover" if trig["kind"] == "nav-item" else "click", "box": trig["box"]},
                "effect": {
                    "visibleDelta": after["visible"] - before["visible"],
                    "heightDelta": after["height"] - before["height"],
                    "dialogsDelta": after["openDialogs"] - before["openDialogs"],
                    "bodyClassChanged": after["bodyClass"] != before["bodyClass"],
                    "ariaExpandedChanged": after["expanded"] != before["expanded"],
                },
                "state_screenshot": os.path.relpath(shot, out_dir).replace("\\", "/"),
            })
            # Reset: Escape, move the mouse away, and confirm we actually got
            # back to the resting state - otherwise reload so the next probe
            # measures against a clean baseline.
            page.keyboard.press("Escape")
            page.mouse.move(2, 2)
            page.wait_for_timeout(350)
            settled = page.evaluate(JS_SIGNATURE)
            if settled["visible"] != before["visible"] or settled["openDialogs"] != before["openDialogs"]:
                restore()
        except Exception as exc:  # noqa: BLE001 - one dead control must not end the probe
            behaviors.append({
                "name": f"{trig['kind']}-{trig['index']}",
                "kind": trig["kind"],
                "label": trig["label"],
                "error": str(exc)[:120],
            })
            try:
                restore()
            except Exception:
                break
    return behaviors


def detect_apps(hosts: list[str]) -> list[dict]:
    found = []
    for host in sorted(set(hosts)):
        for needle, mechanic in APP_SIGNATURES.items():
            if needle in host:
                found.append({"host": host, "app": needle, "mechanic": mechanic})
                break
    return found


def capture(url: str, out_dir: str, mode: str, do_assets: bool, do_behaviors: bool) -> dict:
    from playwright.sync_api import sync_playwright

    os.makedirs(out_dir, exist_ok=True)
    report: dict = {"url": url, "mode": mode, "viewports": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # --- one context per viewport, at-rest screenshots -------------
            for name, (w, h) in VIEWPORTS.items():
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
                page = ctx.new_page()
                page.goto(url, wait_until="commit", timeout=60000)
                prepare(page)
                if name == "desktop":
                    report["dismissed_overlays"] = dismiss_overlays(page)
                else:
                    dismiss_overlays(page)
                released = page.evaluate(RELEASE_SCROLL_JS)
                page.wait_for_timeout(250)
                shot = os.path.join(out_dir, f"{name}.png")
                page.screenshot(path=shot, full_page=True)
                report["viewports"][name] = {
                    "size": [w, h],
                    "screenshot": f"{name}.png",
                    "released_scroll_containers": released[2:],
                }

                if name == "desktop":
                    dom = page.evaluate(JS_DOM, {"minBox": MIN_BOX, "maxElements": MAX_ELEMENTS})
                    with open(os.path.join(out_dir, "dom.json"), "w", encoding="utf-8") as fh:
                        json.dump(dom, fh, indent=1)
                    with open(os.path.join(out_dir, "tokens.json"), "w", encoding="utf-8") as fh:
                        json.dump(build_tokens(dom), fh, indent=2)
                    report["element_count"] = len(dom["elements"])

                    found = page.evaluate(JS_ASSETS)
                    for a in found["assets"]:
                        if a.get("kind") == "image" and a.get("srcset"):
                            a["url"] = urllib.parse.urljoin(url, largest_from_srcset(a["srcset"], a["url"]))
                    if do_assets:
                        download_assets(found["assets"], os.path.join(out_dir, "assets"))
                    with open(os.path.join(out_dir, "assets.json"), "w", encoding="utf-8") as fh:
                        json.dump(found, fh, indent=2)
                    report["asset_count"] = len(found["assets"])
                    report["font_count"] = len(found["fonts"])
                    report["script_hosts"] = page.evaluate(JS_SCRIPT_HOSTS)

                ctx.close()

            # --- behavior probe, desktop viewport --------------------------
            if do_behaviors:
                ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
                page = ctx.new_page()
                page.goto(url, wait_until="commit", timeout=60000)
                prepare(page)
                dismiss_overlays(page)
                behaviors = probe_behaviors(page, out_dir)
                apps = detect_apps(report.get("script_hosts", []))
                with open(os.path.join(out_dir, "behaviors.json"), "w", encoding="utf-8") as fh:
                    json.dump({"url": url, "interactions": behaviors, "third_party_apps": apps}, fh, indent=2)
                report["behavior_count"] = len([b for b in behaviors if "error" not in b])
                report["app_count"] = len(apps)
                ctx.close()
        finally:
            browser.close()

    with open(os.path.join(out_dir, "capture-report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture a page for Shopify cloning.")
    ap.add_argument("url")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--mode", choices=["remote", "local"], default="remote")
    ap.add_argument("--no-assets", action="store_true", help="skip downloading images/fonts")
    ap.add_argument("--no-behaviors", action="store_true", help="skip the interaction probe")
    ap.add_argument("--replay", help="behaviors.json from a remote run (local mode: re-shoot the same states)")
    args = ap.parse_args()

    do_behaviors = not args.no_behaviors
    if args.mode == "local" and args.replay:
        do_behaviors = True

    report = capture(args.url, args.out, args.mode, not args.no_assets, do_behaviors)

    print(f"captured {args.url} -> {args.out}")
    print(f"  viewports     {', '.join(report['viewports'])}")
    print(f"  elements      {report.get('element_count', 0)}")
    print(f"  assets        {report.get('asset_count', 0)} ({report.get('font_count', 0)} fonts)")
    print(f"  behaviors     {report.get('behavior_count', 0)}")
    print(f"  third-party   {report.get('app_count', 0)} app(s) detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
