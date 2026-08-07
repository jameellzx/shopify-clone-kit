#!/usr/bin/env python3
"""Validate the Shopify Clone Kit before installing or shipping.

Checks every skill for:
  - a SKILL.md that exists
  - YAML frontmatter with name + description
  - name matching its directory
  - a description long enough to actually trigger on
  - SKILL.md size (warns past the progressive-disclosure threshold)
  - every `references/...` / `scripts/...` path mentioned in prose resolving to a real file
  - orphaned reference files nothing points at
  - bundled Python scripts compiling

Usage:  python build/validate.py
Exit:   0 = clean, 1 = errors found
"""
import os
import py_compile
import re
import tempfile
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "plugins", "shopify-clone-kit", "skills")
SOFT_LINE_LIMIT = 400
PLACEHOLDER = re.compile(r"[<{*]")

errors, warnings = [], []


def check(skill):
    d = os.path.join(SKILLS, skill)
    manifest = os.path.join(d, "SKILL.md")
    if not os.path.isfile(manifest):
        errors.append(f"{skill}: no SKILL.md")
        return 0

    text = open(manifest, encoding="utf-8").read()
    lines = text.count("\n") + 1

    fm = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not fm:
        errors.append(f"{skill}: missing YAML frontmatter")
    else:
        block = fm.group(1)
        name = re.search(r"^name:\s*(\S+)", block, re.M)
        desc = re.search(r"^description:\s*(.+)", block, re.M)
        if not name:
            errors.append(f"{skill}: frontmatter missing 'name'")
        elif name.group(1) != skill:
            errors.append(f"{skill}: frontmatter name '{name.group(1)}' != directory name")
        if not desc:
            errors.append(f"{skill}: frontmatter missing 'description'")
        elif len(desc.group(1)) < 60:
            warnings.append(f"{skill}: description is short ({len(desc.group(1))} chars) - may trigger unreliably")

    if lines > SOFT_LINE_LIMIT:
        warnings.append(f"{skill}: SKILL.md is {lines} lines - consider moving detail into references/")

    cited = set()
    for ref in re.findall(r"`((?:references|scripts)/[^`]+)`", text):
        if PLACEHOLDER.search(ref):
            continue
        cited.add(ref)
        if not os.path.exists(os.path.join(d, ref.replace("/", os.sep))):
            errors.append(f"{skill}: dead reference -> {ref}")

    refdir = os.path.join(d, "references")
    if os.path.isdir(refdir):
        for f in sorted(os.listdir(refdir)):
            if f"references/{f}" not in cited:
                warnings.append(f"{skill}: references/{f} exists but SKILL.md never points at it")

    scriptdir = os.path.join(d, "scripts")
    if os.path.isdir(scriptdir):
        for f in sorted(os.listdir(scriptdir)):
            if not f.endswith(".py"):
                continue
            path = os.path.join(scriptdir, f)
            # cfile must be a real path: os.devnull is rejected on Windows.
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    py_compile.compile(path, doraise=True, cfile=os.path.join(tmp, f + "c"))
                except py_compile.PyCompileError as exc:
                    errors.append(f"{skill}: scripts/{f} does not compile -> {exc.msg.strip().splitlines()[-1]}")

    return lines


def main():
    if not os.path.isdir(SKILLS):
        print(f"ERROR: skills directory not found: {SKILLS}")
        return 1

    skills = sorted(d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d)))
    print(f"Validating {len(skills)} skill(s) in {SKILLS}\n")
    for s in skills:
        n = check(s)
        refdir = os.path.join(SKILLS, s, "references")
        nrefs = len(os.listdir(refdir)) if os.path.isdir(refdir) else 0
        print(f"  {s:28} {str(n) + ' lines':>12}   {nrefs} reference file(s)")

    print()
    for w in warnings:
        print(f"  WARN   {w}")
    for e in errors:
        print(f"  ERROR  {e}")

    print()
    if errors:
        print(f"FAILED - {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"PASSED - 0 errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
