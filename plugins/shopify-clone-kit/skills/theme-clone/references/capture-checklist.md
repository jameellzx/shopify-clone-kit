# Capture checklist

What a good capture contains, and what quietly ruins one.

## Outputs

| File | Contains |
|---|---|
| `desktop.png` / `tablet.png` / `mobile.png` | Full-page, animations frozen, overlays dismissed |
| `dom.json` | Visible elements with box geometry + the computed styles that matter |
| `tokens.json` | Frequency-ranked colors, fonts, sizes, spacing, radii, shadows, container widths |
| `assets.json` + `assets/` | Every image/SVG/font with role, natural and rendered size, plus the downloaded file |
| `behaviors.json` | Interactions that changed the page, and third-party app hosts |
| `states/*.png` | One screenshot per interaction state |
| `capture-report.json` | Counts and viewport metadata for the run |

## Things that break a capture

**Cookie / consent walls.** The script clicks common accept and close controls first. If a wall survives, it sits on every screenshot and the diff loop chases a ghost. Check `dismissed_overlays` in the report; if empty and the screenshot has a banner, pass a custom selector or capture manually.

**Lazy loading.** Handled by scrolling the full height before shooting. Sites using scroll-linked reveal animations still need the freeze CSS — otherwise elements screenshot mid-fade at opacity 0.4 and the clone gets built to a half-faded design.

**Sticky headers.** They repeat down a full-page screenshot on some engines. Check the desktop shot; if the header appears more than once, capture the header separately at viewport height.

**Carousels that auto-advance.** The freeze CSS stops CSS animation but not `setInterval`. If the tablet and desktop shots show different slides, that is why — treat the first slide as canonical and get the rest from the state screenshots.

**Fonts that load late.** `networkidle` usually covers it. A screenshot in a fallback face produces wrong measurements for every text block — verify `tokens.json` families against what the design obviously uses.

**Bot protection.** Cloudflare interstitials and rate limits produce a valid screenshot of a challenge page. Always eyeball `desktop.png` before decomposing anything. Fall back to a browser-automation server with a logged-in profile (PinchTab or similar), or a stealth-fetch tool.

**Login-gated pages.** Not capturable headlessly. Use the screenshot-only path.

**Viewport-dependent markup.** Some themes render a different DOM per breakpoint. `dom.json` is desktop-only, so mobile-specific components must be read from `mobile.png` visually.

## Before moving to decompose

1. Open `desktop.png` and confirm it is the actual page, fully rendered, no overlay.
2. Check `tokens.json` families and colors match what the page obviously uses.
3. Check `assets.json` has no `error` entries for anything visually important.
4. Check `behaviors.json` found the mechanics you can see — a page with a visible mega-menu and an empty `interactions` list means the probe's selectors missed; add a selector and re-run rather than cloning a dead page.
5. Note anything the probe classified as `navigation` — those are links, not mechanics.

## Screenshot-only path

Drop images into the capture directory and skip straight to decompose. State it plainly in the summary: spacing is estimated from pixels rather than measured from computed styles, so the diff loop carries the burden of accuracy and typically needs more iterations.

## Local mode

The same script, pointed at `shopify theme dev`, produces the candidate screenshots for diffing. Same browser, same waits, same freeze CSS, so the comparison is apples to apples:

```bash
python scripts/capture.py http://127.0.0.1:9292 --mode local --no-assets --out .clone/<run>/local
```
