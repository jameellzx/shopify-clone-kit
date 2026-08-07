#!/usr/bin/env python3
"""Audit a generated Shopify section against the editability contract.

The contract: if a merchant could plausibly want it different, it is a setting.
This script proves it mechanically instead of trusting the generator.

Fails a section on:
  - invalid or missing {% schema %}, missing presets, missing name
  - a literal color, font-family, size, or user-visible string in the markup
    or stylesheet with no backing setting
  - settings defined but never referenced (fake dynamism), or referenced but
    never defined (broken render)
  - a hardcoded product/collection handle
  - repeated markup that should be blocks
  - third-party <script src> - app mechanics must be recreated natively
  - missing contract categories (layout / color / typography / behavior)

Usage:
    python schema_audit.py sections/hero.liquid
    python schema_audit.py sections/ --json
    python schema_audit.py sections/hero.liquid --plan .clone/run/settings-plan.json

Exit: 0 = every audited file passes, 1 = at least one failure
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SCHEMA_RE = re.compile(r"\{%-?\s*schema\s*-?%\}(.*?)\{%-?\s*endschema\s*-?%\}", re.S)
STYLESHEET_RE = re.compile(r"\{%-?\s*stylesheet\s*-?%\}(.*?)\{%-?\s*endstylesheet\s*-?%\}", re.S)
JAVASCRIPT_RE = re.compile(r"\{%-?\s*javascript\s*-?%\}(.*?)\{%-?\s*endjavascript\s*-?%\}", re.S)
LIQUID_OUTPUT_RE = re.compile(r"\{\{.*?\}\}", re.S)
LIQUID_TAG_RE = re.compile(r"\{%.*?%\}", re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
LIQUID_COMMENT_RE = re.compile(r"\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}", re.S)

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3,8})\b")
RGB_RE = re.compile(r"\brgba?\([^)]*\)")
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;{}]+)")
LENGTH_RE = re.compile(r"(?<![\w-])(\d+(?:\.\d+)?)(px|rem|em)\b")
HANDLE_RE = re.compile(
    r"(?:all_products|collections|articles|pages|blogs)\s*\[\s*['\"]([^'\"]+)['\"]\s*\]"
)
SCRIPT_SRC_RE = re.compile(r"<script[^>]+src\s*=\s*['\"]([^'\"]+)['\"]", re.I)
CLASS_RE = re.compile(r'class\s*=\s*"([^"]*)"')
SETTING_REF_RE = re.compile(r"\b(?:section|block)\.settings\.([A-Za-z0-9_]+)")

# Lengths that are structural rather than design decisions.
ALLOWED_LENGTHS = {"0px", "1px", "2px", "100px"}
# CSS declarations whose numeric values are mechanics, not taste.
STRUCTURAL_DECLS = ("border-width", "outline", "translate", "z-index", "flex-basis")

CONTRACT_CATEGORIES = {
    "layout": (
        "padding", "margin", "gap", "column", "columns", "width", "height",
        "align", "spacing", "layout", "position", "order", "reverse", "sticky", "full_width",
    ),
    "color": ("color", "scheme", "background", "overlay", "gradient"),
    "typography": ("font", "size", "weight", "line_height", "letter", "transform", "heading_size"),
    "content": ("text", "heading", "title", "image", "richtext", "link", "url", "product", "collection", "label"),
}
BREAKPOINT_HINTS = ("mobile", "tablet", "desktop", "_sm", "_md", "_lg")
COLOR_TYPES = {"color", "color_scheme", "color_background"}
BEHAVIOR_HINTS = ("autoplay", "speed", "interval", "loop", "arrows", "dots", "delay",
                  "animation", "threshold", "trigger", "enable", "show", "sticky", "duration")


def strip_liquid(text: str) -> str:
    return LIQUID_TAG_RE.sub(" ", LIQUID_OUTPUT_RE.sub(" ", text))


def split_file(text: str) -> tuple[str, str, str, dict | None, str | None]:
    """Return (markup, css, js, schema_dict, schema_error)."""
    css = "\n".join(STYLESHEET_RE.findall(text))
    js = "\n".join(JAVASCRIPT_RE.findall(text))
    schema_match = SCHEMA_RE.search(text)
    schema, schema_error = None, None
    if not schema_match:
        schema_error = "no {% schema %} block"
    else:
        try:
            schema = json.loads(schema_match.group(1))
        except json.JSONDecodeError as exc:
            schema_error = f"schema is not valid JSON: {exc}"

    markup = SCHEMA_RE.sub("", text)
    markup = STYLESHEET_RE.sub("", markup)
    markup = JAVASCRIPT_RE.sub("", markup)
    markup = LIQUID_COMMENT_RE.sub("", markup)
    markup = COMMENT_RE.sub("", markup)
    return markup, css, js, schema, schema_error


def collect_settings(schema: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    section_settings, block_settings = {}, {}
    for s in schema.get("settings", []) or []:
        if isinstance(s, dict) and s.get("id"):
            section_settings[s["id"]] = s
    for b in schema.get("blocks", []) or []:
        for s in (b.get("settings") or []):
            if isinstance(s, dict) and s.get("id"):
                block_settings[s["id"]] = s
    return section_settings, block_settings


def audit_text_literals(markup: str) -> list[str]:
    """User-visible strings that should have been settings."""
    body = strip_liquid(markup)
    body = re.sub(r"<(script|style|svg)[\s\S]*?</\1>", " ", body, flags=re.I)
    findings = []
    for chunk in re.findall(r">([^<>]+)<", body):
        text = chunk.replace("&nbsp;", " ").strip()
        if len(text) < 2 or not re.search(r"[A-Za-z]{2,}", text):
            continue
        findings.append(text[:60])
    return findings


def audit_css_literals(css: str) -> tuple[list[str], list[str], list[str]]:
    colors = HEX_RE.findall(css) + RGB_RE.findall(css)
    fonts = [f.strip() for f in FONT_FAMILY_RE.findall(css) if "var(" not in f and "{{" not in f]
    lengths = []
    # Check declaration by declaration, not line by line: a one-line rule that
    # mixes `gap: var(--x)` with `top: 8px` must still flag the literal.
    body = re.sub(r"@media[^{]*\{", " ", css)
    for declaration in re.split(r"[;{}]", body):
        decl = declaration.strip()
        if not decl or ":" not in decl:
            continue
        prop, _, value = decl.partition(":")
        prop, value = prop.strip(), value.strip()
        if prop.startswith("--") or "var(" in value:
            continue
        if any(structural in prop for structural in STRUCTURAL_DECLS):
            continue
        for number, unit in LENGTH_RE.findall(value):
            token = f"{number}{unit}"
            if token in ALLOWED_LENGTHS:
                continue
            lengths.append(f"{prop}: {value[:40]} -> {token}")
    return colors, fonts, lengths


FOR_LOOP_RE = re.compile(r"\{%-?\s*for\s.*?\{%-?\s*endfor\s*-?%\}", re.S)
LIQUID_FORM_RE = re.compile(r"\{%-?\s*form\s.*?\{%-?\s*endform\s*-?%\}", re.S)
HTML_FORM_RE = re.compile(r"<form[\s\S]*?</form>", re.I)


def audit_repetition(markup: str, has_blocks: bool) -> list[str]:
    """Flag markup copy-pasted N times that should have been blocks.

    Content inside a `{% for %}` is already dynamic - a loop over filters,
    pagination parts or products repeats by design - so those bodies are
    removed before counting."""
    if has_blocks:
        return []
    markup = FOR_LOOP_RE.sub(" ", markup)
    # Form controls are distinct inputs, not repeatable content blocks.
    markup = LIQUID_FORM_RE.sub(" ", markup)
    markup = HTML_FORM_RE.sub(" ", markup)
    counts: dict[str, int] = {}
    for classes in CLASS_RE.findall(markup):
        key = " ".join(sorted(classes.split()))
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return [f"{k} x{v}" for k, v in counts.items() if v >= 3]


def audit_ranges(settings: dict[str, dict]) -> list[str]:
    """Shopify rejects a whole theme file over a bad range. The rules:
    step must have at most one decimal digit, (max - min) must divide evenly by
    step, and the resulting step count must not exceed 101."""
    problems = []
    for setting_id, s in settings.items():
        if s.get("type") != "range":
            continue
        try:
            lo, hi, step = float(s["min"]), float(s["max"]), float(s.get("step", 1))
        except (KeyError, TypeError, ValueError):
            problems.append(f"range '{setting_id}' is missing a numeric min/max/step")
            continue
        if step <= 0:
            problems.append(f"range '{setting_id}' has step {step} - must be positive")
            continue
        decimals = len(str(step).partition(".")[2].rstrip("0"))
        if decimals > 1:
            problems.append(f"range '{setting_id}' step {step} has more than 1 decimal digit - Shopify rejects the file")
        span = hi - lo
        steps = span / step
        if abs(steps - round(steps)) > 1e-6:
            problems.append(f"range '{setting_id}': (max - min) = {span:g} is not evenly divisible by step {step:g}")
        elif round(steps) > 101:
            problems.append(f"range '{setting_id}': {round(steps)} steps exceeds Shopify's limit of 101")
        elif round(steps) < 3:
            problems.append(f"range '{setting_id}': only {round(steps)} step(s) - Shopify requires at least 3")
        default = s.get("default")
        if isinstance(default, (int, float)):
            if not (lo <= default <= hi):
                problems.append(f"range '{setting_id}': default {default} is outside {lo:g}-{hi:g}")
            else:
                offsets = (default - lo) / step
                if abs(offsets - round(offsets)) > 1e-6:
                    problems.append(
                        f"range '{setting_id}': default {default:g} is not on a step boundary "
                        f"(min {lo:g}, step {step:g}) - Shopify rejects the file"
                    )
    return problems


def category_coverage(settings: dict[str, dict]) -> dict[str, bool]:
    ids = " ".join(settings.keys()).lower()
    types = {s.get("type") for s in settings.values()}
    coverage = {}
    for category, hints in CONTRACT_CATEGORIES.items():
        coverage[category] = any(h in ids for h in hints)
    coverage["color"] = coverage["color"] or bool(types & COLOR_TYPES)
    coverage["typography"] = coverage["typography"] or "font_picker" in types
    coverage["breakpoints"] = any(h in ids for h in BREAKPOINT_HINTS)
    coverage["behavior"] = any(h in ids for h in BEHAVIOR_HINTS)
    return coverage


def audit_file(path: str, plan: dict | None = None) -> dict:
    text = open(path, encoding="utf-8").read()
    markup, css, js, schema, schema_error = split_file(text)
    errors: list[str] = []
    warnings: list[str] = []

    if schema_error:
        return {"file": path, "errors": [schema_error], "warnings": [], "coverage": {}, "passed": False}

    if not schema.get("name"):
        errors.append("schema has no 'name'")
    if not schema.get("presets"):
        errors.append("schema has no 'presets' - section cannot be added in the theme editor")

    section_settings, block_settings = collect_settings(schema)
    all_settings = {**section_settings, **block_settings}
    referenced = set(SETTING_REF_RE.findall(text))

    for undefined in sorted(referenced - set(all_settings)):
        errors.append(f"markup references settings.{undefined} which the schema never defines")
    for unused in sorted(set(all_settings) - referenced):
        errors.append(f"setting '{unused}' is defined but never used - it will do nothing in the editor")

    colors, fonts, lengths = audit_css_literals(css)
    for c in sorted(set(colors)):
        errors.append(f"hardcoded color in CSS: {c}")
    for f in sorted(set(fonts)):
        errors.append(f"hardcoded font-family in CSS: {f}")
    for lng in lengths[:20]:
        errors.append(f"hardcoded length in CSS: {lng}")

    inline_colors = HEX_RE.findall(strip_liquid(markup)) + RGB_RE.findall(strip_liquid(markup))
    for c in sorted(set(inline_colors)):
        errors.append(f"hardcoded color in markup: {c}")

    for text_literal in audit_text_literals(markup)[:20]:
        errors.append(f"hardcoded visible text: {text_literal!r} - should be a setting")

    for handle in sorted(set(HANDLE_RE.findall(text))):
        errors.append(f"hardcoded resource handle: {handle!r} - use a product/collection picker setting")

    for src in SCRIPT_SRC_RE.findall(markup):
        errors.append(f"third-party script: {src} - recreate the mechanic natively instead")

    for repeat in audit_repetition(markup, bool(schema.get("blocks"))):
        errors.append(f"repeated markup with no blocks defined: {repeat}")

    errors.extend(audit_ranges(all_settings))

    coverage = category_coverage(all_settings)
    for category, present in coverage.items():
        if not present:
            errors.append(f"contract gap: no '{category}' settings on this section")

    if plan:
        planned = {s for s in plan.get(os.path.basename(path), {}).get("settings", [])}
        for missing in sorted(planned - set(all_settings)):
            errors.append(f"settings-plan promised '{missing}' but the schema does not have it")

    if js and "shopify:section:load" not in text:
        warnings.append("section has JS but no shopify:section:load handler - it will break during editing")

    score = round(100 * sum(coverage.values()) / len(coverage), 1) if coverage else 0.0
    return {
        "file": path,
        "errors": errors,
        "warnings": warnings,
        "coverage": coverage,
        "coverage_score": score,
        "setting_count": len(all_settings),
        "block_count": len(schema.get("blocks") or []),
        "passed": not errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="a .liquid file or a directory of them")
    ap.add_argument("--plan", help="settings-plan.json from Phase 3")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding="utf-8")) if args.plan else None

    if os.path.isdir(args.target):
        files = [os.path.join(args.target, f) for f in sorted(os.listdir(args.target)) if f.endswith(".liquid")]
    else:
        files = [args.target]
    if not files:
        print(f"no .liquid files found at {args.target}")
        return 1

    results = [audit_file(f, plan) for f in files]

    if args.json:
        print(json.dumps({"results": results}, indent=2))
    else:
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"\n{status}  {os.path.basename(r['file'])}   "
                  f"{r.get('setting_count', 0)} settings, {r.get('block_count', 0)} block type(s), "
                  f"contract coverage {r.get('coverage_score', 0)}%")
            for cat, present in r.get("coverage", {}).items():
                if not present:
                    print(f"       missing category: {cat}")
            for e in r["errors"]:
                print(f"       ERROR  {e}")
            for w in r["warnings"]:
                print(f"       WARN   {w}")

    failed = [r for r in results if not r["passed"]]
    if not args.json:
        print(f"\n{len(results) - len(failed)}/{len(results)} section(s) pass the editability contract")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
