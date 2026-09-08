from __future__ import annotations

from dataclasses import dataclass
from math import atan2, isfinite, tau
from typing import Any

from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    NavPoint,
)
from perfect_assassin.movement.world_structure_index import (
    WorldStructureSpatialIndex,
)


@dataclass(frozen=True, slots=True)
class StructureContainmentEvidence:
    structure_id: str
    asset_path: str
    nav_coverage: str
    evidence: str = "AABB_3D_PLUS_WMO_NAV_SURFACE"
    confidence: float = 0.95

    def __post_init__(self) -> None:
        if (
            not self.structure_id
            or not self.asset_path
            or self.nav_coverage not in {"FULL", "PARTIAL", "NONE", "GLOBAL_WMO"}
            or self.evidence != "AABB_3D_PLUS_WMO_NAV_SURFACE"
            or self.confidence != 0.95
        ):
            raise ValueError("structure containment evidence is invalid")


@dataclass(frozen=True, slots=True)
class EnvironmentBoundary:
    left: NavPoint
    right: NavPoint
    midpoint: NavPoint
    bearing_rad: float
    distance_yards: float
    length_yards: float
    kind: str = "NAVMESH_COMPONENT_BOUNDARY"
    physical_wall_semantics: str = "CANDIDATE_NOT_OBJECT_CLASSIFIED"
    topology_confidence: float = 1.0

    def __post_init__(self) -> None:
        values = (
            self.left.x, self.left.y, self.left.z,
            self.right.x, self.right.y, self.right.z,
            self.midpoint.x, self.midpoint.y, self.midpoint.z,
            self.bearing_rad, self.distance_yards, self.length_yards,
        )
        if (
            any(not isfinite(value) for value in values)
            or not 0.0 <= self.bearing_rad < tau
            or self.distance_yards < 0
            or self.length_yards <= 0
            or self.kind != "NAVMESH_COMPONENT_BOUNDARY"
            or self.physical_wall_semantics != "CANDIDATE_NOT_OBJECT_CLASSIFIED"
            or self.topology_confidence != 1.0
        ):
            raise ValueError("environment boundary evidence is invalid")


@dataclass(frozen=True, slots=True)
class VerifiedEnvironmentEgress:
    left: NavPoint
    right: NavPoint
    midpoint: NavPoint
    bearing_rad: float
    width_yards: float
    distance_yards: float
    route_distance_yards: float
    from_surfaces: frozenset[str]
    to_surfaces: frozenset[str]
    kind: str = "VERIFIED_TOPOLOGICAL_EGRESS"
    route_verified: bool = True
    topology_confidence: float = 1.0

    def __post_init__(self) -> None:
        allowed = {"ground", "wmo", "doodad"}
        values = (
            self.left.x, self.left.y, self.left.z,
            self.right.x, self.right.y, self.right.z,
            self.midpoint.x, self.midpoint.y, self.midpoint.z,
            self.bearing_rad, self.width_yards,
            self.distance_yards, self.route_distance_yards,
        )
        if (
            any(not isfinite(value) for value in values)
            or not 0.0 <= self.bearing_rad < tau
            or self.width_yards <= 0
            or self.distance_yards < 0
            or self.route_distance_yards < 0
            or not self.from_surfaces
            or not self.to_surfaces
            or not self.from_surfaces.issubset(allowed)
            or not self.to_surfaces.issubset(allowed)
            or self.kind != "VERIFIED_TOPOLOGICAL_EGRESS"
            or not self.route_verified
            or self.topology_confidence != 1.0
        ):
            raise ValueError("verified environment egress is invalid")


@dataclass(frozen=True, slots=True)
class LocalEnvironmentAwareness:
    map_name: str
    observed_monotonic_s: float
    position: NavPoint
    environment_state: str
    environment_confidence: float
    physical_surfaces: frozenset[str]
    topology_complete: bool
    containing_structures: tuple[StructureContainmentEvidence, ...]
    boundaries: tuple[EnvironmentBoundary, ...]
    verified_egresses: tuple[VerifiedEnvironmentEgress, ...]
    candidate_opening_bearings_rad: tuple[float, ...]
    nearby_wmo_count: int
    nearby_static_obstacle_count: int
    source: str = "WORLD_PACK_STRUCTURE_INDEX_PLUS_DETOUR_BVH"
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.map_name
            or not isfinite(self.observed_monotonic_s)
            or any(not isfinite(value) for value in (
                self.position.x, self.position.y, self.position.z,
            ))
        ):
            raise ValueError("local environment identity or time is invalid")
        if self.environment_state not in {
            "INSIDE_STATIC_WMO",
            "OPEN_GROUND",
            "CONFINED_STATIC_SPACE",
            "STATIC_TRANSITION",
            "WMO_TRANSITION_OR_UNRESOLVED",
        }:
            raise ValueError("local environment state is invalid")
        if not 0.0 <= self.environment_confidence <= 1.0:
            raise ValueError("local environment confidence is invalid")
        if not self.physical_surfaces.issubset({"ground", "wmo", "doodad"}):
            raise ValueError("local environment surfaces are invalid")
        if any(
            not isfinite(value) or not 0.0 <= value < tau
            for value in self.candidate_opening_bearings_rad
        ):
            raise ValueError("local environment opening bearing is invalid")
        if self.nearby_wmo_count < 0 or self.nearby_static_obstacle_count < 0:
            raise ValueError("local environment structure count is invalid")
        if self.execution_authority:
            raise ValueError("local environment awareness cannot grant authority")

    def to_record(self) -> dict[str, Any]:
        point = lambda value: [value.x, value.y, value.z]
        return {
            "record_type": "local_environment_awareness",
            "schema_version": "1.0",
            "map_name": self.map_name,
            "observed_monotonic_s": self.observed_monotonic_s,
            "position": point(self.position),
            "environment_state": self.environment_state,
            "environment_confidence": self.environment_confidence,
            "physical_surfaces": sorted(self.physical_surfaces),
            "topology_complete": self.topology_complete,
            "containing_structures": [{
                "structure_id": item.structure_id,
                "asset_path": item.asset_path,
                "nav_coverage": item.nav_coverage,
                "evidence": item.evidence,
                "confidence": item.confidence,
            } for item in self.containing_structures],
            "boundaries": [{
                "left": point(item.left),
                "right": point(item.right),
                "midpoint": point(item.midpoint),
                "bearing_rad": item.bearing_rad,
                "distance_yards": item.distance_yards,
                "length_yards": item.length_yards,
                "kind": item.kind,
                "physical_wall_semantics": item.physical_wall_semantics,
                "topology_confidence": item.topology_confidence,
            } for item in self.boundaries],
            "verified_egresses": [{
                "left": point(item.left),
                "right": point(item.right),
                "midpoint": point(item.midpoint),
                "bearing_rad": item.bearing_rad,
                "width_yards": item.width_yards,
                "distance_yards": item.distance_yards,
                "route_distance_yards": item.route_distance_yards,
                "from_surfaces": sorted(item.from_surfaces),
                "to_surfaces": sorted(item.to_surfaces),
                "kind": item.kind,
                "route_verified": item.route_verified,
                "topology_confidence": item.topology_confidence,
            } for item in self.verified_egresses],
            "candidate_opening_bearings_rad": list(
                self.candidate_opening_bearings_rad
            ),
            "nearby_wmo_count": self.nearby_wmo_count,
            "nearby_static_obstacle_count": self.nearby_static_obstacle_count,
            "source": self.source,
            "execution_authority": False,
        }


def _midpoint(left: NavPoint, right: NavPoint) -> NavPoint:
    return NavPoint(
        (left.x + right.x) / 2.0,
        (left.y + right.y) / 2.0,
        (left.z + right.z) / 2.0,
    )


def _bearing(origin: NavPoint, target: NavPoint) -> float:
    return atan2(target.y - origin.y, target.x - origin.x) % tau


def build_local_environment_awareness(
    *,
    map_name: str,
    observed_monotonic_s: float,
    position: NavPoint,
    nav_awareness: LocalStaticAwareness,
    structures: WorldStructureSpatialIndex,
    nearby_radius_yards: float = 100.0,
) -> LocalEnvironmentAwareness:
    if (
        not map_name
        or not isfinite(observed_monotonic_s)
        or observed_monotonic_s < 0
        or not isfinite(nearby_radius_yards)
        or not 1.0 <= nearby_radius_yards <= 1_000.0
    ):
        raise ValueError("local environment request is invalid")
    nearby = structures.nearby(
        x=position.x,
        y=position.y,
        z=position.z,
        radius_yards=nearby_radius_yards,
    )
    containing_wmos = tuple(
        hit for hit in nearby
        if hit.structure.kind == "WMO" and hit.contains_3d is True
    )
    containment = tuple(
        StructureContainmentEvidence(
            structure_id=hit.structure.structure_id,
            asset_path=hit.structure.asset_path,
            nav_coverage=hit.structure.nav_coverage,
        )
        for hit in containing_wmos
    )
    # The overhead ray is deliberately short (it is a local camera/clearance
    # probe, not a room-height measurement).  A tall WMO can therefore have a
    # clear ray for the whole probe while the resolved nav polygon is still
    # unambiguously on the WMO surface and inside its immutable 3D bounds.
    # Containment plus the WMO surface is sufficient for the structure claim;
    # keep ``overhead_clear`` as an independent ceiling/camera signal.
    inside_supported = bool(
        containment and "wmo" in nav_awareness.physical_surfaces
    )
    if inside_supported:
        state, confidence = "INSIDE_STATIC_WMO", 0.95
    elif "wmo" in nav_awareness.physical_surfaces:
        state, confidence = "WMO_TRANSITION_OR_UNRESOLVED", 0.60
    elif nav_awareness.environment_class == "OPEN_GROUND":
        state, confidence = "OPEN_GROUND", 0.95
    elif nav_awareness.environment_class == "CONFINED_STATIC_SPACE":
        state, confidence = "CONFINED_STATIC_SPACE", 0.75
    else:
        state, confidence = "STATIC_TRANSITION", 0.65

    boundaries = []
    for item in nav_awareness.wall_segments:
        midpoint = _midpoint(item.left, item.right)
        boundaries.append(EnvironmentBoundary(
            left=item.left,
            right=item.right,
            midpoint=midpoint,
            bearing_rad=_bearing(position, midpoint),
            distance_yards=item.distance_yards,
            length_yards=item.left.distance_2d(item.right),
        ))
    egresses = []
    for item in nav_awareness.egress_portals:
        midpoint = _midpoint(item.left, item.right)
        egresses.append(VerifiedEnvironmentEgress(
            left=item.left,
            right=item.right,
            midpoint=midpoint,
            bearing_rad=_bearing(position, midpoint),
            width_yards=item.width_yards,
            distance_yards=item.distance_yards,
            route_distance_yards=item.route_distance_yards,
            from_surfaces=item.from_surfaces,
            to_surfaces=item.to_surfaces,
        ))
    topology_complete = not any((
        nav_awareness.component_truncated,
        nav_awareness.wall_segments_truncated,
        nav_awareness.surface_transition_portals_truncated,
        not nav_awareness.egress_inference_complete,
        nav_awareness.egress_portals_truncated,
    ))
    return LocalEnvironmentAwareness(
        map_name=map_name,
        observed_monotonic_s=observed_monotonic_s,
        position=position,
        environment_state=state,
        environment_confidence=confidence,
        physical_surfaces=nav_awareness.physical_surfaces,
        topology_complete=topology_complete,
        containing_structures=containment,
        boundaries=tuple(sorted(
            boundaries, key=lambda item: (item.distance_yards, item.bearing_rad),
        )),
        verified_egresses=tuple(sorted(
            egresses, key=lambda item: (item.route_distance_yards, item.bearing_rad),
        )),
        candidate_opening_bearings_rad=nav_awareness.candidate_opening_bearings_rad,
        nearby_wmo_count=sum(hit.structure.kind == "WMO" for hit in nearby),
        nearby_static_obstacle_count=sum(
            hit.structure.kind == "DOODAD" for hit in nearby
        ),
    )
