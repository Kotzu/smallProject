from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite

from perfect_assassin.movement.client_navmesh import (
    LocalWallSegment,
    NavCorridor,
    NavPoint,
)


@dataclass(frozen=True, slots=True)
class ConditionalTraversalFrontier:
    """A disconnected interior frontier, never an executable shortcut.

    Client assets can prove that Detour topology ends at this point, but they
    cannot prove that a door, gate, lift, script, or encounter is traversable.
    Live client-visible evidence is mandatory before interaction or replanning
    across the boundary.
    """

    map_name: str
    frontier: NavPoint
    requested_stop: NavPoint
    kind: str
    remaining_distance_yards: float
    requested_vertical_delta_yards: float
    boundary_segments: tuple[LocalWallSegment, ...]
    source: str = "client_asset_disconnected_wmo_topology"
    requires_live_visible_confirmation: bool = True
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if not self.map_name or len(self.map_name) > 64:
            raise ValueError("conditional frontier map is invalid")
        if self.kind not in {
            "POSSIBLE_WMO_DOOR_OR_GATE",
            "POSSIBLE_WMO_DOOR_GATE_OR_FLOOR_TRANSITION",
        }:
            raise ValueError("conditional frontier kind is invalid")
        if (
            not isfinite(self.remaining_distance_yards)
            or self.remaining_distance_yards <= 0
            or not isfinite(self.requested_vertical_delta_yards)
            or self.requested_vertical_delta_yards < 0
            or len(self.boundary_segments) > 32
        ):
            raise ValueError("conditional frontier geometry is invalid")
        if (
            not self.requires_live_visible_confirmation
            or self.execution_authority
        ):
            raise ValueError("conditional frontier cannot grant authority")


def infer_conditional_traversal_frontier(
    corridor: NavCorridor,
    *,
    maximum_stalled_progress_yards: float = 0.75,
    minimum_remaining_distance_yards: float = 2.0,
    boundary_radius_yards: float = 12.0,
) -> ConditionalTraversalFrontier | None:
    """Classify a stalled WMO frontier without claiming what blocks it."""

    bounds = (
        maximum_stalled_progress_yards,
        minimum_remaining_distance_yards,
        boundary_radius_yards,
    )
    if any(not isfinite(value) or value <= 0 for value in bounds):
        raise ValueError("conditional frontier bounds are invalid")
    if corridor.complete or corridor.requested_stop is None:
        return None
    awareness = corridor.start_awareness
    if awareness is None or "wmo" not in awareness.physical_surfaces:
        return None
    # A verified egress is already a normal route candidate, not a speculative
    # interaction point.
    if awareness.egress_portals:
        return None
    progress = corridor.start.distance_2d(corridor.stop)
    vertical_delta = abs(corridor.requested_stop.z - corridor.stop.z)
    remaining = hypot(
        corridor.stop.distance_2d(corridor.requested_stop), vertical_delta,
    )
    if (
        progress > maximum_stalled_progress_yards
        or remaining < minimum_remaining_distance_yards
    ):
        return None
    kind = (
        "POSSIBLE_WMO_DOOR_GATE_OR_FLOOR_TRANSITION"
        if vertical_delta > 3.0
        else "POSSIBLE_WMO_DOOR_OR_GATE"
    )
    boundary_segments = tuple(
        sorted(
            (
                segment for segment in awareness.wall_segments
                if segment.distance_yards <= boundary_radius_yards
            ),
            key=lambda segment: segment.distance_yards,
        )[:32]
    )
    return ConditionalTraversalFrontier(
        map_name=corridor.map_name,
        frontier=corridor.stop,
        requested_stop=corridor.requested_stop,
        kind=kind,
        remaining_distance_yards=remaining,
        requested_vertical_delta_yards=vertical_delta,
        boundary_segments=boundary_segments,
    )
