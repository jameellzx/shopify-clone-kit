# Schema cookbook

Every setting type, with the form the generator should emit. Copy shapes from here rather than recalling them.

## Setting types

```json
{ "type": "text",            "id": "heading",       "label": "Heading", "default": "Heading" }
{ "type": "textarea",        "id": "body",          "label": "Body" }
{ "type": "richtext",        "id": "content",       "label": "Content", "default": "<p>Text</p>" }
{ "type": "inline_richtext", "id": "eyebrow",       "label": "Eyebrow" }
{ "type": "html",            "id": "embed",         "label": "Custom HTML" }
{ "type": "number",          "id": "count",         "label": "Count", "default": 4 }
{ "type": "range",           "id": "gap", "min": 0, "max": 80, "step": 2, "unit": "px", "label": "Gap", "default": 24 }
{ "type": "checkbox",        "id": "full_width",    "label": "Full width", "default": false }
{ "type": "select",          "id": "alignment",     "label": "Alignment", "default": "center",
  "options": [ { "value": "left", "label": "Left" }, { "value": "center", "label": "Center" } ] }
{ "type": "radio",           "id": "media_position","label": "Media position", "default": "left",
  "options": [ { "value": "left", "label": "Left" }, { "value": "right", "label": "Right" } ] }
{ "type": "color",           "id": "text_color",    "label": "Text", "default": "#121212" }
{ "type": "color_background","id": "gradient",      "label": "Gradient" }
{ "type": "color_scheme",    "id": "color_scheme",  "label": "Color scheme", "default": "scheme-1" }
{ "type": "font_picker",     "id": "heading_font",  "label": "Heading font", "default": "assistant_n4" }
{ "type": "image_picker",    "id": "image",         "label": "Image" }
{ "type": "video",           "id": "video",         "label": "Video" }
{ "type": "video_url",       "id": "video_url",     "label": "Video URL", "accept": ["youtube", "vimeo"] }
{ "type": "url",             "id": "button_link",   "label": "Button link" }
{ "type": "product",         "id": "featured",      "label": "Product" }
{ "type": "product_list",    "id": "products",      "label": "Products", "limit": 12 }
{ "type": "collection",      "id": "collection",    "label": "Collection" }
{ "type": "collection_list", "id": "collections",   "label": "Collections", "limit": 6 }
{ "type": "blog",            "id": "blog",          "label": "Blog" }
{ "type": "page",            "id": "page",          "label": "Page" }
{ "type": "link_list",       "id": "menu",          "label": "Menu", "default": "main-menu" }
{ "type": "metaobject",      "id": "spec",          "label": "Spec", "metaobject_type": "spec" }
{ "type": "liquid",          "id": "custom_liquid", "label": "Custom Liquid" }
{ "type": "header",          "content": "Layout" }
{ "type": "paragraph",       "content": "Shown above the grid." }
```

## Section shell

```liquid
{% schema %}
{
  "name": "Section name",
  "tag": "section",
  "class": "ck-section",
  "limit": 1,
  "enabled_on": { "templates": ["index", "product"] },
  "settings": [ ... ],
  "blocks": [ { "type": "item", "name": "Item", "limit": 6, "settings": [ ... ] } ],
  "max_blocks": 12,
  "presets": [ { "name": "Section name", "blocks": [ { "type": "item" }, { "type": "item" } ] } ]
}
{% endschema %}
```

- `presets` is mandatory — no presets, no way to add the section.
- `enabled_on` / `disabled_on` restrict where it can be placed. Use for header/footer-shaped sections.
- `limit` on a block type caps that type; `max_blocks` caps the total.

## Font picker → CSS

```liquid
{%- assign hf = section.settings.heading_font -%}
style="--ck-heading-font: {{ hf.family }}, {{ hf.fallback_families }}; --ck-heading-weight: {{ hf.weight }};"
{{ hf | font_face: font_display: 'swap' }}
{{ hf | font_modify: 'weight', 'bold' | font_face: font_display: 'swap' }}
```

## Color scheme

```liquid
<div class="color-{{ section.settings.color_scheme }} gradient">
```

Schemes come from `config/settings_schema.json`; the class gives the section the merchant's palette for free. Per-section color settings then override specific slots.

## Range gotcha

`(max - min) / step` must be a whole number ≤ 101, and `step` must divide the span evenly, or the theme fails to save. Check every generated range.

## Block boilerplate

```liquid
{%- for block in section.blocks -%}
  <div class="ck-item" {{ block.shopify_attributes }}
       style="--ck-item-bg: {{ block.settings.background }};">
    {{ block.settings.title }}
  </div>
{%- endfor -%}
```

`{{ block.shopify_attributes }}` is required — without it the editor cannot highlight or scroll to the block.

## Section-level JSON templates

A cloned page is a template that composes sections:

```json
{
  "sections": {
    "hero":     { "type": "ck-hero",     "settings": { "heading": "..." } },
    "features": { "type": "ck-features", "blocks": { "a": { "type": "item" } }, "block_order": ["a"] }
  },
  "order": ["hero", "features"]
}
```

Write it to `templates/page.<name>.json` or `templates/product.<name>.json`. Preset defaults should already match the source, so the template only carries what differs.

## Theme settings

Global tokens go in `config/settings_schema.json` under a dedicated group so the clone's tokens are obvious and reversible:

```json
{ "name": "Clone tokens", "settings": [
  { "type": "color", "id": "ck_brand", "label": "Brand color", "default": "#121212" },
  { "type": "range", "id": "ck_container", "min": 800, "max": 1600, "step": 20, "unit": "px", "label": "Container width", "default": 1200 }
] }
```

Reference as `{{ settings.ck_brand }}` and use as the default for section-level overrides.
