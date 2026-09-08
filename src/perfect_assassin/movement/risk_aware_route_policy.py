from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from typing import Literal

from perfect_assassin.movement.road_semantic_planner import (
    RoadWorldPoint,
    SemanticRoadRoute,
)
from perfect_assassin.movement.world_model import HistoricalRiskArea


ThreatSource = Literal["LIVE_VISIBLE", "REMEMBERED_OBSERVED"]


@dataclass(frozen=True, slots=True)
class TravelCapability:
    """Only current, visible gameplay state that affects travel risk."""

    level: int
    health_fraction: float
    stealth_ready: bool
    escape_ready: bool

    def __post_init__(self) -> None:
        if not 1 <= self.level <= 100:
            raise ValueError("travel capability level is invalid")
        if not isfinite(self.health_fraction) or not 0.05 <= self.health_fraction <= 1.0:
            raise ValueError("travel capability health fraction is invalid")


@dataclass(frozen=True, slots=True)
class ObservedRouteThreat:
    """A bounded risk record, never a fabricated remote entity location."""

    x: float
    y: float
    radius_yards: float
    severity: float
    observed_at_s: float
    expires_at_s: float
    source: ThreatSource

    def __post_init__(self) -> None:
        if any(not isfinite(value) for value in (
            self.x, self.y, self.radius_yards, self.severity,
            self.observed_at_s, self.expires_at_s,
        )):
            raise ValueError("observed route threat is non-finite")
        if not 1.0 <= self.radius_yards <= 100.0:
            raise ValueError("observed route threat radius is invalid")
        if not 0.0 < self.severity <= 5.0:
            raise ValueError("observed route threat severity is invalid")
        if self.expires_at_s <= self.observed_at_s:
            raise ValueError("observed route threat expiry is invalid")


@dataclass(frozen=True, slots=True)
class TravelRouteCandidate:
    """A route candidate from global semantics, before local Detour execution."""

    route_id: str
    points: tuple[RoadWorldPoint, ...]
    road_fraction: float
    terrain_difficulty: float
    unexplored_fraction: float
    topographic_validation_fraction: float = 0.0

    def __post_init__(self) -> None:
        if not self.route_id or len(self.points) < 2:
            raise ValueError("travel route candidate identity or points are invalid")
        if any(
            not isfinite(value) or not 0.0 <= value <= 1.0
            for value in (
                self.road_fraction,
                self.terrain_difficulty,
                self.unexplored_fraction,
                self.topographic_validation_fraction,
            )
        ):
            raise ValueError("travel route candidate risk fields are invalid")

    @property
    def distance_yards(self) -> float:
        return sum(
            hypot(right.x - left.x, right.y - left.y)
            for left, right in zip(self.points, self.points[1:])
        )


@dataclass(frozen=True, slots=True)
class RouteEvaluation:
    route_id: str
    distance_yards: float
    travel_time_seconds: float
    risk_score: float
    expected_delay_seconds: float
    expected_arrival_seconds: float
    within_risk_budget: bool
    topographically_eligible: bool


@dataclass(frozen=True, slots=True)
class RoutePolicyDecision:
    selected: RouteEvaluation
    alternatives: tuple[RouteEvaluation, ...]
    risk_budget: float
    reason: str
    dynamic_knowledge: str = "OBSERVED_ONLY_FOG_OF_WAR"
    execution_authority: bool = False


def semantic_route_candidate(
    route: SemanticRoadRoute,
    *,
    unexplored_fraction: float = 0.0,
) -> TravelRouteCandidate:
    """Convert an atlas A* variant into a risk-scored, non-executable route."""

    points = (route.start, *route.waypoints, route.destination)
    deduplicated = tuple(
        point for index, point in enumerate(points)
        if index == 0
        or point.x != points[index - 1].x
        or point.y != points[index - 1].y
    )
    cell_count = (
        route.road_cell_count
        + route.near_road_cell_count
        + route.offroad_bridge_cell_count
    )
    if cell_count <= 0:
        raise ValueError("semantic route has no cells for risk evaluation")
    road_fraction = route.road_cell_count / cell_count
    terrain_difficulty = min(
        1.0,
        (
            0.25 * route.near_road_cell_count
            + 0.85 * route.offroad_bridge_cell_count
        ) / cell_count,
    )
    return TravelRouteCandidate(
        route_id=route.profile_id,
        points=deduplicated,
        road_fraction=road_fraction,
        terrain_difficulty=terrain_difficulty,
        unexplored_fraction=unexplored_fraction,
    )


def _point_segment_distance(
    *, x: float, y: float, left: RoadWorldPoint, right: RoadWorldPoint,
) -> float:
    dx, dy = right.x - left.x, right.y - left.y
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return hypot(x - left.x, y - left.y)
    projected = max(
        0.0,
        min(1.0, ((x - left.x) * dx + (y - left.y) * dy) / length_squared),
    )
    return hypot(x - (left.x + projected * dx), y - (left.y + projected * dy))


def _threat_exposure(
    candidate: TravelRouteCandidate,
    threats: tuple[ObservedRouteThreat, ...],
    *,
    now_s: float,
) -> float:
    exposure = 0.0
    for threat in threats:
        if threat.expires_at_s <= now_s:
            continue
        nearest = min(
            _point_segment_distance(
                x=threat.x, y=threat.y, left=left, right=right,
            )
            for left, right in zip(candidate.points, candidate.points[1:])
        )
        if nearest < threat.radius_yards:
            exposure += threat.severity * (1.0 - nearest / threat.radius_yards)
    return exposure


def _historical_risk_exposure(
    candidate: TravelRouteCandidate,
    areas: tuple[HistoricalRiskArea, ...],
) -> float:
    """Use permanent experience as regional risk, never as live remote ESP."""

    exposure = 0.0
    for area in areas:
        nearest = min(
            _point_segment_distance(
                x=area.x, y=area.y, left=left, right=right,
            )
            for left, right in zip(candidate.points, candidate.points[1:])
        )
        if nearest < area.radius_yards:
            exposure += 0.30 * area.risk_score * (1.0 - nearest / area.radius_yards)
    return exposure


def _vulnerability(capability: TravelCapability) -> float:
    level_factor = min(capability.level, 60) / 60.0
    value = (1.35 - 0.45 * level_factor) * (1.70 - 0.70 * capability.health_fraction)
    if capability.stealth_ready:
        value *= 0.55
    if capability.escape_ready:
        value *= 0.75
    return value


def _risk_budget(capability: TravelCapability) -> float:
    level_factor = min(capability.level, 60) / 60.0
    return (
        0.20
        + 0.55 * level_factor
        + 0.25 * capability.health_fraction
        + (0.20 if capability.stealth_ready else 0.0)
        + (0.15 if capability.escape_ready else 0.0)
    )


class RiskAwareRoutePolicy:
    """Choose the lowest expected arrival time inside an adaptive risk budget.

    Global routes come from roads, operator waypoints, or other offline
    geometry. The policy never invents entities beyond the observed visibility
    set. An expired live coordinate cannot impersonate a current entity, but
    its permanent observation remains as a modest regional risk prior.
    """

    TRAVEL_SPEED_YARDS_PER_SECOND = 7.0
    RISK_DELAY_SCALE_SECONDS = 25.0
    OFFROAD_NAVIGATION_DELAY_SECONDS_PER_YARD = 0.015
    INDETERMINATE_RISK_MARGIN = 0.05
    MAX_UNVALIDATED_TERRAIN_DIFFICULTY = 0.20
    MIN_TOPOGRAPHIC_VALIDATION_FRACTION = 0.95

    def choose(
        self,
        *,
        candidates: tuple[TravelRouteCandidate, ...],
        capability: TravelCapability,
        observed_threats: tuple[ObservedRouteThreat, ...] = (),
        historical_risk_areas: tuple[HistoricalRiskArea, ...] = (),
        now_s: float,
    ) -> RoutePolicyDecision:
        if not candidates or len({item.route_id for item in candidates}) != len(candidates):
            raise ValueError("route candidates must be non-empty and uniquely named")
        if not isfinite(now_s):
            raise ValueError("route policy time is invalid")
        budget = _risk_budget(capability)
        vulnerability = _vulnerability(capability)
        evaluations: list[RouteEvaluation] = []
        for candidate in candidates:
            distance = candidate.distance_yards
            if distance <= 0.0:
                raise ValueError("route candidate has no traversable length")
            # Stealth and escape tools reduce encounter exposure; they do not
            # make an unknown hillside, ravine or forest chord easier to
            # navigate. Keep topographic difficulty outside the combat
            # vulnerability multiplier.
            encounter_risk = (
                0.35 * candidate.unexplored_fraction
                + _threat_exposure(candidate, observed_threats, now_s=now_s)
                + _historical_risk_exposure(candidate, historical_risk_areas)
            )
            risk_score = candidate.terrain_difficulty + encounter_risk * vulnerability
            topographically_eligible = (
                candidate.terrain_difficulty
                <= self.MAX_UNVALIDATED_TERRAIN_DIFFICULTY
                or candidate.topographic_validation_fraction
                >= self.MIN_TOPOGRAPHIC_VALIDATION_FRACTION
            )
            travel_time = distance / self.TRAVEL_SPEED_YARDS_PER_SECOND
            navigation_delay = (
                distance
                * (1.0 - candidate.road_fraction)
                * self.OFFROAD_NAVIGATION_DELAY_SECONDS_PER_YARD
            )
            expected_delay = self.RISK_DELAY_SCALE_SECONDS * risk_score * risk_score
            evaluations.append(RouteEvaluation(
                route_id=candidate.route_id,
                distance_yards=distance,
                travel_time_seconds=travel_time + navigation_delay,
                risk_score=risk_score,
                expected_delay_seconds=expected_delay,
                expected_arrival_seconds=travel_time + navigation_delay + expected_delay,
                within_risk_budget=(
                    risk_score <= budget and topographically_eligible
                ),
                topographically_eligible=topographically_eligible,
            ))
        evaluations.sort(key=lambda item: (item.expected_arrival_seconds, item.route_id))
        eligible = [item for item in evaluations if item.topographically_eligible]
        if not eligible:
            raise ValueError("no route candidate has sufficient topographic evidence")
        acceptable = [item for item in eligible if item.within_risk_budget]
        if acceptable:
            selected = acceptable[0]
        else:
            lowest_risk = min(item.risk_score for item in eligible)
            candidates_by_id = {item.route_id: item for item in candidates}
            indistinguishable = tuple(
                item
                for item in eligible
                if item.risk_score <= lowest_risk + self.INDETERMINATE_RISK_MARGIN
            )
            selected = min(
                indistinguishable,
                key=lambda item: (
                    -candidates_by_id[item.route_id].road_fraction,
                    item.risk_score,
                    item.expected_arrival_seconds,
                    item.route_id,
                ),
            )
        shortest = min(evaluations, key=lambda item: (item.distance_yards, item.route_id))
        rejected_shortest = not shortest.topographically_eligible
        if rejected_shortest and selected.route_id != shortest.route_id:
            reason = (
                "unvalidated_offroad_rejected_prefer_topographic_road_evidence"
            )
        elif not acceptable and len(indistinguishable) > 1:
            reason = (
                "no_candidate_is_within_risk_budget_prefer_road_when_"
                "known_risk_is_indistinguishable"
            )
        elif not acceptable:
            reason = "no_candidate_is_within_risk_budget_choose_lowest_known_risk"
        elif selected.route_id == shortest.route_id:
            reason = "shortest_route_has_lowest_expected_arrival_inside_risk_budget"
        else:
            reason = "longer_route_reduces_expected_known_risk_delay"
        return RoutePolicyDecision(
            selected=selected,
            alternatives=tuple(evaluations),
            risk_budget=budget,
            reason=reason,
        )
