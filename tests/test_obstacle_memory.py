from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from perfect_assassin.movement.obstacle_memory import (
    LEGACY_MERGED_DISC_REPRESENTATION,
    LOCAL_CLEARANCE_EVIDENCE,
    LearnedObstacle,
    LearnedObstacleMemory,
)


NOW = datetime(2026, 8, 26, 5, 30, tzinfo=timezone.utc)


class LearnedObstacleMemoryTests(unittest.TestCase):
    def test_planning_blocker_adds_actor_capsule_without_rewriting_memory(self) -> None:
        observed = LearnedObstacle(
            obstacle_id="obstacle:fixture",
            map_name="Azeroth",
            zone_index=25,
            x=10.0,
            y=20.0,
            z=30.0,
            radius=3.0,
            observations=2,
            first_observed_at="2026-08-28T10:00:00Z",
            last_observed_at="2026-08-28T10:01:00Z",
            last_run_id="run:fixture",
        )

        self.assertEqual(observed.blocker, (10.0, 20.0, 30.0, 3.0))
        self.assertEqual(
            observed.planning_blocker(),
            (10.0, 20.0, 30.0, 4.25),
        )
        for invalid in (-0.01, 5.01, float("nan")):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    ValueError, "actor obstacle clearance is invalid",
                ):
                    observed.planning_blocker(actor_clearance_world=invalid)

    def test_first_observation_is_provisional_and_round_trips(self) -> None:
        memory = LearnedObstacleMemory.empty(client_build=8606).observe(
            map_name="Azeroth",
            zone_index=25,
            blocker=(2220.1, 261.7, 34.2, 1.5),
            run_id="navigation:test-1",
            observed_at=NOW,
        )

        self.assertEqual(len(memory.obstacles), 1)
        self.assertEqual(memory.obstacles[0].confidence, "provisional")
        restored = LearnedObstacleMemory.from_record(
            memory.to_record(), expected_client_build=8606,
        )
        self.assertEqual(restored, memory)

    def test_repeat_observation_merges_and_confirms(self) -> None:
        first = LearnedObstacleMemory.empty(client_build=8606).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(10.0, 20.0, 30.0, 1.5),
            run_id="navigation:test-1", observed_at=NOW,
        )
        second = first.observe(
            map_name="Azeroth", zone_index=25,
            blocker=(10.5, 20.0, 30.2, 2.0),
            run_id="navigation:test-2", observed_at=NOW + timedelta(hours=1),
        )

        self.assertEqual(len(second.obstacles), 1)
        self.assertEqual(second.obstacles[0].observations, 2)
        self.assertEqual(second.obstacles[0].confidence, "confirmed")
        self.assertEqual(second.obstacles[0].radius, 2.25)

    def test_repeat_contacts_expand_memory_to_cover_every_observed_edge(self) -> None:
        first = LearnedObstacleMemory.empty(client_build=8606).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(0.0, 0.0, 10.0, 2.0),
            run_id="navigation:first-edge", observed_at=NOW,
        )
        merged = first.observe(
            map_name="Azeroth", zone_index=25,
            blocker=(3.0, 0.0, 10.0, 2.0),
            run_id="navigation:second-edge", observed_at=NOW + timedelta(minutes=1),
        )

        obstacle = merged.obstacles[0]
        self.assertAlmostEqual(obstacle.x, 1.5)
        self.assertAlmostEqual(obstacle.radius, 3.5)
        self.assertGreaterEqual(obstacle.radius, abs(obstacle.x - 0.0) + 2.0)
        self.assertGreaterEqual(obstacle.radius, abs(3.0 - obstacle.x) + 2.0)

    def test_local_clearance_contacts_form_bounded_cells_instead_of_one_wall_disc(self) -> None:
        memory = LearnedObstacleMemory.empty(client_build=8606).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(0.0, 0.0, 10.0, 1.5),
            run_id="navigation:first-contact", observed_at=NOW,
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        ).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(3.0, 0.0, 10.0, 1.5),
            run_id="navigation:second-contact",
            observed_at=NOW + timedelta(minutes=1),
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        self.assertEqual(len(memory.obstacles), 2)
        self.assertEqual({item.radius for item in memory.obstacles}, {1.5})

    def test_repeat_local_contact_confirms_only_its_boundary_cell(self) -> None:
        memory = LearnedObstacleMemory.empty(client_build=8606).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(0.0, 0.0, 10.0, 1.5),
            run_id="navigation:first-contact", observed_at=NOW,
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        ).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(0.5, 0.0, 10.0, 2.0),
            run_id="navigation:repeat-contact",
            observed_at=NOW + timedelta(minutes=1),
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        self.assertEqual(len(memory.obstacles), 1)
        self.assertTrue(memory.obstacles[0].planning_confirmed)
        self.assertEqual(memory.obstacles[0].radius, 2.0)

    def test_nearby_is_zone_scoped_distance_sorted_and_bounded(self) -> None:
        memory = LearnedObstacleMemory.empty(client_build=8606)
        for index in range(12):
            memory = memory.observe(
                map_name="Azeroth", zone_index=25,
                blocker=(float(index * 10), 0.0, 30.0, 1.5),
                run_id=f"navigation:test-{index}", observed_at=NOW,
            )
        memory = memory.observe(
            map_name="Azeroth", zone_index=26,
            blocker=(1.0, 0.0, 30.0, 1.5),
            run_id="navigation:other-zone", observed_at=NOW,
        )

        nearby = memory.nearby(
            map_name="Azeroth", zone_index=25,
            x=55.0, y=0.0, now=NOW, limit=8,
        )

        self.assertEqual(len(nearby), 8)
        self.assertTrue(all(item.zone_index == 25 for item in nearby))
        self.assertEqual([item.x for item in nearby[:2]], [50.0, 60.0])

    def test_stale_provisional_obstacle_expires_but_confirmed_survives(self) -> None:
        provisional = LearnedObstacleMemory.empty(client_build=8606).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(10.0, 20.0, 30.0, 1.5),
            run_id="navigation:test-1", observed_at=NOW,
        )
        confirmed = provisional.observe(
            map_name="Azeroth", zone_index=25,
            blocker=(10.0, 20.0, 30.0, 1.5),
            run_id="navigation:test-2", observed_at=NOW + timedelta(hours=1),
        )

        self.assertEqual(provisional.nearby(
            map_name="Azeroth", zone_index=25, x=10.0, y=20.0,
            now=NOW + timedelta(days=8),
        ), ())
        self.assertEqual(len(confirmed.nearby(
            map_name="Azeroth", zone_index=25, x=10.0, y=20.0,
            now=NOW + timedelta(days=3650),
        )), 1)

    def test_wrong_client_build_fails_closed(self) -> None:
        record = LearnedObstacleMemory.empty(client_build=8606).to_record()
        with self.assertRaisesRegex(ValueError, "client build mismatch"):
            LearnedObstacleMemory.from_record(record, expected_client_build=12340)

    def test_local_clearance_obstacle_round_trips_without_detour_identity_merge(self) -> None:
        memory = LearnedObstacleMemory.empty(client_build=8606).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(10.0, 20.0, 30.0, 1.5),
            run_id="navigation:local", observed_at=NOW,
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        ).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(10.0, 20.0, 30.0, 1.5),
            run_id="navigation:polygon", observed_at=NOW,
        )

        self.assertEqual(len(memory.obstacles), 2)
        restored = LearnedObstacleMemory.from_record(
            memory.to_record(), expected_client_build=8606,
        )
        self.assertEqual(
            {item.evidence for item in restored.obstacles},
            {LOCAL_CLEARANCE_EVIDENCE, "collision_slide_and_successful_detour_exclusion"},
        )

    def test_single_local_clearance_cannot_become_permanent_static_geometry(self) -> None:
        memory = LearnedObstacleMemory.empty(client_build=8606).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(10.0, 20.0, 30.0, 1.5),
            run_id="navigation:validated-bypass", observed_at=NOW,
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        )

        obstacle = memory.obstacles[0]
        self.assertEqual(obstacle.confidence, "provisional")
        self.assertFalse(obstacle.planning_confirmed)
        self.assertEqual(memory.nearby(
            map_name="Azeroth", zone_index=25, x=10.0, y=20.0,
            now=NOW + timedelta(days=8),
        ), ())

    def test_legacy_merged_local_disc_is_preserved_but_cannot_shape_routes(self) -> None:
        record = LearnedObstacleMemory.empty(client_build=8606).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(10.0, 20.0, 30.0, 5.0),
            run_id="navigation:legacy", observed_at=NOW,
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        ).observe(
            map_name="Azeroth", zone_index=25,
            blocker=(10.0, 20.0, 30.0, 5.0),
            run_id="navigation:legacy-repeat",
            observed_at=NOW + timedelta(minutes=1),
            evidence=LOCAL_CLEARANCE_EVIDENCE,
        ).to_record()
        del record["obstacles"][0]["representation"]

        restored = LearnedObstacleMemory.from_record(
            record, expected_client_build=8606,
        )

        self.assertEqual(
            restored.obstacles[0].representation,
            LEGACY_MERGED_DISC_REPRESENTATION,
        )
        self.assertFalse(restored.obstacles[0].planning_confirmed)


if __name__ == "__main__":
    unittest.main()
