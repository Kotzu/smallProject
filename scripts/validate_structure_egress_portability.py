from __future__ import annotations

import argparse
import hashlib
import json
from math import hypot, isfinite
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "integrations" / "windows-input"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from client_navmesh_backend import ClientAssetNavmeshQuery
from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.engine import MovementEngine
from perfect_assassin.movement.local_environment_awareness import (
    LocalEnvironmentAwareness,
    StructureContainmentEvidence,
)
from perfect_assassin.movement.predictive_steering import (
    PredictiveSteeringController,
)
from perfect_assassin.movement.structure_access_graph import (
    StructureAccessSpatialGraph,
    load_structure_access_graph,
)
from perfect_assassin.movement.world_model import LayeredWorldModel
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    load_world_structure_index,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, record: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(record, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def candidate_goals_beyond_opening(
    *, start: NavPoint, opening: NavPoint,
) -> tuple[NavPoint, ...]:
    """Derive outward trials from geometry, never from a saved route."""

    dx, dy = opening.x - start.x, opening.y - start.y
    distance = hypot(dx, dy)
    if not isfinite(distance) or distance < 0.50:
        return ()
    unit_x, unit_y = dx / distance, dy / distance
    return tuple(
        NavPoint(
            opening.x + unit_x * extension,
            opening.y + unit_y * extension,
            opening.z,
        )
        for extension in (4.0, 8.0, 12.0)
    )


def _awareness_from_observation(
    *,
    map_name: str,
    observation: Mapping[str, Any],
    structure: Mapping[str, Any],
) -> LocalEnvironmentAwareness:
    position = observation["position"]
    return LocalEnvironmentAwareness(
        map_name=map_name,
        observed_monotonic_s=float(observation["observed_monotonic_s"]),
        position=NavPoint(
            float(position[0]), float(position[1]), float(position[2]),
        ),
        environment_state="INSIDE_STATIC_WMO",
        environment_confidence=0.95,
        physical_surfaces=frozenset({"wmo"}),
        topology_complete=bool(observation["topology_complete"]),
        containing_structures=(StructureContainmentEvidence(
            structure_id=str(structure["structure_id"]),
            asset_path=str(structure["asset_path"]),
            nav_coverage=str(structure["nav_coverage"]),
        ),),
        boundaries=(),
        verified_egresses=(),
        candidate_opening_bearings_rad=(),
        nearby_wmo_count=1,
        nearby_static_obstacle_count=0,
    )


def exercise_worldpack_egress(
    *,
    map_name: str,
    navmesh_sha256: str,
    graph: StructureAccessSpatialGraph,
    structure_index_record: Mapping[str, Any],
    query: ClientAssetNavmeshQuery,
    maximum_opening_trials: int = 16,
) -> dict[str, Any]:
    if not 1 <= maximum_opening_trials <= 64:
        raise ValueError("opening trial bound is invalid")
    structures = {
        str(item["structure_id"]): item
        for item in structure_index_record["structures"]
        if item["kind"] == "WMO"
    }
    observations = {
        str(item["observation_sha256"]): item
        for item in graph.record["observations"]
    }
    attempts = 0
    rejection_count = 0
    openings = sorted(
        graph.record["access_openings"], key=lambda item: item["opening_id"],
    )
    for opening_record in openings:
        if attempts >= maximum_opening_trials:
            break
        if (
            opening_record.get("execution_authority") is not False
            or float(opening_record["connected_width_yards"]) < 0.75
        ):
            continue
        for observation_sha256 in opening_record["source_observation_sha256"]:
            observation = observations.get(str(observation_sha256))
            if observation is None:
                continue
            common_structures = sorted(
                set(str(value) for value in opening_record["structure_ids"])
                & set(
                    str(value)
                    for value in observation["containing_structure_ids"]
                )
                & structures.keys()
            )
            if not common_structures:
                continue
            structure_id = common_structures[0]
            awareness = _awareness_from_observation(
                map_name=map_name,
                observation=observation,
                structure=structures[structure_id],
            )
            midpoint = opening_record["midpoint"]
            opening = NavPoint(
                float(midpoint[0]), float(midpoint[1]), float(midpoint[2]),
            )
            isolated_graph = StructureAccessSpatialGraph({
                "access_openings": [opening_record],
            })
            engine = MovementEngine(
                navigator=query,
                steering=PredictiveSteeringController(),
                world=LayeredWorldModel(
                    map_name=map_name,
                    static_navmesh_sha256=navmesh_sha256.upper(),
                ),
                structure_access=isolated_graph,
            )
            for goal in candidate_goals_beyond_opening(
                start=awareness.position, opening=opening,
            ):
                attempts += 1
                direct = NavCorridor(
                    map_name=map_name,
                    adt_x=0,
                    adt_y=0,
                    start=awareness.position,
                    stop=awareness.position,
                    points=(awareness.position,),
                    complete=False,
                    requested_stop=goal,
                )
                proposal = engine.plan_via_known_structure_egress(
                    awareness=awareness,
                    direct_corridor=direct,
                    goal_x=goal.x,
                    goal_y=goal.y,
                    goal_z=goal.z,
                )
                if proposal is None:
                    rejection_count += 1
                    if attempts >= maximum_opening_trials:
                        break
                    continue
                if proposal.opening_id != str(opening_record["opening_id"]):
                    raise ValueError("egress policy selected an unscoped opening")
                return {
                    "status": "PASS",
                    "map_name": map_name,
                    "structure_id": proposal.structure_id,
                    "opening_id": proposal.opening_id,
                    "observation_sha256": str(observation_sha256),
                    "start_world": [
                        awareness.position.x,
                        awareness.position.y,
                        awareness.position.z,
                    ],
                    "opening_world": [opening.x, opening.y, opening.z],
                    "derived_goal_world": [goal.x, goal.y, goal.z],
                    "approach_complete": proposal.approach.complete,
                    "continuation_complete": proposal.continuation.complete,
                    "direct_frontier_remaining_yards": (
                        proposal.direct_frontier_remaining_yards
                    ),
                    "continuation_frontier_remaining_yards": (
                        proposal.continuation_frontier_remaining_yards
                    ),
                    "opening_trials": attempts,
                    "rejected_trials": rejection_count,
                    "saved_route_or_coordinate_used": False,
                    "execution_authority": False,
                }
            if attempts >= maximum_opening_trials:
                break
    raise ValueError(
        f"no navmesh-revalidated structure egress for {map_name!r} "
        f"after {attempts} bounded trials"
    )


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the same standalone structure-egress policy against "
            "multiple independently sealed WorldPacks."
        )
    )
    parser.add_argument("--profile", type=Path, action="append", required=True)
    parser.add_argument("--index", type=Path, action="append", required=True)
    parser.add_argument("--graph", type=Path, action="append", required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-opening-trials", type=int, default=16)
    args = parser.parse_args(argv)
    if not (
        len(args.profile) == len(args.index) == len(args.graph)
        and len(args.profile) >= 2
    ):
        parser.error(
            "provide matching --profile/--index/--graph lists for at least "
            "two WorldPacks"
        )
    if not 1 <= args.maximum_opening_trials <= 64:
        parser.error("--maximum-opening-trials must be between 1 and 64")
    worker = args.worker.resolve()
    if not worker.is_file():
        raise ValueError("standalone nav worker is unavailable")
    if args.output.exists():
        raise ValueError("structure egress evidence output already exists")
    worker_sha256 = _sha256(worker)

    cases = []
    seen_pack_ids: set[str] = set()
    for profile_path, index_path, graph_path in zip(
        args.profile, args.index, args.graph, strict=True,
    ):
        binding = load_world_pack_runtime_profile(
            profile_path,
            store_root=args.store_root,
            profile_schema_path=(
                ROOT / "contracts" / "world-pack-runtime-profile.schema.json"
            ),
            pack_schema_path=(
                ROOT / "contracts" / "standalone-world-pack.schema.json"
            ),
            catalog_schema_path=(
                ROOT / "contracts" / "client-world-catalog.schema.json"
            ),
        )
        pack_id = str(binding.pack.manifest["pack_id"])
        if pack_id in seen_pack_ids:
            raise ValueError("egress portability requires distinct WorldPacks")
        seen_pack_ids.add(pack_id)
        dependencies = dict(binding.pack.manifest["runtime_dependencies"])
        if any(dependencies.values()):
            raise ValueError("egress portability requires standalone WorldPacks")
        verified_index = load_world_structure_index(
            index_path,
            schema_path=ROOT / "contracts" / "world-structure-index.schema.json",
            pack=binding.pack,
        )
        graph = load_structure_access_graph(
            graph_path,
            schema_path=ROOT / "contracts" / "structure-access-graph.schema.json",
            pack=binding.pack,
            structure_index_record=verified_index.record,
            expected_probe_worker_sha256=worker_sha256,
        )
        map_name = str(graph.record["map_name"])
        map_record = binding.pack.catalog.map_by_id(int(graph.record["map_id"]))
        if map_record.internal_name != map_name:
            raise ValueError("graph map identity is inconsistent")
        proof = exercise_worldpack_egress(
            map_name=map_name,
            navmesh_sha256=map_record.nav_tiles_sha256,
            graph=graph,
            structure_index_record=verified_index.record,
            query=ClientAssetNavmeshQuery(
                worker=worker, nav_root=binding.pack.nav_root,
            ),
            maximum_opening_trials=args.maximum_opening_trials,
        )
        cases.append({
            "profile_id": binding.profile_id,
            "pack_id": pack_id,
            "content_sha256": binding.pack.manifest["content_sha256"],
            "structure_index_id": verified_index.record["index_id"],
            "structure_access_graph_id": graph.record["graph_id"],
            "runtime_dependencies": dependencies,
            "proof": proof,
        })

    record = {
        "record_type": "standalone_structure_egress_portability_validation",
        "schema_version": "1.0",
        "status": "PASS",
        "worker_sha256": worker_sha256,
        "worldpacks": cases,
        "runtime_location_special_cases": [],
        "saved_routes": [],
        "execution_authority": False,
    }
    _atomic_write_json(args.output, record)
    print(json.dumps({
        "status": "PASS",
        "worldpack_count": len(cases),
        "maps": [item["proof"]["map_name"] for item in cases],
        "output": str(args.output.resolve()),
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
