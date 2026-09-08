from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import perfect_assassin.movement.live_trial_gate as live_trial_gate
from perfect_assassin.movement.live_trial_gate import verify_movement_live_trials


class MovementLiveTrialGateTests(unittest.TestCase):
    def test_empty_registry_reports_zero_of_ten_without_authority(self) -> None:
        report = verify_movement_live_trials(
            {
                "record_type": "movement_live_trial_set",
                "schema_version": "1.0",
                "baseline_id": "baseline-v1",
                "required_trial_count": 10,
                "execution_authority": False,
                "trials": [],
            },
            repository_root=__import__("pathlib").Path.cwd(),
            expected_baseline_id="baseline-v1",
        )
        self.assertEqual(report.valid_trial_count, 0)
        self.assertEqual(report.required_trial_count, 10)
        self.assertFalse(report.promotion_eligible)
        self.assertIn("minimum_filmed_trials_not_met", report.failures)

    def test_trial_registry_cannot_claim_execution_authority(self) -> None:
        report = verify_movement_live_trials(
            {
                "record_type": "movement_live_trial_set",
                "schema_version": "1.0",
                "baseline_id": "baseline-v1",
                "required_trial_count": 10,
                "execution_authority": True,
                "trials": [],
            },
            repository_root=__import__("pathlib").Path.cwd(),
            expected_baseline_id="baseline-v1",
        )
        self.assertEqual(report.failures, ("invalid_trial_set",))

    def test_stationary_artifact_must_prove_the_crypt_location(self) -> None:
        base = {
            "record_type": "stationary_pose_validation",
            "schema_version": "1.0",
            "passed": True,
            "position_source": "COORDINATE_HUD",
            "facing_source": "COORDINATE_HUD_EXACT",
            "expected_location_id": "landmark:deathknell-crypt",
            "expected_map_name": "Azeroth",
            "expected_coordinate_system": "tbc243_client_world_xy",
            "within_expected_location": True,
            "execution_authority": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "stationary.json"
            artifact.write_text(json.dumps(base), encoding="utf-8")
            failures: list[str] = []
            live_trial_gate._verify_stationary(artifact, "trial:1", failures)
            self.assertEqual(failures, [])

            artifact.write_text(json.dumps({
                **base,
                "within_expected_location": False,
            }), encoding="utf-8")
            live_trial_gate._verify_stationary(artifact, "trial:1", failures)
        self.assertIn("trial:1:stationary_validation_failed", failures)


if __name__ == "__main__":
    unittest.main()
