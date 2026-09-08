from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

from perfect_assassin.execution.combat_authorization import (
    issue_combat_execution_authorization_snapshot,
)
from perfect_assassin.execution.combat_runtime_arm import (
    CombatRuntimeArmError,
    issue_combat_runtime_arm_snapshot,
    load_combat_runtime_arm,
)
from tests.test_movement_runtime_arm import (
    exact_json_bytes,
    realm_revalidation_record,
    session_authorization_raw,
    session_receipt_record,
)


ROOT = Path(__file__).resolve().parents[1]
AUTH_SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
ARM_SCHEMA = ROOT / "contracts" / "combat-runtime-arm.schema.json"
RECEIPT_SCHEMA = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
REALM_SCHEMA = ROOT / "contracts" / "local-realm-revalidation.schema.json"
BASE = ROOT / "config" / "execution-targets" / "tbc_243_lab_combat_observer.json"
ISSUED_AT = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
NOW = ISSUED_AT + timedelta(seconds=1)


class CombatRuntimeArmTests(unittest.TestCase):
    def setUp(self) -> None:
        self.combat_raw = issue_combat_execution_authorization_snapshot(
            BASE.read_bytes(),
            schema_path=AUTH_SCHEMA,
            now_utc=ISSUED_AT,
            evidence_ref="gate:combat:f4a:test",
            acknowledge_controlled_combat=True,
        )
        self.session_auth_raw = session_authorization_raw()
        self.receipt_raw = exact_json_bytes(
            session_receipt_record(
                exact_session_authorization_raw=self.session_auth_raw
            )
        )
        self.revalidation_raw = exact_json_bytes(
            realm_revalidation_record(
                self.receipt_raw,
                authorization_raw=self.combat_raw,
            )
        )

    def issue(self) -> bytes:
        return issue_combat_runtime_arm_snapshot(
            authorization_raw=self.combat_raw,
            authorization_schema_path=AUTH_SCHEMA,
            session_authorization_raw=self.session_auth_raw,
            session_receipt_raw=self.receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            realm_revalidation_raw=self.revalidation_raw,
            realm_revalidation_schema_path=REALM_SCHEMA,
            arm_schema_path=ARM_SCHEMA,
            now_utc=NOW,
            now_monotonic_ms=1000.0,
            clock_id="clock:windows:monotonic",
            acknowledge_controlled_combat=True,
        )

    def test_exact_evidence_chain_issues_and_loads_short_arm(self) -> None:
        raw = self.issue()
        arm = load_combat_runtime_arm(
            raw,
            arm_schema_path=ARM_SCHEMA,
            authorization_raw=self.combat_raw,
            authorization_schema_path=AUTH_SCHEMA,
            session_authorization_raw=self.session_auth_raw,
            session_receipt_raw=self.receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            realm_revalidation_raw=self.revalidation_raw,
            realm_revalidation_schema_path=REALM_SCHEMA,
            now_utc=NOW + timedelta(milliseconds=10),
            now_monotonic_ms=1010.0,
        )
        self.assertEqual(arm.pid, 4242)
        self.assertEqual(arm.policy["max_actions"], 64)
        self.assertLessEqual(
            arm.expires_at_monotonic_ms - arm.issued_at_monotonic_ms,
            75_000,
        )

    def test_auth_receipt_revalidation_and_policy_substitution_fail_closed(self) -> None:
        arm = json.loads(self.issue())
        arm["policy"]["player_targets_authorized"] = True
        with self.assertRaises(CombatRuntimeArmError):
            load_combat_runtime_arm(
                exact_json_bytes(arm),
                arm_schema_path=ARM_SCHEMA,
                authorization_raw=self.combat_raw,
                authorization_schema_path=AUTH_SCHEMA,
                session_authorization_raw=self.session_auth_raw,
                session_receipt_raw=self.receipt_raw,
                session_receipt_schema_path=RECEIPT_SCHEMA,
                realm_revalidation_raw=self.revalidation_raw,
                realm_revalidation_schema_path=REALM_SCHEMA,
                now_utc=NOW,
                now_monotonic_ms=1001.0,
            )
        forged_revalidation = json.loads(self.revalidation_raw)
        forged_revalidation["authorization_sha256"] = "A" * 64
        with self.assertRaisesRegex(CombatRuntimeArmError, "identity"):
            issue_combat_runtime_arm_snapshot(
                authorization_raw=self.combat_raw,
                authorization_schema_path=AUTH_SCHEMA,
                session_authorization_raw=self.session_auth_raw,
                session_receipt_raw=self.receipt_raw,
                session_receipt_schema_path=RECEIPT_SCHEMA,
                realm_revalidation_raw=exact_json_bytes(forged_revalidation),
                realm_revalidation_schema_path=REALM_SCHEMA,
                arm_schema_path=ARM_SCHEMA,
                now_utc=NOW,
                now_monotonic_ms=1000.0,
                clock_id="clock:windows:monotonic",
                acknowledge_controlled_combat=True,
            )

    def test_acknowledgement_and_monotonic_expiry_are_required(self) -> None:
        with self.assertRaisesRegex(CombatRuntimeArmError, "acknowledgement"):
            issue_combat_runtime_arm_snapshot(
                authorization_raw=self.combat_raw,
                authorization_schema_path=AUTH_SCHEMA,
                session_authorization_raw=self.session_auth_raw,
                session_receipt_raw=self.receipt_raw,
                session_receipt_schema_path=RECEIPT_SCHEMA,
                realm_revalidation_raw=self.revalidation_raw,
                realm_revalidation_schema_path=REALM_SCHEMA,
                arm_schema_path=ARM_SCHEMA,
                now_utc=NOW,
                now_monotonic_ms=1000.0,
                clock_id="clock:windows:monotonic",
                acknowledge_controlled_combat=False,
            )
        raw = self.issue()
        with self.assertRaisesRegex(CombatRuntimeArmError, "monotonic"):
            load_combat_runtime_arm(
                raw,
                arm_schema_path=ARM_SCHEMA,
                authorization_raw=self.combat_raw,
                authorization_schema_path=AUTH_SCHEMA,
                session_authorization_raw=self.session_auth_raw,
                session_receipt_raw=self.receipt_raw,
                session_receipt_schema_path=RECEIPT_SCHEMA,
                realm_revalidation_raw=self.revalidation_raw,
                realm_revalidation_schema_path=REALM_SCHEMA,
                now_utc=NOW,
                now_monotonic_ms=99_999.0,
            )

    def test_receipt_local_offset_is_normalized_without_changing_the_instant(self) -> None:
        receipt = json.loads(self.receipt_raw)
        local_timezone = timezone(timedelta(hours=3))
        for field in ("created_at", "expires_at"):
            moment = datetime.fromisoformat(
                receipt[field].replace("Z", "+00:00")
            )
            receipt[field] = moment.astimezone(local_timezone).isoformat()
        local_receipt_raw = exact_json_bytes(receipt)
        local_revalidation_raw = exact_json_bytes(
            realm_revalidation_record(
                local_receipt_raw,
                authorization_raw=self.combat_raw,
            )
        )
        raw = issue_combat_runtime_arm_snapshot(
            authorization_raw=self.combat_raw,
            authorization_schema_path=AUTH_SCHEMA,
            session_authorization_raw=self.session_auth_raw,
            session_receipt_raw=local_receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            realm_revalidation_raw=local_revalidation_raw,
            realm_revalidation_schema_path=REALM_SCHEMA,
            arm_schema_path=ARM_SCHEMA,
            now_utc=NOW,
            now_monotonic_ms=1000.0,
            clock_id="clock:windows:monotonic",
            acknowledge_controlled_combat=True,
        )
        arm = load_combat_runtime_arm(
            raw,
            arm_schema_path=ARM_SCHEMA,
            authorization_raw=self.combat_raw,
            authorization_schema_path=AUTH_SCHEMA,
            session_authorization_raw=self.session_auth_raw,
            session_receipt_raw=local_receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            realm_revalidation_raw=local_revalidation_raw,
            realm_revalidation_schema_path=REALM_SCHEMA,
            now_utc=NOW,
            now_monotonic_ms=1001.0,
        )
        self.assertEqual(arm.pid, 4242)


if __name__ == "__main__":
    unittest.main()
