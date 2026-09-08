from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.structure_access_graph import (
    load_structure_access_graph,
)
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    load_world_structure_index,
)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Query route-verified structure openings from a pinned WorldPack."
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--x", type=float, required=True)
    parser.add_argument("--y", type=float, required=True)
    parser.add_argument("--z", type=float)
    parser.add_argument("--structure-id")
    parser.add_argument("--maximum-distance", type=float, default=1_000.0)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)
    coordinates = [args.x, args.y, args.maximum_distance]
    if args.z is not None:
        coordinates.append(args.z)
    if any(not math.isfinite(value) for value in coordinates):
        raise ValueError("structure access query coordinates are invalid")

    binding = load_world_pack_runtime_profile(
        args.profile,
        store_root=args.store_root,
        profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
    )
    loaded_index = load_world_structure_index(
        args.index,
        schema_path=ROOT / "contracts" / "world-structure-index.schema.json",
        pack=binding.pack,
    )
    graph = load_structure_access_graph(
        args.graph,
        schema_path=ROOT / "contracts" / "structure-access-graph.schema.json",
        pack=binding.pack,
        structure_index_record=loaded_index.record,
    )
    matches = graph.nearest_openings(
        x=args.x,
        y=args.y,
        z=args.z,
        structure_id=args.structure_id,
        maximum_distance_yards=args.maximum_distance,
        limit=args.limit,
    )
    print(json.dumps({
        "status": "VERIFIED_STRUCTURE_ACCESS_QUERY",
        "graph_id": graph.record["graph_id"],
        "coverage_state": graph.record["coverage_state"],
        "query": {
            "position": [args.x, args.y, args.z],
            "structure_id": args.structure_id,
            "maximum_distance_yards": args.maximum_distance,
            "limit": args.limit,
        },
        "matches": list(matches),
        "execution_authority": False,
    }, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
