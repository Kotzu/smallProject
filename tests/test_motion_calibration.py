from __future__ import annotations

import copy
import unittest
from pathlib import Path

from perfect_assassin.contract_validation import (
    ContractValidationError,
    ContractValidator,
)
from perfect_assassin.movement import (
    DeterministicMotionModelFitter,
    MotionCalibrationError,
)


ROOT = Path(__file__).resolve().parents[1]


def actor_binding(context: str = "lab_clone") -> dict:
    champion = context == "champion"
    return {
        "schema_version": "1.0",
        "instance_id": "instance:predator",
        "actor_role": "champion_journey" if champion else "lab_clone",
        "actor_id": "champion:predator" if champion else "lab-clone:calibration",
        "decision_context": context,
        "memory_namespace": (
            "memory:champion:predator" if champion else "memory:lab:calibration"
        ),
        "expected_character_name": "Predator",
        "credential_alias": "lab.operator",
        "binding_assurance": {
            "state": "configured_expected_only",
            "evidence_refs": ["execution-target:tbc243-lab"],
        },
    }


def synthetic_trace(
    trace_id: str = "motion-trace:synthetic:001",
    *,
    started_monotonic_s: float = 10.0,
) -> dict:
    actions = [
        (0.0, 0.0),
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0, 0.0),
        (1.0, 0.0),
        (1.0, 0.0),
        (0.0, 0.0),
        (0.0, 0.0),
        (0.0, 1.0),
        (0.0, 1.0),
        (0.0, 1.0),
        (0.0, 1.0),
        (0.0, 0.0),
    ]
    x_positions = [0.0, 0.0, 0.0, 0.7, 1.4, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1]
    yaw_degrees = [
        170.0,
        170.0,
        170.0,
        170.0,
        170.0,
        170.0,
        170.0,
        170.0,
        170.0,
        -178.0,
        -166.0,
        -154.0,
        -154.0,
    ]
    samples = []
    for index, ((forward, turn), x, yaw) in enumerate(
        zip(actions, x_positions, yaw_degrees, strict=True)
    ):
        monotonic_s = started_monotonic_s + index * 0.1
        samples.append(
            {
                "sample_index": index,
                "pose_observation_id": f"{trace_id}:pose:{index:03d}",
                "action_observation_id": f"{trace_id}:action:{index:03d}",
                "timing": {
                    "sample_monotonic_s": monotonic_s,
                    "pose_monotonic_s": monotonic_s,
                    "action_monotonic_s": monotonic_s,
                    "sync_skew_ms": 0.0,
                },
                "pose": {
                    # PA-024B5 starts from the calibrated 2D WorldMap position.
                    "position": {"x": x, "y": 0.0},
                    "body_yaw_deg": yaw,
                },
                "action": {"forward_axis": forward, "turn_axis": turn},
                "uncertainty": {
                    "position_radius_95": 0.001,
                    "yaw_error_95_deg": 0.01,
                    "timing_error_95_ms": 0.0,
                },
            }
        )
    ended_monotonic_s = samples[-1]["timing"]["sample_monotonic_s"]
    return {
        "record_type": "motion_calibration_trace",
        "schema_version": "0.1",
        "trace_id": trace_id,
        "session_id": "session:calibration",
        "target_profile": "tbc_243_lab",
        "actor_binding": actor_binding(),
        "authorization_sha256": "A" * 64,
        "decision_context": "lab_clone",
        "client_build": "2.4.3.8606",
        "build_signature": "wow-exe:406da0c1",
        "map_ref": "map:tirisfal_glades",
        "map_signature": "client-assets:tirisfal:v1",
        "coordinate_space": "tbc243:world-map:tirisfal:2d",
        "trace_kind": "synthetic_fixture",
        "timing": {
            "monotonic_clock_id": "fixture-clock:calibration",
            "started_monotonic_s": started_monotonic_s,
            "ended_monotonic_s": ended_monotonic_s,
            "duration_ms": (ended_monotonic_s - started_monotonic_s) * 1000.0,
            "maximum_sync_skew_ms": 0.0,
        },
        "samples": samples,
        "provenance": {
            "pose_origin": "replay_fixture",
            "action_origin": "replay_fixture",
            "capability": "synchronized_pose_action_trace",
            "scope": "synthetic_fixture",
            "confidence": 1.0,
            "evidence_refs": ["fixture:known-motion-response"],
        },
        "execution_authority": False,
        "created_at": "2026-08-23T01:00:00Z",
    }


def manual_trace(context: str = "lab_clone") -> dict:
    value = synthetic_trace("motion-trace:manual:001")
    value["trace_kind"] = "manual_trace"
    value["decision_context"] = context
    value["actor_binding"] = actor_binding(context)
    value["provenance"] = {
        "pose_origin": "visible_addon_hud",
        "action_origin": "manual_input_observation",
        "capability": "synchronized_pose_action_trace",
        "scope": (
            "unpromoted_evaluation_only"
            if context == "champion"
            else "lab_evaluation_only"
        ),
        "confidence": 0.96,
        "evidence_refs": ["manual-trace:operator-consent:001"],
    }
    return value


class MotionCalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ContractValidator(
            ROOT / "contracts" / "motion-calibration.schema.json"
        )
        self.fitter = DeterministicMotionModelFitter(self.validator)

    def test_synthetic_2d_trace_fits_known_speed_turn_rate_and_latency(self) -> None:
        trace = synthetic_trace()
        self.validator.validate(trace)
        self.assertNotIn("z", trace["samples"][0]["pose"]["position"])

        model = self.fitter.fit(
            [trace],
            model_id="motion-model:fixture:001",
            created_at="2026-08-23T01:01:00Z",
        )

        self.validator.validate(model)
        estimates = model["estimates"]
        self.assertAlmostEqual(
            estimates["forward_speed_world_units_per_s"]["value"], 7.0
        )
        self.assertAlmostEqual(estimates["turn_rate_deg_per_s"]["value"], 120.0)
        self.assertAlmostEqual(
            estimates["forward_input_latency_ms"]["lower_bound"], 0.0
        )
        self.assertAlmostEqual(
            estimates["forward_input_latency_ms"]["upper_bound"], 100.0
        )
        self.assertAlmostEqual(
            estimates["turn_input_latency_ms"]["lower_bound"], 0.0
        )
        self.assertAlmostEqual(
            estimates["turn_input_latency_ms"]["upper_bound"], 100.0
        )
        self.assertGreater(
            estimates["forward_speed_world_units_per_s"]["uncertainty_95"], 0
        )
        self.assertGreater(estimates["turn_rate_deg_per_s"]["uncertainty_95"], 0)
        self.assertIs(model["execution_authority"], False)
        self.assertEqual(model["provenance"]["scope"], "synthetic_fixture")

    def test_fit_is_deterministic_when_trace_input_order_changes(self) -> None:
        first = synthetic_trace("motion-trace:synthetic:001", started_monotonic_s=10.0)
        second = synthetic_trace("motion-trace:synthetic:002", started_monotonic_s=20.0)

        ordered = self.fitter.fit(
            [first, second],
            model_id="motion-model:fixture:deterministic",
            created_at="2026-08-23T01:01:00Z",
        )
        reversed_order = self.fitter.fit(
            [second, first],
            model_id="motion-model:fixture:deterministic",
            created_at="2026-08-23T01:01:00Z",
        )

        self.assertEqual(ordered, reversed_order)
        self.assertEqual(ordered["timing"]["trace_count"], 2)
        self.assertEqual(ordered["timing"]["sample_count"], 26)

    def test_manual_lab_trace_remains_evaluation_only(self) -> None:
        trace = manual_trace()
        self.validator.validate(trace)

        model = self.fitter.fit(
            [trace],
            model_id="motion-model:manual:lab",
            created_at="2026-08-23T01:01:00Z",
        )

        self.assertEqual(model["source_trace_kind"], "manual_trace")
        self.assertEqual(model["provenance"]["scope"], "lab_evaluation_only")
        self.assertEqual(
            model["provenance"]["origin"], "deterministic_manual_trace_fit"
        )

    def test_configured_champion_binding_cannot_promote_calibration(self) -> None:
        trace = manual_trace("champion")
        self.validator.validate(trace)
        self.assertEqual(
            trace["provenance"]["scope"], "unpromoted_evaluation_only"
        )

        model = self.fitter.fit(
            [trace],
            model_id="motion-model:manual:champion-unpromoted",
            created_at="2026-08-23T01:01:00Z",
        )
        self.assertEqual(model["decision_context"], "champion")
        self.assertEqual(
            model["provenance"]["scope"], "unpromoted_evaluation_only"
        )

        falsely_promoted = copy.deepcopy(model)
        falsely_promoted["provenance"]["scope"] = "champion_eligible"
        with self.assertRaises(ContractValidationError):
            self.validator.validate(falsely_promoted)

    def test_champion_contract_rejects_server_or_lab_oracle_input(self) -> None:
        trace = manual_trace("champion")
        trace["provenance"]["pose_origin"] = "server_ground_truth"
        trace["provenance"]["action_origin"] = "lab_oracle"
        trace["provenance"]["scope"] = "lab_evaluation_only"
        with self.assertRaises(ContractValidationError):
            self.validator.validate(trace)

        model = self.fitter.fit(
            [manual_trace("champion")],
            model_id="motion-model:manual:champion-unpromoted",
            created_at="2026-08-23T01:01:00Z",
        )
        model["source_trace_kind"] = "lab_oracle_evaluation"
        model["provenance"]["origin"] = "deterministic_lab_oracle_fit"
        model["provenance"]["scope"] = "lab_evaluation_only"
        with self.assertRaises(ContractValidationError):
            self.validator.validate(model)

    def test_lab_oracle_trace_is_recordable_but_not_fit_for_control(self) -> None:
        trace = synthetic_trace("motion-trace:lab-oracle:001")
        trace["trace_kind"] = "lab_oracle_evaluation"
        trace["provenance"] = {
            "pose_origin": "server_ground_truth",
            "action_origin": "lab_oracle",
            "capability": "synchronized_pose_action_trace",
            "scope": "lab_evaluation_only",
            "confidence": 1.0,
            "evidence_refs": ["lab-evaluator:mangos-mmaps"],
        }
        self.validator.validate(trace)

        with self.assertRaisesRegex(MotionCalibrationError, "evaluation-only"):
            self.fitter.fit(
                [trace],
                model_id="motion-model:oracle:denied",
                created_at="2026-08-23T01:01:00Z",
            )

    def test_non_monotonic_or_understated_sync_timing_fails_closed(self) -> None:
        backwards = synthetic_trace()
        repeated_time = backwards["samples"][3]["timing"]["pose_monotonic_s"]
        backwards["samples"][4]["timing"]["pose_monotonic_s"] = repeated_time
        backwards["samples"][4]["timing"]["action_monotonic_s"] = repeated_time
        with self.assertRaisesRegex(MotionCalibrationError, "strictly increasing"):
            self.fitter.fit(
                [backwards],
                model_id="motion-model:invalid:clock",
                created_at="2026-08-23T01:01:00Z",
            )

        understated = synthetic_trace()
        understated["samples"][3]["timing"]["action_monotonic_s"] -= 0.01
        understated["timing"]["maximum_sync_skew_ms"] = 20.0
        with self.assertRaisesRegex(MotionCalibrationError, "understates"):
            self.fitter.fit(
                [understated],
                model_id="motion-model:invalid:sync",
                created_at="2026-08-23T01:01:00Z",
            )

    def test_non_finite_numbers_are_rejected_by_contract_and_fit_guards(self) -> None:
        non_finite = synthetic_trace()
        non_finite["samples"][3]["pose"]["position"]["x"] = float("nan")
        with self.assertRaisesRegex(ContractValidationError, "non-finite"):
            self.validator.validate(non_finite)

        overflowing_delta = synthetic_trace()
        overflowing_delta["samples"][2]["pose"]["position"]["x"] = -1e308
        overflowing_delta["samples"][3]["pose"]["position"]["x"] = 1e308
        with self.assertRaisesRegex(MotionCalibrationError, "not finite"):
            self.fitter.fit(
                [overflowing_delta],
                model_id="motion-model:invalid:overflow",
                created_at="2026-08-23T01:01:00Z",
            )

    def test_identity_and_authorization_cannot_be_mixed_across_traces(self) -> None:
        first = synthetic_trace("motion-trace:synthetic:001")
        second = synthetic_trace("motion-trace:synthetic:002", started_monotonic_s=20.0)
        second["authorization_sha256"] = "B" * 64
        with self.assertRaisesRegex(MotionCalibrationError, "authorization_sha256"):
            self.fitter.fit(
                [first, second],
                model_id="motion-model:invalid:mixed-authorization",
                created_at="2026-08-23T01:01:00Z",
            )


if __name__ == "__main__":
    unittest.main()
