from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "integrations" / "windows-input"))

from client_navmesh_backend import ClientAssetNavmeshQuery
from persistent_navmesh_awareness import PersistentNavmeshAwarenessService

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import (
    ClientNavmeshError,
    NavCorridor,
)
from perfect_assassin.movement.mppi_steering import (
    MppiConfiguration,
    MppiSteeringController,
)
from perfect_assassin.movement.steering_simulation import (
    simulate_steering_batch,
    steering_run_passes_quality,
)
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_steering_corpus import (
    WorldSteeringCourseRequest,
    build_world_steering_course_requests,
    build_world_steering_scenario,
    classify_world_corridor_risk,
    simulation_runs_for_risk,
)

DEFAULT_WORKER = (
    ROOT / "data" / "runtime" / "native-build" / "pa_nav_probe-v34"
    / "Debug" / "pa_nav_probe.exe"
)
CORPUS_SCHEMA = ROOT / "contracts" / "world-steering-corpus-report.schema.json"
MAX_CHECKPOINT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _QueryResult:
    request: WorldSteeringCourseRequest
    corridor: NavCorridor | None
    state: str
    detail: str | None


def _query_course(
    item: tuple[WorldSteeringCourseRequest, Path, Path, float],
) -> _QueryResult:
    request, worker, nav_root, timeout_seconds = item
    try:
        corridor = ClientAssetNavmeshQuery(
            worker=worker,
            nav_root=nav_root,
            timeout_seconds=timeout_seconds,
        ).find_corridor(
            map_name=request.map_name,
            start=request.start,
            stop_x=request.stop.x,
            stop_y=request.stop.y,
            stop_z=request.stop.z,
        )
    except (ClientNavmeshError, OSError, TimeoutError) as error:
        return _QueryResult(request, None, "QUERY_FAILED", str(error)[-512:])
    if not corridor.complete:
        return _QueryResult(
            request, corridor, "PARTIAL_CORRIDOR",
            "Detour did not reach the requested local endpoint",
        )
    try:
        build_world_steering_scenario(request, corridor, runs=100)
    except ValueError as error:
        return _QueryResult(request, corridor, "INELIGIBLE_CORRIDOR", str(error))
    return _QueryResult(request, corridor, "RESOLVED", None)


def _query_partition(
    item: tuple[
        tuple[tuple[WorldSteeringCourseRequest, ...], ...],
        Path,
        Path,
        str,
        float,
        int,
    ],
) -> tuple[_QueryResult, ...]:
    (
        tile_request_groups,
        worker,
        nav_root,
        map_name,
        timeout_seconds,
        corridors_per_tile,
    ) = item
    results: list[_QueryResult] = []
    service = PersistentNavmeshAwarenessService(
        worker=worker, nav_root=nav_root, map_name=map_name,
    )
    try:
        for requests in tile_request_groups:
            resolved = 0
            for request in requests:
                try:
                    start = service.sample(
                        request.start.x, request.start.y, request.start.z,
                    ).resolved
                    stop = service.sample(
                        request.stop.x, request.stop.y, start.z,
                    ).resolved
                except RuntimeError as error:
                    results.append(_QueryResult(
                        request, None, "ENDPOINT_UNAVAILABLE", str(error)[-512:],
                    ))
                    continue
                resolved_request = replace(request, start=start, stop=stop)
                result = _query_course((
                    resolved_request, worker, nav_root, timeout_seconds,
                ))
                results.append(result)
                if result.state == "RESOLVED":
                    resolved += 1
                    if resolved >= corridors_per_tile:
                        break
    finally:
        service.close()
    return tuple(results)


def _stable_seed(request_id: str) -> int:
    return int.from_bytes(
        hashlib.sha256(request_id.encode("utf-8")).digest()[:4], "little",
    )


def _simulate_course(
    item: tuple[
        WorldSteeringCourseRequest,
        NavCorridor,
        int,
        int,
        int,
        str,
        int,
        int,
        int,
    ],
) -> dict[str, Any]:
    (
        request,
        corridor,
        base_runs,
        risk_runs,
        extreme_runs,
        controller_id,
        mppi_batch_size,
        mppi_time_steps,
        mppi_replan_interval_ticks,
    ) = item
    risk = classify_world_corridor_risk(corridor)
    runs = simulation_runs_for_risk(
        risk,
        base_runs=base_runs,
        risk_runs=risk_runs,
        extreme_runs=extreme_runs,
    )
    scenario = build_world_steering_scenario(request, corridor, runs=runs)
    controller_factory = None
    if controller_id == "pa_mppi_v1":
        controller_factory = partial(
            MppiSteeringController,
            configuration=MppiConfiguration(
                batch_size=mppi_batch_size,
                time_steps=mppi_time_steps,
            ),
            replan_interval_ticks=mppi_replan_interval_ticks,
        )
    elif controller_id != "geometric_predictive_v1":
        raise ValueError("world steering controller is invalid")
    simulation_arguments: dict[str, Any] = {
        "seed_offset": _stable_seed(request.request_id),
    }
    if controller_factory is not None:
        simulation_arguments["controller_factory"] = controller_factory
    summary, trials = simulate_steering_batch(scenario, **simulation_arguments)
    quality_failures = [
        {
            "trial_index": index,
            **asdict(trial),
        }
        for index, trial in enumerate(trials)
        if not steering_run_passes_quality(scenario, trial)
    ][:20]
    return {
        "request_id": request.request_id,
        "map_id": request.map_id,
        "map_name": request.map_name,
        "grid_x": request.grid_x,
        "grid_y": request.grid_y,
        "resolved_start": asdict(corridor.start),
        "resolved_stop": asdict(corridor.stop),
        "guidance_point_count": len(corridor.guidance_points()),
        "polygon_count": len(corridor.polygons),
        "portal_count": len(corridor.portals),
        "replay_geometry": {
            "raw_points": [asdict(point) for point in corridor.points],
            "guidance_points": [
                asdict(point) for point in corridor.guidance_points()
            ],
            "polygons": [
                {
                    "index": polygon.index,
                    "area": polygon.area,
                    "polygon_type": polygon.polygon_type,
                    "slope_degrees": polygon.slope_degrees,
                    "centroid": asdict(polygon.centroid),
                    "vertices": [asdict(point) for point in polygon.vertices],
                    "physical_surfaces": sorted(polygon.physical_surfaces),
                }
                for polygon in corridor.polygons
            ],
            "portals": [asdict(portal) for portal in corridor.portals],
            "steering_attributes": {
                "doodad_avoidance_applied": corridor.doodad_avoidance_applied,
                "doodad_detour_count": corridor.doodad_detour_count,
                "clearance_inset_count": corridor.clearance_inset_count,
            },
        },
        "risk": asdict(risk),
        "quality_limits": {
            "maximum_cross_track_world": scenario.maximum_allowed_cross_track_world,
            "maximum_pivot_fraction": scenario.maximum_allowed_pivot_fraction,
            "maximum_steering_sign_changes": (
                scenario.maximum_allowed_steering_sign_changes
            ),
        },
        "summary": asdict(summary),
        "sample_quality_failures": quality_failures,
    }


def _atomic_write_json(path: Path, record: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(path.suffix + ".partial")
    staging.write_text(
        json.dumps(
            record,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=False,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    staging.replace(path)


def _policy_record(
    arguments: argparse.Namespace,
    *,
    tile_limit: int | None,
) -> dict[str, Any]:
    controller_configuration = None
    if arguments.controller_id == "pa_mppi_v1":
        implementation_path = (
            ROOT / "src" / "perfect_assassin" / "movement" / "mppi_steering.py"
        )
        controller_configuration = {
            "configuration_id": "pa-mppi-v1-default-critics",
            "implementation_sha256": hashlib.sha256(
                implementation_path.read_bytes(),
            ).hexdigest(),
            "batch_size": arguments.mppi_batch_size,
            "time_steps": arguments.mppi_time_steps,
            "replan_interval_ticks": arguments.mppi_replan_interval_ticks,
        }
    return {
        "course_generator": "uniform-adt-local-patterns-v1",
        "runner_implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes(),
        ).hexdigest(),
        "contract_sha256": hashlib.sha256(
            (
                ROOT / "contracts" / "world-steering-corpus-report.schema.json"
            ).read_bytes(),
        ).hexdigest(),
        "controller_id": arguments.controller_id,
        "controller_configuration": controller_configuration,
        "candidate_patterns_per_tile": arguments.candidate_patterns_per_tile,
        "corridors_per_tile": arguments.corridors_per_tile,
        "base_runs": arguments.base_runs,
        "risk_runs": arguments.risk_runs,
        "extreme_runs": arguments.extreme_runs,
        "tile_limit": tile_limit,
    }


def _world_pack_record(binding: Any, world_map: Any) -> dict[str, Any]:
    return {
        "profile_id": binding.profile_id,
        "pack_id": binding.pack.manifest["pack_id"],
        "content_sha256": binding.pack.manifest["content_sha256"],
        "catalog_id": binding.pack.catalog.catalog_id,
        "client_version": binding.pack.catalog.client_version,
        "client_build": binding.pack.catalog.client_build,
        "map_id": world_map.map_id,
        "map_name": world_map.internal_name,
    }


def _tile_checkpoint_path(
    directory: Path,
    *,
    map_name: str,
    grid_x: int,
    grid_y: int,
) -> Path:
    if not map_name or not map_name.replace("_", "").isalnum():
        raise ValueError("map name is unsafe for a checkpoint path")
    root = directory.resolve()
    path = (root / map_name / f"{grid_x:02d}_{grid_y:02d}.json").resolve()
    if root not in path.parents:
        raise ValueError("checkpoint path escaped its directory")
    return path


def _tile_report(
    *,
    world_pack: dict[str, Any],
    policy: dict[str, Any],
    catalog_tile_count: int,
    grid_x: int,
    grid_y: int,
    query_results: tuple[_QueryResult, ...],
    simulation_results: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    query_failures = [
        {
            "request_id": item.request.request_id,
            "grid_x": item.request.grid_x,
            "grid_y": item.request.grid_y,
            "state": item.state,
            "detail": item.detail,
        }
        for item in query_results if item.state != "RESOLVED"
    ]
    simulated_tiles = {
        (int(item["grid_x"]), int(item["grid_y"]))
        for item in simulation_results
    }
    if simulated_tiles - {(grid_x, grid_y)} or any(
        (item.request.grid_x, item.request.grid_y) != (grid_x, grid_y)
        for item in query_results
    ):
        raise ValueError("tile checkpoint mixes ADT coordinates")
    return {
        "record_type": "world_steering_corpus_report",
        "schema_version": "1.0",
        "execution_authority": False,
        "world_pack": world_pack,
        "policy": {**policy, "tile_limit": 1},
        "coverage": {
            "catalog_tile_count": catalog_tile_count,
            "selected_tile_count": 1,
            "available_candidate_request_count": int(
                policy["candidate_patterns_per_tile"]
            ),
            "attempted_request_count": len(query_results),
            "resolved_complete_corridor_count": sum(
                item.state == "RESOLVED" for item in query_results
            ),
            "simulated_corridor_count": len(simulation_results),
            "simulated_tile_count": len(simulated_tiles),
            "query_or_eligibility_failure_count": len(query_failures),
            "quality_failed_corridor_count": sum(
                int(item["summary"]["quality_passed_runs"])
                != int(item["summary"]["runs"])
                for item in simulation_results
            ),
            "total_simulated_trials": sum(
                int(item["summary"]["runs"])
                for item in simulation_results
            ),
        },
        "query_failures": query_failures,
        "corridors": list(simulation_results),
    }


def _checkpoint_matches(
    record: dict[str, Any],
    *,
    world_pack: dict[str, Any],
    policy: dict[str, Any],
    grid_x: int,
    grid_y: int,
) -> bool:
    if record.get("world_pack") != world_pack:
        return False
    actual_policy = record.get("policy")
    if not isinstance(actual_policy, dict):
        return False
    for field, expected in policy.items():
        if field != "tile_limit" and actual_policy.get(field) != expected:
            return False
    coordinates = {
        (int(item["grid_x"]), int(item["grid_y"]))
        for key in ("query_failures", "corridors")
        for item in record.get(key, [])
    }
    if coordinates and coordinates != {(grid_x, grid_y)}:
        raise ValueError("checkpoint contains another ADT")
    coverage = record.get("coverage", {})
    return (
        coverage.get("selected_tile_count") == 1
        and coverage.get("available_candidate_request_count")
        == policy["candidate_patterns_per_tile"]
    )


def _load_checkpoint(
    path: Path,
    *,
    validator: ContractValidator,
    world_pack: dict[str, Any],
    policy: dict[str, Any],
    grid_x: int,
    grid_y: int,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    if path.stat().st_size > MAX_CHECKPOINT_BYTES:
        raise ValueError(f"steering checkpoint is oversized: {path}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read steering checkpoint: {path}") from error
    if not isinstance(record, dict):
        raise TypeError(f"steering checkpoint root is invalid: {path}")
    if not _checkpoint_matches(
        record,
        world_pack=world_pack,
        policy=policy,
        grid_x=grid_x,
        grid_y=grid_y,
    ):
        return None
    validator.validate(record)
    return record


def _aggregate_tile_reports(
    *,
    world_pack: dict[str, Any],
    policy: dict[str, Any],
    catalog_tile_count: int,
    selected_tile_count: int,
    available_candidate_request_count: int,
    tile_reports: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    query_failures = sorted(
        (
            item
            for report in tile_reports
            for item in report["query_failures"]
        ),
        key=lambda item: str(item["request_id"]),
    )
    corridors = sorted(
        (
            item
            for report in tile_reports
            for item in report["corridors"]
        ),
        key=lambda item: str(item["request_id"]),
    )
    coverage_rows = tuple(report["coverage"] for report in tile_reports)
    return {
        "record_type": "world_steering_corpus_report",
        "schema_version": "1.0",
        "execution_authority": False,
        "world_pack": world_pack,
        "policy": policy,
        "coverage": {
            "catalog_tile_count": catalog_tile_count,
            "selected_tile_count": selected_tile_count,
            "available_candidate_request_count": available_candidate_request_count,
            "attempted_request_count": sum(
                int(item["attempted_request_count"]) for item in coverage_rows
            ),
            "resolved_complete_corridor_count": sum(
                int(item["resolved_complete_corridor_count"])
                for item in coverage_rows
            ),
            "simulated_corridor_count": len(corridors),
            "simulated_tile_count": len({
                (int(item["grid_x"]), int(item["grid_y"]))
                for item in corridors
            }),
            "query_or_eligibility_failure_count": len(query_failures),
            "quality_failed_corridor_count": sum(
                int(item["summary"]["quality_passed_runs"])
                != int(item["summary"]["runs"])
                for item in corridors
            ),
            "total_simulated_trials": sum(
                int(item["summary"]["runs"]) for item in corridors
            ),
        },
        "query_failures": query_failures,
        "corridors": corridors,
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve real WorldPack corridors across one complete client map "
            "and exercise the production steering controller deterministically."
        ),
    )
    parser.add_argument("--world-pack-profile", type=Path, required=True)
    parser.add_argument("--world-pack-store", type=Path, required=True)
    parser.add_argument("--map-name", required=True)
    parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--candidate-patterns-per-tile", type=int, default=50)
    parser.add_argument("--corridors-per-tile", type=int, default=1)
    parser.add_argument("--base-runs", type=int, default=100)
    parser.add_argument("--risk-runs", type=int, default=1_000)
    parser.add_argument("--extreme-runs", type=int, default=10_000)
    parser.add_argument(
        "--controller-id",
        choices=("geometric_predictive_v1", "pa_mppi_v1"),
        default="geometric_predictive_v1",
    )
    parser.add_argument("--mppi-batch-size", type=int, default=256)
    parser.add_argument("--mppi-time-steps", type=int, default=56)
    parser.add_argument("--mppi-replan-interval-ticks", type=int, default=4)
    parser.add_argument("--query-jobs", type=int, default=4)
    parser.add_argument("--simulation-jobs", type=int, default=4)
    parser.add_argument("--query-timeout-seconds", type=float, default=10.0)
    parser.add_argument(
        "--tile-limit", type=int,
        help="Bounded deterministic smoke subset; omission means the full map.",
    )
    parser.add_argument(
        "--tile", action="append", default=[], metavar="GRID_X,GRID_Y",
        help="Select an exact catalog ADT for a bounded smoke run; repeatable.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--checkpoint-directory",
        type=Path,
        help=(
            "Atomically persist one schema-valid report per ADT so a full-map "
            "run can resume without repeating completed simulations."
        ),
    )
    arguments = parser.parse_args()
    if not 1 <= arguments.candidate_patterns_per_tile <= 50:
        parser.error("--candidate-patterns-per-tile must be between one and fifty")
    if not 1 <= arguments.corridors_per_tile <= 4:
        parser.error("--corridors-per-tile must be between one and four")
    if arguments.corridors_per_tile > arguments.candidate_patterns_per_tile:
        parser.error("--corridors-per-tile exceeds available candidate patterns")
    if not 1 <= arguments.query_jobs <= 8:
        parser.error("--query-jobs must be between one and eight")
    if not 1 <= arguments.simulation_jobs <= 8:
        parser.error("--simulation-jobs must be between one and eight")
    if not 0.1 <= arguments.query_timeout_seconds <= 10.0:
        parser.error("--query-timeout-seconds must be between 0.1 and 10")
    if not 32 <= arguments.mppi_batch_size <= 20_000:
        parser.error("--mppi-batch-size must be between 32 and 20000")
    if not 12 <= arguments.mppi_time_steps <= 160:
        parser.error("--mppi-time-steps must be between 12 and 160")
    if not 1 <= arguments.mppi_replan_interval_ticks <= 20:
        parser.error("--mppi-replan-interval-ticks must be between one and twenty")
    if arguments.tile_limit is not None and arguments.tile_limit < 1:
        parser.error("--tile-limit must be positive")
    selected_tiles = []
    for raw_tile in arguments.tile:
        try:
            grid_x, grid_y = (int(value) for value in raw_tile.split(","))
        except (TypeError, ValueError):
            parser.error("--tile must use GRID_X,GRID_Y")
        if not 0 <= grid_x <= 63 or not 0 <= grid_y <= 63:
            parser.error("--tile coordinates must be between zero and 63")
        selected_tiles.append((grid_x, grid_y))
    arguments.tile = tuple(selected_tiles)
    if arguments.tile and arguments.tile_limit is not None:
        parser.error("--tile and --tile-limit cannot be combined")
    if not (
        100 <= arguments.base_runs <= arguments.risk_runs
        <= arguments.extreme_runs <= 100_000
    ):
        parser.error(
            "simulation run counts must satisfy "
            "100 <= base <= risk <= extreme <= 100000"
        )
    return arguments


def main() -> int:
    arguments = _arguments()
    validator = ContractValidator(CORPUS_SCHEMA)
    binding = load_world_pack_runtime_profile(
        arguments.world_pack_profile,
        store_root=arguments.world_pack_store,
        profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
    )
    world_map = binding.pack.catalog.map_by_internal_name(arguments.map_name)
    world_pack = _world_pack_record(binding, world_map)
    policy = _policy_record(arguments, tile_limit=arguments.tile_limit)
    requests = build_world_steering_course_requests(
        world_map,
        courses_per_tile=arguments.candidate_patterns_per_tile,
    )
    if arguments.tile_limit is not None:
        selected_tiles = sorted({
            (item.grid_x, item.grid_y) for item in requests
        })[:arguments.tile_limit]
        selected = set(selected_tiles)
        requests = tuple(
            item for item in requests
            if (item.grid_x, item.grid_y) in selected
        )
    if arguments.tile:
        available = {(item.grid_x, item.grid_y) for item in requests}
        missing = set(arguments.tile) - available
        if missing:
            raise ValueError(f"selected tiles are absent from the catalog: {sorted(missing)}")
        selected = set(arguments.tile)
        requests = tuple(
            item for item in requests
            if (item.grid_x, item.grid_y) in selected
        )
    grouped_requests: dict[
        tuple[int, int], list[WorldSteeringCourseRequest]
    ] = {}
    for request in requests:
        grouped_requests.setdefault(
            (request.grid_x, request.grid_y), [],
        ).append(request)
    cached_reports: dict[tuple[int, int], dict[str, Any]] = {}
    fresh_groups: dict[
        tuple[int, int], tuple[WorldSteeringCourseRequest, ...]
    ] = {}
    for tile, tile_requests in sorted(grouped_requests.items()):
        checkpoint = None
        if arguments.checkpoint_directory is not None:
            checkpoint_path = _tile_checkpoint_path(
                arguments.checkpoint_directory,
                map_name=arguments.map_name,
                grid_x=tile[0],
                grid_y=tile[1],
            )
            checkpoint = _load_checkpoint(
                checkpoint_path,
                validator=validator,
                world_pack=world_pack,
                policy=policy,
                grid_x=tile[0],
                grid_y=tile[1],
            )
        if checkpoint is None:
            fresh_groups[tile] = tuple(tile_requests)
        else:
            cached_reports[tile] = checkpoint
    print(json.dumps({
        "phase": "RESUME_SCAN",
        "selected_tiles": len(grouped_requests),
        "checkpoint_hits": len(cached_reports),
        "tiles_to_query": len(fresh_groups),
    }, sort_keys=True))
    ordered_groups = tuple(fresh_groups.values())
    partitions = tuple(
        tuple(ordered_groups[index::arguments.query_jobs])
        for index in range(min(arguments.query_jobs, len(ordered_groups)))
        if ordered_groups[index::arguments.query_jobs]
    )
    query_inputs = tuple(
        (
            partition,
            arguments.worker,
            binding.pack.nav_root,
            arguments.map_name,
            arguments.query_timeout_seconds,
            arguments.corridors_per_tile,
        )
        for partition in partitions
    )
    if query_inputs:
        with ThreadPoolExecutor(max_workers=len(partitions)) as executor:
            query_results = tuple(sorted(
                (
                    result
                    for partition_results in executor.map(
                        _query_partition, query_inputs,
                    )
                    for result in partition_results
                ),
                key=lambda item: item.request.request_id,
            ))
    else:
        query_results = ()
    print(json.dumps({
        "phase": "QUERY_COMPLETE",
        "attempts": len(query_results),
        "resolved_corridors": sum(
            item.state == "RESOLVED" for item in query_results
        ),
    }, sort_keys=True))
    query_by_tile: dict[tuple[int, int], list[_QueryResult]] = {
        tile: [] for tile in fresh_groups
    }
    for item in query_results:
        query_by_tile[(item.request.grid_x, item.request.grid_y)].append(item)
    resolved = tuple(
        item for item in query_results
        if item.state == "RESOLVED" and item.corridor is not None
    )
    simulation_inputs = tuple(
        (
            item.request,
            item.corridor,
            arguments.base_runs,
            arguments.risk_runs,
            arguments.extreme_runs,
            arguments.controller_id,
            arguments.mppi_batch_size,
            arguments.mppi_time_steps,
            arguments.mppi_replan_interval_ticks,
        )
        for item in resolved
    )
    expected_by_tile: dict[tuple[int, int], int] = {}
    for item in resolved:
        tile = (item.request.grid_x, item.request.grid_y)
        expected_by_tile[tile] = expected_by_tile.get(tile, 0) + 1
    simulations_by_tile: dict[
        tuple[int, int], list[dict[str, Any]]
    ] = {tile: [] for tile in expected_by_tile}
    fresh_reports: dict[tuple[int, int], dict[str, Any]] = {}

    def persist_tile(tile: tuple[int, int]) -> None:
        tile_record = _tile_report(
            world_pack=world_pack,
            policy=policy,
            catalog_tile_count=len(world_map.tiles),
            grid_x=tile[0],
            grid_y=tile[1],
            query_results=tuple(query_by_tile[tile]),
            simulation_results=tuple(sorted(
                simulations_by_tile.get(tile, []),
                key=lambda item: str(item["request_id"]),
            )),
        )
        validator.validate(tile_record)
        fresh_reports[tile] = tile_record
        if arguments.checkpoint_directory is not None:
            _atomic_write_json(
                _tile_checkpoint_path(
                    arguments.checkpoint_directory,
                    map_name=arguments.map_name,
                    grid_x=tile[0],
                    grid_y=tile[1],
                ),
                tile_record,
            )

    for tile in fresh_groups:
        if tile not in expected_by_tile:
            persist_tile(tile)

    completed_simulations = 0

    def accept_simulation(result: dict[str, Any]) -> None:
        nonlocal completed_simulations
        tile = (int(result["grid_x"]), int(result["grid_y"]))
        simulations_by_tile[tile].append(result)
        completed_simulations += 1
        if len(simulations_by_tile[tile]) == expected_by_tile[tile]:
            persist_tile(tile)
        if completed_simulations % 25 == 0:
            print(json.dumps({
                "phase": "SIMULATION_PROGRESS",
                "completed_corridors": completed_simulations,
                "total_corridors": len(simulation_inputs),
            }, sort_keys=True))

    if arguments.simulation_jobs == 1:
        for result in map(_simulate_course, simulation_inputs):
            accept_simulation(result)
    elif simulation_inputs:
        with ProcessPoolExecutor(
            max_workers=arguments.simulation_jobs,
            max_tasks_per_child=16,
        ) as executor:
            for result in executor.map(_simulate_course, simulation_inputs):
                accept_simulation(result)

    tile_reports = tuple(
        (cached_reports | fresh_reports)[tile]
        for tile in sorted(grouped_requests)
    )
    record = _aggregate_tile_reports(
        world_pack=world_pack,
        policy=policy,
        catalog_tile_count=len(world_map.tiles),
        selected_tile_count=len(grouped_requests),
        available_candidate_request_count=len(requests),
        tile_reports=tile_reports,
    )
    validator.validate(record)
    _atomic_write_json(arguments.output, record)
    print(json.dumps(record["coverage"], indent=2, sort_keys=True))
    return 0 if record["corridors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
