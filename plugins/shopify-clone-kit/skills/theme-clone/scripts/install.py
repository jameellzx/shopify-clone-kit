"""Install a saved homepage template (from this قوالب folder) into a Shopify theme.

Usage:
    python install.py --list
    python install.py <template> <theme_folder> [--store x.myshopify.com --theme-id 123]

What it does:
  1. copies sections/*.liquid into <theme>/sections/
  2. backs up the theme's templates/index.json, then writes the template's homepage
  3. adds the template's footer to sections/footer-group.json (the old footer is kept, only hidden)
  4. with --store and --theme-id: pushes only those files with the Shopify CLI

Images: the homepage points at shopify://shop_images/<name>.jpg. Upload the files in
<template>/images/ to the store first (Admin > Content > Files), keeping the file names.
"""
import argparse, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def templates():
    out = []
    for name in sorted(os.listdir(HERE)):
        meta = os.path.join(HERE, name, "template.json")
        if os.path.isfile(meta):
            out.append((name, json.load(open(meta, encoding="utf-8"))))
    return out


def load_json(path):
    # Shopify JSON files may start with a /* comment */ header; strip it.
    text = open(path, encoding="utf-8-sig").read()
    if text.lstrip().startswith("/*"):
        text = text[text.index("*/") + 2:]
    return json.loads(text)


def write_json(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:  # no BOM: Shopify rejects it
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template", nargs="?")
    ap.add_argument("theme", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--store")
    ap.add_argument("--theme-id")
    a = ap.parse_args()

    if a.list or not a.template:
        for name, meta in templates():
            print(f"{name:24} {meta.get('title', '')}  ({len(meta.get('sections', []))} sections)")
        return 0

    src = os.path.join(HERE, a.template)
    if not os.path.isfile(os.path.join(src, "template.json")):
        sys.exit(f"no template named {a.template!r}; run with --list")
    theme = os.path.abspath(a.theme)
    for need in ("layout/theme.liquid", "sections", "templates"):
        if not os.path.exists(os.path.join(theme, need)):
            sys.exit(f"{theme} is not a Shopify theme folder (missing {need})")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(theme, ".clone", f"backup-{stamp}")
    os.makedirs(backup, exist_ok=True)
    pushed = []

    for f in sorted(os.listdir(os.path.join(src, "sections"))):
        shutil.copy(os.path.join(src, "sections", f), os.path.join(theme, "sections", f))
        pushed.append(f"sections/{f}")
    print(f"copied {len(pushed)} sections")

    index = os.path.join(theme, "templates", "index.json")
    if os.path.exists(index):
        shutil.copy(index, os.path.join(backup, "index.json"))
    write_json(index, load_json(os.path.join(src, "templates", "index.json")))
    pushed.append("templates/index.json")
    print("wrote templates/index.json (old one in .clone/" + os.path.basename(backup) + ")")

    footer_src = os.path.join(src, "templates", "footer-section.json")
    group = os.path.join(theme, "sections", "footer-group.json")
    if os.path.exists(footer_src) and os.path.exists(group):
        shutil.copy(group, os.path.join(backup, "footer-group.json"))
        fg = load_json(group)
        new = load_json(footer_src)
        for key in fg["sections"]:
            if key not in new:
                fg["sections"][key]["disabled"] = True
        fg["sections"].update(new)
        fg["order"] = list(new) + [k for k in fg["order"] if k not in new]
        write_json(group, fg)
        pushed.append("sections/footer-group.json")
        print("added template footer (old footer hidden, not deleted)")

    if a.store and a.theme_id:
        cmd = ["shopify", "theme", "push", "--theme", a.theme_id, "--path", theme, "--store", a.store, "--nodelete"]
        for p in pushed:
            cmd += ["--only", p]
        print("pushing:", " ".join(cmd))
        subprocess.run(cmd, shell=(os.name == "nt"), check=False)

    print("\nnext: upload images/ to Admin > Content > Files (keep the names), then open the theme editor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
