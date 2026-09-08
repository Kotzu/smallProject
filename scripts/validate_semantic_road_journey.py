from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
WINDOWS_INPUT = ROOT / "integrations" / "windows-input"
if str(WINDOWS_INPUT) not in sys.path:
    sys.path.insert(0, str(WINDOWS_INPUT))

from client_navmesh_backend import ClientAssetNavmeshQuery
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import NavPoint
from perfect_assassin.movement.road_semantic_planner import ClientRoadSemanticPlanner
from perfect_assassin.movement.semantic_live_gate import (
    build_semantic_live_gate_record,
    semantic_live_gate_identity,
)
from perfect_assassin.movement.semantic_navigation import validate_semantic_road_journey
from perfect_assassin.movement.world_pack_runtime import load_world_pack_runtime_profile
from perfect_assassin.runtime_paths import external_runtime_root


DEFAULT_WORKER = (
    ROOT / "data" / "runtime" / "native-build"
    / "pa_nav_probe-v34" / "Debug" / "pa_nav_probe.exe"
)
DEFAULT_WORLD_PACK_PROFILE = (
    ROOT / "config" / "navigation" / "world-pack-runtime-tbc243-azeroth-full-v3.json"
)
DEFAULT_WORLD_PACK_STORE = external_runtime_root(ROOT) / "worldpacks"
RESULT_PATH = ROOT / "data" / "runtime" / "navigation-f3b" / "semantic-road-journey-validation.json"
GATE_PATH = ROOT / "data" / "runtime" / "operator" / "movement-engine-semantic-gate.json"


CASES = (
    (
        "canonical_crypt_spawn_to_brill",
        "ARRIVE",
        NavPoint(1676.3695751699802, 1677.4669576125532, 121.67),
        2259.25,
        290.43,
    ),
    (
        "brill_to_crypt",
        "ARRIVE",
        NavPoint(2259.25, 290.43, 34.11),
        1676.3695751699802,
        1677.4669576125532,
    ),
    ("deathknell_to_brill", "ARRIVE", NavPoint(1843.55, 1589.97, 93.29), 2259.25, 290.43),
    ("brill_to_deathknell", "ARRIVE", NavPoint(2259.25, 290.43, 34.11), 1843.55, 1589.97),
    (
        "brill_to_south_road_holdout",
        "ARRIVE",
        NavPoint(2259.25, 290.43, 34.11),
        2043.75,
        285.416656,
    ),
    ("hill_fixture_requires_reset", "RESET_REQUIRED", NavPoint(2026.2765, 1224.868, 64.53), 1843.55, 1589.97),
)
CASE_NAMES = tuple(item[0] for item in CASES)


def select_validation_cases(requested: list[str]) -> tuple[tuple[object, ...], ...]:
    if len(set(requested)) != len(requested):
        raise ValueError("validation case selection contains duplicates")
    unknown = set(requested) - set(CASE_NAMES)
    if unknown:
        raise ValueError("validation case selection is unknown")
    selected = set(requested)
    return tuple(
        case for case in CASES
        if not requested or case[0] in selected
    )


def _atomic_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False,
        prefix=f".{path.name}.", suffix=".tmp",
    ) as stream:
        json.dump(record, stream, separators=(",", ":"))
        temporary = Path(stream.name)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate generated ADT-road waypoints against immutable 3D navmesh."
    )
    parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--world-pack-profile", type=Path, default=DEFAULT_WORLD_PACK_PROFILE)
    parser.add_argument("--world-pack-store", type=Path, default=DEFAULT_WORLD_PACK_STORE)
    parser.add_argument("--legacy-loose-nav-assets", action="store_true")
    parser.add_argument("--nav-root", type=Path)
    parser.add_argument("--result", type=Path, default=RESULT_PATH)
    parser.add_argument(
        "--case", action="append", choices=CASE_NAMES, default=[],
        help="run a diagnostic subset; repeat for multiple cases",
    )
    parser.add_argument("--write-offline-gate", action="store_true")
    parser.add_argument("--enable-live-authority", action="store_true")
    parser.add_argument("--acknowledge-validated-lab-movement", action="store_true")
    arguments = parser.parse_args()
    if arguments.enable_live_authority and not (
        arguments.write_offline_gate
        and arguments.acknowledge_validated_lab_movement
    ):
        parser.error(
            "live authority requires a freshly written gate and explicit LAB acknowledgement"
        )
    if arguments.case and (
        arguments.write_offline_gate or arguments.enable_live_authority
    ):
        parser.error("a diagnostic case subset cannot write a live gate")

    if arguments.legacy_loose_nav_assets:
        if arguments.nav_root is None:
            parser.error("legacy loose validation requires --nav-root")
        if arguments.write_offline_gate or arguments.enable_live_authority:
            parser.error("legacy loose nav assets cannot write a live gate")
        nav_root = arguments.nav_root.resolve()
        binding = None
    else:
        if arguments.nav_root is not None:
            parser.error("--nav-root requires --legacy-loose-nav-assets")
        binding = load_world_pack_runtime_profile(
            arguments.world_pack_profile,
            store_root=arguments.world_pack_store,
            profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
            pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
            catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
        )
        nav_root = binding.pack.nav_root

    planner = ClientRoadSemanticPlanner(sidecar_root=nav_root / "semantics")
    navigator = ClientAssetNavmeshQuery(
        worker=arguments.worker, nav_root=nav_root,
    )
    records: list[dict[str, object]] = []
    all_safe = True
    selected_cases = select_validation_cases(arguments.case)
    for name, expected, start, destination_x, destination_y in selected_cases:
        validation = validate_semantic_road_journey(
            planner=planner,
            navigator=navigator,
            map_name="Azeroth",
            start=start,
            destination_x=destination_x,
            destination_y=destination_y,
        )
        stages = [
            {
                "index": stage.index,
                "requested": [stage.requested_x, stage.requested_y],
                "stop": [stage.corridor.stop.x, stage.corridor.stop.y, stage.corridor.stop.z],
                "complete": stage.corridor.complete,
                "minimum_z": stage.minimum_z,
                "maximum_z": stage.maximum_z,
                "vertical_detour_yards": stage.vertical_detour_yards,
                "path_length_yards": stage.path_length_yards,
                "direct_distance_yards": stage.direct_distance_yards,
                "maximum_segment_grade_degrees": stage.maximum_segment_grade_degrees,
                "downhill_escape": stage.downhill_escape,
                "road_polygon_count": sum(
                    polygon.area == 1 for polygon in stage.corridor.polygons
                ),
                "steep_polygon_count": sum(
                    polygon.area == 10 for polygon in stage.corridor.polygons
                ),
                "safe": stage.safe,
                "reason": stage.reason,
            }
            for stage in validation.stages
        ]
        case_pass = (
            validation.safe
            if expected == "ARRIVE"
            else (
                not validation.safe
                and validation.reason == "partial_local_navmesh_corridor"
            )
        )
        record = {
            "name": name,
            "expected": expected,
            "case_pass": case_pass,
            "safe": validation.safe,
            "reset_required": expected == "RESET_REQUIRED" and case_pass,
            "destination_reached": validation.destination_reached,
            "reason": validation.reason,
            "semantic_waypoint_count": len(validation.route.waypoints),
            "semantic_road_cells": validation.route.road_cell_count,
            "semantic_near_road_cells": validation.route.near_road_cell_count,
            "semantic_bridge_cells": validation.route.offroad_bridge_cell_count,
            "validated_stage_count": len(stages),
            "stages": stages,
        }
        records.append(record)
        all_safe = all_safe and case_pass
        print(json.dumps({key: value for key, value in record.items() if key != "stages"}, sort_keys=True), flush=True)

    result = {
        "record_type": "semantic_road_journey_validation",
        "schema_version": "2.0",
        "status": "PASS" if all_safe else "FAIL",
        "map_name": "Azeroth",
        "runtime_world_source": "WORLD_PACK" if binding is not None else "LEGACY_LOOSE_NAV_ASSETS",
        "world_pack_profile_id": binding.profile_id if binding is not None else None,
        "world_pack_id": str(binding.pack.manifest["pack_id"]) if binding is not None else None,
        "world_pack_content_sha256": (
            str(binding.pack.manifest["content_sha256"]) if binding is not None else None
        ),
        "target_profile": binding.pack.catalog.target_profile if binding is not None else None,
        "client_version": binding.pack.catalog.client_version if binding is not None else None,
        "client_build": binding.pack.catalog.client_build if binding is not None else None,
        "nav_profile_id": binding.pack.catalog.nav_profile_id if binding is not None else None,
        "technology": [
            "exact_client_atlas", "adt_texture_semantics",
            "weighted_global_astar", "immutable_recast_detour",
        ],
        "selected_case_count": len(selected_cases),
        "full_regression_suite": len(selected_cases) == len(CASES),
        "cases": records,
        "execution_authority": False,
    }
    _atomic_json(arguments.result, result)
    if arguments.write_offline_gate:
        assert binding is not None
        identity = semantic_live_gate_identity(
            binding,
            profile_path=arguments.world_pack_profile,
            worker_path=arguments.worker,
        )
        gate = build_semantic_live_gate_record(
            identity,
            validation_result=arguments.result,
            status=str(result["status"]),
            live_authority_enabled=bool(all_safe and arguments.enable_live_authority),
        )
        ContractValidator(
            ROOT / "contracts" / "semantic-movement-live-gate.schema.json"
        ).validate(gate)
        _atomic_json(GATE_PATH, gate)
    print(json.dumps({"result_path": str(arguments.result), "status": result["status"]}, sort_keys=True))
    return 0 if all_safe else 3


if __name__ == "__main__":
    raise SystemExit(main())
