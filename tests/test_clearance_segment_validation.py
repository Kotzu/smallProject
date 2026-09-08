"""Offline regression proofs for the ME503 remembered-obstacle envelope."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "integrations" / "windows-input"))
from run_navmesh_roaming import (
    DEFAULT_ACTOR_CLEARANCE_WORLD,
    _corridor_preserves_obstacle_clearance,
    _inject_confirmed_clearance_priors,
    _point_segment_distance_2d,
)
from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.obstacle_memory import LearnedObstacle, LOCAL_CLEARANCE_EVIDENCE
from perfect_assassin.movement.road_semantic_planner import RoadWorldPoint


def obstacle(radius=1.0):
    return LearnedObstacle(
        obstacle_id="obstacle:segment-clearance", map_name="SyntheticWorld",
        zone_index=77, x=10.0, y=0.0, z=5.0, radius=radius, observations=3,
        first_observed_at="2026-08-01T00:00:00Z",
        last_observed_at="2026-08-03T00:00:00Z",
        last_run_id="navigation:synthetic", evidence=LOCAL_CLEARANCE_EVIDENCE,
    )


class Query:
    def __init__(self, max_lateral=float("inf"), bend_inside=False, projection=0.0):
        self.max_lateral = max_lateral
        self.bend_inside = bend_inside
        self.projection = projection
        self.returned = []

    def find_corridor(self, *, map_name, start, stop_x, stop_y, stop_z=None):
        stop = NavPoint(stop_x, stop_y, stop_z)
        if max(abs(start.y), abs(stop.y)) > self.max_lateral:
            return NavCorridor(map_name, 0, 0, start, start, (start, start),
                               complete=False, requested_stop=stop)
        # Bend or project the crossing leg only; both requested corners stay safe.
        crossing = start.x < 10.0 < stop.x
        if crossing and self.projection:
            stop = NavPoint(stop.x, stop.y * (1 - self.projection / abs(stop.y)), stop.z)
        points = (start, NavPoint(10.0, 0.5, stop.z), stop) if (
            crossing and self.bend_inside
        ) else (start, stop)
        corridor = NavCorridor(map_name, 0, 0, start, stop, points)
        self.returned.append(corridor)
        return corridor


def inject(blocker, query, **kwargs):
    return _inject_confirmed_clearance_priors(
        route_start=RoadWorldPoint(0.0, 0.0), goals=(RoadWorldPoint(20.0, 0.0),),
        obstacles=(blocker,), query=query, map_name="SyntheticWorld", **kwargs,
    )


class ClearanceSegmentTests(unittest.TestCase):
    def assert_unresolved(self, result):
        goals, evidence = result
        self.assertEqual(goals, (RoadWorldPoint(20.0, 0.0),))
        self.assertEqual(evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED")

    def test_safe_endpoints_do_not_allow_interior_navmesh_bend(self):
        self.assert_unresolved(inject(obstacle(), Query(bend_inside=True)))

    def test_small_projection_must_not_consume_body_clearance(self):
        # 0.09 is below the 0.10 projection tolerance, but not body-safe.
        self.assert_unresolved(inject(obstacle(), Query(max_lateral=2.25, projection=0.09)))

    def test_safe_straight_segments_remain_available_for_larger_obstacle(self):
        blocker = obstacle(radius=1.5)
        query = Query()
        goals, evidence = inject(blocker, query)
        self.assertEqual(evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_APPLIED")
        self.assertEqual(len(goals), 3)
        center = RoadWorldPoint(blocker.x, blocker.y)
        minimum = _point_segment_distance_2d(center, goals[0], goals[1])
        self.assertGreaterEqual(minimum + 1e-6, blocker.radius + DEFAULT_ACTOR_CLEARANCE_WORLD)

    def test_boundary_still_adapts_when_actual_navmesh_arc_is_safe(self):
        class OutwardQuery(Query):
            def find_corridor(self, **kwargs):
                corridor = super().find_corridor(**kwargs)
                if corridor.complete and corridor.start.x < 10.0 < corridor.stop.x:
                    middle = NavPoint(10.0, 2.5 if corridor.start.y > 0 else -2.5, 5.0)
                    return replace(corridor, points=(corridor.start, middle, corridor.stop))
                return corridor

        blocker = obstacle()
        query = OutwardQuery(max_lateral=1.80)
        goals, evidence = inject(blocker, query)
        self.assertEqual(evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_APPLIED")
        self.assertEqual(evidence[0]["clearance_profile"], "adaptive_boundary_sample")
        self.assertAlmostEqual(abs(goals[0].y), 1.75)
        # The straight chord is unsafe; the validated Detour arc is safe.
        middle = RoadWorldPoint(10.0, -2.5 if goals[0].y < 0 else 2.5)
        for start, stop in ((goals[0], middle), (middle, goals[1])):
            self.assertGreaterEqual(
                _point_segment_distance_2d(RoadWorldPoint(10.0, 0.0), start, stop),
                blocker.radius + DEFAULT_ACTOR_CLEARANCE_WORLD,
            )

    def test_segment_clearance_is_translation_and_rotation_independent(self):
        for rotate in (False, True):
            for reverse in (False, True):
                for distance, safe in ((2.249, False), (2.25, True), (2.251, True)):
                    with self.subTest(rotate=rotate, reverse=reverse, distance=distance):
                        def transform(x, y):
                            x, y = (-y, x) if rotate else (x, y)
                            return NavPoint(x + 137.0, y - 83.0, 5.0)
                        center = transform(0.0, 0.0)
                        blocker = replace(obstacle(), x=center.x, y=center.y)
                        points = (transform(-4.0, distance), transform(4.0, distance))
                        if reverse:
                            points = points[::-1]
                        corridor = NavCorridor("SyntheticWorld", 0, 0, *points, points)
                        self.assertEqual(_corridor_preserves_obstacle_clearance(corridor, blocker), safe)

    def test_unsafe_resume_corridor_is_not_cached(self):
        class UnsafeResumeQuery(Query):
            def find_corridor(self, **kwargs):
                corridor = super().find_corridor(**kwargs)
                if corridor.stop.x == 20.0:
                    return replace(corridor, points=(corridor.start, NavPoint(12.0, 0.5, 5.0), corridor.stop))
                return corridor

        cache = {}
        _, evidence = inject(obstacle(), UnsafeResumeQuery(), continuation_cache=cache)
        self.assertEqual(evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_APPLIED")
        self.assertEqual(cache, {})

    def test_far_fallback_cannot_cache_path_through_obstacle(self):
        class UnsafeGlobalQuery(Query):
            observed_blockers = ()

            def with_observed_blockers(self, blockers):
                self.global_query = True
                return self

            def find_corridor(self, *, map_name, start, stop_x, stop_y, stop_z=None):
                stop = NavPoint(stop_x, stop_y, stop_z)
                if getattr(self, "global_query", False):
                    return NavCorridor(map_name, 0, 0, start, stop,
                                       (start, NavPoint(500.0, 0.5, 5.0), stop))
                return NavCorridor(map_name, 0, 0, start, start, (start, start),
                                   complete=False, requested_stop=stop)

        cache = {}
        goals, evidence = _inject_confirmed_clearance_priors(
            route_start=RoadWorldPoint(0.0, 0.0), goals=(RoadWorldPoint(1000.0, 0.0),),
            obstacles=(replace(obstacle(), x=500.0),), query=UnsafeGlobalQuery(),
            map_name="SyntheticWorld", continuation_cache=cache,
        )
        self.assertEqual(goals, (RoadWorldPoint(1000.0, 0.0),))
        self.assertEqual(evidence[0]["kind"], "CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED")
        self.assertEqual(cache, {})


if __name__ == "__main__":
    unittest.main()
