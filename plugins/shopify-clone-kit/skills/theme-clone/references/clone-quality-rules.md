# Quality rules and acceptance

## Hard rules — non-negotiable in generated code

1. No third-party scripts, app embeds, or external CDN dependencies. Mechanics are recreated natively (`references/app-behavior-recreations.md`).
2. No hardcoded color, length, font family, visible string, image path, or resource handle. Everything is a setting (`references/editability-contract.md`).
3. No inline `<style>` outside `{% stylesheet %}`; no `<script>` outside `{% javascript %}` or an `assets/` file.
4. No `!important` except to override a base-theme rule, and then with a comment saying which.
5. No jQuery, no bundlers, no build step. Vanilla JS only.
6. Every section has `presets`. Every block root emits `{{ block.shopify_attributes }}`.
7. JS re-initializes on `shopify:section:load` and cleans up on `shopify:section:unload`.
8. `prefers-reduced-motion` honored for every animation.
9. Mobile-first media queries, using breakpoints measured from the capture.
10. Images through `image_url` / `image_tag` with `widths` + `sizes`; explicit width/height or aspect-ratio to prevent layout shift.

## Acceptance gates — all four required per section

| Gate | Threshold |
|---|---|
| Desktop diff | ≥ 95% |
| Mobile diff | ≥ 90% |
| Every captured state diff | same thresholds as the page it belongs to |
| Schema audit + editor round-trip | 100% coverage, zero errors, every changed setting visibly moves the render |

A section that misses any gate is reported with its actual numbers and the contact sheet. Never round a 91% up to "matches the source".

## The iteration loop

Max **4** fix iterations per section. Each iteration: read the worst bands from `diff-report.json`, form one specific hypothesis per band (`hero heading 48px vs 44px`, `card grid gap 24px vs 32px`), fix, re-render, re-diff. If the score stops improving across two iterations, stop and report — the remaining delta is usually a font substitution or an image the source loads dynamically, and burning more passes will not fix it.

## Reading a diff band

| Symptom | Usual cause |
|---|---|
| Everything below y=N shifted | one element above is the wrong height — fix the topmost failing band first, never the biggest |
| Thin repeated failures | line-height or letter-spacing off |
| One band at ~0% | element missing entirely, or an image failed to load |
| Uniform low score across the page | wrong background, wrong container width, or a font that never loaded |
| Desktop passes, mobile fails | a breakpoint value copied from the wrong source, or missing per-breakpoint settings |

Fix the topmost failing band first. Vertical layout errors cascade downward, so one fix at the top routinely clears six bands below it.

## Definition of done for a run

- Every section passes all four gates, or its shortfall is stated with numbers.
- `schema_audit.py` exits 0 across the whole `sections/` directory.
- The local preview's console is clean and its network log has no 404s and no requests to the source domain.
- One commit per section, pushed to the GitHub-connected branch.
- The summary lists: sections created, settings per section, mechanics recreated, mechanics deliberately not recreated, and the final diff scores.
