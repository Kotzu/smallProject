from __future__ import annotations

import json
from dataclasses import replace
from math import atan2, degrees, isclose, isfinite
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from perfect_assassin.movement.client_navmesh import (
    ClientNavmeshError,
    LocalSurfaceTransitionPortal,
    LocalStaticAwareness,
    LocalTopologicalEgressPortal,
    LocalWallSegment,
    NavCorridor,
    NavPolygon,
    NavPoint,
    NavPortal,
    RadialClearanceProbe,
)


def nav_worker_creation_flags() -> int:
    """Run read-only nav workers below the realtime capture/control clock.

    The native worker only performs bounded client-asset queries.  On Windows
    its default priority can contend with DXGI capture when the frontier
    preplanner fans out several cold tile loads at once.  Keep the flag
    capability-detected so offline/test hosts and non-Windows platforms retain
    the same command shape without inventing a platform-specific dependency.
    """

    return int(
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    )


class ClientAssetNavmeshQuery:
    """Fail-closed process adapter for the isolated client-asset Detour worker."""

    surface_evidence_available = True

    def __init__(
        self, *, worker: Path, nav_root: Path, timeout_seconds: float = 3.0,
        observed_blockers: tuple[tuple[float, float, float, float], ...] = (),
        _auto_retry_depth: int = 0,
        _structure_egress_bounds: tuple[float, float, float, float, float, float] | None = None,
    ):
        self._worker = worker.resolve()
        self._nav_root = nav_root.resolve()
        if not self._worker.is_file() or not self._nav_root.is_dir():
            raise ClientNavmeshError("nav worker or root is unavailable")
        if not 0.1 <= timeout_seconds <= 10.0:
            raise ClientNavmeshError("nav query timeout is outside its bound")
        self._timeout_seconds = float(timeout_seconds)
        if len(observed_blockers) > 8 or any(
            len(blocker) != 4
            or any(not isfinite(value) for value in blocker)
            or not -500.0 <= blocker[2] <= 5000.0
            or not 1.0 <= blocker[3] <= 30.0
            for blocker in observed_blockers
        ):
            raise ClientNavmeshError("observed blockers are invalid")
        self._observed_blockers = observed_blockers
        if _structure_egress_bounds is not None:
            if (
                len(_structure_egress_bounds) != 6
                or any(not isfinite(value) for value in _structure_egress_bounds)
            ):
                raise ClientNavmeshError("structure egress bounds are invalid")
            minimum_x, minimum_y, minimum_z, maximum_x, maximum_y, maximum_z = (
                float(value) for value in _structure_egress_bounds
            )
            if (
                minimum_x > maximum_x
                or minimum_y > maximum_y
                or minimum_z > maximum_z
            ):
                raise ClientNavmeshError("structure egress bounds are inverted")
            self._structure_egress_bounds = (
                minimum_x, minimum_y, minimum_z,
                maximum_x, maximum_y, maximum_z,
            )
        else:
            self._structure_egress_bounds = None
        if not 0 <= _auto_retry_depth <= 5:
            raise ClientNavmeshError("automatic doodad retry depth is invalid")
        self._auto_retry_depth = _auto_retry_depth

    def for_structure_egress(
        self,
        *,
        bounds: tuple[float, float, float, float, float, float],
    ) -> ClientAssetNavmeshQuery:
        """Return a query scoped to one immutable structure's exit.

        Learned blocker discs describe client-observed geometry, but an old
        disc recorded *inside* the WMO can seal every route to its door.  The
        WMO's own client navmesh and the verified access graph are the source
        of truth for this short boundary leg, so only blocker centres inside
        that same 3-D structure bounds are omitted.  Outside blockers stay in
        the query and continue to protect the route after the exit.
        """

        validated = ClientAssetNavmeshQuery(
            worker=self._worker,
            nav_root=self._nav_root,
            timeout_seconds=self._timeout_seconds,
            observed_blockers=(),
            _auto_retry_depth=self._auto_retry_depth,
            _structure_egress_bounds=bounds,
        )
        filtered = validated._filter_structure_egress_blockers(
            self._observed_blockers
        )
        if (
            filtered == self._observed_blockers
            and self._structure_egress_bounds == validated._structure_egress_bounds
        ):
            return self
        return ClientAssetNavmeshQuery(
            worker=self._worker,
            nav_root=self._nav_root,
            timeout_seconds=self._timeout_seconds,
            observed_blockers=filtered,
            _auto_retry_depth=self._auto_retry_depth,
            _structure_egress_bounds=validated._structure_egress_bounds,
        )

    def with_observed_blockers(
        self,
        observed_blockers: tuple[tuple[float, float, float, float], ...],
    ) -> ClientAssetNavmeshQuery:
        """Replace observed blockers without dropping an active egress scope."""

        filtered = self._filter_structure_egress_blockers(observed_blockers)
        if filtered == self._observed_blockers:
            return self
        return ClientAssetNavmeshQuery(
            worker=self._worker,
            nav_root=self._nav_root,
            timeout_seconds=self._timeout_seconds,
            observed_blockers=filtered,
            _auto_retry_depth=self._auto_retry_depth,
            _structure_egress_bounds=self._structure_egress_bounds,
        )

    @property
    def observed_blockers(
        self,
    ) -> tuple[tuple[float, float, float, float], ...]:
        """Expose the immutable blocker set for a derived bounded query."""

        return self._observed_blockers

    def without_structure_egress_scope(self) -> ClientAssetNavmeshQuery:
        """Return the same query after the actor has crossed the exit anchor."""

        if self._structure_egress_bounds is None:
            return self
        return ClientAssetNavmeshQuery(
            worker=self._worker,
            nav_root=self._nav_root,
            timeout_seconds=self._timeout_seconds,
            observed_blockers=self._observed_blockers,
            _auto_retry_depth=self._auto_retry_depth,
        )

    def _filter_structure_egress_blockers(
        self,
        observed_blockers: tuple[tuple[float, float, float, float], ...] | list[tuple[float, float, float, float]],
    ) -> tuple[tuple[float, float, float, float], ...]:
        if self._structure_egress_bounds is None:
            return tuple(observed_blockers)
        minimum_x, minimum_y, minimum_z, maximum_x, maximum_y, maximum_z = (
            self._structure_egress_bounds
        )
        return tuple(
            blocker
            for blocker in observed_blockers
            if not (
                minimum_x <= blocker[0] <= maximum_x
                and minimum_y <= blocker[1] <= maximum_y
                and minimum_z <= blocker[2] <= maximum_z
            )
        )

    def find_corridor(
        self,
        *,
        map_name: str,
        start: NavPoint,
        stop_x: float,
        stop_y: float,
        stop_z: float | None = None,
    ) -> NavCorridor:
        if (
            re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_ '\-]{0,95}", map_name)
            is None
            or map_name != map_name.rstrip()
        ):
            raise ClientNavmeshError("map name is invalid")
        values = (start.x, start.y, start.z, stop_x, stop_y)
        if any(not isfinite(value) or abs(value) > 100_000 for value in values):
            raise ClientNavmeshError("nav coordinates are invalid")
        if stop_z is not None and (not isfinite(stop_z) or abs(stop_z) > 100_000):
            raise ClientNavmeshError("nav stop height is invalid")
        command = [
            str(self._worker), str(self._nav_root), map_name,
            repr(start.x), repr(start.y), repr(start.z), repr(stop_x), repr(stop_y),
        ]
        if stop_z is not None:
            command.extend(("--stop-z", repr(stop_z)))
        for blocker in self._observed_blockers:
            command.extend(repr(value) for value in blocker)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
            check=False,
            # Corridor planning is an isolated, bounded request.  It must not
            # create an interactive console over WoW; continuous local
            # awareness uses the separate long-lived service instead.
            creationflags=nav_worker_creation_flags(),
        )
        awareness_observed_monotonic_s = time.monotonic()
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if completed.returncode != 0 or len(lines) != 1:
            detail = completed.stderr.strip()[-512:] or "worker rejected query"
            raise ClientNavmeshError(detail)
        try:
            record: dict[str, Any] = json.loads(lines[0])
        except (json.JSONDecodeError, TypeError) as error:
            raise ClientNavmeshError("worker output is not strict JSON") from error
        legacy_shape = {
            "status", "adt_x", "adt_y", "start", "stop", "height_candidates",
            "stop_height_candidates", "path", "polygons", "portals", "complete",
            "requested_stop",
            "doodad_avoidance_applied", "doodad_detour_count",
            "doodad_unresolved_segment_count",
            "doodad_unresolved_blockers",
            "clearance_inset_count",
            "steep_polygons_penalized",
            "observed_blocker_polygons_excluded",
            "impassable_uphill_polygons_excluded",
            "road_polygons_preferred", "nearest_road_polygon_to_start",
            "road_polygon_bounds",
            "search_vantage_radial_clear_count",
            "search_vantage_radial_probe_count",
            "search_vantage_radial_probe_radius",
            "search_vantage_overhead_clear",
            "search_vantage_physical_surfaces",
            "start_awareness",
        }
        floor_aware_shape = legacy_shape | {"requested_stop_z_hint"}
        topology_repair_shape = floor_aware_shape | {
            "topology_gap_direct_shortcut_applied",
            "doodad_polygons_penalized",
        }
        movement_simplification_shape = topology_repair_shape | {
            "movement_path_shortcut_count",
        }
        if record.get("status") != "OK" or set(record) not in {
            frozenset(legacy_shape), frozenset(floor_aware_shape),
            frozenset(topology_repair_shape),
            frozenset(movement_simplification_shape),
        }:
            raise ClientNavmeshError("worker output shape is not exact")
        if stop_z is not None:
            if "requested_stop_z_hint" not in record:
                raise ClientNavmeshError("floor-aware worker evidence is missing")
            returned_stop_z_hint = self._finite_number(
                record["requested_stop_z_hint"], name="requested stop height hint",
            )
            if not isclose(returned_stop_z_hint, stop_z, rel_tol=1e-9, abs_tol=1e-5):
                raise ClientNavmeshError("worker stop height hint does not match query")
        elif (
            "requested_stop_z_hint" in record
            and record["requested_stop_z_hint"] is not None
        ):
            raise ClientNavmeshError("worker returned an unsolicited stop height hint")
        points = self._points(record.get("path"))
        polygons = self._polygons(record.get("polygons"))
        portals = self._portals(record.get("portals"))
        resolved_start = self._point(record.get("start"))
        resolved_stop = self._point(record.get("stop"))
        requested_stop = self._point(record.get("requested_stop"))
        complete = record.get("complete")
        if not isinstance(complete, bool):
            raise ClientNavmeshError("corridor completion state is invalid")
        height_candidate_count = self._bounded_int(
            record.get("height_candidates"), minimum=1, maximum=64,
            name="start height candidate count",
        )
        stop_height_candidate_count = self._bounded_int(
            record.get("stop_height_candidates"), minimum=1, maximum=64,
            name="stop height candidate count",
        )
        topology_gap_direct_shortcut_applied = record.get(
            "topology_gap_direct_shortcut_applied", False
        )
        if not isinstance(topology_gap_direct_shortcut_applied, bool):
            raise ClientNavmeshError("topology-gap shortcut state is invalid")
        doodad_avoidance_applied = record.get("doodad_avoidance_applied")
        doodad_detour_count = record.get("doodad_detour_count")
        if not isinstance(doodad_avoidance_applied, bool):
            raise ClientNavmeshError("doodad avoidance state is invalid")
        doodad_detour_count = self._bounded_int(
            doodad_detour_count, minimum=0, maximum=4096, name="doodad detour count"
        )
        doodad_unresolved_segment_count = self._bounded_int(
            record.get("doodad_unresolved_segment_count"), minimum=0, maximum=4096,
            name="doodad unresolved segment count",
        )
        doodad_unresolved_blockers = self._blockers(
            record.get("doodad_unresolved_blockers"),
            name="doodad unresolved blockers",
        )
        if (
            doodad_unresolved_segment_count == 0
            and doodad_unresolved_blockers
        ):
            raise ClientNavmeshError("resolved corridor reported stale doodad blockers")
        clearance_inset_count = self._bounded_int(
            record.get("clearance_inset_count"), minimum=0, maximum=4096,
            name="clearance inset count",
        )
        steep_polygons_penalized = self._bounded_int(
            record.get("steep_polygons_penalized"), minimum=0, maximum=1_000_000,
            name="steep polygon count",
        )
        doodad_polygons_penalized = self._bounded_int(
            record.get("doodad_polygons_penalized", 0), minimum=0,
            maximum=1_000_000, name="doodad polygon count",
        )
        movement_path_shortcut_count = self._bounded_int(
            record.get("movement_path_shortcut_count", 0), minimum=0,
            maximum=4096, name="movement path shortcut count",
        )
        observed_blocker_polygons_excluded = self._bounded_int(
            record.get("observed_blocker_polygons_excluded"), minimum=0,
            maximum=1_000_000, name="observed blocker polygon count",
        )
        impassable_uphill_polygons_excluded = self._bounded_int(
            record.get("impassable_uphill_polygons_excluded"), minimum=0,
            maximum=1_000_000, name="impassable uphill polygon count",
        )
        road_polygons_preferred = self._bounded_int(
            record.get("road_polygons_preferred"), minimum=0,
            maximum=1_000_000, name="preferred road polygon count",
        )
        nearest_road_polygon_to_start = self._finite_number(
            record.get("nearest_road_polygon_to_start"),
            name="nearest road polygon distance",
        )
        if nearest_road_polygon_to_start < -1:
            raise ClientNavmeshError("nearest road polygon distance is outside its bound")
        road_polygon_bounds_value = record.get("road_polygon_bounds")
        if (
            not isinstance(road_polygon_bounds_value, list)
            or len(road_polygon_bounds_value) != 4
        ):
            raise ClientNavmeshError("road polygon bounds are invalid")
        road_polygon_bounds = tuple(
            self._finite_number(value, name="road polygon bound")
            for value in road_polygon_bounds_value
        )
        if (
            road_polygons_preferred > 0
            and (
                road_polygon_bounds[0] > road_polygon_bounds[2]
                or road_polygon_bounds[1] > road_polygon_bounds[3]
            )
        ):
            raise ClientNavmeshError("road polygon bounds are inverted")
        search_vantage_radial_clear_count = self._bounded_int(
            record.get("search_vantage_radial_clear_count"), minimum=0, maximum=64,
            name="search vantage radial clear count",
        )
        search_vantage_radial_probe_count = self._bounded_int(
            record.get("search_vantage_radial_probe_count"), minimum=1, maximum=64,
            name="search vantage radial probe count",
        )
        if search_vantage_radial_clear_count > search_vantage_radial_probe_count:
            raise ClientNavmeshError("search vantage radial counts are inconsistent")
        search_vantage_radial_probe_radius = self._finite_number(
            record.get("search_vantage_radial_probe_radius"),
            name="search vantage radial probe radius",
        )
        if not 1.0 <= search_vantage_radial_probe_radius <= 30.0:
            raise ClientNavmeshError("search vantage radial radius is outside its bound")
        search_vantage_overhead_clear = record.get("search_vantage_overhead_clear")
        if not isinstance(search_vantage_overhead_clear, bool):
            raise ClientNavmeshError("search vantage overhead state is invalid")
        search_vantage_physical_surfaces = self._physical_surfaces(
            record.get("search_vantage_physical_surfaces"),
            name="search vantage physical surfaces",
        )
        start_awareness = self._start_awareness(record.get("start_awareness"))
        if not points or points[0].distance_2d(resolved_start) > 6.0:
            raise ClientNavmeshError("corridor is not bound to the resolved start")
        if points[-1].distance_2d(resolved_stop) > 6.0:
            raise ClientNavmeshError("corridor is not bound to the resolved stop")
        corridor = NavCorridor(
            map_name=map_name,
            adt_x=self._exact_adt(record.get("adt_x")),
            adt_y=self._exact_adt(record.get("adt_y")),
            start=resolved_start,
            stop=resolved_stop,
            points=points,
            polygons=polygons,
            portals=portals,
            complete=complete,
            height_candidate_count=height_candidate_count,
            stop_height_candidate_count=stop_height_candidate_count,
            requested_stop=requested_stop,
            topology_gap_direct_shortcut_applied=(
                topology_gap_direct_shortcut_applied
            ),
            doodad_avoidance_applied=doodad_avoidance_applied,
            doodad_detour_count=doodad_detour_count,
            doodad_unresolved_segment_count=doodad_unresolved_segment_count,
            doodad_unresolved_blockers=doodad_unresolved_blockers,
            clearance_inset_count=clearance_inset_count,
            steep_polygons_penalized=steep_polygons_penalized,
            doodad_polygons_penalized=doodad_polygons_penalized,
            movement_path_shortcut_count=movement_path_shortcut_count,
            observed_blocker_polygons_excluded=observed_blocker_polygons_excluded,
            impassable_uphill_polygons_excluded=impassable_uphill_polygons_excluded,
            road_polygons_preferred=road_polygons_preferred,
            nearest_road_polygon_to_start=(
                None if nearest_road_polygon_to_start < 0
                else nearest_road_polygon_to_start
            ),
            road_polygon_bounds=(
                None if road_polygons_preferred == 0 else road_polygon_bounds
            ),
            search_vantage_radial_clear_count=search_vantage_radial_clear_count,
            search_vantage_radial_probe_count=search_vantage_radial_probe_count,
            search_vantage_radial_probe_radius=search_vantage_radial_probe_radius,
            search_vantage_overhead_clear=search_vantage_overhead_clear,
            search_vantage_physical_surfaces=search_vantage_physical_surfaces,
            start_awareness=start_awareness,
            awareness_observed_monotonic_s=awareness_observed_monotonic_s,
        )
        merged_blockers = list(self._observed_blockers)
        retry_blockers = list(corridor.doodad_unresolved_blockers)
        unsafe_grade_blocker = self._first_unsafe_grade_blocker(corridor)
        if unsafe_grade_blocker is not None:
            retry_blockers.append(unsafe_grade_blocker)
        if not retry_blockers:
            return corridor

        for blocker in retry_blockers:
            if len(merged_blockers) >= 8:
                break
            if any(
                ((blocker[0] - existing[0]) ** 2
                 + (blocker[1] - existing[1]) ** 2) ** 0.5 < 1.0
                and abs(blocker[2] - existing[2]) < 2.5
                for existing in merged_blockers
            ):
                continue
            merged_blockers.append(blocker)
            break
        if (
            self._auto_retry_depth < 5
            and len(merged_blockers) > len(self._observed_blockers)
        ):
            retry = ClientAssetNavmeshQuery(
                worker=self._worker,
                nav_root=self._nav_root,
                timeout_seconds=self._timeout_seconds,
                observed_blockers=tuple(merged_blockers),
                _auto_retry_depth=self._auto_retry_depth + 1,
                _structure_egress_bounds=self._structure_egress_bounds,
            )
            return retry.find_corridor(
                map_name=map_name,
                start=start,
                stop_x=stop_x,
                stop_y=stop_y,
                stop_z=stop_z,
            )
        # Never grant a complete live corridor when client geometry proved an
        # unresolved M2/WMO intersection or the post-funnel guidance contains
        # an unwalkable vertical transition. Returning a partial proposal lets
        # the semantic planner choose a finer/global alternative fail-closed.
        return replace(corridor, complete=False)

    @staticmethod
    def _first_unsafe_grade_blocker(
        corridor: NavCorridor,
    ) -> tuple[float, float, float, float] | None:
        """Locate a client-geometry path transition steeper than the actor envelope.

        Polygon slope filtering alone is insufficient after funnel inset and
        local doodad detours: two individually walkable points can still be
        joined across different detail-mesh heights. Tiny quantized steps use
        the same bounded allowance as the semantic journey validator.
        """
        for left, right in zip(corridor.points, corridor.points[1:]):
            horizontal = left.distance_2d(right)
            vertical = abs(right.z - left.z)
            is_walkable_step = horizontal <= 0.75 and vertical <= 0.85
            if horizontal <= 0.05 or is_walkable_step:
                continue
            if degrees(atan2(vertical, horizontal)) <= 42.0:
                continue
            return (
                (left.x + right.x) * 0.5,
                (left.y + right.y) * 0.5,
                (left.z + right.z) * 0.5,
                1.5,
            )
        return None

    @classmethod
    def _start_awareness(cls, value: Any) -> LocalStaticAwareness:
        if not isinstance(value, dict) or set(value) != {
            "physical_surfaces", "probe_radius_yards", "overhead_clear",
            "radial_probes", "topology_radius_yards",
            "component_polygon_count", "component_truncated",
            "wall_segments_truncated", "surface_transition_portals_truncated",
            "egress_inference_complete", "egress_portals_truncated",
            "wall_segments", "surface_transition_portals", "egress_portals",
        }:
            raise ClientNavmeshError("start awareness shape is invalid")
        surfaces = cls._physical_surfaces(
            value["physical_surfaces"], name="start awareness physical surfaces",
        )
        if not surfaces:
            raise ClientNavmeshError("start awareness physical surfaces are empty")
        radius = cls._finite_number(
            value["probe_radius_yards"], name="start awareness probe radius",
        )
        overhead_clear = value["overhead_clear"]
        if not isinstance(overhead_clear, bool):
            raise ClientNavmeshError("start awareness overhead state is invalid")
        topology_radius = cls._finite_number(
            value["topology_radius_yards"],
            name="start awareness topology radius",
        )
        component_polygon_count = cls._bounded_int(
            value["component_polygon_count"], minimum=0, maximum=2048,
            name="start awareness component polygon count",
        )
        component_truncated = value["component_truncated"]
        if not isinstance(component_truncated, bool):
            raise ClientNavmeshError(
                "start awareness component truncation state is invalid"
            )
        wall_segments_truncated = value["wall_segments_truncated"]
        surface_transition_portals_truncated = value[
            "surface_transition_portals_truncated"
        ]
        egress_inference_complete = value["egress_inference_complete"]
        egress_portals_truncated = value["egress_portals_truncated"]
        if not isinstance(wall_segments_truncated, bool):
            raise ClientNavmeshError(
                "start awareness wall truncation state is invalid"
            )
        if not isinstance(surface_transition_portals_truncated, bool):
            raise ClientNavmeshError(
                "start awareness transition truncation state is invalid"
            )
        if not isinstance(egress_inference_complete, bool):
            raise ClientNavmeshError(
                "start awareness egress inference state is invalid"
            )
        if not isinstance(egress_portals_truncated, bool):
            raise ClientNavmeshError(
                "start awareness egress truncation state is invalid"
            )
        raw_probes = value["radial_probes"]
        if not isinstance(raw_probes, list) or not 8 <= len(raw_probes) <= 64:
            raise ClientNavmeshError("start awareness radial probe count is invalid")
        probes: list[RadialClearanceProbe] = []
        for item in raw_probes:
            if not isinstance(item, dict) or set(item) != {
                "bearing_rad", "clearance_yards", "navmesh_reachable",
            }:
                raise ClientNavmeshError("start awareness radial probe shape is invalid")
            navmesh_reachable = item["navmesh_reachable"]
            if not isinstance(navmesh_reachable, bool):
                raise ClientNavmeshError(
                    "start awareness navmesh reachability is invalid"
                )
            try:
                probes.append(RadialClearanceProbe(
                    bearing_rad=cls._finite_number(
                        item["bearing_rad"], name="start awareness bearing",
                    ),
                    clearance_yards=cls._finite_number(
                        item["clearance_yards"], name="start awareness clearance",
                    ),
                    navmesh_reachable=navmesh_reachable,
                ))
            except ValueError as error:
                raise ClientNavmeshError(str(error)) from error
        try:
            return LocalStaticAwareness(
                physical_surfaces=surfaces,
                probe_radius_yards=radius,
                overhead_clear=overhead_clear,
                radial_probes=tuple(probes),
                topology_radius_yards=topology_radius,
                component_polygon_count=component_polygon_count,
                component_truncated=component_truncated,
                wall_segments_truncated=wall_segments_truncated,
                surface_transition_portals_truncated=(
                    surface_transition_portals_truncated
                ),
                egress_inference_complete=egress_inference_complete,
                egress_portals_truncated=egress_portals_truncated,
                wall_segments=cls._local_wall_segments(value["wall_segments"]),
                surface_transition_portals=cls._local_surface_transition_portals(
                    value["surface_transition_portals"]
                ),
                egress_portals=cls._local_egress_portals(
                    value["egress_portals"]
                ),
            )
        except ValueError as error:
            raise ClientNavmeshError(str(error)) from error

    @classmethod
    def _local_wall_segments(cls, value: Any) -> tuple[LocalWallSegment, ...]:
        if not isinstance(value, list) or len(value) > 128:
            raise ClientNavmeshError("local wall segment count is invalid")
        result: list[LocalWallSegment] = []
        for item in value:
            if not isinstance(item, dict) or set(item) != {
                "left", "right", "distance_yards",
            }:
                raise ClientNavmeshError("local wall segment shape is invalid")
            result.append(LocalWallSegment(
                left=cls._point(item["left"]),
                right=cls._point(item["right"]),
                distance_yards=cls._finite_number(
                    item["distance_yards"], name="local wall distance",
                ),
            ))
        return tuple(result)

    @classmethod
    def _local_surface_transition_portals(
        cls, value: Any
    ) -> tuple[LocalSurfaceTransitionPortal, ...]:
        if not isinstance(value, list) or len(value) > 64:
            raise ClientNavmeshError("local surface transition count is invalid")
        result: list[LocalSurfaceTransitionPortal] = []
        for item in value:
            if not isinstance(item, dict) or set(item) != {
                "left", "right", "width_yards", "distance_yards",
                "from_surfaces", "to_surfaces",
            }:
                raise ClientNavmeshError("local surface transition shape is invalid")
            result.append(LocalSurfaceTransitionPortal(
                left=cls._point(item["left"]),
                right=cls._point(item["right"]),
                width_yards=cls._finite_number(
                    item["width_yards"], name="local surface transition width",
                ),
                distance_yards=cls._finite_number(
                    item["distance_yards"], name="local surface transition distance",
                ),
                from_surfaces=cls._physical_surfaces(
                    item["from_surfaces"], name="local transition origin surfaces",
                ),
                to_surfaces=cls._physical_surfaces(
                    item["to_surfaces"], name="local transition destination surfaces",
                ),
            ))
        return tuple(result)

    @classmethod
    def _local_egress_portals(
        cls, value: Any
    ) -> tuple[LocalTopologicalEgressPortal, ...]:
        if not isinstance(value, list) or len(value) > 32:
            raise ClientNavmeshError("local topological egress count is invalid")
        result: list[LocalTopologicalEgressPortal] = []
        for item in value:
            if not isinstance(item, dict) or set(item) != {
                "left", "right", "width_yards", "distance_yards",
                "route_distance_yards", "from_overhead_clear",
                "to_overhead_clear", "from_surfaces", "to_surfaces",
            }:
                raise ClientNavmeshError("local topological egress shape is invalid")
            from_overhead_clear = item["from_overhead_clear"]
            to_overhead_clear = item["to_overhead_clear"]
            if (
                not isinstance(from_overhead_clear, bool)
                or not isinstance(to_overhead_clear, bool)
            ):
                raise ClientNavmeshError(
                    "local topological egress overhead state is invalid"
                )
            result.append(LocalTopologicalEgressPortal(
                left=cls._point(item["left"]),
                right=cls._point(item["right"]),
                width_yards=cls._finite_number(
                    item["width_yards"], name="local egress width",
                ),
                distance_yards=cls._finite_number(
                    item["distance_yards"], name="local egress distance",
                ),
                route_distance_yards=cls._finite_number(
                    item["route_distance_yards"],
                    name="local egress route distance",
                ),
                from_overhead_clear=from_overhead_clear,
                to_overhead_clear=to_overhead_clear,
                from_surfaces=cls._physical_surfaces(
                    item["from_surfaces"], name="local egress origin surfaces",
                ),
                to_surfaces=cls._physical_surfaces(
                    item["to_surfaces"],
                    name="local egress destination surfaces",
                ),
            ))
        return tuple(result)

    @classmethod
    def _polygons(cls, value: Any) -> tuple[NavPolygon, ...]:
        if not isinstance(value, list) or not 1 <= len(value) <= 4096:
            raise ClientNavmeshError("corridor polygon count is invalid")
        result: list[NavPolygon] = []
        for expected_index, item in enumerate(value):
            if not isinstance(item, dict) or set(item) != {
                "index", "area", "type", "slope_degrees", "vertices", "centroid",
                "physical_surfaces",
            }:
                raise ClientNavmeshError("corridor polygon shape is invalid")
            index = cls._bounded_int(item["index"], minimum=0, maximum=4095, name="polygon index")
            if index != expected_index:
                raise ClientNavmeshError("corridor polygon order is invalid")
            area = cls._bounded_int(item["area"], minimum=0, maximum=63, name="polygon area")
            polygon_type = cls._bounded_int(item["type"], minimum=0, maximum=1, name="polygon type")
            vertices = cls._points_between(item["vertices"], minimum=3, maximum=6)
            surfaces = cls._physical_surfaces(
                item["physical_surfaces"], name="polygon physical surfaces",
            )
            slope = cls._finite_number(item["slope_degrees"], name="polygon slope")
            if not 0 <= slope <= 90.001:
                raise ClientNavmeshError("polygon slope is outside its bound")
            result.append(NavPolygon(
                index=index,
                area=area,
                polygon_type=polygon_type,
                slope_degrees=slope,
                centroid=cls._point(item["centroid"]),
                vertices=vertices,
                physical_surfaces=surfaces,
            ))
        return tuple(result)

    @staticmethod
    def _physical_surfaces(value: Any, *, name: str) -> frozenset[str]:
        if (
            not isinstance(value, list)
            or len(value) != len(set(value))
            or any(
                not isinstance(surface, str)
                or surface not in {"ground", "wmo", "doodad"}
                for surface in value
            )
        ):
            raise ClientNavmeshError(f"{name} are invalid")
        return frozenset(value)

    @classmethod
    def _portals(cls, value: Any) -> tuple[NavPortal, ...]:
        if not isinstance(value, list) or len(value) > 4095:
            raise ClientNavmeshError("corridor portal count is invalid")
        result: list[NavPortal] = []
        for expected_index, item in enumerate(value):
            if not isinstance(item, dict) or set(item) != {
                "from_index", "to_index", "left", "right", "width",
            }:
                raise ClientNavmeshError("corridor portal shape is invalid")
            from_index = cls._bounded_int(
                item["from_index"], minimum=0, maximum=4095, name="portal origin"
            )
            to_index = cls._bounded_int(
                item["to_index"], minimum=1, maximum=4096, name="portal destination"
            )
            if from_index != expected_index or to_index != expected_index + 1:
                raise ClientNavmeshError("corridor portal order is invalid")
            width = cls._finite_number(item["width"], name="portal width")
            if width <= 0 or width > 1_000:
                raise ClientNavmeshError("portal width is outside its bound")
            result.append(NavPortal(
                from_index=from_index,
                to_index=to_index,
                left=cls._point(item["left"]),
                right=cls._point(item["right"]),
                width=width,
            ))
        return tuple(result)

    @classmethod
    def _points(cls, value: Any) -> tuple[NavPoint, ...]:
        return cls._points_between(value, minimum=1, maximum=4096)

    @classmethod
    def _points_between(
        cls, value: Any, *, minimum: int, maximum: int
    ) -> tuple[NavPoint, ...]:
        if not isinstance(value, list) or not minimum <= len(value) <= maximum:
            raise ClientNavmeshError("corridor point count is invalid")
        return tuple(cls._point(item) for item in value)

    @classmethod
    def _blockers(
        cls, value: Any, *, name: str
    ) -> tuple[tuple[float, float, float, float], ...]:
        if not isinstance(value, list) or len(value) > 8:
            raise ClientNavmeshError(f"{name} are invalid")
        result: list[tuple[float, float, float, float]] = []
        for item in value:
            if (
                not isinstance(item, list)
                or len(item) != 4
                or any(
                    isinstance(component, bool)
                    or not isinstance(component, (int, float))
                    for component in item
                )
            ):
                raise ClientNavmeshError(f"{name} are invalid")
            blocker = tuple(float(component) for component in item)
            if (
                any(not isfinite(component) for component in blocker)
                or any(abs(component) > 100_000 for component in blocker[:3])
                or not 1.0 <= blocker[3] <= 30.0
            ):
                raise ClientNavmeshError(f"{name} are outside their bounds")
            result.append(blocker)
        return tuple(result)

    @staticmethod
    def _point(value: Any) -> NavPoint:
        if not isinstance(value, list) or len(value) != 3:
            raise ClientNavmeshError("nav point is invalid")
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
            raise ClientNavmeshError("nav point type is invalid")
        point = NavPoint(*(float(item) for item in value))
        if any(not isfinite(item) or abs(item) > 100_000 for item in (point.x, point.y, point.z)):
            raise ClientNavmeshError("nav point is non-finite or unbounded")
        return point

    @staticmethod
    def _exact_adt(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ClientNavmeshError("ADT coordinate is invalid")
        exact = int(value)
        if float(value) != exact or not 0 <= exact < 64:
            raise ClientNavmeshError("ADT coordinate is outside the client grid")
        return exact

    @staticmethod
    def _finite_number(value: Any, *, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ClientNavmeshError(f"{name} is invalid")
        result = float(value)
        if not isfinite(result):
            raise ClientNavmeshError(f"{name} is non-finite")
        return result

    @staticmethod
    def _bounded_int(value: Any, *, minimum: int, maximum: int, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ClientNavmeshError(f"{name} is invalid")
        if not minimum <= value <= maximum:
            raise ClientNavmeshError(f"{name} is outside its bound")
        return value
