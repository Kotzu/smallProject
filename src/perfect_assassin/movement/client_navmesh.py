from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite, tau
from typing import Protocol, runtime_checkable


class ClientNavmeshError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class NavPoint:
    x: float
    y: float
    z: float

    def distance_2d(self, other: "NavPoint") -> float:
        return hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True, slots=True)
class NavPolygon:
    index: int
    area: int
    polygon_type: int
    slope_degrees: float
    centroid: NavPoint
    vertices: tuple[NavPoint, ...]
    physical_surfaces: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.index < 0 or not 0 <= self.area <= 63 or self.polygon_type not in (0, 1):
            raise ValueError("nav polygon identity is invalid")
        if not isfinite(self.slope_degrees) or not 0 <= self.slope_degrees <= 90.001:
            raise ValueError("nav polygon slope is invalid")
        if not 3 <= len(self.vertices) <= 6:
            raise ValueError("nav polygon vertex count is invalid")
        if not self.physical_surfaces.issubset({"ground", "wmo", "doodad"}):
            raise ValueError("nav polygon physical surfaces are invalid")


@dataclass(frozen=True, slots=True)
class NavPortal:
    from_index: int
    to_index: int
    left: NavPoint
    right: NavPoint
    width: float

    def __post_init__(self) -> None:
        if self.from_index < 0 or self.to_index != self.from_index + 1:
            raise ValueError("nav portal topology is invalid")
        if not isfinite(self.width) or self.width <= 0:
            raise ValueError("nav portal width is invalid")


@dataclass(frozen=True, slots=True)
class PortalLateralClearance:
    """Client-geometry evidence for the space beside an actor at one portal.

    ``left`` and ``right`` are the portal endpoints supplied by the Detour
    worker.  The values describe where the actor's *centre* is relative to
    those two edges; they are not server coordinates and they do not grant
    movement authority.  A bridge and a narrow doorway use the same generic
    measurement.
    """

    portal_index: int
    width_yards: float
    left_edge_clearance_yards: float
    right_edge_clearance_yards: float
    actor_radius_yards: float = 0.55
    safety_margin_yards: float = 0.35

    def __post_init__(self) -> None:
        values = (
            self.width_yards,
            self.left_edge_clearance_yards,
            self.right_edge_clearance_yards,
            self.actor_radius_yards,
            self.safety_margin_yards,
        )
        if (
            type(self.portal_index) is not int
            or self.portal_index < 0
            or any(not isfinite(value) for value in values)
            or self.width_yards <= 0
            or self.left_edge_clearance_yards < 0
            or self.right_edge_clearance_yards < 0
            or self.actor_radius_yards <= 0
            or self.actor_radius_yards > 2.0
            or self.safety_margin_yards < 0
            or self.safety_margin_yards > 2.0
            or self.left_edge_clearance_yards > self.width_yards + 0.05
            or self.right_edge_clearance_yards > self.width_yards + 0.05
        ):
            raise ValueError("portal lateral clearance is invalid")

    @property
    def minimum_edge_clearance_yards(self) -> float:
        return min(
            self.left_edge_clearance_yards,
            self.right_edge_clearance_yards,
        )

    @property
    def free_left_clearance_yards(self) -> float:
        return self.left_edge_clearance_yards - (
            self.actor_radius_yards + self.safety_margin_yards
        )

    @property
    def free_right_clearance_yards(self) -> float:
        return self.right_edge_clearance_yards - (
            self.actor_radius_yards + self.safety_margin_yards
        )

    @property
    def actor_capsule_inside_safe_envelope(self) -> bool:
        return (
            self.free_left_clearance_yards >= 0.0
            and self.free_right_clearance_yards >= 0.0
        )

    @property
    def signed_center_offset_yards(self) -> float:
        """Offset from the portal centre; positive means toward ``right``."""

        return (
            self.left_edge_clearance_yards
            - self.right_edge_clearance_yards
        ) * 0.5


@dataclass(frozen=True, slots=True)
class RadialClearanceProbe:
    bearing_rad: float
    clearance_yards: float
    navmesh_reachable: bool

    def __post_init__(self) -> None:
        if not isfinite(self.bearing_rad) or not 0 <= self.bearing_rad < tau:
            raise ValueError("radial clearance bearing is invalid")
        if not isfinite(self.clearance_yards) or self.clearance_yards < 0:
            raise ValueError("radial clearance distance is invalid")
        if not isinstance(self.navmesh_reachable, bool):
            raise ValueError("radial clearance navmesh state is invalid")


@dataclass(frozen=True, slots=True)
class LocalWallSegment:
    left: NavPoint
    right: NavPoint
    distance_yards: float

    def __post_init__(self) -> None:
        coordinates = (
            self.left.x, self.left.y, self.left.z,
            self.right.x, self.right.y, self.right.z,
            self.distance_yards,
        )
        if any(not isfinite(value) for value in coordinates):
            raise ValueError("local wall segment geometry is invalid")
        if self.distance_yards < 0 or self.left.distance_2d(self.right) <= 0.01:
            raise ValueError("local wall segment bounds are invalid")


@dataclass(frozen=True, slots=True)
class LocalSurfaceTransitionPortal:
    left: NavPoint
    right: NavPoint
    width_yards: float
    distance_yards: float
    from_surfaces: frozenset[str]
    to_surfaces: frozenset[str]

    def __post_init__(self) -> None:
        allowed = {"ground", "wmo", "doodad"}
        coordinates = (
            self.left.x, self.left.y, self.left.z,
            self.right.x, self.right.y, self.right.z,
            self.width_yards, self.distance_yards,
        )
        if any(not isfinite(value) for value in coordinates):
            raise ValueError("local surface transition geometry is invalid")
        if self.width_yards <= 0 or self.distance_yards < 0:
            raise ValueError("local surface transition bounds are invalid")
        if (
            not self.from_surfaces
            or not self.to_surfaces
            or not self.from_surfaces.issubset(allowed)
            or not self.to_surfaces.issubset(allowed)
            or "wmo" not in self.from_surfaces
            or "wmo" in self.to_surfaces
        ):
            raise ValueError("local surface transition semantics are invalid")


@dataclass(frozen=True, slots=True)
class LocalTopologicalEgressPortal:
    """A covered-to-open portal with a complete route from the actor."""

    left: NavPoint
    right: NavPoint
    width_yards: float
    distance_yards: float
    route_distance_yards: float
    from_overhead_clear: bool
    to_overhead_clear: bool
    from_surfaces: frozenset[str]
    to_surfaces: frozenset[str]

    def __post_init__(self) -> None:
        allowed = {"ground", "wmo", "doodad"}
        coordinates = (
            self.left.x, self.left.y, self.left.z,
            self.right.x, self.right.y, self.right.z,
            self.width_yards, self.distance_yards, self.route_distance_yards,
        )
        if any(not isfinite(value) for value in coordinates):
            raise ValueError("local topological egress geometry is invalid")
        if (
            self.width_yards <= 0
            or self.distance_yards < 0
            or self.route_distance_yards < 0
        ):
            raise ValueError("local topological egress bounds are invalid")
        if (
            not isinstance(self.from_overhead_clear, bool)
            or not isinstance(self.to_overhead_clear, bool)
            or self.from_overhead_clear
            or not self.to_overhead_clear
        ):
            raise ValueError("local topological egress overhead transition is invalid")
        if (
            not self.from_surfaces
            or not self.to_surfaces
            or not self.from_surfaces.issubset(allowed)
            or not self.to_surfaces.issubset(allowed)
            or "wmo" not in self.from_surfaces
        ):
            raise ValueError("local topological egress surfaces are invalid")


@dataclass(frozen=True, slots=True)
class LocalStaticAwareness:
    """Bounded client-asset evidence around the corridor's resolved start.

    The polar samples describe static collision only.  They do not reveal
    entities, grant movement authority, or turn a clear ray into a route.
    """

    physical_surfaces: frozenset[str]
    probe_radius_yards: float
    overhead_clear: bool
    radial_probes: tuple[RadialClearanceProbe, ...]
    topology_radius_yards: float = 60.0
    component_polygon_count: int = 0
    component_truncated: bool = False
    wall_segments_truncated: bool = False
    surface_transition_portals_truncated: bool = False
    egress_inference_complete: bool = True
    egress_portals_truncated: bool = False
    wall_segments: tuple[LocalWallSegment, ...] = ()
    surface_transition_portals: tuple[LocalSurfaceTransitionPortal, ...] = ()
    egress_portals: tuple[LocalTopologicalEgressPortal, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.physical_surfaces
            or not self.physical_surfaces.issubset({"ground", "wmo", "doodad"})
        ):
            raise ValueError("local awareness physical surfaces are invalid")
        if not isfinite(self.probe_radius_yards) or not 1 <= self.probe_radius_yards <= 30:
            raise ValueError("local awareness probe radius is invalid")
        if not isinstance(self.overhead_clear, bool):
            raise ValueError("local awareness overhead state is invalid")
        if not 8 <= len(self.radial_probes) <= 64:
            raise ValueError("local awareness probe count is invalid")
        bearings = tuple(item.bearing_rad for item in self.radial_probes)
        if any(left >= right for left, right in zip(bearings, bearings[1:])):
            raise ValueError("local awareness probe order is invalid")
        if any(
            item.clearance_yards > self.probe_radius_yards + 0.01
            for item in self.radial_probes
        ):
            raise ValueError("local awareness clearance exceeds its probe radius")
        if (
            not isfinite(self.topology_radius_yards)
            or not 1 <= self.topology_radius_yards <= 100
            or not 0 <= self.component_polygon_count <= 2048
            or not isinstance(self.component_truncated, bool)
            or not isinstance(self.wall_segments_truncated, bool)
            or not isinstance(self.surface_transition_portals_truncated, bool)
            or not isinstance(self.egress_inference_complete, bool)
            or not isinstance(self.egress_portals_truncated, bool)
            or len(self.wall_segments) > 128
            or len(self.surface_transition_portals) > 64
            or len(self.egress_portals) > 32
        ):
            raise ValueError("local awareness topology is invalid")
        if self.surface_transition_portals and "wmo" not in self.physical_surfaces:
            raise ValueError("local awareness transitions require a WMO origin")
        if self.egress_portals and (
            "wmo" not in self.physical_surfaces
            or self.overhead_clear
        ):
            raise ValueError("local awareness egress evidence is inconsistent")

    @property
    def open_fraction(self) -> float:
        threshold = self.probe_radius_yards * 0.95
        return sum(
            item.clearance_yards >= threshold for item in self.radial_probes
        ) / len(self.radial_probes)

    @property
    def environment_class(self) -> str:
        if "wmo" in self.physical_surfaces:
            if self.egress_portals:
                return "WMO_STRUCTURE_WITH_EGRESS"
            return "WMO_STRUCTURE_OR_TRANSITION"
        if (
            self.physical_surfaces == frozenset({"ground"})
            and self.overhead_clear
            and self.open_fraction >= 0.75
        ):
            return "OPEN_GROUND"
        if not self.overhead_clear or self.open_fraction <= 0.25:
            return "CONFINED_STATIC_SPACE"
        return "STATIC_TRANSITION"

    @property
    def candidate_opening_bearings_rad(self) -> tuple[float, ...]:
        """Clear directions to validate against navmesh, never executable exits."""
        threshold = self.probe_radius_yards * 0.90
        return tuple(
            item.bearing_rad
            for item in self.radial_probes
            if item.clearance_yards >= threshold and item.navmesh_reachable
        )

@dataclass(frozen=True, slots=True)
class NavCorridor:
    map_name: str
    adt_x: int
    adt_y: int
    start: NavPoint
    stop: NavPoint
    points: tuple[NavPoint, ...]
    polygons: tuple[NavPolygon, ...] = ()
    portals: tuple[NavPortal, ...] = ()
    source: str = "client_asset_navmesh"
    execution_authority: bool = False
    complete: bool = True
    height_candidate_count: int = 1
    stop_height_candidate_count: int = 1
    requested_stop: NavPoint | None = None
    topology_gap_direct_shortcut_applied: bool = False
    doodad_avoidance_applied: bool = False
    doodad_detour_count: int = 0
    doodad_unresolved_segment_count: int = 0
    doodad_unresolved_blockers: tuple[tuple[float, float, float, float], ...] = ()
    clearance_inset_count: int = 0
    steep_polygons_penalized: int = 0
    doodad_polygons_penalized: int = 0
    movement_path_shortcut_count: int = 0
    observed_blocker_polygons_excluded: int = 0
    impassable_uphill_polygons_excluded: int = 0
    road_polygons_preferred: int = 0
    nearest_road_polygon_to_start: float | None = None
    road_polygon_bounds: tuple[float, float, float, float] | None = None
    search_vantage_radial_clear_count: int = 0
    search_vantage_radial_probe_count: int = 0
    search_vantage_radial_probe_radius: float = 0.0
    search_vantage_overhead_clear: bool = False
    search_vantage_physical_surfaces: frozenset[str] = frozenset()
    start_awareness: LocalStaticAwareness | None = None
    awareness_observed_monotonic_s: float | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.height_candidate_count <= 64:
            raise ValueError("start height candidate count is invalid")
        if not 1 <= self.stop_height_candidate_count <= 64:
            raise ValueError("stop height candidate count is invalid")
        if type(self.topology_gap_direct_shortcut_applied) is not bool:
            raise ValueError("topology-gap shortcut state is invalid")
        if self.complete and self.requested_stop is not None and self.stop.distance_2d(self.requested_stop) > 0.05:
            raise ValueError("complete corridor must reach its requested stop")
        if not self.complete and self.requested_stop is None:
            raise ValueError("partial corridor must retain its requested stop")
        if self.doodad_detour_count < 0 or self.doodad_avoidance_applied != (self.doodad_detour_count > 0):
            raise ValueError("doodad avoidance evidence is inconsistent")
        if self.doodad_unresolved_segment_count < 0:
            raise ValueError("doodad unresolved segment count is invalid")
        if (
            len(self.doodad_unresolved_blockers) > 8
            or any(
                len(blocker) != 4
                or any(not isfinite(value) for value in blocker)
                or not 1.0 <= blocker[3] <= 30.0
                for blocker in self.doodad_unresolved_blockers
            )
            or (
                self.doodad_unresolved_segment_count == 0
                and self.doodad_unresolved_blockers
            )
        ):
            raise ValueError("doodad unresolved blocker evidence is invalid")
        if self.clearance_inset_count < 0:
            raise ValueError("clearance inset count is invalid")
        if self.steep_polygons_penalized < 0:
            raise ValueError("steep polygon count is invalid")
        if self.doodad_polygons_penalized < 0:
            raise ValueError("doodad polygon count is invalid")
        if self.movement_path_shortcut_count < 0:
            raise ValueError("movement path shortcut count is invalid")
        if self.observed_blocker_polygons_excluded < 0:
            raise ValueError("observed blocker polygon count is invalid")
        if self.impassable_uphill_polygons_excluded < 0:
            raise ValueError("impassable uphill polygon count is invalid")
        if self.road_polygons_preferred < 0:
            raise ValueError("preferred road polygon count is invalid")
        if self.nearest_road_polygon_to_start is not None and (
            not isfinite(self.nearest_road_polygon_to_start)
            or self.nearest_road_polygon_to_start < 0
        ):
            raise ValueError("nearest road polygon distance is invalid")
        if self.road_polygon_bounds is not None and (
            len(self.road_polygon_bounds) != 4
            or any(not isfinite(value) for value in self.road_polygon_bounds)
            or self.road_polygon_bounds[0] > self.road_polygon_bounds[2]
            or self.road_polygon_bounds[1] > self.road_polygon_bounds[3]
        ):
            raise ValueError("road polygon bounds are invalid")
        if (
            self.search_vantage_radial_clear_count < 0
            or self.search_vantage_radial_probe_count < 0
            or self.search_vantage_radial_clear_count
            > self.search_vantage_radial_probe_count
            or not isfinite(self.search_vantage_radial_probe_radius)
            or self.search_vantage_radial_probe_radius < 0
        ):
            raise ValueError("search vantage evidence is invalid")
        if not self.search_vantage_physical_surfaces.issubset(
            {"ground", "wmo", "doodad"}
        ):
            raise ValueError("search vantage physical surfaces are invalid")
        if self.awareness_observed_monotonic_s is not None and (
            self.start_awareness is None
            or not isfinite(self.awareness_observed_monotonic_s)
            or self.awareness_observed_monotonic_s < 0
        ):
            raise ValueError("corridor awareness observation time is invalid")
        if self.polygons:
            if tuple(item.index for item in self.polygons) != tuple(range(len(self.polygons))):
                raise ValueError("nav corridor polygon order is invalid")
            if len(self.portals) != len(self.polygons) - 1:
                raise ValueError("nav corridor portal count is invalid")
            if any(
                portal.from_index != index or portal.to_index != index + 1
                for index, portal in enumerate(self.portals)
            ):
                raise ValueError("nav corridor portal order is invalid")

    @property
    def geometry_aware(self) -> bool:
        return bool(self.polygons) and len(self.portals) == len(self.polygons) - 1

    @property
    def minimum_portal_width(self) -> float | None:
        return min((portal.width for portal in self.portals), default=None)

    def portal_lateral_clearance_at(
        self,
        position: NavPoint,
        *,
        actor_radius_yards: float = 0.55,
        safety_margin_yards: float = 0.35,
        association_distance_yards: float = 8.0,
    ) -> PortalLateralClearance | None:
        """Measure edge space from the nearest attached portal.

        This is deliberately a local witness, not a route waypoint.  It is
        useful on bridges, stairs and doorways where a centreline alone does
        not say how much room remains before the player capsule reaches an
        edge.  If no nearby portal exists, the safe answer is ``None``.
        """

        values = (
            position.x,
            position.y,
            position.z,
            actor_radius_yards,
            safety_margin_yards,
            association_distance_yards,
        )
        if (
            any(not isfinite(value) for value in values)
            or actor_radius_yards <= 0
            or actor_radius_yards > 2.0
            or safety_margin_yards < 0
            or safety_margin_yards > 2.0
            or not 1.0 <= association_distance_yards <= 20.0
        ):
            raise ValueError("portal lateral clearance query is invalid")
        if not self.geometry_aware:
            return None

        candidates: list[tuple[float, int, NavPortal]] = []
        for index, portal in enumerate(self.portals):
            midpoint = NavPoint(
                (portal.left.x + portal.right.x) * 0.5,
                (portal.left.y + portal.right.y) * 0.5,
                (portal.left.z + portal.right.z) * 0.5,
            )
            distance = position.distance_2d(midpoint)
            if (
                distance <= association_distance_yards
                and abs(position.z - midpoint.z) <= 3.0
            ):
                candidates.append((distance, index, portal))
        if not candidates:
            return None
        _, index, portal = min(candidates, key=lambda item: (item[0], item[1]))

        dx = portal.right.x - portal.left.x
        dy = portal.right.y - portal.left.y
        length_squared = dx * dx + dy * dy
        if length_squared <= 0.0025:
            return None
        fraction = (
            (position.x - portal.left.x) * dx
            + (position.y - portal.left.y) * dy
        ) / length_squared
        fraction = max(0.0, min(1.0, fraction))
        return PortalLateralClearance(
            portal_index=index,
            width_yards=portal.width,
            left_edge_clearance_yards=portal.width * fraction,
            right_edge_clearance_yards=portal.width * (1.0 - fraction),
            actor_radius_yards=actor_radius_yards,
            safety_margin_yards=safety_margin_yards,
        )

    def search_vantage_rejection(self) -> str | None:
        """Explain why the requested stop is unsuitable for open-space hunting.

        The evidence comes exclusively from immutable client geometry: Detour's
        terminal polygon plus bounded radial and overhead collision rays.  An
        absent/older worker contract is rejected rather than treated as open.
        """
        surfaces = self.search_vantage_physical_surfaces
        if not surfaces:
            return "requested_endpoint_surface_evidence_missing"
        if "ground" not in surfaces or surfaces.intersection({"wmo", "doodad"}):
            return "requested_endpoint_is_not_open_terrain"
        if self.search_vantage_radial_probe_count < 8:
            return "radial_clearance_evidence_missing"
        if self.search_vantage_radial_probe_radius < 6.0:
            return "radial_clearance_radius_too_small"
        if (
            self.search_vantage_radial_clear_count
            / self.search_vantage_radial_probe_count
            < 0.75
        ):
            return "radial_clearance_is_occluded"
        if not self.search_vantage_overhead_clear:
            return "camera_overhead_clearance_is_occluded"
        return None

    def guidance_points(self) -> tuple[NavPoint, ...]:
        """Return the worker's Detour-validated, layer-projected movement path.

        Polygon portals remain attached as geometry and clearance evidence.
        Steering through every portal midpoint recreates the unsmoothed polygon
        corridor and can introduce severe zig-zags that are absent from the
        funnel path.  A same-floor spatial revisit is also erased here.  Such a
        loop cannot advance a shortest path and caused the controller to walk
        back over the crypt floor before taking the real stair transition.
        Height-separated switchbacks remain intact, so stairs, bridges and
        stacked WMO floors are never flattened into an unsafe XY shortcut.
        """
        return _erase_same_floor_revisits(self.points)


def _erase_same_floor_revisits(
    points: tuple[NavPoint, ...],
    *,
    revisit_radius_yards: float = 0.80,
    floor_tolerance_yards: float = 0.75,
) -> tuple[NavPoint, ...]:
    """Erase true spatial loops while preserving vertical topology."""

    if len(points) < 4:
        return points
    result: list[NavPoint] = []
    for point in points:
        revisit_index: int | None = None
        # Ignore adjacent geometry: funnel points can be densely sampled and
        # collapsing those would change an ordinary curve rather than a loop.
        for index in range(len(result) - 3, -1, -1):
            previous = result[index]
            if (
                previous.distance_2d(point) <= revisit_radius_yards
                and abs(previous.z - point.z) <= floor_tolerance_yards
            ):
                revisit_index = index
                break
        if revisit_index is not None:
            del result[revisit_index + 1:]
        if not result or result[-1].distance_2d(point) > 0.01 or abs(
            result[-1].z - point.z
        ) > 0.01:
            result.append(point)
    return tuple(result)


@runtime_checkable
class ClientNavmeshQuery(Protocol):
    # Adapters that return start-surface evidence can opt into the bounded
    # structure-exit anchor refinement.  Legacy/test navigators remain on the
    # baseline graph-midpoint proposal.
    surface_evidence_available: bool

    def for_structure_egress(
        self,
        *,
        bounds: tuple[float, float, float, float, float, float],
    ) -> ClientNavmeshQuery: ...

    def find_corridor(
        self,
        *,
        map_name: str,
        start: NavPoint,
        stop_x: float,
        stop_y: float,
        stop_z: float | None = None,
    ) -> NavCorridor: ...
