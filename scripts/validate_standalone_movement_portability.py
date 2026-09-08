from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from math import pi, tau
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "integrations" / "windows-input"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from client_navmesh_backend import ClientAssetNavmeshQuery
from perfect_assassin.movement.client_navmesh import (
    ClientNavmeshError,
    LocalStaticAwareness,
    NavCorridor,
    NavPoint,
)
from perfect_assassin.movement.client_world_catalog import ClientWorldMap
from perfect_assassin.movement.dynamic_avoidance import (
    DynamicCollisionAvoidance,
    DynamicEntityTracker,
    ScreenEntityObservation,
)
from perfect_assassin.movement.predictive_steering import SteeringIntent
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    build_world_structure_index_record,
)


ADT_SIZE_YARDS = 533.0 + (1.0 / 3.0)
MINIMUM_SIDE_CLEARANCE_YARDS = 1.50


@dataclass(frozen=True, slots=True)
class ProbeCandidate:
    """One map-derived probe seed; never an executable route or waypoint."""

    source: str
    position: NavPoint


@dataclass(frozen=True, slots=True)
class ResolvedProbe:
    candidate: ProbeCandidate
    corridor: NavCorridor
    attempts: int


def _evenly_spaced(values: tuple[Any, ...], maximum: int) -> tuple[Any, ...]:
    if maximum < 1:
        raise ValueError("sample bound must be positive")
    if len(values) <= maximum:
        return values
    if maximum == 1:
        return (values[len(values) // 2],)
    indices = {
        round(index * (len(values) - 1) / (maximum - 1))
        for index in range(maximum)
    }
    return tuple(values[index] for index in sorted(indices))


def _tile_position(
    *, grid_x: int, grid_y: int, fraction_x: float, fraction_y: float, z: float,
) -> NavPoint:
    """Convert ADT indices to the client world frame used by the nav worker."""
    if not 0.0 < fraction_x < 1.0 or not 0.0 < fraction_y < 1.0:
        raise ValueError("tile probe fraction is invalid")
    return NavPoint(
        (32.0 - (grid_y + fraction_y)) * ADT_SIZE_YARDS,
        (32.0 - (grid_x + fraction_x)) * ADT_SIZE_YARDS,
        z,
    )


def build_probe_candidates(
    map_record: ClientWorldMap,
    structure_record: Mapping[str, Any],
    *,
    maximum_candidates: int,
) -> tuple[ProbeCandidate, ...]:
    """Derive bounded probe seeds from immutable map geometry and nav tiles.

    Large WMO bounds are sampled first because tile centres can fall between
    floors in an interior map.  Outdoor coverage then uses a deterministic,
    evenly distributed tile sample.  No map name or world coordinate affects
    the strategy.
    """
    if not 8 <= maximum_candidates <= 512:
        raise ValueError("portability probe bound is invalid")
    if int(structure_record.get("map_id", -1)) != map_record.map_id:
        raise ValueError("structure record does not match the map")
    if str(structure_record.get("map_name", "")) != map_record.internal_name:
        raise ValueError("structure record map name is inconsistent")

    candidates: list[ProbeCandidate] = []
    seen: set[tuple[int, int, int]] = set()

    def append(source: str, point: NavPoint) -> None:
        key = (
            round(point.x * 1_000),
            round(point.y * 1_000),
            round(point.z * 1_000),
        )
        if key not in seen:
            seen.add(key)
            candidates.append(ProbeCandidate(source, point))

    wmos = tuple(sorted(
        (
            item for item in structure_record.get("structures", ())
            if item.get("kind") == "WMO"
            and item.get("nav_coverage") in {"FULL", "PARTIAL", "GLOBAL_WMO"}
        ),
        key=lambda item: (
            -float(item["horizontal_radius_yards"]),
            str(item["structure_id"]),
        ),
    ))
    for item in _evenly_spaced(wmos, min(24, len(wmos) or 1)) if wmos else ():
        bounds = item["bounds"]
        minimum = bounds["min"]
        maximum = bounds["max"]
        centre = item["center"]
        min_x = float(minimum["x"])
        min_y = float(minimum["y"])
        min_z = float(minimum["z"])
        max_x = float(maximum["x"])
        max_y = float(maximum["y"])
        max_z = float(maximum["z"])
        centre_x = float(centre["x"])
        centre_y = float(centre["y"])
        z_values = (
            float(centre["z"]),
            min_z + (max_z - min_z) * 0.25,
            min_z + (max_z - min_z) * 0.75,
        )
        xy_values = (
            (centre_x, centre_y),
            (min_x + (max_x - min_x) * 0.35, centre_y),
            (min_x + (max_x - min_x) * 0.65, centre_y),
            (centre_x, min_y + (max_y - min_y) * 0.35),
            (centre_x, min_y + (max_y - min_y) * 0.65),
        )
        for x, y in xy_values:
            for z in z_values:
                append("WORLD_STRUCTURE_WMO", NavPoint(x, y, z))
                if len(candidates) >= maximum_candidates:
                    return tuple(candidates)

    tiles = tuple(sorted(
        map_record.tiles,
        key=lambda item: (item.grid_x, item.grid_y, item.artifact),
    ))
    sampled_tiles = _evenly_spaced(tiles, min(24, len(tiles) or 1)) if tiles else ()
    for tile in sampled_tiles:
        for fraction_x, fraction_y in (
            (0.50, 0.50),
            (0.25, 0.25),
            (0.75, 0.75),
            (0.25, 0.75),
            (0.75, 0.25),
        ):
            for z in (0.0, 100.0):
                append(
                    "NAV_TILE_INTERIOR",
                    _tile_position(
                        grid_x=tile.grid_x,
                        grid_y=tile.grid_y,
                        fraction_x=fraction_x,
                        fraction_y=fraction_y,
                        z=z,
                    ),
                )
                if len(candidates) >= maximum_candidates:
                    return tuple(candidates)
    if not candidates:
        raise ValueError("map produced no standalone probe candidates")
    return tuple(candidates)


def resolve_static_awareness(
    query: ClientAssetNavmeshQuery,
    *,
    map_name: str,
    candidates: Iterable[ProbeCandidate],
) -> ResolvedProbe:
    """Find one adapter-validated local awareness sample without local hints."""
    attempts = 0
    failures: list[str] = []
    for candidate in candidates:
        for dx, dy in ((4.0, 0.0), (-4.0, 0.0), (0.0, 4.0), (0.0, -4.0)):
            attempts += 1
            try:
                corridor = query.find_corridor(
                    map_name=map_name,
                    start=candidate.position,
                    stop_x=candidate.position.x + dx,
                    stop_y=candidate.position.y + dy,
                )
            except ClientNavmeshError as error:
                failures.append(str(error))
                continue
            if corridor.start_awareness is None:
                failures.append("validated corridor omitted local static awareness")
                continue
            return ResolvedProbe(candidate, corridor, attempts)
    detail = failures[-1] if failures else "no candidates were attempted"
    raise ValueError(
        f"no adapter-validated local awareness for {map_name!r} "
        f"after {attempts} attempts: {detail}"
    )


def _mature_dynamic_tracks() -> tuple[Any, ...]:
    tracker = DynamicEntityTracker()
    for observed_at_s, y in ((1.0, 0.42), (1.1, 0.49), (1.2, 0.55)):
        tracks = tracker.update(
            (ScreenEntityObservation(
                observed_at_s=observed_at_s,
                center_x_normalized=0.08,
                center_y_normalized=y,
                width_normalized=0.08,
                height_normalized=0.012,
                reaction="FRIENDLY",
                confidence=0.95,
                source_key="portability:crossing-entity",
            ),),
            now_s=observed_at_s,
        )
    return tracks


def _nearest_probe(
    awareness: LocalStaticAwareness, *, bearing_rad: float,
) -> Any:
    bearing = bearing_rad % tau
    return min(
        awareness.radial_probes,
        key=lambda item: abs(((item.bearing_rad - bearing + pi) % tau) - pi),
    )


def exercise_dynamic_policy(
    awareness: LocalStaticAwareness,
) -> dict[str, Any]:
    """Exercise the same avoidance policy against real map-derived clearance."""
    tracks = _mature_dynamic_tracks()
    headings = tuple(
        probe.bearing_rad - pi / 4 for probe in awareness.radial_probes
    )
    selected = None
    selected_heading = None
    selected_policy = None
    for heading in headings:
        policy = DynamicCollisionAvoidance(
            minimum_static_clearance_yards=MINIMUM_SIDE_CLEARANCE_YARDS,
        )
        decision = policy.decide(
            tracks,
            now_s=1.2,
            heading_rad=heading,
            static_awareness=awareness,
        )
        if decision.state == "AVOID":
            selected = decision
            selected_heading = heading
            selected_policy = policy
            break
    if selected is None:
        selected_policy = DynamicCollisionAvoidance(
            minimum_static_clearance_yards=MINIMUM_SIDE_CLEARANCE_YARDS,
        )
        selected_heading = 0.0
        selected = selected_policy.decide(
            tracks,
            now_s=1.2,
            heading_rad=selected_heading,
            static_awareness=awareness,
        )

    if selected.state == "AVOID":
        side_bearing = selected_heading + (
            pi / 4 if selected.side == "LEFT" else -pi / 4
        )
        side_probe = _nearest_probe(awareness, bearing_rad=side_bearing)
        if (
            not side_probe.navmesh_reachable
            or side_probe.clearance_yards < MINIMUM_SIDE_CLEARANCE_YARDS
        ):
            raise ValueError("dynamic policy selected an unproven static side")
        opposing_delta = 5 if selected.side == "LEFT" else -5
        base = SteeringIntent(
            "FOLLOW", 50, opposing_delta, NavPoint(4.0, 0.0, 0.0),
            "portability_validation",
        )
        applied = selected_policy.apply(
            base, selected, maximum_mouse_delta=5,
        )
        if applied.state != "DYNAMIC_AVOID":
            raise ValueError("dynamic avoidance did not reach its movement contract")
        if selected.side == "LEFT" and applied.mouse_delta_x > 0:
            raise ValueError("left avoidance arc reversed direction")
        if selected.side == "RIGHT" and applied.mouse_delta_x < 0:
            raise ValueError("right avoidance arc reversed direction")
        clearance = side_probe.clearance_yards
        reachable = side_probe.navmesh_reachable
    elif selected.state == "YIELD":
        base = SteeringIntent(
            "FOLLOW", 50, 0, NavPoint(4.0, 0.0, 0.0),
            "portability_validation",
        )
        applied = selected_policy.apply(
            base, selected, maximum_mouse_delta=5,
        )
        if applied.state != "DYNAMIC_YIELD" or applied.forward_hold_ms != 0:
            raise ValueError("blocked static sides did not produce a bounded yield")
        clearance = None
        reachable = None
    else:
        raise ValueError("mature collision-lane track produced no bounded action")

    return {
        "state": selected.state,
        "side": selected.side,
        "heading_rad": selected_heading,
        "risk": selected.risk,
        "selected_static_clearance_yards": clearance,
        "selected_static_side_reachable": reachable,
        "applied_state": applied.state,
        "applied_forward_hold_ms": applied.forward_hold_ms,
        "applied_mouse_delta_x": applied.mouse_delta_x,
        "static_memory_write": False,
    }


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


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate map-neutral Movement Engine awareness and transient "
            "avoidance against sealed standalone WorldPacks."
        )
    )
    parser.add_argument("--profile", type=Path, action="append", required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-candidates-per-map", type=int, default=96)
    args = parser.parse_args(argv)
    if not 8 <= args.maximum_candidates_per_map <= 512:
        parser.error("--maximum-candidates-per-map must be between 8 and 512")
    worker = args.worker.resolve()
    if not worker.is_file():
        raise ValueError("standalone nav worker is unavailable")
    if args.output.exists():
        raise ValueError("portability evidence output already exists")

    packs = []
    seen_pack_ids: set[str] = set()
    for profile in args.profile:
        binding = load_world_pack_runtime_profile(
            profile,
            store_root=args.store_root,
            profile_schema_path=(
                ROOT / "contracts" / "world-pack-runtime-profile.schema.json"
            ),
            pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
            catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
        )
        pack_id = str(binding.pack.manifest["pack_id"])
        if pack_id in seen_pack_ids:
            raise ValueError("portability profiles resolve the same WorldPack twice")
        seen_pack_ids.add(pack_id)
        dependencies = dict(binding.pack.manifest["runtime_dependencies"])
        if any(dependencies.values()):
            raise ValueError("portability validation requires a standalone WorldPack")

        query = ClientAssetNavmeshQuery(worker=worker, nav_root=binding.pack.nav_root)
        maps = []
        for map_record in binding.pack.catalog.maps:
            structure_record = build_world_structure_index_record(
                binding.pack, map_name=map_record.internal_name,
            )
            candidates = build_probe_candidates(
                map_record,
                structure_record,
                maximum_candidates=args.maximum_candidates_per_map,
            )
            resolved = resolve_static_awareness(
                query,
                map_name=map_record.internal_name,
                candidates=candidates,
            )
            awareness = resolved.corridor.start_awareness
            if awareness is None:  # defended again for type narrowing
                raise ValueError("resolved portability probe has no static awareness")
            maps.append({
                "map_id": map_record.map_id,
                "map_name": map_record.internal_name,
                "candidate_source": resolved.candidate.source,
                "candidate_count": len(candidates),
                "probe_attempts": resolved.attempts,
                "resolved_position": [
                    resolved.corridor.start.x,
                    resolved.corridor.start.y,
                    resolved.corridor.start.z,
                ],
                "corridor_complete": resolved.corridor.complete,
                "physical_surfaces": sorted(awareness.physical_surfaces),
                "environment_class": awareness.environment_class,
                "component_polygon_count": awareness.component_polygon_count,
                "dynamic_avoidance": exercise_dynamic_policy(awareness),
            })
        packs.append({
            "profile_id": binding.profile_id,
            "pack_id": pack_id,
            "content_sha256": binding.pack.manifest["content_sha256"],
            "runtime_dependencies": dependencies,
            "maps": maps,
        })

    record = {
        "record_type": "standalone_movement_portability_validation",
        "schema_version": "1.0",
        "status": "PASS",
        "worker_sha256": _sha256(worker),
        "worldpacks": packs,
        "runtime_location_special_cases": [],
        "dynamic_entity_persistence": "TRANSIENT_SCREEN_TRACK_ONLY",
        "execution_authority": False,
    }
    _atomic_write_json(args.output, record)
    print(json.dumps({
        "status": record["status"],
        "worldpack_count": len(packs),
        "map_count": sum(len(item["maps"]) for item in packs),
        "output": str(args.output.resolve()),
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
