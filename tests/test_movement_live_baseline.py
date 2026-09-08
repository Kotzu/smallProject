from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.movement.live_baseline import verify_movement_live_baseline


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "config" / "movement-lab" / "crypt-egress-live-baseline-v1.json"


class MovementLiveBaselineTests(unittest.TestCase):
    def test_reviewed_crypt_baseline_is_intact(self) -> None:
        record = json.loads(BASELINE.read_text(encoding="utf-8"))
        report = verify_movement_live_baseline(record, repository_root=ROOT)
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.artifact_count, 5)
        self.assertGreater(report.checked_bytes, 70_000_000)

    def test_changed_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "evidence.bin"
            artifact.write_bytes(b"reviewed")
            record = {
                "record_type": "movement_live_baseline",
                "schema_version": "1.0",
                "baseline_id": "fixture",
                "scope": "fixture",
                "review_state": "OPERATOR_REVIEWED_REFERENCE",
                "execution_authority": False,
                "artifacts": [{
                    "role": "REVIEW_VIDEO",
                    "path": "evidence.bin",
                    "bytes": len(b"reviewed"),
                    "sha256": hashlib.sha256(b"different").hexdigest(),
                }],
                "promotion_requirements": {
                    "minimum_filmed_crypt_exits": 10,
                    "require_no_blockage": True,
                    "require_no_regression_against_reference": True,
                    "require_operator_review": True,
                },
            }
            report = verify_movement_live_baseline(record, repository_root=root)
        self.assertFalse(report.passed)
        self.assertIn("artifact_0:sha256_mismatch", report.failures)


if __name__ == "__main__":
    unittest.main()
