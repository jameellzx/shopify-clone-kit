# Visual element → Shopify object

What you see in the capture, and what it must be bound to in Liquid. Anything on this list rendered as static markup is a defect.

## Product

| On screen | Liquid |
|---|---|
| Product title | `{{ product.title }}` |
| Price | `{{ product.selected_or_first_available_variant.price \| money }}` |
| Compare-at / strikethrough | `{{ variant.compare_at_price \| money }}` (guard `> price`) |
| Unit price | `{{ variant.unit_price \| money }} / {{ variant.unit_price_measurement.reference_unit }}` |
| Sale badge | `{% if product.compare_at_price > product.price %}` |
| Sold out badge | `{% unless product.available %}` |
| Gallery | `{% for media in product.media %}` + `{{ media \| image_url: width: 1946 \| image_tag }}` |
| Variant swatches / dropdowns | `{% for option in product.options_with_values %}` |
| Add to cart | `{% form 'product', product %}` … `{{ form \| payment_button }}` |
| Quantity | `<input name="quantity">` inside the product form |
| Inventory line | `{{ variant.inventory_quantity }}`, `variant.inventory_policy` |
| Description / tabs | `{{ product.description }}`, `product.metafields.*` |
| Star rating | `product.metafields.reviews.rating`, `.rating_count` |
| SKU / vendor / type | `{{ variant.sku }}`, `{{ product.vendor }}`, `{{ product.type }}` |
| Related products | `recommendations.products` or a `product_list` setting |

## Collection

| On screen | Liquid |
|---|---|
| Product grid | `{% for product in collection.products %}` |
| Grid from a picker | `{% for product in collections[section.settings.collection].products %}` |
| Filters | `{% for filter in collection.filters %}` |
| Sort dropdown | `collection.sort_options`, `collection.sort_by` |
| Pagination | `{% paginate collection.products by n %}` + `{{ paginate \| default_pagination }}` |
| Result count | `{{ collection.products_count }}` |
| Collection banner | `{{ collection.image }}`, `{{ collection.description }}` |

## Cart

| On screen | Liquid |
|---|---|
| Line items | `{% for item in cart.items %}` |
| Line price | `{{ item.final_line_price \| money }}` |
| Subtotal | `{{ cart.total_price \| money }}` |
| Discounts | `{% for discount in cart.cart_level_discount_applications %}` |
| Item count badge | `{{ cart.item_count }}` |
| Free-shipping bar | `{{ cart.total_price }}` vs a threshold setting |

## Navigation, shop, customer

| On screen | Liquid |
|---|---|
| Header / footer menu | `{% for link in linklists[section.settings.menu].links %}` |
| Second level | `{% for child in link.links %}` |
| Active state | `link.active`, `link.child_active` |
| Logo | `{{ settings.logo \| image_url: width: 600 \| image_tag }}` |
| Shop name | `{{ shop.name }}` |
| Payment icons | `{% for type in shop.enabled_payment_types %}{{ type \| payment_type_svg_tag }}{% endfor %}` |
| Currency / locale picker | `{% form 'localization' %}` + `localization.available_countries` |
| Account links | `{% if shop.customer_accounts_enabled %}`, `customer.name` |
| Newsletter form | `{% form 'customer' %}` with `contact[email]` |
| Contact form | `{% form 'contact' %}` |
| Search | `{% form 'search' %}`, `/search/suggest.json` for predictive |
| Blog / article | `blog.articles`, `article.image`, `article.excerpt` |

## Images — always through the image filters

```liquid
{{ section.settings.image | image_url: width: 1600 | image_tag:
     loading: 'lazy', widths: '375, 550, 750, 1100, 1500, 1780, 2000',
     sizes: '(min-width: 990px) 50vw, 100vw', alt: section.settings.image.alt }}
```

Never a bare `<img src="//cdn.shopify.com/...">` — it loses responsive srcset and the merchant's ability to swap the image.

## Section Rendering API

For anything that used to be an app's AJAX: `/?sections=section-id` returns rendered section HTML. Used by cart drawer, load-more, filter updates, and variant-dependent blocks.

## Metafields

Structured content the theme editor should not own (spec tables, ingredient lists, care instructions) belongs in `product.metafields.<namespace>.<key>`, surfaced through a `metaobject` or `text` setting naming the key. Prefer a metaobject over inventing a block when the same data repeats across products.
