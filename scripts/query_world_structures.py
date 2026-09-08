from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    WorldStructureIndexError,
    load_world_structure_index,
)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Query immutable local WMO/doodad awareness from a verified WorldPack index."
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--x", type=float, required=True)
    parser.add_argument("--y", type=float, required=True)
    parser.add_argument("--z", type=float)
    parser.add_argument("--radius", type=float, default=100.0)
    parser.add_argument("--kind", action="append", choices=("WMO", "DOODAD"))
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(argv)
    values = (args.x, args.y, args.radius) if args.z is None else (
        args.x, args.y, args.z, args.radius,
    )
    if any(not math.isfinite(value) for value in values):
        raise WorldStructureIndexError("query coordinates are not finite")
    if not 0.0 <= args.radius <= 1_000.0:
        raise WorldStructureIndexError("query radius must be between 0 and 1,000 yards")
    if not 1 <= args.limit <= 100:
        raise WorldStructureIndexError("query result limit must be between 1 and 100")

    binding = load_world_pack_runtime_profile(
        args.profile,
        store_root=args.store_root,
        profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
    )
    loaded = load_world_structure_index(
        args.index,
        schema_path=ROOT / "contracts" / "world-structure-index.schema.json",
        pack=binding.pack,
    )
    hits = loaded.spatial.nearby(
        x=args.x,
        y=args.y,
        z=args.z,
        radius_yards=args.radius,
        kinds=args.kind,
    )
    coverage_counts = {"FULL": 0, "PARTIAL": 0, "NONE": 0, "GLOBAL_WMO": 0}
    for hit in hits:
        coverage_counts[hit.structure.nav_coverage] += 1
    selected = hits[: args.limit]
    print(json.dumps({
        "status": "VERIFIED_QUERY",
        "index_id": loaded.record["index_id"],
        "map_id": loaded.record["map_id"],
        "map_name": loaded.record["map_name"],
        "query": {
            "x": args.x,
            "y": args.y,
            "z": args.z,
            "radius_yards": args.radius,
            "kinds": sorted(set(args.kind or ("WMO", "DOODAD"))),
        },
        "matching_structure_count": len(hits),
        "returned_structure_count": len(selected),
        "nav_coverage_counts": coverage_counts,
        "structures": [{
            "structure_id": hit.structure.structure_id,
            "kind": hit.structure.kind,
            "asset_path": hit.structure.asset_path,
            "collision_role": hit.structure.collision_role,
            "nav_coverage": hit.structure.nav_coverage,
            "horizontal_distance_yards": round(hit.horizontal_distance_yards, 6),
            "vertical_distance_yards": (
                None if hit.vertical_distance_yards is None
                else round(hit.vertical_distance_yards, 6)
            ),
            "contains_horizontal": hit.contains_horizontal,
            "contains_3d": hit.contains_3d,
        } for hit in selected],
        "static_knowledge_semantics": "PINNED_CLIENT_ASSET_BOUNDS",
        "dynamic_entity_knowledge": "NONE",
        "execution_authority": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
