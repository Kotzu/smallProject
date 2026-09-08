from __future__ import annotations

import copy
import unittest
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


ROOT = Path(__file__).resolve().parents[1]


def covariance(ordering: list[str], diagonal: list[float]) -> dict:
    matrix = [0.0] * 16
    for index, value in enumerate(diagonal):
        matrix[index * 4 + index] = value
    return {
        "dimension": 4,
        "ordering": ordering,
        "matrix_row_major": matrix,
    }


def freshness(status: str = "FRESH", age_ms: float = 20.0) -> dict:
    return {
        "observed_at": "2026-08-22T18:00:00Z",
        "published_at": "2026-08-22T18:00:00.020Z",
        "age_ms": age_ms,
        "stale_after_ms": 250.0,
        "status": status,
    }


def provenance(
    origin: str,
    scope: str = "champion_eligible",
    source_id: str = "fixture_pose_provider",
) -> dict:
    return {
        "source_id": source_id,
        "origin": origin,
        "capability": "pose_observation",
        "scope": scope,
        "evidence_refs": ["frame:fixture:0001"],
    }


def player_component(state: str = "ANCHORED") -> dict:
    return {
        "tracking_state": state,
        "pose": {
            "position": {"x": 0.42, "y": 0.64, "z": 0.0},
            "body_yaw_deg": 35.0,
            "linear_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "uncertainty": {
            "covariance": covariance(
                ["x", "y", "z", "body_yaw_rad"],
                [0.01, 0.01, 0.04, 0.0025],
            ),
            "position_radius_95": 0.25,
            "vertical_error_95": 0.4,
            "yaw_error_95_deg": 3.0,
        },
        "confidence": 0.97,
        "freshness": freshness(),
        "provenance": provenance("minimap_vision"),
    }


def camera_component() -> dict:
    return {
        "tracking_state": "TRACKED",
        "pose": {
            "reference_frame": "player_relative",
            "yaw_deg": -12.0,
            "pitch_deg": -18.0,
            "roll_deg": 0.0,
            "zoom": 7.5,
        },
        "uncertainty": {
            "covariance": covariance(
                ["yaw_rad", "pitch_rad", "roll_rad", "zoom"],
                [0.004, 0.004, 0.001, 0.09],
            ),
            "angular_error_95_deg": 5.0,
            "zoom_error_95": 0.5,
        },
        "confidence": 0.9,
        "freshness": freshness(age_ms=24.0),
        "provenance": provenance("scene_vision", source_id="fixture_camera_provider"),
    }


def pose_observation() -> dict:
    return {
        "record_type": "pose_observation",
        "schema_version": "0.1",
        "observation_id": "pose-observation:fixture:0001",
        "session_id": "session:fixture",
        "champion_id": "champion:predator",
        "target_profile": "tbc_243_lab",
        "decision_context": "champion",
        "client_build": "2.4.3.8606",
        "build_signature": "wow-tbc-2.4.3.8606-enGB",
        "map_ref": "map:tirisfal_glades",
        "map_signature": "fixture:tirisfal:v1",
        "coordinate_space": {
            "space_id": "tbc243:minimap:tirisfal",
            "kind": "normalized_map",
            "units": "normalized",
            "axis_convention": "x-east,y-south,z-up",
        },
        "provider_id": "fixture_pose_provider",
        "provider_version": "0.1.0",
        "navigation_state": "ANCHORED",
        "player": player_component(),
        "camera": camera_component(),
        "execution_authority": False,
        "created_at": "2026-08-22T18:00:00.020Z",
    }


def pose_estimate() -> dict:
    value = pose_observation()
    value["record_type"] = "pose_estimate"
    value["estimate_id"] = "pose-estimate:fixture:0001"
    del value["observation_id"]
    value["estimator_id"] = "fixture_pose_fusion"
    value["estimator_version"] = "0.1.0"
    value["input_observation_ids"] = ["pose-observation:fixture:0001"]
    del value["provider_id"]
    del value["provider_version"]
    value["navigation_state"] = "TRACKED"
    value["player"]["tracking_state"] = "TRACKED"
    value["player"]["provenance"] = provenance(
        "fused_client_observations", source_id="fixture_pose_fusion"
    )
    value["camera"]["provenance"] = provenance(
        "fused_client_observations", source_id="fixture_pose_fusion"
    )
    return value


class PoseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ContractValidator(ROOT / "contracts" / "pose.schema.json")

    def test_observation_keeps_player_and_camera_pose_separate(self) -> None:
        value = pose_observation()
        self.validator.validate(value)
        self.assertEqual(value["player"]["pose"]["body_yaw_deg"], 35.0)
        self.assertEqual(value["camera"]["pose"]["yaw_deg"], -12.0)

    def test_estimate_requires_covariance_and_freshness(self) -> None:
        value = pose_estimate()
        self.validator.validate(value)

        without_covariance = copy.deepcopy(value)
        del without_covariance["player"]["uncertainty"]["covariance"]
        with self.assertRaises(ContractValidationError):
            self.validator.validate(without_covariance)

        without_freshness = copy.deepcopy(value)
        del without_freshness["camera"]["freshness"]
        with self.assertRaises(ContractValidationError):
            self.validator.validate(without_freshness)

    def test_lost_estimate_is_explicit_and_contains_no_current_player_pose(self) -> None:
        value = pose_estimate()
        value["navigation_state"] = "LOST"
        value["player"]["tracking_state"] = "LOST"
        value["player"]["pose"] = None
        value["player"]["uncertainty"] = None
        value["player"]["confidence"] = 0
        value["player"]["freshness"] = freshness("EXPIRED", age_ms=5000.0)
        self.validator.validate(value)

    def test_lost_player_rejects_a_populated_pose(self) -> None:
        value = pose_estimate()
        previous_pose = copy.deepcopy(value["player"]["pose"])
        value["navigation_state"] = "LOST"
        value["player"]["tracking_state"] = "LOST"
        value["player"]["uncertainty"] = None
        value["player"]["confidence"] = 0
        value["player"]["pose"] = previous_pose
        with self.assertRaises(ContractValidationError):
            self.validator.validate(value)

    def test_navigation_state_must_match_player_tracking_state(self) -> None:
        value = pose_estimate()
        value["navigation_state"] = "DEGRADED"
        with self.assertRaises(ContractValidationError):
            self.validator.validate(value)

    def test_champion_rejects_server_ground_truth_pose(self) -> None:
        value = pose_observation()
        value["player"]["provenance"] = provenance(
            "server_ground_truth",
            scope="lab_evaluation_only",
            source_id="lab_server_pose_oracle",
        )
        with self.assertRaises(ContractValidationError):
            self.validator.validate(value)

    def test_champion_rejects_lab_oracle_estimate(self) -> None:
        value = pose_estimate()
        value["player"]["provenance"] = provenance(
            "lab_oracle",
            scope="lab_evaluation_only",
            source_id="mangos_mmap_oracle",
        )
        with self.assertRaises(ContractValidationError):
            self.validator.validate(value)

    def test_lab_clone_can_record_server_pose_only_for_evaluation(self) -> None:
        value = pose_observation()
        value["decision_context"] = "lab_clone"
        value["champion_id"] = "lab-clone:fixture"
        value["player"]["provenance"] = provenance(
            "server_ground_truth",
            scope="lab_evaluation_only",
            source_id="lab_server_pose_oracle",
        )
        self.validator.validate(value)

        mislabeled = copy.deepcopy(value)
        mislabeled["player"]["provenance"]["scope"] = "champion_eligible"
        with self.assertRaises(ContractValidationError):
            self.validator.validate(mislabeled)


if __name__ == "__main__":
    unittest.main()
