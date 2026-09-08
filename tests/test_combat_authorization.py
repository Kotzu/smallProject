from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import unittest


from perfect_assassin.adapter.combat_authorization import (
    COMBAT_OBSERVER_AUTHORIZATION_ID,
    CombatAuthorizationError,
    issue_combat_observer_authorization_snapshot,
)
from perfect_assassin.contract_validation import ContractValidator


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "execution-targets" / "tbc_243_lab_combat_observer.json"
SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"


class CombatAuthorizationTests(unittest.TestCase):
    def test_exact_profile_issues_only_a_fresh_read_only_window(self) -> None:
        raw = issue_combat_observer_authorization_snapshot(
            TEMPLATE.read_bytes(),
            schema_path=SCHEMA,
            now_utc=datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc),
        )
        record = json.loads(raw)
        ContractValidator(SCHEMA).validate(record)
        self.assertEqual(record["authorization_id"], COMBAT_OBSERVER_AUTHORIZATION_ID)
        self.assertEqual(record["permitted_modes"], [])
        self.assertEqual(
            set(record["permitted_capabilities"]),
            {"SCREEN_CAPTURE_READ_ONLY", "VISIBLE_COMBAT_HUD_READ_ONLY"},
        )
        self.assertEqual(record["approval"]["recorded_at"], "2026-08-24T09:00:00.000000Z")
        self.assertEqual(record["approval"]["expires_at"], "2026-08-24T09:30:00.000000Z")

    def test_scope_mutation_and_missing_acknowledgement_are_refused(self) -> None:
        template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        template["permitted_capabilities"] = ["SCREEN_CAPTURE_READ_ONLY"]
        with self.assertRaisesRegex(CombatAuthorizationError, "exact read-only"):
            issue_combat_observer_authorization_snapshot(
                (json.dumps(template) + "\n").encode(),
                schema_path=SCHEMA,
                now_utc=datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc),
            )
        source = (ROOT / "scripts" / "issue_combat_observer_authorization.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("--acknowledge-combat-observation", source)
        self.assertNotIn("SendInput", source)

    def test_nonfinite_duplicate_and_naive_time_fail_closed(self) -> None:
        with self.assertRaises(CombatAuthorizationError):
            issue_combat_observer_authorization_snapshot(
                b'{"a":1,"a":2}',
                schema_path=SCHEMA,
                now_utc=datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc),
            )
        with self.assertRaisesRegex(CombatAuthorizationError, "timezone-aware"):
            issue_combat_observer_authorization_snapshot(
                TEMPLATE.read_bytes(),
                schema_path=SCHEMA,
                now_utc=datetime(2026, 8, 24, 9, 0),
            )


if __name__ == "__main__":
    unittest.main()
