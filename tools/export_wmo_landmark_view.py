"""Render exact WMO wire edges for offline landmark selection, not a camera view."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from perfect_assassin.adapter.wmo_bundle import load_wmo_bundle, read_bounded
from perfect_assassin.adapter.wmo_landmarks import resolve_landmarks
from perfect_assassin.movement.world_pack_runtime import load_world_pack_runtime_profile
from perfect_assassin.movement.world_structure_index import load_world_structure_index


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", type=Path, required=True)
    p.add_argument("--store-root", type=Path, required=True)
    p.add_argument("--bundle-config", type=Path, required=True)
    p.add_argument("--structure-id", required=True)
    p.add_argument("--group", type=int, required=True)
    p.add_argument("--maximum-z", type=float)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError("output directory already exists")
    if args.maximum_z is not None and not np.isfinite(args.maximum_z):
        raise ValueError("invalid slice")
    pack = load_world_pack_runtime_profile(
        args.profile,
        store_root=args.store_root,
        profile_schema_path=ROOT / "contracts/world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts/standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts/client-world-catalog.schema.json",
    ).pack
    spec = json.loads(read_bounded(args.bundle_config, 16384))
    index = load_world_structure_index(
        ROOT / spec["index"],
        pack=pack,
        schema_path=ROOT / "contracts/world-structure-index.schema.json",
    )
    bundle = load_wmo_bundle(
        ROOT / spec["directory"], expected_sha256=spec["sha256"], pack=pack, index=index
    )
    structure = bundle.structures[args.structure_id]
    mesh = next(
        m for m in bundle.models[structure["asset_path"]] if m.group_index == args.group
    )
    matrix = np.array(structure["transform_matrix"]).reshape(4, 4)
    world = mesh.vertices @ matrix[:3, :3].T + matrix[:3, 3]
    # Weld exact coordinates for display only; references retain original vertex IDs.
    coordinates, edges = {}, {}
    for triangle in mesh.indices[mesh.retained]:
        points = world[triangle]
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        if np.linalg.norm(normal) < 1e-9:
            continue
        normal /= np.linalg.norm(normal)
        for a, b in ((0, 1), (1, 2), (2, 0)):
            pa, pb = tuple(points[a]), tuple(points[b])
            coordinates.setdefault(pa, int(triangle[a]))
            coordinates.setdefault(pb, int(triangle[b]))
            edges.setdefault(tuple(sorted((pa, pb))), []).append(normal)
    edges = [
        e
        for e, normals in edges.items()
        if not (len(normals) == 2 and abs(np.dot(*normals)) > 0.99999)
    ]
    if args.maximum_z is not None:
        edges = [e for e in edges if max(e[0][2], e[1][2]) <= args.maximum_z]
    if not edges:
        raise ValueError("no edges in slice")
    used = sorted({point for edge in edges for point in edge})
    if len(used) > 2000 or len(edges) > 20000:
        raise ValueError(
            "view exceeds offline display budget; use a smaller group/slice"
        )
    references = [
        {"group_index": args.group, "vertex_index": coordinates[point]}
        for point in used
    ]
    batches = [
        resolve_landmarks(
            bundle, structure_id=args.structure_id, references=references[i : i + 64]
        )
        for i in range(0, len(references), 64)
    ]
    result = dict(batches[0])
    result["points"] = [point for batch in batches for point in batch["points"]]
    result["display_scope"] = "RETAINED_TRIANGLE_SHARP_EDGES_OR_BOUNDARIES"
    result["maximum_world_z_slice"] = args.maximum_z
    image = Image.new("RGB", (2000, 1100), "white")
    draw = ImageDraw.Draw(image)
    for panel, axes, title in [
        (0, (1, 0), "PLAN: world Y / X"),
        (1, (1, 2), "ELEVATION: world Y / Z"),
    ]:
        values = np.array(used)[:, axes]
        low, high = values.min(axis=0), values.max(axis=0)
        scale = min(900 / max(high[0] - low[0], 1), 930 / max(high[1] - low[1], 1))

        def pixel(point, axes=axes, panel=panel, low=low, scale=scale):
            v = np.array(point)[list(axes)]
            return (
                panel * 1000 + 50 + (v[0] - low[0]) * scale,
                1040 - (v[1] - low[1]) * scale,
            )

        draw.text(
            (panel * 1000 + 30, 20),
            title + " | asset vertices; NOT observed actor/camera",
            fill="black",
        )
        for a, b in edges:
            draw.line((*pixel(a), *pixel(b)), fill="#355770", width=2)
        for point in used:
            x, y = pixel(point)
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill="#c84628")
            draw.text((x + 3, y - 10), str(coordinates[point]), fill="#8c2717")
    args.output.mkdir(parents=True, exist_ok=False)
    image.save(args.output / "edges.png")
    with (args.output / "landmarks.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(
        json.dumps(
            {
                "points": len(used),
                "edges": len(edges),
                "group": args.group,
                "world_min": world.min(axis=0).tolist(),
                "world_max": world.max(axis=0).tolist(),
                "pixel_correspondence_verified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
