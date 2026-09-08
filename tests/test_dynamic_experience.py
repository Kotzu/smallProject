from __future__ import annotations

from dataclasses import replace
from contextlib import closing
from pathlib import Path
import tempfile
import sqlite3
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.dynamic_avoidance import DynamicEntityTrack
from perfect_assassin.movement.dynamic_experience import (
    DynamicExperienceStore,
    encounter_from_track,
    escaped_risk_observation,
)


ROOT = Path(__file__).parents[1]


def _track(*, reaction: str = "HOSTILE") -> DynamicEntityTrack:
    return DynamicEntityTrack(
        track_id="dynamic-screen:7",
        reaction=reaction,  # type: ignore[arg-type]
        first_observed_at_s=10.0,
        last_observed_at_s=10.2,
        expires_at_s=11.0,
        center_x_normalized=0.15,
        center_y_normalized=0.48,
        velocity_x_normalized_per_s=0.02,
        velocity_y_normalized_per_s=-0.01,
        width_normalized=0.12,
        height_normalized=0.02,
        position_uncertainty_normalized=0.04,
        confidence=0.91,
        observation_count=3,
        source_key=None,
    )


def _observation(*, reaction: str = "HOSTILE"):
    return encounter_from_track(
        _track(reaction=reaction),
        session_id="run:test:durable-memory",
        map_name="Azeroth",
        navmesh_sha256="A" * 64,
        observed_at_utc="2026-08-28T12:00:00.000000Z",
        observer_world_x=1843.25,
        observer_world_y=1591.75,
        observer_world_z=93.5,
        observer_facing_rad=1.25,
    )


class DynamicExperienceTests(unittest.TestCase):
    def test_summary_uses_covering_index_without_temporary_grouping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DynamicExperienceStore(Path(directory) / "memory.sqlite3") as store:
                store.append(_observation())
                statements: list[str] = []
                store._connection.set_trace_callback(statements.append)
                store.summary_record(map_name="Azeroth", navmesh_sha256="A" * 64)
                store._connection.set_trace_callback(None)
                summary_query = next(sql for sql in statements if "GROUP BY reaction" in sql)
                plan = store._connection.execute(
                    "EXPLAIN QUERY PLAN " + summary_query,
                ).fetchall()
                description = " ".join(str(row[3]) for row in plan)
                self.assertIn(
                    "COVERING INDEX dynamic_encounters_world_reaction_time", description,
                )
                self.assertNotIn("TEMP B-TREE", description)

    def test_existing_v2_database_is_indexed_without_changing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite3"
            with DynamicExperienceStore(path) as store:
                store.append(_observation())
                store.append(replace(_observation(), event_id="B" * 64, reaction="NEUTRAL"))
                store.append(replace(_observation(), event_id="C" * 64, map_name="Other"))
                expected = store.summary_record(map_name="Azeroth", navmesh_sha256="A" * 64)
                before = store._connection.execute(
                    "SELECT * FROM dynamic_encounters ORDER BY event_id"
                ).fetchall()
            with closing(sqlite3.connect(path)) as legacy:
                legacy.execute("DROP INDEX dynamic_encounters_world_reaction_time")
                self.assertEqual(legacy.execute("PRAGMA user_version").fetchone()[0], 2)
            # Reopening is the migration path, including a second idempotent open.
            for _ in range(2):
                with DynamicExperienceStore(path) as reopened:
                    self.assertEqual(reopened.summary_record(
                        map_name="Azeroth", navmesh_sha256="A" * 64,
                    ), expected)
                    self.assertEqual(reopened._connection.execute(
                        "SELECT * FROM dynamic_encounters ORDER BY event_id"
                    ).fetchall(), before)
                    self.assertEqual(reopened._connection.execute(
                        "PRAGMA synchronous"
                    ).fetchone()[0], 2)  # FULL durability remains enabled.

    def test_observation_preserves_encounter_without_inventing_entity_position(self) -> None:
        record = _observation().to_record()
        ContractValidator(
            ROOT / "contracts" / "dynamic-encounter-observation.schema.json"
        ).validate(record)
        self.assertEqual(
            record["observer_world_position"],
            [1843.25, 1591.75, 93.5],
        )
        self.assertIsNone(record["entity_world_position"])
        self.assertEqual(
            record["entity_position_semantics"],
            "UNKNOWN_NOT_INFERRED",
        )
        self.assertFalse(record["execution_authority"])

    def test_sqlite_wal_store_survives_reopen_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dynamic-experience.sqlite3"
            observation = _observation()
            with DynamicExperienceStore(path) as store:
                self.assertTrue(store.append(observation))
                self.assertFalse(store.append(observation))
            with DynamicExperienceStore(path) as reopened:
                summary = reopened.summary_record(
                    map_name="Azeroth",
                    navmesh_sha256="A" * 64,
                )
                ContractValidator(
                    ROOT / "contracts" / "dynamic-experience-summary.schema.json"
                ).validate(summary)
                self.assertEqual(summary["observation_count"], 1)
                self.assertEqual(summary["reaction_counts"]["HOSTILE"], 1)
                self.assertEqual(
                    summary["last_observed_at_utc"],
                    "2026-08-28T12:00:00.000000Z",
                )

    def test_same_event_id_with_different_content_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dynamic-experience.sqlite3"
            observation = _observation()
            with DynamicExperienceStore(path) as store:
                store.append(observation)
                with self.assertRaisesRegex(ValueError, "event id collision"):
                    store.append(replace(observation, confidence=0.5))

    def test_active_track_expiry_does_not_delete_persistent_experience(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dynamic-experience.sqlite3"
            with DynamicExperienceStore(path) as store:
                store.append(_observation(reaction="NEUTRAL"))
                summary = store.summary_record(
                    map_name="Azeroth",
                    navmesh_sha256="A" * 64,
                )
            self.assertEqual(summary["observation_count"], 1)
            self.assertEqual(summary["reaction_counts"]["NEUTRAL"], 1)
            self.assertEqual(
                summary["experience_semantics"],
                "APPEND_ONLY_OBSERVER_POSE_ENCOUNTER_MEMORY",
            )

    def test_hostile_observer_poses_become_persistent_regional_risk_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dynamic-experience.sqlite3"
            first = _observation()
            second = replace(
                first,
                event_id="B" * 64,
                observed_at_utc="2026-08-28T12:01:00.000000Z",
                observer_world_x=1848.0,
                observer_world_y=1590.0,
                confidence=0.60,
            )
            neutral = replace(
                first,
                event_id="C" * 64,
                observed_at_utc="2026-08-28T12:02:00.000000Z",
                reaction="NEUTRAL",
            )
            with DynamicExperienceStore(path) as store:
                store.append(first)
                store.append(second)
                store.append(neutral)
                areas = store.historical_risk_areas(
                    map_name="Azeroth",
                    navmesh_sha256="A" * 64,
                )

            self.assertEqual(len(areas), 1)
            self.assertEqual(areas[0].observation_count, 2)
            self.assertAlmostEqual(areas[0].risk_score, 1.51)
            self.assertAlmostEqual(areas[0].x, (1843.25 + 1848.0) / 2.0)
            self.assertEqual(areas[0].kind, "HOSTILE_NPC")
            self.assertIn("observer-hostile-risk", areas[0].area_id)

    def test_regional_risk_query_rejects_other_navmesh_binding_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DynamicExperienceStore(
                Path(directory) / "dynamic-experience.sqlite3"
            ) as store:
                with self.assertRaisesRegex(ValueError, "risk binding"):
                    store.historical_risk_areas(
                        map_name="Azeroth",
                        navmesh_sha256="short",
                    )

    def test_escaped_risky_aggro_becomes_permanent_maximum_risk_area(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dynamic-experience.sqlite3"
            observation = escaped_risk_observation(
                session_id="journey:test",
                map_name="Azeroth",
                navmesh_sha256="A" * 64,
                observed_at_utc="2026-08-28T12:03:00.000000Z",
                observer_world_x=2115.0,
                observer_world_y=933.0,
                observer_world_z=41.0,
                encounter_id="combat:escape",
                navigation_run_id="nav:one",
            )
            with DynamicExperienceStore(path) as store:
                self.assertTrue(store.append_escaped_risk(observation))
                self.assertFalse(store.append_escaped_risk(observation))
            with DynamicExperienceStore(path) as reopened:
                areas = reopened.historical_risk_areas(
                    map_name="Azeroth",
                    navmesh_sha256="A" * 64,
                )
            self.assertEqual(len(areas), 1)
            self.assertEqual(areas[0].kind, "HOSTILE_NPC")
            self.assertEqual(areas[0].risk_score, 5.0)
            self.assertEqual(areas[0].radius_yards, 45.0)
            self.assertIn("escaped-risk", areas[0].area_id)


if __name__ == "__main__":
    unittest.main()
