from __future__ import annotations

import unittest

from perfect_assassin.movement.risk_aware_route_policy import (
    ObservedRouteThreat,
    RiskAwareRoutePolicy,
    TravelCapability,
    TravelRouteCandidate,
    semantic_route_candidate,
)
from perfect_assassin.movement.road_semantic_planner import (
    RoadWorldPoint,
    SemanticRoadRoute,
)
from perfect_assassin.movement.world_model import HistoricalRiskArea


class RiskAwareRoutePolicyTests(unittest.TestCase):
    def candidates(self) -> tuple[TravelRouteCandidate, TravelRouteCandidate]:
        shortcut = TravelRouteCandidate(
            route_id="shortcut",
            points=(RoadWorldPoint(0, 0), RoadWorldPoint(100, 0)),
            road_fraction=0.10,
            terrain_difficulty=0.05,
            unexplored_fraction=0.20,
        )
        road = TravelRouteCandidate(
            route_id="road",
            points=(
                RoadWorldPoint(0, 0), RoadWorldPoint(0, 35),
                RoadWorldPoint(100, 35), RoadWorldPoint(100, 0),
            ),
            road_fraction=1.0,
            terrain_difficulty=0.0,
            unexplored_fraction=0.0,
        )
        return shortcut, road

    def test_low_level_character_takes_a_longer_road_around_visible_hostiles(self) -> None:
        shortcut, road = self.candidates()
        decision = RiskAwareRoutePolicy().choose(
            candidates=(shortcut, road),
            capability=TravelCapability(
                level=1, health_fraction=0.55,
                stealth_ready=False, escape_ready=False,
            ),
            observed_threats=(ObservedRouteThreat(
                x=50, y=0, radius_yards=30, severity=1.0,
                observed_at_s=10, expires_at_s=30, source="LIVE_VISIBLE",
            ),),
            now_s=15,
        )

        self.assertEqual(decision.selected.route_id, "road")
        self.assertEqual(
            decision.reason, "longer_route_reduces_expected_known_risk_delay",
        )
        self.assertGreater(
            next(item for item in decision.alternatives if item.route_id == "shortcut").risk_score,
            decision.risk_budget,
        )

    def test_capable_stealthed_character_can_take_the_shortcut(self) -> None:
        shortcut, road = self.candidates()
        decision = RiskAwareRoutePolicy().choose(
            candidates=(shortcut, road),
            capability=TravelCapability(
                level=60, health_fraction=1.0,
                stealth_ready=True, escape_ready=True,
            ),
            observed_threats=(ObservedRouteThreat(
                x=50, y=0, radius_yards=30, severity=1.0,
                observed_at_s=10, expires_at_s=30, source="LIVE_VISIBLE",
            ),),
            now_s=15,
        )

        self.assertEqual(decision.selected.route_id, "shortcut")
        self.assertEqual(
            decision.reason,
            "shortest_route_has_lowest_expected_arrival_inside_risk_budget",
        )

    def test_expired_observations_cannot_steer_the_route(self) -> None:
        shortcut, road = self.candidates()
        decision = RiskAwareRoutePolicy().choose(
            candidates=(shortcut, road),
            capability=TravelCapability(
                level=1, health_fraction=0.55,
                stealth_ready=False, escape_ready=False,
            ),
            observed_threats=(ObservedRouteThreat(
                x=50, y=0, radius_yards=30, severity=5.0,
                observed_at_s=10, expires_at_s=12, source="REMEMBERED_OBSERVED",
            ),),
            now_s=15,
        )

        self.assertEqual(decision.selected.route_id, "shortcut")

    def test_permanent_historical_experience_survives_live_coordinate_expiry(self) -> None:
        shortcut, road = self.candidates()
        decision = RiskAwareRoutePolicy().choose(
            candidates=(shortcut, road),
            capability=TravelCapability(
                level=1, health_fraction=0.55,
                stealth_ready=False, escape_ready=False,
            ),
            historical_risk_areas=(HistoricalRiskArea(
                area_id="observed-risk:HOSTILE_NPC:1:0",
                kind="HOSTILE_NPC",
                x=50, y=0, radius_yards=30, risk_score=3.0,
                observation_count=4, first_observed_s=1, last_observed_s=12,
            ),),
            now_s=15,
        )

        self.assertEqual(decision.selected.route_id, "road")
        self.assertEqual(decision.reason, "longer_route_reduces_expected_known_risk_delay")

    def test_no_observation_means_no_fabricated_remote_threat(self) -> None:
        shortcut, road = self.candidates()
        decision = RiskAwareRoutePolicy().choose(
            candidates=(shortcut, road),
            capability=TravelCapability(
                level=1, health_fraction=0.55,
                stealth_ready=False, escape_ready=False,
            ),
            now_s=15,
        )

        self.assertEqual(decision.selected.route_id, "shortcut")
        self.assertEqual(decision.dynamic_knowledge, "OBSERVED_ONLY_FOG_OF_WAR")

    def test_stealth_does_not_make_unvalidated_hillside_humanlike(self) -> None:
        hillside = TravelRouteCandidate(
            route_id="shortcut",
            points=(RoadWorldPoint(0, 0), RoadWorldPoint(100, 0)),
            road_fraction=0.35,
            terrain_difficulty=0.42,
            unexplored_fraction=0.0,
        )
        road = TravelRouteCandidate(
            route_id="road_backbone",
            points=(
                RoadWorldPoint(0, 0), RoadWorldPoint(0, 20),
                RoadWorldPoint(100, 20), RoadWorldPoint(100, 0),
            ),
            road_fraction=0.98,
            terrain_difficulty=0.02,
            unexplored_fraction=0.0,
        )

        decision = RiskAwareRoutePolicy().choose(
            candidates=(hillside, road),
            capability=TravelCapability(60, 1.0, True, True),
            now_s=15,
        )

        self.assertEqual(decision.selected.route_id, "road_backbone")
        self.assertFalse(
            next(
                item for item in decision.alternatives
                if item.route_id == "shortcut"
            ).topographically_eligible
        )
        self.assertEqual(
            decision.reason,
            "unvalidated_offroad_rejected_prefer_topographic_road_evidence",
        )

    def test_fully_topography_validated_shortcut_remains_available(self) -> None:
        shortcut = TravelRouteCandidate(
            route_id="shortcut",
            points=(RoadWorldPoint(0, 0), RoadWorldPoint(70, 0)),
            road_fraction=0.35,
            terrain_difficulty=0.30,
            unexplored_fraction=0.0,
            topographic_validation_fraction=1.0,
        )
        road = TravelRouteCandidate(
            route_id="road_backbone",
            points=(RoadWorldPoint(0, 0), RoadWorldPoint(100, 0)),
            road_fraction=1.0,
            terrain_difficulty=0.0,
            unexplored_fraction=0.0,
        )

        decision = RiskAwareRoutePolicy().choose(
            candidates=(shortcut, road),
            capability=TravelCapability(60, 1.0, True, True),
            now_s=15,
        )

        self.assertEqual(decision.selected.route_id, "shortcut")
        self.assertTrue(
            next(
                item for item in decision.alternatives
                if item.route_id == "shortcut"
            ).topographically_eligible
        )

    def test_indistinguishable_over_budget_risk_prefers_road_evidence(self) -> None:
        shortcut = TravelRouteCandidate(
            route_id="shortcut",
            points=(RoadWorldPoint(0, 0), RoadWorldPoint(100, 0)),
            road_fraction=0.10,
            terrain_difficulty=0.98,
            unexplored_fraction=0.0,
            topographic_validation_fraction=1.0,
        )
        road = TravelRouteCandidate(
            route_id="road_backbone",
            points=(RoadWorldPoint(0, 0), RoadWorldPoint(110, 0)),
            road_fraction=0.95,
            terrain_difficulty=1.0,
            unexplored_fraction=0.0,
            topographic_validation_fraction=1.0,
        )
        decision = RiskAwareRoutePolicy().choose(
            candidates=(shortcut, road),
            capability=TravelCapability(
                level=1, health_fraction=0.05,
                stealth_ready=False, escape_ready=False,
            ),
            now_s=15,
        )

        self.assertFalse(any(item.within_risk_budget for item in decision.alternatives))
        self.assertEqual(decision.selected.route_id, "road_backbone")
        self.assertEqual(
            decision.reason,
            "no_candidate_is_within_risk_budget_prefer_road_when_"
            "known_risk_is_indistinguishable",
        )

    def test_semantic_variants_become_scored_candidates_without_authored_points(self) -> None:
        start = RoadWorldPoint(0, 0)
        stop = RoadWorldPoint(20, 0)
        route = SemanticRoadRoute(
            start=start,
            destination=stop,
            road_entry=start,
            road_exit=stop,
            waypoints=(start, RoadWorldPoint(10, 0), stop),
            road_cell_count=2,
            near_road_cell_count=1,
            offroad_bridge_cell_count=1,
            expanded_cell_count=4,
            path_cost=5.0,
            profile_id="balanced",
        )

        candidate = semantic_route_candidate(route, unexplored_fraction=0.25)

        self.assertEqual(candidate.route_id, "balanced")
        self.assertAlmostEqual(candidate.road_fraction, 0.5)
        self.assertGreater(candidate.terrain_difficulty, 0.0)
        self.assertEqual(candidate.unexplored_fraction, 0.25)


if __name__ == "__main__":
    unittest.main()
