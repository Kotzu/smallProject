from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.brain.leveling import (
    LevelingBrain,
    LevelingRequest,
)
from perfect_assassin.knowledge.leveling_plan import load_leveling_plan
from perfect_assassin.knowledge.route_teacher import (
    RouteTeacherImportConfig,
    import_zygor_lua,
)


class LevelingBrainTests(unittest.TestCase):
    def _catalog(self):
        return import_zygor_lua(
            '''
ZygorGuidesViewer:RegisterGuide("fixture",{},[[
step
|goto Tirisfal Glades 10,20
step
talk Undertaker Mordo##1568
step
|goto Tirisfal Glades 30,40
]])
''',
            config=RouteTeacherImportConfig(
                catalog_id="fixture.leveling.catalog",
                target_profile="tbc243_lab",
                client_version="2.4.3",
                client_build="2.4.3.8606",
                provider_version="8.1.37070",
                retrieved_at="2026-09-01T00:00:00Z",
                source_uri="local://user-owned-guide.lua",
                default_map_id=0,
                default_map_name="Azeroth",
                zone_map_bindings={"Tirisfal Glades": (0, "Azeroth")},
            ),
        )

    def test_level_selects_ordered_advisory_steps_and_next_goal(self) -> None:
        plan = LevelingBrain().plan(
            self._catalog(),
            LevelingRequest(current_level=1, map_id=0, limit=3),
            plan_id="leveling.plan.test",
        )
        self.assertEqual(plan.status, "READY")
        self.assertEqual([step.step_order for step in plan.steps], [1, 2, 3])
        self.assertEqual(plan.next_goal, (0.10, 0.20))
        self.assertFalse(any(step.execution_authority for step in plan.steps))

    def test_leveling_cursor_skips_completed_steps_and_keeps_non_coordinate_advice(self) -> None:
        catalog = self._catalog()
        completed = frozenset({catalog.entries[0].entry_id})
        plan = LevelingBrain().plan(
            catalog,
            LevelingRequest(
                current_level=1,
                map_id=0,
                completed_entry_ids=completed,
                limit=2,
            ),
            plan_id="leveling.plan.cursor",
        )
        self.assertEqual([step.step_order for step in plan.steps], [2, 3])
        self.assertEqual(plan.next_goal, (0.30, 0.40))

    def test_no_matching_map_is_fail_closed_without_goal(self) -> None:
        plan = LevelingBrain().plan(
            self._catalog(),
            LevelingRequest(current_level=10, map_id=1),
            plan_id="leveling.plan.empty",
        )
        self.assertEqual(plan.status, "NO_STEP")
        self.assertIsNone(plan.next_goal)

    def test_plan_round_trip_rechecks_read_only_authority(self) -> None:
        plan = LevelingBrain().plan(
            self._catalog(),
            LevelingRequest(current_level=1, map_id=0),
            plan_id="leveling.plan.roundtrip",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(plan.to_record()), encoding="utf-8")
            restored = load_leveling_plan(path)
        self.assertEqual(restored, plan)
        invalid = plan.to_record()
        invalid["execution_authority"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_leveling_plan(path)


if __name__ == "__main__":
    unittest.main()
