# Recreating app-driven mechanics natively

Commercial Shopify sites lean on paid apps for behavior that is perfectly expressible in Liquid plus a little vanilla JS. A clone that drops those mechanics is not a replica.

**Rule: the generated theme contains zero third-party scripts and zero app embeds.** Every mechanic found by the capture probe gets rebuilt from Shopify primitives, with all its parameters exposed as settings per the editability contract.

`capture.py` writes `behaviors.json` with two lists: `interactions` (what actually changed when a control was driven) and `third_party_apps` (hosts matched against known app signatures). Work through both.

---

## Recipes

### Sticky / floating add-to-cart bar
`IntersectionObserver` on the real `product-form`. When it leaves the viewport, reveal a fixed bar containing a cloned variant selector and a submit button that targets the same form id. Settings: trigger offset, position (top/bottom), which fields to show, background/text colors, mobile-only toggle.

### Countdown / urgency timer
`<time datetime="{{ block.settings.end_at }}">` plus a small ticker. Never trust client time alone for anything transactional — this is display only. Settings: end date/time, expiry behavior (hide / show message / restart), labels for each unit, colors, size.

### Quantity breaks / volume discounts
Tiers as blocks (`min_quantity`, `discount_label`, `price_override`). Selecting a tier sets the quantity input and writes a `properties[_tier]` line-item property. Real discounting is a Shopify function or automatic discount — the section renders and communicates the tiers, it does not invent pricing.

### Product reviews & star ratings
`product.metafields.reviews.rating` and `.rating_count` are Shopify's native review metafields. Render stars from `rating.value` / `rating.scale_max`. Settings: star style, size, color, show count, position, hide when no reviews.

### Mega-menu / dropdown navigation
`{% for link in linklists[section.settings.menu].links %}` with `link.links` recursion for the second level. Featured images and promo columns are blocks. Open on hover at desktop via CSS `:hover`/`:focus-within`, on click at mobile with `aria-expanded`. Settings: menu picker, columns, image per column, open-on trigger, animation.

### Slider / carousel
CSS scroll-snap (`scroll-snap-type: x mandatory`) plus a controller that moves `scrollLeft`. No library. Settings: slides per view **per breakpoint**, gap, autoplay, interval, loop, arrows, dots, drag-to-scroll, transition speed.

### Cart drawer / slide-out cart
Post to `/cart/add.js`, then re-render with the Section Rendering API (`?sections=cart-drawer`). Settings: position, free-shipping threshold + bar colors, upsell block, note field, continue-shopping label.

### Upsell / cross-sell / frequently-bought
Source from a `product_list` setting, a `collection` setting, or `product.metafields.custom.related`. Fall back to `recommendations.products` via `/recommendations/products.json?product_id=&limit=`. Settings: source, count, layout, add-to-cart mode.

### Wishlist
`localStorage` for guests; a customer metafield when `customer` exists. Render the icon from the same product card partial. Settings: icon style, position, filled/outline colors, drawer vs page.

### Back-in-stock / notify me
Native `{% form 'contact' %}` with a hidden variant id and product title. Shows only when `variant.available == false`. Settings: heading, body, button label, success message, colors.

### Size guide / spec popup
`<dialog>` element, content from a `page` picker or `richtext`. Settings: trigger label, dialog width, content source, close-on-backdrop.

### Announcement bar rotator
Blocks, each with its own text, link, colors, and icon. Rotate with the same scroll-snap controller or a simple opacity cycle. Settings: interval, transition, pause on hover, dismissible, sticky.

### Cookie / consent bar
Shopify's `window.Shopify.customerPrivacy` API — never a third-party consent script. Settings: copy, button labels, position, colors, categories shown.

### Trust badges / payment icons / USP strip
Blocks with `image_picker` or a built-in icon `select`, plus `{{ shop.enabled_payment_types }}` rendered through `payment_type_svg_tag`. Settings: per-block icon, label, link, columns per breakpoint.

### Sticky / transparent-on-scroll header
Scroll listener toggling a class; CSS handles the rest. Settings: transparent-on-home toggle, scrolled background, scrolled height, logo swap image, blur amount.

### Infinite scroll / load more
`{% paginate collection.products by section.settings.page_size %}` plus an `IntersectionObserver` that fetches the next page and appends via the Section Rendering API. Settings: mode (paginate / button / auto), page size, button label.

### Predictive search
Shopify's native `/search/suggest.json`. Settings: resource types, result count, show images, show price.

### Email capture popup
`<dialog>` plus `{% form 'customer' %}`. Settings: trigger (delay / scroll depth / exit intent), frequency (localStorage key), heading, body, image, success message, colors.

---

## When a mechanic is not recreatable

Real integrations — payment gateways, fulfillment, subscription billing, loyalty ledgers — are not front-end behavior. Record them in the manifest as `external: <app>` with a one-line note, and leave the visual shell in place with settings for its copy. Say so in the summary rather than silently dropping it.

## Extending this file

When the probe finds a mechanic with no recipe here, write one during the run and append it to this file: what triggers it, what changes, which Shopify primitive replaces the app, and the settings it must expose. The table compounds with use.
