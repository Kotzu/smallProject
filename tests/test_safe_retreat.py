from __future__ import annotations

import unittest

from perfect_assassin.movement.client_navmesh import NavPoint
from perfect_assassin.movement.safe_retreat import (
    SafeRetreatTrail,
    corridor_from_retreat_context,
)


class SafeRetreatTrailTests(unittest.TestCase):
    def test_reversed_corridor_uses_only_physically_observed_breadcrumbs(self) -> None:
        trail = SafeRetreatTrail(map_name="Azeroth", sample_spacing_world=1.0)
        for x, y in ((0, 0), (2, 0), (4, 1), (6, 2), (8, 2)):
            trail.observe(NavPoint(float(x), float(y), 10.0))

        corridor = trail.reversed_corridor(current=NavPoint(8.5, 2.0, 10.0))

        self.assertEqual(corridor.start, NavPoint(8.5, 2.0, 10.0))
        self.assertEqual(corridor.stop, NavPoint(0.0, 0.0, 10.0))
        self.assertEqual(corridor.source, "fresh_client_visible_reverse_breadcrumbs")
        self.assertFalse(corridor.execution_authority)

    def test_coordinate_jump_clears_preteleport_history(self) -> None:
        trail = SafeRetreatTrail(
            map_name="Azeroth",
            sample_spacing_world=1.0,
            maximum_sample_jump_world=5.0,
        )
        trail.observe(NavPoint(0.0, 0.0, 1.0))
        trail.observe(NavPoint(2.0, 0.0, 1.0))
        trail.observe(NavPoint(100.0, 100.0, 5.0))

        record = trail.record()

        self.assertEqual(record.points, (NavPoint(100.0, 100.0, 5.0),))
        with self.assertRaisesRegex(ValueError, "insufficient"):
            trail.reversed_corridor(current=NavPoint(101.0, 100.0, 5.0))

    def test_subsampled_noise_does_not_create_zigzag_breadcrumbs(self) -> None:
        trail = SafeRetreatTrail(map_name="Azeroth", sample_spacing_world=1.5)
        self.assertTrue(trail.observe(NavPoint(0.0, 0.0, 1.0)))
        self.assertFalse(trail.observe(NavPoint(0.3, 0.2, 1.0)))
        self.assertFalse(trail.observe(NavPoint(0.8, -0.1, 1.0)))
        self.assertTrue(trail.observe(NavPoint(1.6, 0.0, 1.0)))
        self.assertEqual(len(trail.record().points), 2)

    def test_handoff_context_requires_exact_provenance_and_live_continuity(self) -> None:
        context = {
            "map": "Azeroth",
            "points": [[0.0, 0.0, 1.0], [2.0, 0.0, 1.0], [4.0, 1.0, 1.0]],
            "sampled_distance_world": 4.25,
            "source": "fresh_client_visible_positions",
            "execution_authority": False,
        }
        corridor = corridor_from_retreat_context(
            context,
            current=NavPoint(4.5, 1.0, 1.0),
            expected_map_name="Azeroth",
        )
        self.assertEqual(corridor.stop, NavPoint(0.0, 0.0, 1.0))

        context["execution_authority"] = True
        with self.assertRaisesRegex(ValueError, "provenance"):
            corridor_from_retreat_context(
                context,
                current=NavPoint(4.5, 1.0, 1.0),
                expected_map_name="Azeroth",
            )

    def test_handoff_can_use_full_bounded_trail_for_a_long_leash(self) -> None:
        points = [[float(x), 0.0, 1.0] for x in range(0, 102, 2)]
        context = {
            "map": "Azeroth",
            "points": points,
            "sampled_distance_world": 100.0,
            "source": "fresh_client_visible_positions",
            "execution_authority": False,
        }
        corridor = corridor_from_retreat_context(
            context,
            current=NavPoint(100.5, 0.0, 1.0),
            expected_map_name="Azeroth",
        )
        distance = sum(
            left.distance_2d(right)
            for left, right in zip(corridor.points, corridor.points[1:])
        )
        self.assertGreater(distance, 95.0)
        self.assertLessEqual(distance, 300.0)

    def test_handoff_accepts_the_producers_full_default_sample_capacity(self) -> None:
        points = [[float(index) * 1.5, 0.0, 1.0] for index in range(201)]
        context = {
            "map": "Azeroth",
            "points": points,
            "sampled_distance_world": 300.0,
            "source": "fresh_client_visible_positions",
            "execution_authority": False,
        }

        corridor = corridor_from_retreat_context(
            context,
            current=NavPoint(300.5, 0.0, 1.0),
            expected_map_name="Azeroth",
        )

        self.assertGreaterEqual(len(corridor.points), 75)

    def test_handoff_rejects_an_overlong_context_even_below_the_point_cap(self) -> None:
        points = [[float(index) * 2.0, 0.0, 1.0] for index in range(154)]
        context = {
            "map": "Azeroth",
            "points": points,
            "sampled_distance_world": 306.0,
            "source": "fresh_client_visible_positions",
            "execution_authority": False,
        }

        with self.assertRaisesRegex(ValueError, "breadcrumb distance"):
            corridor_from_retreat_context(
                context,
                current=NavPoint(306.5, 0.0, 1.0),
                expected_map_name="Azeroth",
            )

    def test_handoff_can_resume_from_the_middle_of_the_verified_reverse_trail(self) -> None:
        points = [[float(index) * 1.5, 0.0, 1.0] for index in range(201)]
        context = {
            "map": "Azeroth",
            "points": points,
            "sampled_distance_world": 300.0,
            "source": "fresh_client_visible_positions",
            "execution_authority": False,
        }

        corridor = corridor_from_retreat_context(
            context,
            current=NavPoint(45.4, 0.1, 1.0),
            expected_map_name="Azeroth",
        )

        self.assertEqual(corridor.start, NavPoint(45.4, 0.1, 1.0))
        self.assertLessEqual(corridor.stop.x, 1.5)
        self.assertTrue(all(point.x <= 46.0 for point in corridor.points))

    def test_resumed_handoff_still_rejects_a_pose_off_the_verified_trail(self) -> None:
        context = {
            "map": "Azeroth",
            "points": [[0.0, 0.0, 1.0], [3.0, 0.0, 1.0], [6.0, 0.0, 1.0]],
            "sampled_distance_world": 6.0,
            "source": "fresh_client_visible_positions",
            "execution_authority": False,
        }

        with self.assertRaisesRegex(ValueError, "detached"):
            corridor_from_retreat_context(
                context,
                current=NavPoint(3.0, 20.0, 1.0),
                expected_map_name="Azeroth",
            )


if __name__ == "__main__":
    unittest.main()
