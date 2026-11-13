# Shopify Clone Kit

One skill — `theme-clone` — that rebuilds any website as pixel-perfect, fully editable Shopify Liquid inside your existing theme. Full site, single page, or one section.

**This folder is the source of truth.** Edit here, never in the installed plugin cache.

---

## What it does

```
capture → decompose → recreate-behaviors → map → generate → verify → ship
```

- **Captures** the source at 1440 / 768 / 390 with animations frozen, plus its computed styles, design tokens, assets, and every interactive state (open menus, drawers, tabs, carousels).
- **Recreates app mechanics natively.** Sticky add-to-cart, countdowns, reviews, mega-menus, cart drawers, quantity breaks — rebuilt from Shopify primitives. The output contains zero third-party scripts.
- **Generates dynamic sections.** Every color, size, font, column count, padding, image, product, and behavior parameter is a theme-editor setting. Enforced by an audit, not by good intentions.
- **Verifies by screenshot diff** against your own `shopify theme dev` render, at rest and in every captured state.

## Install (Claude Code)

```bash
/plugin marketplace add jameellzx/shopify-clone-kit
```

```bash
/plugin install shopify-clone-kit@shopify-clone-kit
```

Restart Claude Code, then ask: "set up the theme-clone tools" (runs `setup.py --install`).

Tools you need: Node.js, Git, Python 3, Shopify CLI (`npm install -g @shopify/cli@latest`), and Google Chrome with the Claude in Chrome extension for sites behind a bot check.

### After editing — always run sync (maintainers)

The plugin cache is **version-pinned**. Editing a skill file does nothing on its own; the version in `plugin.json` has to change and the plugin has to be reinstalled. One command does all of it:

```bash
powershell -ExecutionPolicy Bypass -File build\sync.ps1
```

That validates → bumps the patch version → refreshes the marketplace → reinstalls → verifies the cache moved. If validation fails, nothing gets installed. Restart Claude Code afterwards.

## Dependencies

```bash
python plugins\shopify-clone-kit\skills\theme-clone\scripts\setup.py --install
```

Installs Playwright + Pillow and downloads Chromium. The verify loop also needs the Shopify CLI (`npm install -g @shopify/cli@latest`) and git.

Windows note: this machine's Application Control policy blocks pip-installed `.exe` shims, so everything runs through `python -m`. Never invoke `playwright.exe` directly.

## Layout

```
plugins\shopify-clone-kit\skills\theme-clone\
  SKILL.md                          workflow: capture → … → ship → save to template library
  references\
    editability-contract.md         the mandatory settings surface
    app-behavior-recreations.md     native recipe per app mechanic
    shopify-object-map.md           visual element → Liquid object
    schema-cookbook.md              every setting type, worked
    liquid-section-patterns.md      settings → CSS variables
    section-skeleton.liquid         canonical section, audits at 100%
    section-antipattern.liquid      every failure mode in one file
    capture-checklist.md            what ruins a capture
    clone-quality-rules.md          hard rules + acceptance gates
  scripts\
    setup.py                        dependency preflight
    capture.py                      viewports, DOM, tokens, assets, behavior probe
    diff.py                         band scoring + contact sheets
    schema_audit.py                 editability-contract linter
    save_template.py                save a finished clone to the template library (قوالب) + gallery
    export_html.py                  render a saved template to one standalone HTML page
    install.py                      install a saved template into any theme (and push)
```

## Template library (قوالب)

Every finished clone can be saved as a reusable template: sections, homepage JSON, footer, images, previews and a
standalone HTML copy that opens without Shopify. A gallery page (`قوالب/index.html`) shows them all.

```bash
python scripts/save_template.py <theme> <name> --title "..." --images <dir>   # save
python scripts/save_template.py --gallery                                     # rebuild the gallery
python قوالب/install.py --list                                                # list
python قوالب/install.py <name> <theme> --store x.myshopify.com --theme-id N   # reuse, no rebuild
```

The library folder is `CK_TEMPLATES_DIR`, else `قوالب/` in the current folder. The HTML export needs
`python -m pip install python-liquid`.

## Using the scripts standalone

```bash
python scripts/capture.py "https://example.com" --out .clone/run
python scripts/diff.py --source .clone/run/desktop.png --candidate .clone/run/local/desktop.png --out .clone/run/diff
python scripts/schema_audit.py sections/
```
