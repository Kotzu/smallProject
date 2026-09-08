"""Compose supplied original tiles using an explicit, offline WMO layout hypothesis."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from perfect_assassin.adapter.minimap_layout import MinimapTile, tile_layout
from perfect_assassin.adapter.wmo_bundle import read_bounded
from perfect_assassin.adapter.wmo_groups import MAX_ROOT_BYTES, parse_wmo_root


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root-wmo", type=Path, required=True)
    p.add_argument("--root-sha256", required=True)
    p.add_argument("--pixel-density", type=float, required=True)
    p.add_argument("--tile", action="append", required=True,
                   help="group:column:row:path (explicit source association)")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists() or not 1 <= len(args.tile) <= 64:
        raise ValueError("output exists or tile count exceeds budget")
    data = read_bounded(args.root_wmo, MAX_ROOT_BYTES)
    if sha256(data).hexdigest() != args.root_sha256.lower():
        raise ValueError("WMO root does not match external hash")
    groups = parse_wmo_root(data)
    tiles, images, sources = [], [], []
    for spec in args.tile:
        group, column, row, name = spec.split(":", 3)
        path = Path(name)
        data = read_bounded(path, 4 * 1024 * 1024)
        from io import BytesIO
        with Image.open(BytesIO(data)) as image:
            if max(image.size) > 256:
                raise ValueError("tile exceeds dimension budget")
            rgba = image.convert("RGBA")
        tiles.append(MinimapTile(int(group), int(column), int(row), *rgba.size))
        images.append(rgba)
        sources.append({"path": str(path), "sha256": sha256(data).hexdigest(),
                        "group_index": int(group), "column": int(column), "row": int(row)})
    layout = tile_layout(groups, tiles, pixels_per_model_unit=args.pixel_density)
    canvas = Image.new("RGBA", tuple(layout["size"]))
    for image, rectangle in zip(images, layout["tiles"]):
        dx = layout["origin_xy"][0] - rectangle["left"]
        dy = layout["origin_xy"][1] - rectangle["top"]
        layer = image.transform(canvas.size, Image.Transform.AFFINE,
                                (1, 0, dx, 0, 1, dy), Image.Resampling.BILINEAR)
        canvas = Image.alpha_composite(canvas, layer)
    layout.update({"tile_sources": sources, "source_association": "EXPLICIT_OPERATOR_INPUT",
                   "composite_order": "INPUT_ORDER_NOT_OCCUPIED_FLOOR_ORDER",
                   "alpha_bbox": canvas.getchannel("A").getbbox()})
    args.output.mkdir(parents=True)
    canvas.save(args.output / "composite.png")
    layout["composite_sha256"] = sha256((args.output / "composite.png").read_bytes()).hexdigest()
    (args.output / "layout.json").write_text(json.dumps(layout, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: layout[k] for k in ("size", "alpha_bbox", "groups_without_supplied_tiles")}))


if __name__ == "__main__":
    main()
