from dataclasses import dataclass
import unittest

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.road_semantic_planner import (
    RoadWorldPoint,
    SemanticRoadRoute,
)
from perfect_assassin.movement.semantic_navigation import (
    select_risk_aware_semantic_route,
    validate_adaptive_semantic_road_journey,
    validate_semantic_road_journey,
)
from perfect_assassin.movement.risk_aware_route_policy import (
    ObservedRouteThreat,
    RiskAwareRoutePolicy,
    TravelCapability,
)


@dataclass
class FixturePlanner:
    route: SemanticRoadRoute

    def plan(self, **_kwargs: object) -> SemanticRoadRoute:
        return self.route


@dataclass
class RiskFixturePlanner:
    routes: tuple[SemanticRoadRoute, ...]

    def plan_variants(self, **_kwargs: object) -> tuple[SemanticRoadRoute, ...]:
        return self.routes


class FixtureNavigator:
    def __init__(self, *, vertical_detour: float = 0.0) -> None:
        self.vertical_detour = vertical_detour

    def find_corridor(self, *, map_name: str, start: NavPoint, stop_x: float, stop_y: float) -> NavCorridor:
        stop = NavPoint(stop_x, stop_y, start.z)
        points = (start, NavPoint((start.x + stop_x) / 2, (start.y + stop_y) / 2,
                                  start.z + self.vertical_detour), stop)
        return NavCorridor(map_name, 29, 28, start, stop, points, requested_stop=stop)


class DetailQuantizedStepNavigator:
    def find_corridor(self, *, map_name: str, start: NavPoint, stop_x: float, stop_y: float) -> NavCorridor:
        stop = NavPoint(stop_x, stop_y, start.z)
        points = (
            start,
            NavPoint(start.x + 0.5, start.y, start.z + 0.8),
            stop,
        )
        return NavCorridor(map_name, 29, 28, start, stop, points, requested_stop=stop)


class RefinementFixtureNavigator:
    def find_corridor(
        self, *, map_name: str, start: NavPoint, stop_x: float, stop_y: float,
    ) -> NavCorridor:
        requested = NavPoint(stop_x, stop_y, start.z)
        if start.distance_2d(requested) > 15.0:
            return NavCorridor(
                map_name,
                29,
                28,
                start,
                start,
                (start,),
                complete=False,
                requested_stop=requested,
            )
        return NavCorridor(
            map_name,
            29,
            28,
            start,
            requested,
            (start, requested),
            requested_stop=requested,
        )


class SemanticNavigationTests(unittest.TestCase):
    def route(self) -> SemanticRoadRoute:
        start = RoadWorldPoint(0, 0)
        stop = RoadWorldPoint(20, 0)
        return SemanticRoadRoute(
            start, stop, start, stop,
            (start, RoadWorldPoint(10, 0), stop),
            3, 0, 0, 3,
        )

    def test_all_generated_local_corridors_are_validated(self) -> None:
        validation = validate_semantic_road_journey(
            planner=FixturePlanner(self.route()),
            navigator=FixtureNavigator(),
            map_name="Azeroth", start=NavPoint(0, 0, 5),
            destination_x=20, destination_y=0,
        )
        self.assertTrue(validation.safe)
        self.assertTrue(validation.destination_reached)
        self.assertEqual(len(validation.stages), 2)
        self.assertFalse(validation.execution_authority)

    def test_excessive_vertical_detour_fails_closed(self) -> None:
        validation = validate_semantic_road_journey(
            planner=FixturePlanner(self.route()),
            navigator=FixtureNavigator(vertical_detour=30),
            map_name="Azeroth", start=NavPoint(0, 0, 5),
            destination_x=20, destination_y=0,
        )
        self.assertFalse(validation.safe)
        self.assertEqual(validation.reason, "local_corridor_exceeds_executable_segment_grade")
        self.assertEqual(len(validation.stages), 1)

    def test_detail_mesh_quantization_does_not_create_false_micro_step_grade(self) -> None:
        validation = validate_semantic_road_journey(
            planner=FixturePlanner(self.route()),
            navigator=DetailQuantizedStepNavigator(),
            map_name="Azeroth", start=NavPoint(0, 0, 5),
            destination_x=20, destination_y=0,
        )
        self.assertTrue(validation.safe)
        self.assertTrue(validation.destination_reached)

    def test_adaptive_validator_refines_a_partial_coarse_frontier(self) -> None:
        validation = validate_adaptive_semantic_road_journey(
            planner=FixturePlanner(self.route()),
            navigator=RefinementFixtureNavigator(),
            map_name="Azeroth",
            start=NavPoint(0, 0, 5),
            destination_x=20,
            destination_y=0,
            coarse_goal_spacing_yards=15.1,
        )

        self.assertTrue(validation.safe)
        self.assertTrue(validation.destination_reached)
        self.assertEqual(validation.reason, "adaptive_semantic_destination_reached")
        self.assertEqual(
            validation.stages[0].reason,
            "partial_corridor_triggered_semantic_refinement",
        )
        self.assertEqual(len(validation.stages), 3)

    def test_risk_policy_selects_an_atlas_road_variant_before_local_execution(self) -> None:
        start = RoadWorldPoint(0, 0)
        stop = RoadWorldPoint(100, 0)
        shortcut = SemanticRoadRoute(
            start, stop, start, stop,
            (start, stop), 1, 0, 10, 10,
            profile_id="shortcut",
        )
        road = SemanticRoadRoute(
            start, stop, start, stop,
            (
                start, RoadWorldPoint(0, 35),
                RoadWorldPoint(100, 35), stop,
            ),
            14, 0, 0, 14,
            profile_id="road_backbone",
        )

        selected = select_risk_aware_semantic_route(
            planner=RiskFixturePlanner((shortcut, road)),
            policy=RiskAwareRoutePolicy(),
            start_x=0,
            start_y=0,
            destination_x=100,
            destination_y=0,
            capability=TravelCapability(1, 0.55, False, False),
            observed_threats=(ObservedRouteThreat(
                x=50, y=0, radius_yards=30, severity=1.0,
                observed_at_s=1, expires_at_s=30, source="LIVE_VISIBLE",
            ),),
            now_s=10,
        )

        self.assertEqual(selected.route.profile_id, "road_backbone")
        self.assertFalse(selected.execution_authority)
        self.assertEqual(
            selected.decision.reason,
            "unvalidated_offroad_rejected_prefer_topographic_road_evidence",
        )


if __name__ == "__main__":
    unittest.main()
