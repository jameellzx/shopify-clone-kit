#!/usr/bin/env python3
"""Score a cloned render against its source screenshot.

Compares two full-page PNGs band by band, so the output is not a single
useless percentage but a ranked list of "the y=1180-1320 band is 61% - look
there". Writes a side-by-side contact sheet with the worst bands boxed.

    python diff.py --source cap/desktop.png --candidate local/desktop.png --out cap/diff/desktop

State mode diffs two directories of interaction screenshots pairwise by filename:

    python diff.py --states cap/states --candidate-states local/states --out cap/diff/states

Exit: 0 if the overall score meets --threshold, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

BAND_HEIGHT = 40
WORST_N = 12


def load_aligned(source_path: str, candidate_path: str) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    """Load both images into a common canvas: candidate scaled to source width,
    both padded (white) to the taller height so a length difference shows up as
    a real mismatch rather than a crash."""
    src = Image.open(source_path).convert("RGB")
    cand = Image.open(candidate_path).convert("RGB")

    if cand.width != src.width:
        ratio = src.width / cand.width
        cand = cand.resize((src.width, max(1, round(cand.height * ratio))), Image.LANCZOS)

    height = max(src.height, cand.height)
    canvas_src = Image.new("RGB", (src.width, height), "white")
    canvas_cand = Image.new("RGB", (src.width, height), "white")
    canvas_src.paste(src, (0, 0))
    canvas_cand.paste(cand, (0, 0))

    return (
        np.asarray(canvas_src, dtype=np.int16),
        np.asarray(canvas_cand, dtype=np.int16),
        (src.width, height),
    )


def band_scores(src: np.ndarray, cand: np.ndarray, band_height: int = BAND_HEIGHT) -> list[dict]:
    """Per-band similarity in [0,1]. Perceptual enough for layout work: mean
    absolute channel error, with a penalty for bands whose mean brightness
    differs a lot (catches a wholly missing block)."""
    height = src.shape[0]
    out = []
    for top in range(0, height, band_height):
        bottom = min(top + band_height, height)
        a = src[top:bottom]
        b = cand[top:bottom]
        mae = float(np.abs(a - b).mean()) / 255.0
        brightness_gap = abs(float(a.mean()) - float(b.mean())) / 255.0
        score = max(0.0, 1.0 - (mae * 0.85 + brightness_gap * 0.15) * 2.0)
        out.append({"y": [top, bottom], "score": round(score, 4), "mae": round(mae, 4)})
    return out


def heatmap(src: np.ndarray, cand: np.ndarray) -> Image.Image:
    delta = np.abs(src - cand).mean(axis=2)
    norm = np.clip(delta * 3, 0, 255).astype(np.uint8)
    rgb = np.zeros((*norm.shape, 3), dtype=np.uint8)
    rgb[..., 0] = norm
    rgb[..., 2] = 255 - norm
    return Image.fromarray(rgb, "RGB")


def contact_sheet(source_path: str, candidate_path: str, src: np.ndarray, cand: np.ndarray,
                  bands: list[dict], out_path: str, max_height: int = 4000) -> None:
    src_img = Image.fromarray(src.astype(np.uint8), "RGB")
    cand_img = Image.fromarray(cand.astype(np.uint8), "RGB")
    heat = heatmap(src, cand)

    worst = {tuple(b["y"]) for b in sorted(bands, key=lambda b: b["score"])[:WORST_N] if b["score"] < 0.95}
    for img in (src_img, cand_img):
        draw = ImageDraw.Draw(img)
        for top, bottom in worst:
            draw.rectangle([0, top, img.width - 1, bottom - 1], outline=(255, 0, 0), width=3)

    scale = min(1.0, max_height / src_img.height)
    if scale < 1.0:
        size = (round(src_img.width * scale), round(src_img.height * scale))
        src_img, cand_img, heat = (i.resize(size, Image.LANCZOS) for i in (src_img, cand_img, heat))

    gap = 16
    sheet = Image.new("RGB", (src_img.width * 3 + gap * 2, src_img.height), "white")
    sheet.paste(src_img, (0, 0))
    sheet.paste(cand_img, (src_img.width + gap, 0))
    sheet.paste(heat, (src_img.width * 2 + gap * 2, 0))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sheet.save(out_path)


def compare(source_path: str, candidate_path: str, out_dir: str, label: str) -> dict:
    src, cand, (width, height) = load_aligned(source_path, candidate_path)
    bands = band_scores(src, cand)
    overall = float(np.mean([b["score"] for b in bands]))
    worst = sorted(bands, key=lambda b: b["score"])[:WORST_N]

    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, f"{label}-contact-sheet.png")
    contact_sheet(source_path, candidate_path, src, cand, bands, sheet_path)

    return {
        "label": label,
        "source": source_path,
        "candidate": candidate_path,
        "canvas": [width, height],
        "score": round(overall, 4),
        "worst_bands": worst,
        "contact_sheet": sheet_path,
        "band_count": len(bands),
    }


def compare_states(source_dir: str, candidate_dir: str, out_dir: str) -> list[dict]:
    results = []
    for name in sorted(os.listdir(source_dir)):
        if not name.endswith(".png"):
            continue
        counterpart = os.path.join(candidate_dir, name)
        if not os.path.exists(counterpart):
            results.append({"label": name, "score": 0.0, "error": "no matching state in candidate"})
            continue
        results.append(compare(os.path.join(source_dir, name), counterpart, out_dir, name[:-4]))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--candidate")
    ap.add_argument("--states", help="directory of source state screenshots")
    ap.add_argument("--candidate-states", help="directory of candidate state screenshots")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="diff")
    ap.add_argument("--threshold", type=float, default=0.95)
    args = ap.parse_args()

    if args.states:
        if not args.candidate_states:
            ap.error("--states requires --candidate-states")
        results = compare_states(args.states, args.candidate_states, args.out)
        payload = {"mode": "states", "threshold": args.threshold, "results": results}
        worst_score = min((r["score"] for r in results), default=1.0)
    else:
        if not (args.source and args.candidate):
            ap.error("--source and --candidate are required")
        result = compare(args.source, args.candidate, args.out, args.label)
        payload = {"mode": "page", "threshold": args.threshold, "results": [result]}
        worst_score = result["score"]

    report_path = os.path.join(args.out, "diff-report.json")
    os.makedirs(args.out, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    for r in payload["results"]:
        if "error" in r:
            print(f"  {r['label']:28} MISSING - {r['error']}")
            continue
        flag = "ok " if r["score"] >= args.threshold else "FAIL"
        print(f"  {flag} {r['label']:24} {r['score'] * 100:5.1f}%")
        for band in r.get("worst_bands", [])[:3]:
            if band["score"] < args.threshold:
                print(f"        y={band['y'][0]}-{band['y'][1]:<6} {band['score'] * 100:5.1f}%")
    print(f"\nreport: {report_path}")
    return 0 if worst_score >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
