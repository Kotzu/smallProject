from __future__ import annotations

import argparse
import hashlib
import json
from math import isfinite
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.structure_access_graph import (
    load_structure_access_graph,
)
from perfect_assassin.movement.semantic_live_gate import semantic_live_gate_identity
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    StructureAwarenessHit,
    load_world_structure_index,
)


def _emit(record: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(record, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _hit_record(hit: StructureAwarenessHit) -> dict[str, object]:
    item = hit.structure
    return {
        "structure_id": item.structure_id,
        "kind": item.kind,
        "asset_path": item.asset_path,
        "nav_coverage": item.nav_coverage,
        "horizontal_distance_yards": hit.horizontal_distance_yards,
        "vertical_distance_yards": hit.vertical_distance_yards,
        "contains_horizontal": hit.contains_horizontal,
        "contains_3d": hit.contains_3d,
    }


def build_nearby_response(
    *,
    request_id: str,
    hits: tuple[StructureAwarenessHit, ...],
    include_hits: bool,
) -> dict[str, object]:
    containing = tuple(
        hit for hit in hits
        if hit.contains_horizontal and hit.contains_3d is not False
    )
    inside_wmo = next(
        (hit for hit in containing if hit.structure.kind == "WMO"), None,
    )
    return {
        "event": "NEARBY",
        "request_id": request_id,
        "wmo_count": sum(hit.structure.kind == "WMO" for hit in hits),
        "obstacle_count": sum(hit.structure.kind == "DOODAD" for hit in hits),
        "full_nav_count": sum(
            hit.structure.nav_coverage == "FULL" for hit in hits
        ),
        "partial_nav_count": sum(
            hit.structure.nav_coverage == "PARTIAL" for hit in hits
        ),
        "no_nav_count": sum(
            hit.structure.nav_coverage == "NONE" for hit in hits
        ),
        "inside_wmo_asset": (
            None if inside_wmo is None else inside_wmo.structure.asset_path
        ),
        "hits": [_hit_record(hit) for hit in hits] if include_hits else [],
        "execution_authority": False,
    }


def _finite_number(value: Any, *, field: str) -> float:
    if not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ValueError(f"{field} must be one finite number")
    return float(value)


def _serve(awareness) -> None:
    for raw_line in sys.stdin:
        request: object = None
        try:
            request = json.loads(raw_line)
            if not isinstance(request, dict):
                raise ValueError("request must be one object")
            request_id = request.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("request_id is required")
            command = request.get("command")
            if command == "SHUTDOWN":
                _emit({
                    "event": "STOPPED",
                    "request_id": request_id,
                    "execution_authority": False,
                })
                return
            if command != "NEARBY":
                raise ValueError("command is not supported")
            x = _finite_number(request.get("x"), field="x")
            y = _finite_number(request.get("y"), field="y")
            z_value = request.get("z")
            z = None if z_value is None else _finite_number(z_value, field="z")
            radius = _finite_number(
                request.get("radius_yards", 100.0), field="radius_yards",
            )
            if not 0.0 <= radius <= 1_000.0:
                raise ValueError("radius_yards is outside the supported range")
            include_hits = request.get("include_hits", False)
            if not isinstance(include_hits, bool):
                raise ValueError("include_hits must be boolean")
            hits = awareness.spatial.nearby(x=x, y=y, z=z, radius_yards=radius)
            _emit(build_nearby_response(
                request_id=request_id,
                hits=hits,
                include_hits=include_hits,
            ))
        except Exception as error:
            _emit({
                "event": "ERROR",
                "request_id": (
                    request.get("request_id")
                    if isinstance(request, dict)
                    and isinstance(request.get("request_id"), str)
                    else "unknown"
                ),
                "detail": f"{type(error).__name__}: {error}",
                "execution_authority": False,
            })


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone read-only WorldPack structure-awareness service."
    )
    parser.add_argument("--world-pack-profile", type=Path, required=True)
    parser.add_argument("--world-pack-store", type=Path, required=True)
    parser.add_argument("--world-structure-index", type=Path, required=True)
    parser.add_argument("--structure-access-graph", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--navigation-worker", type=Path,
                        help="Planner artifact for the movement gate; --worker still validates graph provenance")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        binding = load_world_pack_runtime_profile(
            args.world_pack_profile,
            store_root=args.world_pack_store,
            profile_schema_path=ROOT
            / "contracts" / "world-pack-runtime-profile.schema.json",
            pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
            catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
        )
        awareness = load_world_structure_index(
            args.world_structure_index,
            schema_path=ROOT / "contracts" / "world-structure-index.schema.json",
            pack=binding.pack,
        )
        graph = load_structure_access_graph(
            args.structure_access_graph,
            schema_path=ROOT / "contracts" / "structure-access-graph.schema.json",
            pack=binding.pack,
            structure_index_record=awareness.record,
            expected_probe_worker_sha256=hashlib.sha256(
                args.worker.read_bytes()
            ).hexdigest(),
        )
        gate_identity = semantic_live_gate_identity(
            binding,
            profile_path=args.world_pack_profile,
            worker_path=args.navigation_worker or args.worker,
        )
    except Exception as error:
        _emit({
            "event": "ERROR",
            "request_id": "startup",
            "detail": f"{type(error).__name__}: {error}",
            "execution_authority": False,
        })
        return 1
    index_record = awareness.record
    graph_record = graph.record
    _emit({
        "event": "READY",
        "world_pack_id": str(binding.pack.manifest["pack_id"]),
        "world_pack_content_sha256": str(binding.pack.manifest["content_sha256"]),
        "structure_index_id": str(index_record["index_id"]),
        "structure_index_sha256": str(graph_record["structure_index_sha256"]),
        "structure_count": int(index_record["structure_count"]),
        "wmo_count": int(index_record["wmo_count"]),
        "doodad_count": int(index_record["doodad_count"]),
        "graph_id": str(graph_record["graph_id"]),
        "graph_content_sha256": str(graph_record["content_sha256"]),
        "access_opening_count": len(graph_record["access_openings"]),
        "semantic_gate_identity": {
            field: getattr(gate_identity, field)
            for field in gate_identity.__dataclass_fields__
        },
        "execution_authority": False,
    })
    _serve(awareness)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
