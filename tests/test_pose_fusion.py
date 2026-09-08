from __future__ import annotations

import copy
import unittest
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.pose import (
    MinimapAnchorMeasurement,
    MinimapAnchorObservationBuilder,
    PoseFusionEngine,
    PoseFusionError,
    PoseIdentity,
)


ROOT = Path(__file__).resolve().parents[1]


def identity() -> PoseIdentity:
    return PoseIdentity(
        session_id="session:pose-fixture",
        champion_id="champion:predator",
        target_profile="tbc_243_lab",
        decision_context="champion",
        client_build="2.4.3.8606",
        build_signature="wow-tbc-2.4.3.8606-enGB",
        map_ref="map:tirisfal_glades",
        map_signature="fixture:tirisfal:v1",
        coordinate_space={
            "space_id": "tbc243:minimap:tirisfal",
            "kind": "normalized_map",
            "units": "normalized",
            "axis_convention": "x-east,y-south,z-up",
        },
    )


def measurement(
    observation_id: str,
    *,
    x: float = 0.42,
    y: float = 0.64,
    yaw: float = 35.0,
    variance: float = 0.01,
    confidence: float = 0.9,
    observed_at: str = "2026-08-22T18:00:00Z",
    published_at: str = "2026-08-22T18:00:00.020Z",
) -> MinimapAnchorMeasurement:
    return MinimapAnchorMeasurement(
        observation_id=observation_id,
        source_id="fixture_minimap_anchor",
        observed_at=observed_at,
        published_at=published_at,
        evidence_ref=f"frame:{observation_id}",
        normalized_x=x,
        normalized_y=y,
        normalized_z=0.0,
        body_yaw_deg=yaw,
        position_variance=variance,
        vertical_variance=variance * 4,
        yaw_variance_rad2=variance,
        confidence=confidence,
    )


def camera_component(yaw: float, reference_frame: str = "player_relative") -> dict:
    matrix = [0.0] * 16
    for index, value in enumerate((0.004, 0.004, 0.001, 0.09)):
        matrix[index * 4 + index] = value
    return {
        "tracking_state": "TRACKED",
        "pose": {
            "reference_frame": reference_frame,
            "yaw_deg": yaw,
            "pitch_deg": -18.0,
            "roll_deg": 0.0,
            "zoom": 7.5,
        },
        "uncertainty": {
            "covariance": {
                "dimension": 4,
                "ordering": ["yaw_rad", "pitch_rad", "roll_rad", "zoom"],
                "matrix_row_major": matrix,
            },
            "angular_error_95_deg": 7.1,
            "zoom_error_95": 0.59,
        },
        "confidence": 0.88,
        "freshness": {
            "observed_at": "2026-08-22T18:00:00Z",
            "published_at": "2026-08-22T18:00:00.020Z",
            "age_ms": 20.0,
            "stale_after_ms": 250.0,
            "status": "FRESH",
        },
        "provenance": {
            "source_id": "fixture_scene_camera",
            "origin": "scene_vision",
            "capability": "pose_observation",
            "scope": "champion_eligible",
            "evidence_refs": ["frame:camera:0001"],
        },
    }


class PoseFusionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ContractValidator(ROOT / "contracts" / "pose.schema.json")
        self.builder = MinimapAnchorObservationBuilder(self.validator)
        self.engine = PoseFusionEngine(self.validator)

    def build(self, value: MinimapAnchorMeasurement) -> dict:
        return self.builder.build(identity(), value)

    def test_minimap_anchor_builds_player_pose_but_never_invents_camera(self) -> None:
        observation = self.build(measurement("pose:anchor:one"))

        self.assertEqual(observation["navigation_state"], "ANCHORED")
        self.assertEqual(observation["player"]["pose"]["body_yaw_deg"], 35.0)
        self.assertEqual(observation["camera"]["tracking_state"], "LOST")
        self.assertIsNone(observation["camera"]["pose"])
        self.assertFalse(observation["execution_authority"])

    def test_expired_anchor_fails_closed_to_lost(self) -> None:
        observation = self.build(
            measurement(
                "pose:anchor:expired",
                published_at="2026-08-22T18:00:02Z",
            )
        )

        self.assertEqual(observation["navigation_state"], "LOST")
        self.assertIsNone(observation["player"]["pose"])
        self.assertEqual(observation["player"]["confidence"], 0)

    def test_low_variance_anchor_dominates_position_without_hiding_uncertainty(self) -> None:
        precise = self.build(
            measurement("pose:anchor:precise", x=0.2, variance=0.0001)
        )
        noisy = self.build(
            measurement("pose:anchor:noisy", x=0.8, variance=0.1)
        )
        estimate = self.engine.fuse(
            [noisy, precise],
            estimate_id="pose:estimate:weighted",
            created_at="2026-08-22T18:00:00.040Z",
        )

        self.assertLess(estimate["player"]["pose"]["position"]["x"], 0.21)
        self.assertGreater(
            estimate["player"]["uncertainty"]["position_radius_95"], 0
        )
        self.assertEqual(
            estimate["input_observation_ids"],
            ["pose:anchor:noisy", "pose:anchor:precise"],
        )

    def test_body_yaw_fusion_wraps_across_180_degrees(self) -> None:
        left = self.build(measurement("pose:anchor:left", yaw=179.0))
        right = self.build(measurement("pose:anchor:right", yaw=-179.0))
        estimate = self.engine.fuse(
            [left, right],
            estimate_id="pose:estimate:yaw-wrap",
            created_at="2026-08-22T18:00:00.040Z",
        )

        self.assertGreater(abs(estimate["player"]["pose"]["body_yaw_deg"]), 175)

    def test_camera_is_fused_independently_from_body(self) -> None:
        observation = self.build(measurement("pose:anchor:camera", yaw=80.0))
        observation["camera"] = camera_component(-20.0)
        self.validator.validate(observation)
        estimate = self.engine.fuse(
            [observation],
            estimate_id="pose:estimate:camera",
            created_at="2026-08-22T18:00:00.040Z",
        )

        self.assertAlmostEqual(estimate["player"]["pose"]["body_yaw_deg"], 80.0)
        self.assertAlmostEqual(estimate["camera"]["pose"]["yaw_deg"], -20.0)
        self.assertEqual(estimate["camera"]["tracking_state"], "TRACKED")

    def test_stale_evidence_degrades_and_expired_evidence_is_lost(self) -> None:
        observation = self.build(measurement("pose:anchor:aging"))
        stale = self.engine.fuse(
            [observation],
            estimate_id="pose:estimate:stale",
            created_at="2026-08-22T18:00:00.600Z",
        )
        expired = self.engine.fuse(
            [observation],
            estimate_id="pose:estimate:expired",
            created_at="2026-08-22T18:00:02Z",
        )

        self.assertEqual(stale["navigation_state"], "DEGRADED")
        self.assertEqual(stale["player"]["freshness"]["status"], "STALE")
        self.assertEqual(expired["navigation_state"], "LOST")
        self.assertIsNone(expired["player"]["pose"])

    def test_map_or_build_mismatch_is_rejected(self) -> None:
        first = self.build(measurement("pose:anchor:first"))
        other_map = copy.deepcopy(first)
        other_map["observation_id"] = "pose:anchor:other-map"
        other_map["map_signature"] = "fixture:other-map:v1"
        self.validator.validate(other_map)

        with self.assertRaisesRegex(PoseFusionError, "map_signature"):
            self.engine.fuse(
                [first, other_map],
                estimate_id="pose:estimate:mismatch",
                created_at="2026-08-22T18:00:00.040Z",
            )

    def test_camera_reference_frames_cannot_be_mixed(self) -> None:
        first = self.build(measurement("pose:anchor:camera-one"))
        second = self.build(measurement("pose:anchor:camera-two"))
        first["camera"] = camera_component(-20.0, "player_relative")
        second["camera"] = camera_component(15.0, "map_world")
        self.validator.validate(first)
        self.validator.validate(second)

        with self.assertRaisesRegex(PoseFusionError, "reference frames"):
            self.engine.fuse(
                [first, second],
                estimate_id="pose:estimate:mixed-camera",
                created_at="2026-08-22T18:00:00.040Z",
            )

    def test_lab_or_server_truth_cannot_enter_client_pose_fusion(self) -> None:
        observation = self.build(measurement("pose:anchor:oracle"))
        observation["decision_context"] = "lab_clone"
        observation["champion_id"] = "lab-clone:pose-fixture"
        observation["player"]["provenance"] = {
            "source_id": "mangos_pose_oracle",
            "origin": "server_ground_truth",
            "capability": "pose_observation",
            "scope": "lab_evaluation_only",
            "evidence_refs": ["lab:pose:oracle:0001"],
        }
        self.validator.validate(observation)

        with self.assertRaisesRegex(PoseFusionError, "server_ground_truth"):
            self.engine.fuse(
                [observation],
                estimate_id="pose:estimate:oracle-rejected",
                created_at="2026-08-22T18:00:00.040Z",
            )

    def test_fusion_is_deterministic_regardless_of_input_order(self) -> None:
        first = self.build(measurement("pose:anchor:a", x=0.3))
        second = self.build(measurement("pose:anchor:b", x=0.7))
        left = self.engine.fuse(
            [first, second],
            estimate_id="pose:estimate:deterministic",
            created_at="2026-08-22T18:00:00.040Z",
        )
        right = self.engine.fuse(
            [second, first],
            estimate_id="pose:estimate:deterministic",
            created_at="2026-08-22T18:00:00.040Z",
        )

        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
