from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest

from perfect_assassin.execution.continuous_motion_authorization import (
    CONTINUOUS_MOTION_ACKNOWLEDGEMENT_REF,
    ContinuousMotionAuthorizationError,
    issue_continuous_motion_authorization_snapshot,
    load_continuous_motion_authorization_profile,
)


ROOT = Path(__file__).resolve().parents[1]
AUTH_SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
FIXED_UI = ROOT / "config" / "execution-targets" / "tbc_243_lab.json"


class ContinuousMotionAuthorizationTests(unittest.TestCase):

    def test_temporal_renewal_names_exact_parent(self) -> None:
        parent = "A" * 64
        now = datetime.now(timezone.utc)
        raw = issue_continuous_motion_authorization_snapshot(
            FIXED_UI.read_bytes(),
            schema_path=AUTH_SCHEMA,
            now_utc=now,
            evidence_refs=("control_center:movement_permission_checked",),
            acknowledge_continuous_motion=True,
            renewal_parent_sha256=parent,
        )
        profile = load_continuous_motion_authorization_profile(
            raw, schema_path=AUTH_SCHEMA, now_utc=now
        )
        self.assertEqual(profile.renews_authorization_sha256, parent)
        self.assertEqual(profile.record["approval"]["renewal_scope"], "temporal_only")

    def test_issuer_requires_a_separate_continuous_acknowledgement(self) -> None:
        with self.assertRaisesRegex(ContinuousMotionAuthorizationError, "acknowledgement"):
            issue_continuous_motion_authorization_snapshot(
                FIXED_UI.read_bytes(),
                schema_path=AUTH_SCHEMA,
                now_utc=datetime.now(timezone.utc),
                evidence_refs=("test:offline",),
                acknowledge_continuous_motion=False,
            )

    def test_issuer_converts_only_the_exact_fixed_ui_template(self) -> None:
        raw = issue_continuous_motion_authorization_snapshot(
            FIXED_UI.read_bytes(),
            schema_path=AUTH_SCHEMA,
            now_utc=datetime.now(timezone.utc),
            evidence_refs=("test:offline",),
            acknowledge_continuous_motion=True,
        )
        profile = load_continuous_motion_authorization_profile(
            raw,
            schema_path=AUTH_SCHEMA,
            now_utc=datetime.now(timezone.utc),
        )
        self.assertEqual(profile.record["authorization_id"], "execution:tbc243-lab:movement-f4a-continuous-navmesh")
        self.assertEqual(profile.record["movement_policy"]["max_hold_duration_ms"], 450)
        self.assertIn(CONTINUOUS_MOTION_ACKNOWLEDGEMENT_REF, profile.record["approval"]["evidence_refs"])
        self.assertEqual(profile.record["approval"]["max_session_minutes"], 10)

    def test_pending_f3a_template_is_not_upgraded(self) -> None:
        pending = ROOT / "config" / "execution-targets" / "tbc_243_lab_movement_f3a.json"
        with self.assertRaises(ContinuousMotionAuthorizationError):
            issue_continuous_motion_authorization_snapshot(
                pending.read_bytes(),
                schema_path=AUTH_SCHEMA,
                now_utc=datetime.now(timezone.utc),
                evidence_refs=("test:offline",),
                acknowledge_continuous_motion=True,
            )


if __name__ == "__main__":
    unittest.main()
