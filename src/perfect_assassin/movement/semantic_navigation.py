from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot, isfinite

from perfect_assassin.movement.client_navmesh import (
    ClientNavmeshQuery,
    NavCorridor,
    NavPoint,
)
from perfect_assassin.movement.road_semantic_planner import (
    ClientRoadSemanticPlanner,
    RoadWorldPoint,
    SemanticRoadRoute,
)
from perfect_assassin.movement.risk_aware_route_policy import (
    ObservedRouteThreat,
    RiskAwareRoutePolicy,
    RoutePolicyDecision,
    TravelCapability,
    semantic_route_candidate,
)
from perfect_assassin.movement.world_model import HistoricalRiskArea


@dataclass(frozen=True, slots=True)
class SemanticNavStage:
    index: int
    requested_x: float
    requested_y: float
    corridor: NavCorridor
    minimum_z: float
    maximum_z: float
    vertical_detour_yards: float
    path_length_yards: float
    direct_distance_yards: float
    maximum_segment_grade_degrees: float
    downhill_escape: bool
    safe: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SemanticJourneyValidation:
    route: SemanticRoadRoute
    stages: tuple[SemanticNavStage, ...]
    destination_reached: bool
    safe: bool
    reason: str
    execution_authority: bool = False


@dataclass(frozen=True, slots=True)
class RiskAwareSemanticRoute:
    """One selected global prior; its local Detour legs remain mandatory."""

    route: SemanticRoadRoute
    decision: RoutePolicyDecision
    execution_authority: bool = False


def select_risk_aware_semantic_route(
    *,
    planner: ClientRoadSemanticPlanner,
    policy: RiskAwareRoutePolicy,
    start_x: float,
    start_y: float,
    destination_x: float,
    destination_y: float,
    capability: TravelCapability,
    observed_threats: tuple[ObservedRouteThreat, ...] = (),
    historical_risk_areas: tuple[HistoricalRiskArea, ...] = (),
    now_s: float,
) -> RiskAwareSemanticRoute:
    """Choose an atlas-derived route variant using bounded observed risk."""

    variants = planner.plan_variants(
        start_x=start_x,
        start_y=start_y,
        destination_x=destination_x,
        destination_y=destination_y,
    )
    decision = policy.choose(
        candidates=tuple(semantic_route_candidate(item) for item in variants),
        capability=capability,
        observed_threats=observed_threats,
        historical_risk_areas=historical_risk_areas,
        now_s=now_s,
    )
    routes_by_id = {item.profile_id: item for item in variants}
    return RiskAwareSemanticRoute(
        route=routes_by_id[decision.selected.route_id],
        decision=decision,
    )


def _measure_semantic_stage(
    *,
    index: int,
    requested_x: float,
    requested_y: float,
    current: NavPoint,
    corridor: NavCorridor,
    local_waypoint_radius_yards: float,
    max_vertical_detour_yards: float,
    max_segment_grade_degrees: float,
    walkable_step_climb_yards: float,
    navmesh_detail_vertical_tolerance_yards: float,
) -> SemanticNavStage:
    heights = [point.z for point in corridor.points]
    minimum_z = min(heights)
    maximum_z = max(heights)
    vertical_detour = max(
        0.0,
        maximum_z - max(current.z, corridor.stop.z),
        min(current.z, corridor.stop.z) - minimum_z,
    )
    path_length = 0.0
    maximum_segment_grade = 0.0
    for left, right in zip(corridor.points, corridor.points[1:]):
        horizontal = left.distance_2d(right)
        path_length += horizontal
        vertical = abs(right.z - left.z)
        is_walkable_step = (
            horizontal <= 0.75
            and vertical
            <= walkable_step_climb_yards + navmesh_detail_vertical_tolerance_yards
        )
        if horizontal > 0.05 and not is_walkable_step:
            maximum_segment_grade = max(
                maximum_segment_grade,
                degrees(atan2(vertical, horizontal)),
            )
    direct_distance = hypot(requested_x - current.x, requested_y - current.y)
    downhill_escape = (
        index == 1
        and maximum_z <= current.z + 1.0
        and corridor.stop.z < current.z - 5.0
    )
    local_goal_distance = hypot(
        corridor.stop.x - requested_x,
        corridor.stop.y - requested_y,
    )
    if not corridor.complete and local_goal_distance > local_waypoint_radius_yards:
        safe = False
        reason = "partial_local_navmesh_corridor"
    elif vertical_detour > max_vertical_detour_yards:
        safe = False
        reason = "local_corridor_has_excessive_vertical_detour"
    elif maximum_segment_grade > max_segment_grade_degrees and not downhill_escape:
        safe = False
        reason = "local_corridor_exceeds_executable_segment_grade"
    else:
        safe = True
        reason = (
            "local_corridor_complete_and_bounded"
            if corridor.complete
            else "local_waypoint_reached_via_bounded_partial_frontier"
        )
    return SemanticNavStage(
        index=index,
        requested_x=requested_x,
        requested_y=requested_y,
        corridor=corridor,
        minimum_z=minimum_z,
        maximum_z=maximum_z,
        vertical_detour_yards=vertical_detour,
        path_length_yards=path_length,
        direct_distance_yards=direct_distance,
        maximum_segment_grade_degrees=maximum_segment_grade,
        downhill_escape=downhill_escape,
        safe=safe,
        reason=reason,
    )


def validate_semantic_road_journey(
    *,
    planner: ClientRoadSemanticPlanner,
    navigator: ClientNavmeshQuery,
    map_name: str,
    start: NavPoint,
    destination_x: float,
    destination_y: float,
    destination_radius_yards: float = 2.0,
    local_waypoint_radius_yards: float = 3.0,
    max_vertical_detour_yards: float = 60.0,
    max_segment_grade_degrees: float = 42.0,
    walkable_step_climb_yards: float = 0.6,
    navmesh_detail_vertical_tolerance_yards: float = 0.25,
) -> SemanticJourneyValidation:
    if not all(isfinite(value) for value in (
        destination_x, destination_y, destination_radius_yards,
        local_waypoint_radius_yards,
        max_vertical_detour_yards, max_segment_grade_degrees,
        walkable_step_climb_yards, navmesh_detail_vertical_tolerance_yards,
    )):
        raise ValueError("semantic journey validation geometry is invalid")
    if (
        destination_radius_yards <= 0
        or local_waypoint_radius_yards <= 0
        or max_vertical_detour_yards <= 0
        or not 1.0 <= max_segment_grade_degrees <= 60.0
        or not 0.1 <= walkable_step_climb_yards <= 1.0
        or not 0.0 <= navmesh_detail_vertical_tolerance_yards <= 0.5
    ):
        raise ValueError("semantic journey validation bounds must be positive")
    route = planner.plan(
        start_x=start.x, start_y=start.y,
        destination_x=destination_x, destination_y=destination_y,
    )
    goals = list(route.waypoints)
    if goals and hypot(goals[0].x - start.x, goals[0].y - start.y) <= 1.0:
        goals.pop(0)
    if not goals or hypot(
        goals[-1].x - destination_x, goals[-1].y - destination_y
    ) > destination_radius_yards:
        goals.append(RoadWorldPoint(destination_x, destination_y))

    current = start
    stages: list[SemanticNavStage] = []
    for index, goal in enumerate(goals, start=1):
        corridor = navigator.find_corridor(
            map_name=map_name,
            start=current,
            stop_x=goal.x,
            stop_y=goal.y,
        )
        stage = _measure_semantic_stage(
            index=index,
            requested_x=goal.x,
            requested_y=goal.y,
            current=current,
            corridor=corridor,
            local_waypoint_radius_yards=local_waypoint_radius_yards,
            max_vertical_detour_yards=max_vertical_detour_yards,
            max_segment_grade_degrees=max_segment_grade_degrees,
            walkable_step_climb_yards=walkable_step_climb_yards,
            navmesh_detail_vertical_tolerance_yards=(
                navmesh_detail_vertical_tolerance_yards
            ),
        )
        stages.append(stage)
        current = corridor.stop
        if not stage.safe:
            return SemanticJourneyValidation(
                route=route,
                stages=tuple(stages),
                destination_reached=False,
                safe=False,
                reason=stage.reason,
            )

    reached = hypot(current.x - destination_x, current.y - destination_y) <= destination_radius_yards
    return SemanticJourneyValidation(
        route=route,
        stages=tuple(stages),
        destination_reached=reached,
        safe=reached,
        reason=(
            "semantic_destination_reached"
            if reached else "semantic_destination_radius_not_reached"
        ),
    )


def validate_adaptive_semantic_road_journey(
    *,
    planner: ClientRoadSemanticPlanner,
    navigator: ClientNavmeshQuery,
    map_name: str,
    start: NavPoint,
    destination_x: float,
    destination_y: float,
    coarse_goal_spacing_yards: float = 60.0,
    destination_radius_yards: float = 2.0,
    local_waypoint_radius_yards: float = 3.0,
    max_vertical_detour_yards: float = 60.0,
    max_segment_grade_degrees: float = 42.0,
    walkable_step_climb_yards: float = 0.6,
    navmesh_detail_vertical_tolerance_yards: float = 0.25,
) -> SemanticJourneyValidation:
    """Validate a global road route with adaptive local-navmesh refinement.

    The fine atlas A* path remains the source of all fallback points. Coarse
    goals reduce query count in open terrain; a partial Detour frontier causes
    monotonic refinement through the original semantic cells. No named place
    or authored route is inserted.
    """

    if not all(isfinite(value) for value in (
        destination_x,
        destination_y,
        coarse_goal_spacing_yards,
        destination_radius_yards,
        local_waypoint_radius_yards,
        max_vertical_detour_yards,
        max_segment_grade_degrees,
        walkable_step_climb_yards,
        navmesh_detail_vertical_tolerance_yards,
    )):
        raise ValueError("adaptive semantic journey geometry is invalid")
    if coarse_goal_spacing_yards <= 3.0:
        raise ValueError("coarse semantic goal spacing must exceed 3 yards")
    if (
        destination_radius_yards <= 0
        or local_waypoint_radius_yards <= 0
        or max_vertical_detour_yards <= 0
        or not 1.0 <= max_segment_grade_degrees <= 60.0
        or not 0.1 <= walkable_step_climb_yards <= 1.0
        or not 0.0 <= navmesh_detail_vertical_tolerance_yards <= 0.5
    ):
        raise ValueError("adaptive semantic journey bounds must be positive")
    route = planner.plan(
        start_x=start.x,
        start_y=start.y,
        destination_x=destination_x,
        destination_y=destination_y,
    )
    fine = route.waypoints
    coarse: list[tuple[int, RoadWorldPoint]] = []
    anchor_x, anchor_y = start.x, start.y
    for route_index, candidate in enumerate(fine):
        if hypot(candidate.x - anchor_x, candidate.y - anchor_y) < coarse_goal_spacing_yards:
            continue
        coarse.append((route_index, candidate))
        anchor_x, anchor_y = candidate.x, candidate.y
    if fine and (not coarse or coarse[-1][0] != len(fine) - 1):
        coarse.append((len(fine) - 1, fine[-1]))

    current = start
    stages: list[SemanticNavStage] = []
    progress_index = 0

    def query_stage(goal_x: float, goal_y: float) -> SemanticNavStage:
        corridor = navigator.find_corridor(
            map_name=map_name,
            start=current,
            stop_x=goal_x,
            stop_y=goal_y,
        )
        return _measure_semantic_stage(
            index=len(stages) + 1,
            requested_x=goal_x,
            requested_y=goal_y,
            current=current,
            corridor=corridor,
            local_waypoint_radius_yards=local_waypoint_radius_yards,
            max_vertical_detour_yards=max_vertical_detour_yards,
            max_segment_grade_degrees=max_segment_grade_degrees,
            walkable_step_climb_yards=walkable_step_climb_yards,
            navmesh_detail_vertical_tolerance_yards=(
                navmesh_detail_vertical_tolerance_yards
            ),
        )

    for target_index, goal in coarse:
        stage = query_stage(goal.x, goal.y)
        if stage.safe:
            stages.append(stage)
            current = stage.corridor.stop
            progress_index = max(progress_index, target_index)
            continue
        if stage.reason != "partial_local_navmesh_corridor":
            stages.append(stage)
            return SemanticJourneyValidation(
                route, tuple(stages), False, False, stage.reason
            )
        if stage.vertical_detour_yards > max_vertical_detour_yards:
            stages.append(stage)
            return SemanticJourneyValidation(
                route,
                tuple(stages),
                False,
                False,
                "partial_corridor_has_excessive_vertical_detour",
            )
        if (
            stage.maximum_segment_grade_degrees > max_segment_grade_degrees
            and not stage.downhill_escape
        ):
            stages.append(stage)
            return SemanticJourneyValidation(
                route,
                tuple(stages),
                False,
                False,
                "partial_corridor_exceeds_executable_segment_grade",
            )

        # The coarse frontier is diagnostic, not a movement command. Preserve
        # its evidence, then refine only forward along the same A* road route.
        stages.append(SemanticNavStage(
            index=stage.index,
            requested_x=stage.requested_x,
            requested_y=stage.requested_y,
            corridor=stage.corridor,
            minimum_z=stage.minimum_z,
            maximum_z=stage.maximum_z,
            vertical_detour_yards=stage.vertical_detour_yards,
            path_length_yards=stage.path_length_yards,
            direct_distance_yards=stage.direct_distance_yards,
            maximum_segment_grade_degrees=stage.maximum_segment_grade_degrees,
            downhill_escape=stage.downhill_escape,
            safe=True,
            reason="partial_corridor_triggered_semantic_refinement",
        ))
        current = stage.corridor.stop
        nearest_index = min(
            range(progress_index, target_index + 1),
            key=lambda index: hypot(
                fine[index].x - current.x,
                fine[index].y - current.y,
            ),
        )
        refined = False
        for route_index in range(nearest_index + 1, target_index + 1):
            candidate = fine[route_index]
            if hypot(candidate.x - current.x, candidate.y - current.y) < 3.0:
                progress_index = route_index
                continue
            fine_stage = query_stage(candidate.x, candidate.y)
            stages.append(fine_stage)
            current = fine_stage.corridor.stop
            if not fine_stage.safe:
                return SemanticJourneyValidation(
                    route, tuple(stages), False, False, fine_stage.reason
                )
            progress_index = route_index
            refined = True
        if not refined and hypot(current.x - goal.x, current.y - goal.y) > local_waypoint_radius_yards:
            return SemanticJourneyValidation(
                route,
                tuple(stages),
                False,
                False,
                "semantic_refinement_made_no_forward_progress",
            )

    destination_goal = NavPoint(destination_x, destination_y, current.z)
    if current.distance_2d(destination_goal) > destination_radius_yards:
        destination_stage = query_stage(destination_x, destination_y)
        stages.append(destination_stage)
        current = destination_stage.corridor.stop
        if not destination_stage.safe:
            return SemanticJourneyValidation(
                route, tuple(stages), False, False, destination_stage.reason
            )
    reached = hypot(current.x - destination_x, current.y - destination_y) <= destination_radius_yards
    return SemanticJourneyValidation(
        route=route,
        stages=tuple(stages),
        destination_reached=reached,
        safe=reached,
        reason=(
            "adaptive_semantic_destination_reached"
            if reached
            else "semantic_destination_radius_not_reached"
        ),
    )
