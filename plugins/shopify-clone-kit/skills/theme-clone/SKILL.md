---
name: theme-clone
description: Clone any website into a Shopify theme as pixel-perfect, fully editable Liquid. Use whenever the user wants to rebuild a site, page, or single section in Shopify — triggers include "clone this site", "copy this page into my theme", "rebuild this section in Shopify", "make my store look like this URL", "recreate this landing page", "turn this into a Shopify section", or pasting a URL alongside a Shopify theme repo. Captures the source at three viewports plus its interactive states, recreates app-driven mechanics natively, generates dynamic sections with full theme-editor settings, and verifies with a screenshot diff loop. Every finished clone is also saved to the user's template library (قوالب) with a standalone HTML copy. Also use when the user says "شو عندنا قوالب", "show my templates", "حطها بالقوالب", "save this as a template", or picks a saved template to install.
---

# theme-clone

Point this at a URL and it rebuilds that design as Shopify Liquid inside the current theme: pixel-perfect, every parameter editable in the theme editor, app mechanics recreated natively, verified by screenshot diff rather than assertion.

Scope is whatever the user asks for — a full site, one page, or a single section.

## Read on demand

| File | Read it when |
|---|---|
| `references/capture-checklist.md` | Before decomposing — what a good capture contains and what silently ruins one |
| `references/app-behavior-recreations.md` | Phase 2.5, always. One native recipe per app-driven mechanic |
| `references/shopify-object-map.md` | Phase 3, whenever the source shows store data — product, collection, cart, nav |
| `references/editability-contract.md` | Phases 3–5, always. The mandatory settings surface |
| `references/schema-cookbook.md` | Phase 4, while writing any `{% schema %}` |
| `references/liquid-section-patterns.md` | Phase 4, before the first section. The settings→CSS-variable pattern |
| `references/section-skeleton.liquid` | Phase 4. Canonical section that passes the audit at 100% — copy its shape |
| `references/section-antipattern.liquid` | When the audit fails and the error is unclear — every failure mode in one file |
| `references/clone-quality-rules.md` | Phase 5, and before claiming anything is done |

Legal compliance for a given source is the user's responsibility and sits outside this skill. Do not run rights checks, license prompts, or copyright commentary. Spend the effort on replication.

## Work directory

Everything for a run lives in `<theme-repo>/.clone/<slug>-<timestamp>/`. Add `.clone/` to `.gitignore` on first use. Each phase writes a file, so a run can be resumed or re-entered mid-way.

`SCRIPTS` below means this skill's `scripts/` directory. On Windows use `python`, not `python3`.

---

## Phase 0 — Preflight

1. Confirm the working directory is a Shopify theme: `layout/theme.liquid`, `sections/`, and `config/settings_schema.json` all present. If not, say so and stop — this skill writes into a theme, it does not create one.
2. `python SCRIPTS/setup.py` — Playwright, Pillow, a Chromium that actually launches, git, and the Shopify CLI. If anything is missing, `python SCRIPTS/setup.py --install`.
3. Ask the user for the scope if it is not already obvious: **full site**, **page**, or **section** (and which section).
4. Note the store's dev URL for Phase 5 (`admin.shopify.com/store/<slug>` → `<slug>.myshopify.com`).

## Phase 1 — Capture

```bash
python SCRIPTS/capture.py "<url>" --out .clone/<run>
```

Produces full-page screenshots at 1440/768/390, `dom.json`, `tokens.json`, `assets.json` plus the downloaded files, `behaviors.json`, and `states/*.png`. Add `--no-assets` to skip downloads, `--no-behaviors` to skip the interaction probe.

**Screenshot-only path:** if the user supplies images instead of a URL, put them in `.clone/<run>/` and skip to Phase 2. Say plainly that spacing is estimated rather than measured, so the diff loop will need more iterations.

Then work `references/capture-checklist.md` before going further. A capture of a cookie wall or a bot-protection page looks perfectly valid in the report — look at `desktop.png` yourself.

## Phase 2 — Decompose

Read `desktop.png`, `mobile.png`, and `dom.json`, and cut the page into section boundaries the way a Shopify developer would: announcement bar, header, hero, logo strip, feature grid, product block, testimonials, FAQ, newsletter, footer.

Write `.clone/<run>/clone-manifest.json` — one entry per section:

```json
{ "name": "Hero", "file": "ck-hero", "y": { "desktop": [0, 720], "mobile": [0, 540] },
  "dom_path": "0/1/0", "purpose": "…", "behaviors": ["carousel-3-next"],
  "blocks": "3 feature cards", "dynamic": ["featured product price"] }
```

**Show the manifest to the user and get agreement before writing any code.** This is the cheapest place to catch "skip the header" or "split that hero in two".

## Phase 2.5 — Recreate app behaviors

Read `references/app-behavior-recreations.md`. For every entry in `behaviors.json` — both `interactions` and `third_party_apps` — decide the native recreation and record it in the manifest.

Entries classified `navigation` are plain links; ignore them. Anything genuinely not front-end (payments, fulfillment, subscription billing) is recorded as `external` with a one-line note and its visual shell is still built. The generated theme contains no third-party scripts.

If the probe found a mechanic with no recipe in the reference, write one and append it to that file during the run.

## Phase 3 — Map to Shopify

For each manifest entry decide section vs snippet vs template, then bind everything the source shows to real store objects using `references/shopify-object-map.md`. Product and collection sources are always pickers, never hardcoded handles.

Apply `references/editability-contract.md` in full and write `.clone/<run>/settings-plan.json`:

```json
{ "ck-hero.liquid": { "settings": ["padding_top", "columns_desktop", "…"], "blocks": ["item"] } }
```

Phase 4 implements this exactly; Phase 5 audits against it.

## Phase 4 — Generate

**One section at a time, in manifest order.** For each:

1. Write `sections/ck-<name>.liquid` following `references/section-skeleton.liquid` — markup, `{% stylesheet %}`, `{% javascript %}`, and a `{% schema %}` implementing every setting in the plan, with blocks and presets.
2. Emit settings as CSS custom properties on the section wrapper; the stylesheet reads only variables. Per-breakpoint values go inside their media query.
3. Recreate the section's behaviors as a custom element, parameters arriving via `data-*` from settings.
4. Register global tokens in `config/settings_schema.json`; section settings default to them.
5. Copy the section's assets from `.clone/<run>/assets/` into `assets/` and reference them with `asset_url`.
6. Run the audit and fix everything before moving on:

```bash
python SCRIPTS/schema_audit.py sections/ck-<name>.liquid --plan .clone/<run>/settings-plan.json
```

7. Commit: `feat(theme): clone <section> from <source>`.

Hard rules are in `references/clone-quality-rules.md`. They are not style preferences — the audit enforces most of them.

## Phase 5 — Verify

1. Add the section to a scratch template, then start the dev server:

```bash
shopify theme dev --store <slug>.myshopify.com
```

2. Capture your own render with the same script, so the comparison is apples to apples:

```bash
python SCRIPTS/capture.py http://127.0.0.1:9292 --mode local --no-assets --out .clone/<run>/local
```

3. Diff the page, then the states:

```bash
python SCRIPTS/diff.py --source .clone/<run>/desktop.png --candidate .clone/<run>/local/desktop.png --out .clone/<run>/diff --label desktop
python SCRIPTS/diff.py --states .clone/<run>/states --candidate-states .clone/<run>/local/states --out .clone/<run>/diff/states --threshold 0.9
```

4. Read the worst bands, fix the **topmost** failing band first — vertical errors cascade downward — re-render, re-diff. Max 4 iterations per section.

5. **Editor round-trip.** For each section change one setting from every category (a color, a font, a column count, a padding, a block add/remove, a behavior parameter), re-render, and confirm the output actually changed. A setting that does not move the render is a defect, not a nitpick.

6. Acceptance: ≥95% desktop, ≥90% mobile, states within the same thresholds, 100% schema audit, clean round-trip. Report the real numbers — never round a 91% up to "matches".

## Phase 6 — Ship

Push the branch. A GitHub-connected theme updates its draft automatically. Print the preview URL, the sections created and how to add them in the customizer, the mechanics recreated, anything deliberately left external, and the final diff scores.

## Phase 7 — Save to the template library (قوالب)

Always, after Phase 6 (and whenever the user says "حطها بالقوالب" / "save this as a template"). The library is the folder in
`CK_TEMPLATES_DIR`, else `قوالب/` in the project folder (`--library` overrides): one folder per template plus `index.html` (gallery), `README.md`, `install.py`.

1. Images: when the page uses photos the user approved (stock via `broll-hunter`, their own uploads), keep the files
   with the exact names used in `shopify://shop_images/<name>` in one folder; keep the photo credits file if there is one.
2. Save (copies sections, homepage, footer, images, previews, source; writes `template.json`; renders the HTML copy;
   screenshots it to `preview-0-html.jpg`; rebuilds the gallery and README table):

```bash
python SCRIPTS/save_template.py <theme_dir> <name> --title "<one line>" --images <img_dir> \
  --credits <photo-credits.json> --previews <editor screenshots...> --source-url <url> \
  --store <slug>.myshopify.com --theme-id <id>
```

   Copy the run's generator (if sections were generated by a script) into `<template>/source/`, and write
   `<template>/README.md` in the user's language: what it is, section list, install command, file list.
3. Open `<library>/<name>/html/index.html` over a local server (`python -m http.server 8780 --directory <library>`,
   or a launch.json entry that runs it) and check every image loads and sliders work. The HTML copy is the same template: the same section
   CSS/JS, settings and copy, rendered by `SCRIPTS/export_html.py` (python-liquid) without Shopify.
4. If the library sits in a git repo, commit the template folder (on a branch when on `main`).

### Showing and reusing templates

- "شو عندنا قوالب" / "show templates": run `python SCRIPTS/save_template.py --gallery` (refreshes previews and the
  gallery), open `<library>/index.html` through that local server, and list each template (name, title,
  section count) in chat.
- User picks one: do NOT rebuild. `python <library>/install.py <name> <theme_dir> --store <slug>.myshopify.com
  --theme-id <id>` copies the sections, backs up and replaces `templates/index.json`, swaps in the footer (old one
  hidden, not deleted) and pushes. Then remind the user to upload `<template>/images/` to Admin > Content > Files with
  the same names (or upload them in Chrome via Content > Files) and check the theme editor.
- JSON written for Shopify must have no BOM (PowerShell `Set-Content -Encoding utf8` adds one and the upload fails).

---

## Failure modes

| Symptom | Do this |
|---|---|
| Capture shows a challenge or consent page | Retry through a browser-automation server with a logged-in profile, or fall back to the screenshot path |
| `behaviors.json` empty on an obviously interactive page | The probe's selectors missed. Add a selector to `JS_TRIGGERS` in `scripts/capture.py` and re-run rather than cloning a dead page |
| Diff stuck below threshold across two iterations | Usually a substituted font or a dynamically loaded image. Report the residual with the contact sheet instead of burning passes |
| Audit fails on "hardcoded length" for a real structural value | Confirm it is genuinely structural (border, 0, 100%), then express it through a variable anyway — the merchant may still want it |
| Section breaks while editing in the customizer | JS is not bound to `shopify:section:load` / `:unload` |
| Section keeps theme's fonts/sizes but your colors work | A `{{ font.family }}` inside `style="…"` truncated the attribute. Move font vars into the scoped `<style>` block (`references/liquid-section-patterns.md`) |
| `@font-face { … }` visible as text on the page | `font_face` output is not wrapped in `<style>` |
| Theme file rejected on upload over a range setting | Run `schema_audit.py` - it checks all four of Shopify's range rules, including template values |
| Full-page screenshot returns only the viewport | The theme scrolls an inner wrapper; `capture.py` releases it and lists what it released in `capture-report.json` |
| "Translation missing:" in rendered output | Use a setting for the visible string rather than a `| t` key the theme may not define |
| Chromium will not launch | `python SCRIPTS/setup.py --install`; never invoke a pip-installed `.exe` shim on this machine — Application Control blocks them |
