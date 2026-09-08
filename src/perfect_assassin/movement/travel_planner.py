from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from typing import Literal


TravelMethod = Literal["ARRIVED", "HEARTHSTONE", "KNOWN_TRANSPORT", "NAVMESH", "EXPLORE"]


@dataclass(frozen=True, slots=True)
class SemanticLocation:
    location_id: str
    map_name: str
    x: float
    y: float
    arrival_radius_yards: float
    provenance: str
    confidence: float

    def __post_init__(self) -> None:
        if not self.location_id or not self.map_name or not self.provenance:
            raise ValueError("semantic location identity is invalid")
        if any(not isfinite(value) for value in (self.x, self.y, self.arrival_radius_yards)):
            raise ValueError("semantic location geometry is invalid")
        if not 0.5 <= self.arrival_radius_yards <= 100 or not 0 <= self.confidence <= 1:
            raise ValueError("semantic location radius or confidence is invalid")


@dataclass(frozen=True, slots=True)
class TravelState:
    map_name: str
    x: float
    y: float
    hearth_bound_location_id: str | None
    hearth_ready: bool
    known_transport_destination_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class TravelPlan:
    destination: SemanticLocation
    method: TravelMethod
    reason: str
    requires_navmesh: bool
    execution_authority: bool = False


class SemanticTravelPlanner:
    """Chooses travel mode from state and knowledge; never embeds a patrol route."""

    def plan(self, *, state: TravelState, destination: SemanticLocation) -> TravelPlan:
        if state.map_name == destination.map_name and hypot(
            state.x - destination.x, state.y - destination.y
        ) <= destination.arrival_radius_yards:
            return TravelPlan(destination, "ARRIVED", "already_inside_destination_radius", False)
        if (
            state.hearth_ready
            and state.hearth_bound_location_id == destination.location_id
        ):
            return TravelPlan(destination, "HEARTHSTONE", "ready_bind_matches_destination", False)
        if destination.location_id in state.known_transport_destination_ids:
            return TravelPlan(destination, "KNOWN_TRANSPORT", "known_transport_reaches_destination", False)
        if destination.confidence >= 0.8:
            return TravelPlan(destination, "NAVMESH", "known_destination_requires_world_route", True)
        return TravelPlan(destination, "EXPLORE", "destination_position_is_not_reliable", False)
