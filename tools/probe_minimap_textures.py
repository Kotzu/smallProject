"""Rank original client textures against an archived minimap ROI, offline only.

Explicit ROI is an experiment parameter, not a reusable live calibration.
Pillow only decodes/resamples textures; matching uses bounded NumPy arrays.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from perfect_assassin.adapter.minimap_texture_probe import masked_texture_match


def transformed(image, angle, scale):
    # Work from alpha bounds, not power-of-two padding around the WMO tile.
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        return None
    image = image.crop(bounds)
    size = tuple(max(1, round(n * scale)) for n in image.size)
    if max(size) > 512:
        return None
    rotated = image.resize(size, Image.Resampling.BILINEAR).rotate(
        angle, Image.Resampling.BICUBIC, expand=True
    )
    if max(rotated.size) > 512:
        return None
    gray = np.asarray(rotated.convert("L"), dtype=float) / 255
    mask = np.asarray(rotated.getchannel("A")) >= 192
    return gray, mask


def rank_reference(observed, valid, image):
    def search(angles, scales):
        rows = []
        for angle in angles:
            for scale in scales:
                pair = transformed(image, angle, scale)
                if pair is None:
                    continue
                result = masked_texture_match(observed, *pair, valid)
                if result["similarity"] is not None:
                    rows.append({**result, "angle_degrees": float(angle % 360),
                                 "scale": float(scale)})
        return sorted(rows, key=lambda row: row["similarity"], reverse=True)

    coarse = search(range(0, 360, 15), (0.75, 1.0, 1.25, 1.5))
    if not coarse:
        return {"status": "INSUFFICIENT_TEXTURE_OR_COVERAGE", "similarity": None}
    best = coarse[0]
    fine = search(
        np.arange(best["angle_degrees"] - 10, best["angle_degrees"] + 11, 2),
        np.arange(max(0.5, best["scale"] - 0.2), best["scale"] + 0.201, 0.05),
    )
    return max([best, *fine], key=lambda row: row["similarity"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--roi", type=int, nargs=4, required=True,
                        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    parser.add_argument("--reference", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= len(args.reference) <= 16:
        raise ValueError("output exists or reference count exceeds budget")
    if args.frame.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("frame exceeds budget")
    with Image.open(args.frame) as frame:
        x1, y1, x2, y2 = args.roi
        if not (0 <= x1 < x2 <= frame.width and 0 <= y1 < y2 <= frame.height
                and max(x2 - x1, y2 - y1) <= 512):
            raise ValueError("invalid bounded ROI")
        roi = frame.crop(args.roi).convert("L")
    observed = np.asarray(roi, dtype=float) / 255
    # Exclude minimap border/buttons. Circle is explicit ROI-relative, not live detection.
    h, w = observed.shape
    yy, xx = np.mgrid[:h, :w]
    valid = (xx - (w - 1) / 2) ** 2 + (yy - (h - 1) / 2) ** 2 < (min(h, w) * 0.43) ** 2
    rows = []
    for path in args.reference:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("reference exceeds budget")
        with Image.open(path) as reference:
            if max(reference.size) > 512:
                raise ValueError("reference dimensions exceed budget")
            image = reference.convert("RGBA")
        result = rank_reference(observed, valid, image)
        rows.append({"reference": str(path), "sha256": sha256(path.read_bytes()).hexdigest(),
                     "dimensions": list(image.size), **result})
        print(path.name, result, flush=True)
    record = {
        "schema_version": 1, "source": "OFFLINE_MINIMAP_TEXTURE_PROBE",
        "frame": str(args.frame), "frame_sha256": sha256(args.frame.read_bytes()).hexdigest(),
        "roi_ltrb": args.roi, "roi_calibration": "MANUAL_OFFLINE_ONLY",
        "valid_circle_radius_fraction": 0.43,
        "similarity_is_probability": False, "candidate_set_exhaustive": False,
        "observed_actor_z": None, "floor_id": None, "execution_authority": False,
        "references": sorted(
            rows,
            key=lambda row: row["similarity"] if row["similarity"] is not None else -2,
            reverse=True,
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(record, target, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
