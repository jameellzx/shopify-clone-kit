#!/usr/bin/env python3
"""Dependency preflight for theme-clone.

Checks (and with --install, installs) everything capture.py / diff.py /
schema_audit.py need:

  - Python packages: playwright, pillow
  - A Playwright Chromium build that actually launches
  - git, and optionally the Shopify CLI (needed for the verify loop, not capture)

Windows note: this machine runs an Application Control policy that blocks
pip-installed `.exe` console shims. Every install and invocation here therefore
goes through `python -m <module>` and never through a bare `playwright.exe`.

Usage:
    python setup.py            # report status
    python setup.py --json     # machine-readable status
    python setup.py --install  # install what's missing, then re-check

Exit: 0 = ready to capture, 1 = something is missing
"""
from __future__ import annotations

import argparse
import importlib
import json
import shutil
import subprocess
import sys

PY_PACKAGES = {"playwright": "playwright", "PIL": "pillow"}
OPTIONAL_BINARIES = ["git", "shopify"]


def _run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def check_packages() -> list[str]:
    missing = []
    for module, package in PY_PACKAGES.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    return missing


def check_chromium() -> tuple[bool, str]:
    """Launch headless Chromium for real. Presence of the package proves nothing."""
    try:
        importlib.import_module("playwright")
    except ImportError:
        return False, "playwright not installed"
    probe = (
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    b = p.chromium.launch()\n"
        "    b.close()\n"
        "print('ok')\n"
    )
    res = _run([sys.executable, "-c", probe])
    if res.returncode == 0 and "ok" in res.stdout:
        return True, "chromium launches"
    detail = (res.stderr or res.stdout).strip().splitlines()
    return False, detail[-1] if detail else "chromium failed to launch"


def install(missing_packages: list[str]) -> None:
    if missing_packages:
        print(f"[setup] installing: {', '.join(missing_packages)}")
        res = _run([sys.executable, "-m", "pip", "install", "--user", *missing_packages])
        sys.stderr.write(res.stderr)
        if res.returncode != 0:
            raise SystemExit("[setup] pip install failed - see output above")
    print("[setup] installing Chromium via `python -m playwright install chromium`")
    res = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    if res.returncode != 0:
        raise SystemExit("[setup] chromium download failed")


def status() -> dict:
    missing_packages = check_packages()
    chromium_ok, chromium_detail = check_chromium()
    binaries = {b: bool(shutil.which(b)) for b in OPTIONAL_BINARIES}
    return {
        "python": sys.executable,
        "missing_packages": missing_packages,
        "chromium_ok": chromium_ok,
        "chromium_detail": chromium_detail,
        "binaries": binaries,
        "can_capture": not missing_packages and chromium_ok,
        "can_verify": bool(binaries.get("shopify")) and bool(binaries.get("git")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--install", action="store_true")
    args = ap.parse_args()

    st = status()
    if args.install and not st["can_capture"]:
        install(st["missing_packages"])
        st = status()

    if args.json:
        print(json.dumps(st, indent=2))
        return 0 if st["can_capture"] else 1

    print(f"python           {st['python']}")
    print(f"packages         {'ok' if not st['missing_packages'] else 'MISSING: ' + ', '.join(st['missing_packages'])}")
    print(f"chromium         {'ok' if st['chromium_ok'] else 'FAIL: ' + st['chromium_detail']}")
    for name, present in st["binaries"].items():
        print(f"{name:16} {'ok' if present else 'not on PATH'}")

    if not st["can_capture"]:
        print("\nRun:  python setup.py --install")
        print("If Chromium still will not launch, capture can fall back to the PinchTab")
        print("server at C:\\dev\\pinchtab (port 9867) or the Scrapling MCP.")
        return 1
    if not st["can_verify"]:
        print("\nCapture is ready. The verify loop also needs the Shopify CLI:")
        print("  npm install -g @shopify/cli@latest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
