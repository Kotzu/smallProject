from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite

from perfect_assassin.movement.client_navmesh import (
    ClientNavmeshError,
    ClientNavmeshQuery,
    NavCorridor,
    NavPoint,
)
from perfect_assassin.movement.predictive_steering import (
    PredictiveSteeringController,
    SteeringIntent,
    SteeringState,
)
from perfect_assassin.movement.local_environment_awareness import (
    LocalEnvironmentAwareness,
    build_local_environment_awareness,
)
from perfect_assassin.movement.world_model import ExperienceCell, LayeredWorldModel
from perfect_assassin.movement.topographic_brain import (
    TopographicBrainSnapshot,
    build_topographic_brain_snapshot,
)
from perfect_assassin.movement.world_structure_index import (
    WorldStructureSpatialIndex,
)
from perfect_assassin.movement.structure_access_graph import (
    StructureAccessSpatialGraph,
)


@dataclass(frozen=True, slots=True)
class RecoveryStep:
    control: str
    hold_ms: int


@dataclass(frozen=True, slots=True)
class StuckRecoveryManeuver:
    steps: tuple[RecoveryStep, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class StructureEgressPlan:
    """A graph-suggested structure exit revalidated by the active navmesh.

    The structure graph supplies durable knowledge, never movement authority.
    Both legs are queried again against the currently loaded standalone
    WorldPack before this proposal can be returned.
    """

    structure_id: str
    opening_id: str
    opening: NavPoint
    approach: NavCorridor
    continuation: NavCorridor
    requested_goal: NavPoint
    direct_frontier_remaining_yards: float
    continuation_frontier_remaining_yards: float
    # The graph midpoint is a boundary witness, not necessarily a traversable
    # actor pose.  A bounded, navmesh-revalidated point just outside that
    # boundary prevents a handoff from steering through the WMO shell.
    exit_anchor: NavPoint | None = None

    @property
    def movement_target(self) -> NavPoint:
        return self.exit_anchor if self.exit_anchor is not None else self.opening

    def __post_init__(self) -> None:
        if (
            not self.structure_id
            or not self.opening_id
            or self.approach.map_name != self.continuation.map_name
            or not self.approach.complete
            or self.approach.stop.distance_2d(self.opening) > 0.75
            or abs(self.approach.stop.z - self.opening.z) > 2.5
            or (
                self.exit_anchor is not None
                and self.exit_anchor.distance_2d(self.opening) > 4.0
            )
            or (
                self.exit_anchor is not None
                and self.continuation.start.distance_2d(self.exit_anchor) > 2.0
            )
            or (
                self.exit_anchor is not None
                and abs(self.continuation.start.z - self.exit_anchor.z) > 2.5
            )
            or self.direct_frontier_remaining_yards < 0
            or self.continuation_frontier_remaining_yards < 0
            or not all(isfinite(value) for value in (
                self.opening.x,
                self.opening.y,
                self.opening.z,
                self.requested_goal.x,
                self.requested_goal.y,
                self.requested_goal.z,
                self.direct_frontier_remaining_yards,
                self.continuation_frontier_remaining_yards,
            ))
        ):
            raise ValueError("structure egress plan is invalid")


def _corridor_path_length(corridor: NavCorridor) -> float:
    points = corridor.guidance_points()
    return sum(
        left.distance_2d(right)
        for left, right in zip(points, points[1:])
    )


@dataclass(slots=True)
class MovementEngine:
    """Pure movement intelligence; owns no keyboard, mouse, or combat policy."""

    navigator: ClientNavmeshQuery
    steering: PredictiveSteeringController
    world: LayeredWorldModel
    structures: WorldStructureSpatialIndex | None = None
    structure_access: StructureAccessSpatialGraph | None = None

    def plan(
        self,
        *,
        start: NavPoint,
        goal_x: float,
        goal_y: float,
        goal_z: float | None = None,
    ) -> NavCorridor:
        query = {
            "map_name": self.world.map_name,
            "start": start,
            "stop_x": goal_x,
            "stop_y": goal_y,
        }
        # Preserve compatibility with legacy 2D workers while allowing an
        # exact floor hint for stacked WMO/interior geometry.
        if goal_z is not None:
            query["stop_z"] = goal_z
        return self.navigator.find_corridor(**query)

    def observe_position(self, *, x: float, y: float, observed_at_s: float) -> ExperienceCell:
        return self.world.observe_position(x=x, y=y, observed_at_s=observed_at_s)

    def mark_stuck(self, *, x: float, y: float, observed_at_s: float) -> ExperienceCell:
        return self.world.mark_stuck(x=x, y=y, observed_at_s=observed_at_s)

    def decide(self, state: SteeringState, corridor: NavCorridor) -> SteeringIntent:
        return self.steering.decide(state, corridor)

    def topographic_context(
        self,
        *,
        observed_monotonic_s: float,
        actor: NavPoint,
        actor_facing_rad: float | None,
        actor_position_source: str,
        actor_facing_source: str,
        controller_heading_rad: float | None,
        destination: NavPoint,
        corridor: NavCorridor,
        environment: LocalEnvironmentAwareness | None,
        semantic_route_profile: str | None,
        semantic_goal_index: int,
        semantic_goal_count: int,
        visible_dynamic_entity_count: int,
        routine_aggro_travel_enabled: bool,
        minimum_travel_health_fraction: float,
    ) -> TopographicBrainSnapshot:
        """Bind all movement knowledge to the current pose and corridor."""

        return build_topographic_brain_snapshot(
            world=self.world,
            observed_monotonic_s=observed_monotonic_s,
            actor=actor,
            actor_facing_rad=actor_facing_rad,
            actor_position_source=actor_position_source,
            actor_facing_source=actor_facing_source,
            controller_heading_rad=controller_heading_rad,
            destination=destination,
            corridor=corridor,
            environment=environment,
            semantic_route_profile=semantic_route_profile,
            semantic_goal_index=semantic_goal_index,
            semantic_goal_count=semantic_goal_count,
            visible_dynamic_entity_count=visible_dynamic_entity_count,
            routine_aggro_travel_enabled=routine_aggro_travel_enabled,
            minimum_travel_health_fraction=minimum_travel_health_fraction,
        )

    def environment_at_corridor_start(
        self,
        corridor: NavCorridor,
        *,
        observed_monotonic_s: float,
        nearby_radius_yards: float = 100.0,
    ) -> LocalEnvironmentAwareness | None:
        if self.structures is None or corridor.start_awareness is None:
            return None
        return build_local_environment_awareness(
            map_name=corridor.map_name,
            observed_monotonic_s=observed_monotonic_s,
            position=corridor.start,
            nav_awareness=corridor.start_awareness,
            structures=self.structures,
            nearby_radius_yards=nearby_radius_yards,
        )

    def known_structure_openings(
        self,
        awareness: LocalEnvironmentAwareness,
        *,
        maximum_distance_yards: float = 100.0,
        limit: int = 8,
    ) -> tuple[dict[str, object], ...]:
        if self.structure_access is None:
            return ()
        if len(awareness.containing_structures) != 1:
            return ()
        structure_id = awareness.containing_structures[0].structure_id
        return tuple(
            dict(item)
            for item in self.structure_access.nearest_openings(
                x=awareness.position.x,
                y=awareness.position.y,
                z=awareness.position.z,
                structure_id=structure_id,
                maximum_distance_yards=maximum_distance_yards,
                limit=limit,
            )
        )

    def plan_via_known_structure_egress(
        self,
        *,
        awareness: LocalEnvironmentAwareness,
        direct_corridor: NavCorridor,
        goal_x: float,
        goal_y: float,
        goal_z: float | None = None,
        maximum_opening_distance_yards: float = 100.0,
        minimum_connected_width_yards: float = 0.75,
        minimum_frontier_improvement_yards: float = 1.0,
        excluded_opening_ids: frozenset[str] = frozenset(),
    ) -> StructureEgressPlan | None:
        """Propose a verified egress leg for a route leaving a known WMO.

        No map name, structure identity, coordinate, or route is embedded in
        this policy.  A candidate must belong to the single WMO that contains
        the actor, describe a covered-to-open transition, be reachable on the
        active navmesh, and leave a continuation that either reaches or makes
        measurable progress toward the caller's original destination.

        A complete Detour corridor is normally authoritative.  The exception
        is a cross-boundary chord from inside one immutable WMO to a point
        outside that same WMO.  A coarse or damaged interior tile can label
        such a chord complete even when it crosses the enclosure.  In that
        case the immutable WorldPack structure bounds prove the boundary
        crossing. Local radial topology may still be incomplete on a stacked
        interior floor; the version-bound graph opening and both legs are
        nevertheless revalidated by Detour before they can become a proposal.
        """

        if (
            self.structure_access is None
            or direct_corridor.map_name != self.world.map_name
            or awareness.map_name != self.world.map_name
            or len(awareness.containing_structures) != 1
            or awareness.position.distance_2d(direct_corridor.start) > 2.0
            or abs(awareness.position.z - direct_corridor.start.z) > 2.5
            or not isfinite(maximum_opening_distance_yards)
            or not 1.0 <= maximum_opening_distance_yards <= 1_000.0
            or not isfinite(minimum_connected_width_yards)
            or minimum_connected_width_yards <= 0
            or not isfinite(minimum_frontier_improvement_yards)
            or minimum_frontier_improvement_yards <= 0
        ):
            return None

        requested_z = (
            float(goal_z)
            if goal_z is not None
            else (
                direct_corridor.requested_stop.z
                if direct_corridor.requested_stop is not None
                else direct_corridor.stop.z
            )
        )
        if not all(isfinite(value) for value in (goal_x, goal_y, requested_z)):
            return None
        requested_goal = NavPoint(float(goal_x), float(goal_y), requested_z)
        structure_id = awareness.containing_structures[0].structure_id
        if direct_corridor.complete:
            if self.structures is None:
                return None
            destination_structures = self.structures.containing(
                x=requested_goal.x,
                y=requested_goal.y,
                z=requested_goal.z,
            )
            if any(
                hit.structure.structure_id == structure_id
                for hit in destination_structures
            ):
                return None
        direct_remaining = direct_corridor.stop.distance_2d(requested_goal)
        candidates: list[
            tuple[tuple[int, float, float, str], StructureEgressPlan]
        ] = []
        try:
            openings = self.structure_access.nearest_openings(
                x=awareness.position.x,
                y=awareness.position.y,
                z=awareness.position.z,
                structure_id=structure_id,
                maximum_distance_yards=maximum_opening_distance_yards,
                limit=8,
            )
        except (KeyError, TypeError, ValueError):
            return None

        for item in openings:
            try:
                opening_id = str(item["opening_id"])
                midpoint = item["midpoint"]
                opening = NavPoint(
                    float(midpoint[0]), float(midpoint[1]), float(midpoint[2]),
                )
                from_surfaces = frozenset(str(value) for value in item["from_surfaces"])
                to_surfaces = frozenset(str(value) for value in item["to_surfaces"])
                connected_width = float(item["connected_width_yards"])
                item_structure_ids = tuple(str(value) for value in item["structure_ids"])
                allowed_surfaces = {"ground", "wmo", "doodad"}
                if (
                    not opening_id
                    or opening_id in excluded_opening_ids
                    or item.get("opening_kind")
                    != "COVERED_TO_OPEN_ROUTE_VERIFIED"
                    or item.get("execution_authority") is not False
                    or structure_id not in item_structure_ids
                    or "wmo" not in from_surfaces
                    or not to_surfaces
                    or not from_surfaces.issubset(allowed_surfaces)
                    or not to_surfaces.issubset(allowed_surfaces)
                    or connected_width < minimum_connected_width_yards
                    or not all(isfinite(value) for value in (
                        opening.x, opening.y, opening.z, connected_width,
                    ))
                ):
                    continue
            except (KeyError, TypeError, ValueError, IndexError):
                continue

            structure_hits = self.structures.nearby(
                x=opening.x,
                y=opening.y,
                z=opening.z,
                radius_yards=0.5,
                kinds=("WMO",),
            ) if self.structures is not None else ()
            structure = next(
                (
                    hit.structure for hit in structure_hits
                    if hit.structure.structure_id == structure_id
                ),
                None,
            )
            egress_navigator = self.navigator
            # Use a class-level lookup so unittest.Mock's dynamic attributes
            # do not masquerade as an optional adapter capability.
            scope_factory = getattr(self.navigator, "for_structure_egress", None)
            if (
                structure is not None
                and callable(scope_factory)
                and callable(getattr(type(self.navigator), "for_structure_egress", None))
            ):
                try:
                    egress_navigator = scope_factory(
                        bounds=(
                            float(structure.bounds.minimum.x),
                            float(structure.bounds.minimum.y),
                            float(structure.bounds.minimum.z),
                            float(structure.bounds.maximum.x),
                            float(structure.bounds.maximum.y),
                            float(structure.bounds.maximum.z),
                        ),
                    )
                except (ClientNavmeshError, TypeError, ValueError):
                    continue

            def plan_egress_leg(
                *,
                start: NavPoint,
                goal_x: float,
                goal_y: float,
                goal_z: float | None = None,
                navigator=egress_navigator,
            ) -> NavCorridor:
                query = {
                    "map_name": self.world.map_name,
                    "start": start,
                    "stop_x": goal_x,
                    "stop_y": goal_y,
                }
                if goal_z is not None:
                    query["stop_z"] = goal_z
                return navigator.find_corridor(**query)

            try:
                boundary_approach = plan_egress_leg(
                    start=awareness.position,
                    goal_x=opening.x,
                    goal_y=opening.y,
                    goal_z=opening.z,
                )
            except RuntimeError:
                continue
            if (
                not boundary_approach.complete
                or boundary_approach.start.distance_2d(awareness.position) > 2.0
                or abs(boundary_approach.start.z - awareness.position.z) > 2.5
                or boundary_approach.stop.distance_2d(opening) > 0.75
                or abs(boundary_approach.stop.z - opening.z) > 2.5
            ):
                continue

            try:
                continuation = plan_egress_leg(
                    start=boundary_approach.stop,
                    goal_x=goal_x,
                    goal_y=goal_y,
                    goal_z=goal_z,
                )
            except RuntimeError:
                continue

            # Boundary midpoints are useful topology evidence but may resolve
            # to the covered side of a WMO.  Search only a tiny, bounded ray
            # from the immutable structure centre toward the opening, then
            # require the resolved continuation start to expose ground.  The
            # direction is asset-derived; no location or waypoint is encoded.
            exit_anchor: NavPoint | None = None
            approach = boundary_approach
            # The production client-asset adapter exposes the local surface
            # evidence needed to prove an outside anchor.  Lightweight test
            # navigators and legacy adapters retain the baseline two-leg
            # proposal instead of fabricating that evidence.
            anchor_search_enabled = (
                getattr(self.navigator, "surface_evidence_available", False) is True
                and structure is not None
            )
            direction_x = opening.x - (
                structure.center.x if structure is not None else awareness.position.x
            )
            direction_y = opening.y - (
                structure.center.y if structure is not None else awareness.position.y
            )
            direction_length = hypot(direction_x, direction_y)
            if not anchor_search_enabled:
                direction_length = 0.0
            if direction_length <= 0.001:
                direction_x = goal_x - opening.x
                direction_y = goal_y - opening.y
                direction_length = hypot(direction_x, direction_y)
            if direction_length <= 0.001 and anchor_search_enabled:
                continue
            if direction_length > 0.001:
                direction_x /= direction_length
                direction_y /= direction_length
            for offset in (
                (0.75, 1.25, 1.75, 2.25, 3.0)
                if anchor_search_enabled else ()
            ):
                candidate = NavPoint(
                    opening.x + direction_x * offset,
                    opening.y + direction_y * offset,
                    opening.z,
                )
                try:
                    candidate_approach = plan_egress_leg(
                        start=boundary_approach.stop,
                        goal_x=candidate.x,
                        goal_y=candidate.y,
                        goal_z=candidate.z,
                    )
                    candidate_continuation = plan_egress_leg(
                        start=candidate_approach.stop,
                        goal_x=goal_x,
                        goal_y=goal_y,
                        goal_z=goal_z,
                    )
                except RuntimeError:
                    continue
                candidate_awareness = candidate_continuation.start_awareness
                if (
                    not candidate_approach.complete
                    or candidate_approach.stop.distance_2d(candidate) > 0.75
                    or abs(candidate_approach.stop.z - candidate.z) > 2.5
                    or candidate_awareness is None
                    or "ground" not in candidate_awareness.physical_surfaces
                    or "wmo" in candidate_awareness.physical_surfaces
                ):
                    continue
                exit_anchor = candidate_approach.stop
                continuation = candidate_continuation
                break
            assert continuation is not None
            if (
                continuation.start.distance_2d(
                    exit_anchor if exit_anchor is not None else approach.stop
                ) > 2.0
                or abs(
                    continuation.start.z
                    - (exit_anchor.z if exit_anchor is not None else approach.stop.z)
                ) > 2.5
            ):
                continue
            continuation_remaining = continuation.stop.distance_2d(requested_goal)
            continuation_progress = approach.stop.distance_2d(continuation.stop)
            if not continuation.complete and (
                continuation_progress < minimum_frontier_improvement_yards
                or direct_remaining - continuation_remaining
                < minimum_frontier_improvement_yards
            ):
                continue

            proposal = StructureEgressPlan(
                structure_id=structure_id,
                opening_id=opening_id,
                opening=opening,
                approach=approach,
                continuation=continuation,
                requested_goal=requested_goal,
                direct_frontier_remaining_yards=direct_remaining,
                continuation_frontier_remaining_yards=continuation_remaining,
                exit_anchor=exit_anchor,
            )
            rank = (
                0 if continuation.complete else 1,
                continuation_remaining,
                _corridor_path_length(approach)
                + _corridor_path_length(continuation),
                opening_id,
            )
            candidates.append((rank, proposal))

        if not candidates:
            return None
        return min(candidates, key=lambda candidate: candidate[0])[1]

    def recovery_maneuver(self, *, attempt: int) -> StuckRecoveryManeuver:
        if attempt not in (0, 1):
            raise ValueError("stuck recovery attempt is outside the reviewed budget")
        lateral = "STRAFE_RIGHT" if attempt == 0 else "STRAFE_LEFT"
        return StuckRecoveryManeuver(
            steps=(
                RecoveryStep("JUMP", 150),
                RecoveryStep("MOVE_BACKWARD", 400),
                RecoveryStep(lateral, 250),
            ),
            reason="bounded_jump_backoff_and_short_lateral_clearance_before_client_navmesh_replan",
        )
