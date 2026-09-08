from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_INPUT = ROOT / "integrations" / "windows-input"
if str(WINDOWS_INPUT) not in sys.path:
    sys.path.insert(0, str(WINDOWS_INPUT))

from run_hunting_engine import (
    combat_search_disposition,
    HuntingEngineError,
    load_search_region,
    local_navigation_disposition,
    patrol_points,
)


class HuntingEngineTests(unittest.TestCase):
    def record(self) -> dict[str, object]:
        return {
            "record_type": "predator_search_region_memory",
            "schema_version": "1.0",
            "region_id": "region:tirisfal:test",
            "client_build": 8606,
            "coordinate_system": "normalized_current_zone_map",
            "map": "Azeroth",
            "zone_index": 25,
            "goal_kind": "hostile_mob",
            "center_normalized": [0.5, 0.5],
            "radius_normalized": 0.01,
            "source_origin": "predator_memory",
            "expires_at": "2026-08-26T07:00:00Z",
            "evidence_refs": ["client-observed:test"],
            "execution_authority": False,
        }

    def load(self, record: dict[str, object], *, hour: int = 6) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "region.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            return load_search_region(
                path, now=datetime(2026, 8, 26, hour, tzinfo=timezone.utc),
            )

    def test_region_is_client_bound_expiring_and_has_no_authority(self) -> None:
        self.assertEqual(self.load(self.record())["source_origin"], "predator_memory")

    def test_region_may_name_a_validated_semantic_entry_but_not_a_path(self) -> None:
        record = self.record()
        record["entry_semantic_destination_id"] = "settlement:deathknell"
        self.assertEqual(
            self.load(record)["entry_semantic_destination_id"],
            "settlement:deathknell",
        )
        record["entry_semantic_destination_id"] = "../../unsafe"
        with self.assertRaises(HuntingEngineError):
            self.load(record)

    def test_server_truth_and_expired_memory_fail_closed(self) -> None:
        server = self.record()
        server["source_origin"] = "server_spawn_state"
        with self.assertRaises(HuntingEngineError):
            self.load(server)
        with self.assertRaisesRegex(HuntingEngineError, "expired"):
            self.load(self.record(), hour=8)

    def test_patrol_is_deterministic_bounded_spiral_not_a_route(self) -> None:
        points = patrol_points(center_x=0.5, center_y=0.5, radius=0.02, count=6)
        self.assertEqual(points, patrol_points(
            center_x=0.5, center_y=0.5, radius=0.02, count=6,
        ))
        self.assertEqual(len(points), 6)
        self.assertEqual(len(set(points)), 6)
        self.assertTrue(all(0.48 <= x <= 0.52 and 0.48 <= y <= 0.52 for x, y in points))
        with self.assertRaises(ValueError):
            patrol_points(center_x=0.5, center_y=0.5, radius=0.02, count=9)

    def test_local_unreachable_samples_are_neither_routes_nor_global_failures(self) -> None:
        self.assertEqual(
            local_navigation_disposition({"status": "ARRIVED", "remaining_world": 4.9}),
            "ACCEPTED_ARRIVAL",
        )
        self.assertEqual(
            local_navigation_disposition({
                "status": "PARTIAL_CORRIDOR_FRONTIER_STUCK",
                "remaining_world": 5.04,
            }),
            "ACCEPTED_NEAR_FRONTIER",
        )
        self.assertEqual(
            local_navigation_disposition({
                "status": "PARTIAL_CORRIDOR_FRONTIER_STUCK",
                "remaining_world": 18.0,
            }),
            "SKIP_UNREACHABLE_SAMPLE",
        )
        self.assertEqual(
            local_navigation_disposition({"status": "SEARCH_VANTAGE_REJECTED"}),
            "SKIP_UNSUITABLE_VANTAGE",
        )
        self.assertEqual(
            local_navigation_disposition({"status": "MANUAL_TAKEOVER"}),
            "STOP_FAIL_CLOSED",
        )

    def test_beyond_plate_range_hands_back_to_patrol_only_without_damage(self) -> None:
        safe_search = {
            "status": "STOPPED_FAIL_CLOSED",
            "detail": "combat acquisition deadline expired",
            "decisions": [
                {"action_id": "combat.monitor_continuous_reacquisition"},
                {"action_id": "combat.monitor_continuous_facing"},
            ],
            "executions": [],
        }
        self.assertEqual(
            combat_search_disposition(safe_search),
            "CONTINUE_PATROL_TARGET_BEYOND_VISUAL_RANGE",
        )
        damaged = dict(safe_search)
        damaged["executions"] = [{"control": "ACTION_SLOT_1"}]
        self.assertEqual(combat_search_disposition(damaged), "STOP_FAIL_CLOSED")

    def test_hunting_navigation_uses_legacy_tbc_heading_fallback(self) -> None:
        source = (WINDOWS_INPUT / "run_hunting_engine.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"--require-exact-body-heading"', source)


if __name__ == "__main__":
    unittest.main()
