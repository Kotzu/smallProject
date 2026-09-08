from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

from perfect_assassin.execution.combat_authorization import (
    CombatExecutionAuthorizationError,
    issue_combat_execution_authorization_snapshot,
    load_combat_execution_authorization,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "config" / "execution-targets" / "tbc_243_lab_combat_observer.json"
SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
NOW = datetime(2026, 8, 24, 9, 15, tzinfo=timezone.utc)


class CombatExecutionAuthorizationTests(unittest.TestCase):
    def issue(self) -> bytes:
        return issue_combat_execution_authorization_snapshot(
            BASE.read_bytes(),
            schema_path=SCHEMA,
            now_utc=NOW,
            evidence_ref="gate:combat:f4a:test",
            acknowledge_controlled_combat=True,
        )

    def test_exact_bounded_profile_round_trips(self) -> None:
        raw = self.issue()
        profile = load_combat_execution_authorization(
            raw,
            schema_path=SCHEMA,
            now_utc=NOW + timedelta(seconds=1),
        )
        self.assertEqual(profile.record["permitted_modes"], ["COMBAT_ONLY"])
        self.assertEqual(profile.record["combat_policy"]["max_actions"], 64)
        self.assertIn(
            "TARGET_EXACT_NAME",
            profile.record["combat_policy"]["allowed_controls"],
        )
        self.assertIn(
            "STRAFE_LEFT",
            profile.record["combat_policy"]["allowed_controls"],
        )
        self.assertIn(
            "STRAFE_RIGHT",
            profile.record["combat_policy"]["allowed_controls"],
        )
        self.assertFalse(profile.record["combat_policy"]["player_targets_authorized"])

    def test_no_ack_expiry_and_policy_widening_fail_closed(self) -> None:
        with self.assertRaisesRegex(CombatExecutionAuthorizationError, "acknowledgement"):
            issue_combat_execution_authorization_snapshot(
                BASE.read_bytes(),
                schema_path=SCHEMA,
                now_utc=NOW,
                evidence_ref="gate:test",
                acknowledge_controlled_combat=False,
            )
        raw = self.issue()
        with self.assertRaisesRegex(CombatExecutionAuthorizationError, "active"):
            load_combat_execution_authorization(
                raw,
                schema_path=SCHEMA,
                now_utc=NOW + timedelta(minutes=2),
            )
        record = json.loads(raw)
        record["combat_policy"]["player_targets_authorized"] = True
        with self.assertRaises(CombatExecutionAuthorizationError):
            load_combat_execution_authorization(
                (json.dumps(record) + "\n").encode(),
                schema_path=SCHEMA,
                now_utc=NOW + timedelta(seconds=1),
            )


if __name__ == "__main__":
    unittest.main()
