# The editability contract

**Zero-hardcode rule: if a merchant could plausibly want it different, it is a setting.**

Every generated section and every block must satisfy this list. `scripts/schema_audit.py` enforces it mechanically — a section that fails the audit is not finished, regardless of how well it renders.

## Required setting categories

Every section carries settings from all six categories. A section with no plausible member of a category (a spacer with no text) still needs the layout, color, and behavior groups.

### 1. Layout
`padding_top`, `padding_bottom`, `gap`, `content_width`, `columns_desktop`, `columns_tablet`, `columns_mobile`, `text_alignment`, `full_width`, `corner_radius`, plus where the design implies it: `media_position`, `reverse_layout`, `sticky`, `min_height`, `vertical_alignment`, `section_height`.

Column counts are **per breakpoint, always three settings**. A single `columns` setting is a contract violation — the merchant cannot fix mobile without breaking desktop.

### 2. Color
`color_scheme` first, so the section inherits the theme's schemes. Then per-section overrides: `background_color`, `text_color`, `heading_color`, `accent_color`, `border_color`, `overlay_color` + `overlay_opacity`, and for every button state `button_background`, `button_text`, `button_hover_background`, `button_border`.

Never emit a raw hex into CSS. Colors reach the stylesheet only as custom properties fed by settings.

### 3. Typography
`font_picker` for heading and body. Then per text role: `*_size`, `*_size_mobile`, `*_weight`, `*_line_height`, `*_letter_spacing`, `*_text_transform`.

A separate mobile size is required wherever the captured source differs across breakpoints — which is nearly always for headings.

### 4. Content
The right picker for what the element actually shows:

| Element | Setting type |
|---|---|
| Plain string | `text` |
| Formatted paragraph | `richtext` |
| Single-line with bold/italic | `inline_richtext` |
| Image | `image_picker` (+ `image_loading`, focal/fit settings) |
| Video | `video` or `video_url` |
| Any link | `url` |
| One product | `product` |
| Many products | `product_list` |
| One / many collections | `collection` / `collection_list` |
| Menu | `link_list` |
| Structured repeatable content | `metaobject` / `metaobject_list` |
| Long-form page content | `page` |

Hardcoded handles (`all_products['blue-tee']`) are a contract violation — always a picker.

### 5. Behavior
Every parameter of any mechanic recreated from `app-behavior-recreations.md`: `autoplay`, `autoplay_interval`, `transition_speed`, `loop`, `show_arrows`, `show_dots`, `slides_per_view_*`, `trigger_offset`, `threshold`, `animation_style`, `animation_delay`, plus `show_on_mobile` / `show_on_desktop` visibility toggles.

### 6. Blocks
Anything appearing more than twice is a block type — feature cards, testimonials, FAQ rows, slides, nav columns, tiers, badges. Each block carries its **own full parameter set** (its own colors, sizes, image, link, alignment), not just a text field. Set `max_blocks`. Always emit `{{ block.shopify_attributes }}` on the block's root element so the theme editor can scroll to and highlight it.

## Structural requirements

- **`presets`** — without it the section cannot be added in the theme editor. Preset defaults must reproduce the captured source exactly, so a fresh insert looks like the original.
- **Settings drive CSS through custom properties.** Emit `--ck-*` variables on the section wrapper from settings; write the stylesheet against those variables only. A customizer change must never require touching CSS.
- **Per-breakpoint variables** are emitted inside their matching media query.
- **Every defined setting must be referenced.** A setting that renders nothing is worse than a missing one — it lies to the merchant. The audit fails on both directions (defined-unused and referenced-undefined).
- **JS re-initializes on `shopify:section:load`** and tears down on `shopify:section:unload`, or the section breaks the moment the merchant edits it.
- **Global tokens** (brand colors, fonts, radii, container width, base spacing) are registered in `config/settings_schema.json` and referenced as `settings.*`. Section defaults point at those globals so one Theme-settings change restyles the whole clone.

## Worked examples

- `references/section-skeleton.liquid` — a section that passes the audit at 100% coverage. Copy its shape.
- `references/section-antipattern.liquid` — the same section written badly. Every error the audit reports, in one file.

Run the audit before claiming a section is done:

```bash
python scripts/schema_audit.py sections/my-section.liquid
```
