# Section patterns

How a generated section is put together. The canonical file is `references/section-skeleton.liquid` — it passes `schema_audit.py` at 100% coverage. `references/section-antipattern.liquid` is the same section written badly; read it once to see every failure mode in one place.

## The settings → CSS variable pattern

This is the load-bearing idea. Settings are emitted as custom properties on the section wrapper; the stylesheet only ever reads variables. A customizer change then repaints without touching CSS, and the audit's "no hardcoded length/color" rule becomes easy to satisfy.

```liquid
<div class="ck-hero"
  style="
    --ck-pad-top: {{ section.settings.padding_top }}px;
    --ck-cols: {{ section.settings.columns_desktop }};
    --ck-cols-mobile: {{ section.settings.columns_mobile }};
    --ck-bg: {{ section.settings.background_color }};
  ">
```

```css
.ck-hero { background: var(--ck-bg); padding-top: var(--ck-pad-top); }
.ck-hero__grid { grid-template-columns: repeat(var(--ck-cols-mobile), minmax(0, 1fr)); }
@media screen and (min-width: 990px) {
  .ck-hero__grid { grid-template-columns: repeat(var(--ck-cols), minmax(0, 1fr)); }
}
```

Mobile-first: the base rule uses the mobile variable, media queries swap in tablet then desktop.

## Scoping

Prefix every class with a section-specific namespace (`ck-<section>__<element>`), and where a cloned style could collide with the base theme, wrap the block in `#shopify-section-{{ section.id }}`. Cloned sections must never restyle the rest of the theme.

## Breakpoints

Take them from the capture, not from habit. Dawn's are 750px and 990px; if the source breaks at 1024px, use 1024px. Record the chosen breakpoints in the section's opening comment so later sections stay consistent.

## JavaScript

Vanilla only, no libraries, no third-party scripts. Prefer a custom element so lifecycle is automatic:

```liquid
{% javascript %}
class CkCarousel extends HTMLElement {
  connectedCallback() {
    this.interval = Number(this.dataset.interval || 0) * 1000;
    if (this.dataset.autoplay === 'true') this.start();
  }
  disconnectedCallback() { this.stop(); }
}
customElements.define('ck-carousel', CkCarousel);
{% endjavascript %}
```

Parameters reach JS through `data-*` attributes populated by settings — never hardcoded in the script. If a plain script is used instead of a custom element, it must bind `shopify:section:load` and `shopify:section:unload`, or the section dies the moment the merchant edits it.

## Accessibility, carried over from the source

Keyboard operability for anything clickable, `aria-expanded` on disclosures, `aria-current` on active nav, focus trapping in dialogs, visible focus rings, and `prefers-reduced-motion` honored for every animation:

```css
@media (prefers-reduced-motion: reduce) {
  .ck-hero * { animation: none !important; transition: none !important; }
}
```

## Performance

- Images through `image_url` + `image_tag` with `widths` and `sizes`, `loading="lazy"` below the fold and `eager` for the LCP image.
- Fonts through `font_face` with `font_display: 'swap'`; self-hosted files preloaded only when they carry the LCP text.
- No layout shift: always emit `width` and `height` (or `aspect-ratio`) on media.
- CSS lives in `{% stylesheet %}`, JS in `{% javascript %}`, so Shopify bundles them per section.

## File placement

| Kind | Path |
|---|---|
| Section | `sections/ck-<name>.liquid` |
| Reused partial | `snippets/ck-<name>.liquid` |
| Shared JS | `assets/ck-<name>.js` |
| Downloaded media/fonts | `assets/` |
| Cloned page | `templates/page.<name>.json` |
| Cloned product page | `templates/product.<name>.json` |
| Global tokens | `config/settings_schema.json` |

## Platform traps that cost a rebuild

These are not style preferences. Each one silently breaks a section on a real store; all were hit while cloning a live site into Horizon.

### Never interpolate a font family into an HTML attribute

`{{ font.family }}` renders multi-word families **with double quotes** (`"Libre Baskerville"`). Inside `style="…"` that quote ends the attribute, and **every custom property after it is dropped** — the section keeps its colors but silently loses all sizes, weights, and fonts, with no error anywhere.

Put font variables in the scoped style block instead:

```liquid
<style>
  #shopify-section-{{ section.id }} {
    --ck-heading-font: {{ hf.family }}, {{ hf.fallback_families }};
    --ck-body-font: {{ bf.family }}, {{ bf.fallback_families }};
  }
  {{ hf | font_face: font_display: 'swap' }}
  {{ bf | font_face: font_display: 'swap' }}
</style>
```

Symptom to recognize: computed styles show every text element at the theme's base size/family while your color settings work fine.

### `font_face` must be wrapped in `<style>`

The filter returns a bare `@font-face { … }` rule, not a tag. Unwrapped, it prints the CSS as visible text at the top of every section. This is the one place a `<style>` tag is allowed outside `{% stylesheet %}`.

### Range settings have four rules, and breaking any one rejects the whole file

Shopify refuses to upload the file — not just the setting — when a `range` violates:

1. `step` has more than one decimal digit (`0.05` is invalid, `0.1` is fine)
2. `(max - min)` is not evenly divisible by `step`
3. the step count exceeds **101** or is fewer than **3**
4. `default` does not land exactly on a step boundary from `min`

`scripts/schema_audit.py` checks all four. Values written into a template JSON must satisfy the same schema — a `padding_top: 260` against a `max: 200` range fails the upload just as hard.

### Themes that scroll an inner wrapper

Horizon pins `html`/`body` to `100dvh` with `overflow: hidden` at ≥990px and scrolls `.page-wrapper`. Full-page screenshots return only the viewport until those containers are released — `capture.py` does this automatically and reports what it released. Any scroll listener in section JS must attach to that wrapper, not `window`.

### Translation keys

`{{ 'products.product.add_to_cart' | t }}` renders `Translation missing:` when the key does not exist in the theme's locale files. Cloned sections should expose visible strings as settings instead — which the editability contract requires anyway.
