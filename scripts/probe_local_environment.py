from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "integrations" / "windows-input"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from client_navmesh_backend import ClientAssetNavmeshQuery
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import NavPoint
from perfect_assassin.movement.local_environment_awareness import (
    build_local_environment_awareness,
)
from perfect_assassin.movement.structure_access_graph import (
    StructureAccessObservation,
    build_structure_access_graph_record,
)
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    load_world_structure_index,
)


DEFAULT_WORKER = (
    ROOT / "data" / "runtime" / "native-build"
    / "pa_nav_probe-v27" / "Debug" / "pa_nav_probe.exe"
)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fuse a WorldPack structure index with one read-only Detour/BVH "
            "local-environment probe."
        )
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--map-id", type=int, required=True)
    parser.add_argument("--x", type=float, required=True)
    parser.add_argument("--y", type=float, required=True)
    parser.add_argument("--z", type=float, required=True)
    parser.add_argument("--stop-x", type=float, required=True)
    parser.add_argument("--stop-y", type=float, required=True)
    parser.add_argument("--stop-z", type=float)
    parser.add_argument("--nearby-radius", type=float, default=100.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--access-graph-output", type=Path)
    args = parser.parse_args(argv)
    values = [args.x, args.y, args.z, args.stop_x, args.stop_y, args.nearby_radius]
    if args.stop_z is not None:
        values.append(args.stop_z)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("local environment probe coordinates are invalid")
    if not 1.0 <= args.nearby_radius <= 1_000.0:
        raise ValueError("local environment nearby radius is invalid")

    binding = load_world_pack_runtime_profile(
        args.profile,
        store_root=args.store_root,
        profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
    )
    map_record = binding.pack.catalog.map_by_id(args.map_id)
    loaded = load_world_structure_index(
        args.index,
        schema_path=ROOT / "contracts" / "world-structure-index.schema.json",
        pack=binding.pack,
    )
    if int(loaded.record["map_id"]) != args.map_id:
        raise ValueError("structure index map does not match the requested map")
    query = ClientAssetNavmeshQuery(
        worker=args.worker,
        nav_root=binding.pack.nav_root,
    )
    request = {
        "map_name": map_record.internal_name,
        "start": NavPoint(args.x, args.y, args.z),
        "stop_x": args.stop_x,
        "stop_y": args.stop_y,
    }
    if args.stop_z is not None:
        request["stop_z"] = args.stop_z
    corridor = query.find_corridor(**request)
    if corridor.start_awareness is None:
        raise ValueError("Detour worker did not return local static awareness")
    awareness = build_local_environment_awareness(
        map_name=map_record.internal_name,
        observed_monotonic_s=time.monotonic(),
        position=corridor.start,
        nav_awareness=corridor.start_awareness,
        structures=loaded.spatial,
        nearby_radius_yards=args.nearby_radius,
    )
    record = awareness.to_record()
    ContractValidator(
        ROOT / "contracts" / "local-environment-awareness.schema.json"
    ).validate(record)
    if args.output is not None:
        if args.output.exists():
            raise ValueError("local environment output already exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    access_graph = None
    if args.access_graph_output is not None:
        if args.access_graph_output.exists():
            raise ValueError("structure access graph output already exists")
        access_graph = build_structure_access_graph_record(
            binding.pack,
            structure_index_record=loaded.record,
            observations=(StructureAccessObservation(
                awareness=awareness,
                nav_awareness=corridor.start_awareness,
                probe_worker_sha256=hashlib.sha256(
                    args.worker.read_bytes()
                ).hexdigest(),
            ),),
        )
        ContractValidator(
            ROOT / "contracts" / "structure-access-graph.schema.json"
        ).validate(access_graph)
        args.access_graph_output.parent.mkdir(parents=True, exist_ok=True)
        args.access_graph_output.write_text(
            json.dumps(access_graph, indent=2, ensure_ascii=False, allow_nan=False)
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps({
        "status": "VERIFIED_LOCAL_ENVIRONMENT",
        "map_id": args.map_id,
        "map_name": map_record.internal_name,
        "resolved_position": [
            corridor.start.x, corridor.start.y, corridor.start.z,
        ],
        "environment_state": awareness.environment_state,
        "environment_confidence": awareness.environment_confidence,
        "topology_complete": awareness.topology_complete,
        "containing_structure_count": len(awareness.containing_structures),
        "boundary_count": len(awareness.boundaries),
        "verified_egress_count": len(awareness.verified_egresses),
        "structure_access_opening_count": (
            len(access_graph["access_openings"]) if access_graph is not None else None
        ),
        "structure_boundary_chain_count": (
            len(access_graph["boundary_chains"]) if access_graph is not None else None
        ),
        "candidate_opening_count": len(
            awareness.candidate_opening_bearings_rad
        ),
        "nearby_wmo_count": awareness.nearby_wmo_count,
        "nearby_static_obstacle_count": awareness.nearby_static_obstacle_count,
        "corridor_complete": corridor.complete,
        "dynamic_entity_knowledge": "NONE",
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
