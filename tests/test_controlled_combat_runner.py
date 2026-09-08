from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "integrations" / "windows-input" / "run_controlled_combat.py"


class ControlledCombatRunnerBoundaryTests(unittest.TestCase):
    def test_runner_requires_explicit_ack_and_exact_short_lived_authority_chain(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('"--acknowledge-controlled-combat"', source)
        self.assertIn("issue_combat_execution_authorization_snapshot", source)
        self.assertIn("IssueCombatRealmRevalidation", source)
        self.assertIn("issue_combat_runtime_arm_snapshot", source)
        self.assertIn("WindowsExactTargetCommandGateway", source)
        self.assertIn('"--target-name"', source)
        self.assertIn("focus_bound_target(target)", source)
        self.assertIn("preflight = perception.next_observation()", source)
        self.assertIn("exact target probe requires a living in-world actor", source)
        self.assertIn("load_combat_runtime_arm", source)
        self.assertIn("WindowsSendInputSink", source)
        self.assertIn("WindowsMouseTurnSink", source)
        self.assertIn("WindowsCombatInputSink", source)
        self.assertIn("PauseHotkeySource", source)
        self.assertIn("ControlledCombatEncounter", source)
        self.assertIn("DxcamWindowCaptureProvider", source)
        self.assertIn("decode_crc_target_bearing", source)
        self.assertIn("SelectedTargetBearingDetector", source)
        self.assertIn("decode_target_bearing_observation", source)
        self.assertIn("selected_bearing.is_bound_to(observed)", source)
        self.assertIn("FRESH_FRAME_RETRY_BUDGET = 3", source)
        self.assertIn("except NoFreshCaptureFrameError", source)

    def test_runner_has_no_forbidden_or_unbounded_control_surface(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn("SetForegroundWindow", source)
        self.assertNotIn("PostMessage", source)
        self.assertNotIn("MOVE_BACKWARD", source)
        self.assertNotIn("JUMP", source)
        self.assertNotIn("LAB_OPERATOR_FIXED_UI", source)
        self.assertNotIn("server truth", source.lower())

    def test_operator_pins_the_exact_adaptive_turn_profile(self):
        source = (ROOT / "scripts" / "Invoke-LabClientOperator.ps1").read_text(
            encoding="utf-8-sig"
        )
        for fragment in (
            "search_turn_hold_duration_ms -ne 200",
            "search_turn_mouse_delta_x -ne 24",
            "turn_near_hold_duration_ms -ne 25",
            "turn_near_mouse_delta_x -ne 4",
            "turn_medium_hold_duration_ms -ne 35",
            "turn_medium_mouse_delta_x -ne 14",
            "turn_far_hold_duration_ms -ne 50",
            "turn_far_mouse_delta_x -ne 28",
            "turn_medium_offset_threshold -ne 0.25",
            "turn_far_offset_threshold -ne 0.60",
            "turn_execution_slack_ms -ne 150",
            "orbit_hold_duration_ms -ne 90",
        ):
            self.assertIn(fragment, source)
        self.assertNotIn("turn_hold_duration_ms -ne 25", source)

    def test_runtime_arm_is_deleted_in_finally_and_result_is_evidence_only(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("arm_path.unlink(missing_ok=True)", source)
        self.assertIn('"execution_authority": False', source)
        self.assertIn("ControlledCombatEncounterFailure", source)
        self.assertIn("_atomic_write(result_path, _exact_json_bytes(failure))", source)
        self.assertIn("sink.close()", source)
        self.assertIn("gateway.close()", source)
        self.assertIn("perception.close()", source)

    def test_runner_uses_one_in_process_frame_for_combat_and_bearing(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn("HUD_PROBE", source)
        self.assertNotIn("CliCombatObservationSource", source)
        self.assertIn("self._combat_detector.detect", source)
        self.assertIn("decode_crc_target_bearing", source)
        self.assertIn("self._bearing_detector.detect", source)
        self.assertIn("observed.target is None", source)
        self.assertIn("combat_record", source)
        self.assertIn("packet.manifest", source)
        self.assertIn("bearing_refinement_is_compatible", source)
        self.assertNotIn("directions_agree", source)

    def test_runner_publishes_read_only_selected_target_range_witness(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("selected_target_melee_range_awareness", source)
        self.assertIn('movement_record["selected_target_range_awareness"]', source)
        self.assertIn('"rogue.auto_attack": observed.attack.in_range', source)
        self.assertIn(
            '"rogue.sinister_strike": (',
            source,
        )
        self.assertIn('"rogue.eviscerate": observed.eviscerate.in_range', source)

    def test_facing_probe_uses_continuous_motion_and_preserves_failure_evidence(self):
        source = RUNNER.read_text(encoding="utf-8")
        block = source[
            source.index("def _run_continuous_facing_probe") : source.index("def run(argv=None)")
        ]
        self.assertIn('"--facing-probe-only"', source)
        self.assertIn("motion_gateway.update(observed, bearing)", block)
        self.assertIn('"CONTINUOUS_FACING_LOCK_VERIFIED"', block)
        self.assertIn('"CONTINUOUS_FACING_LOCK_NOT_ACQUIRED"', block)
        self.assertIn('"motion_records": records', block)
        self.assertIn('"discrete_turn_actions": 0', block)
        self.assertIn("CONTINUOUS_CONTROL_PERIOD_S", block)
        self.assertIn('"HOLD_WORLD_REPOSITION", "HOLD_LOST_TARGET"', block)
        self.assertNotIn("ACTION_SLOT_", block)

    def test_friendly_dummy_calibration_is_exact_and_no_attack_only(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('"--allow-friendly-dummy-facing"', source)
        self.assertIn('args.target_name != "Undercity Practice Dummy"', source)
        self.assertIn("not args.facing_probe_only", source)
        self.assertIn('"red" if args.allow_friendly_dummy_facing else None', source)

    def test_facing_transfer_probe_is_one_impulse_and_has_no_combat_actions(self):
        source = RUNNER.read_text(encoding="utf-8")
        block = source[
            source.index("def _run_facing_transfer_probe") : source.index("def run(argv=None)")
        ]
        self.assertIn('"--facing-transfer-probe-only"', source)
        self.assertIn('len(impulse_indexes) != 8', block)
        self.assertIn('"actions_executed": 0', block)
        self.assertIn('"discrete_turn_actions": 0', block)

    def test_read_only_facing_observation_cannot_send_target_or_turn_input(self):
        source = RUNNER.read_text(encoding="utf-8")
        block = source[
            source.index("def _observe_facing_only") : source.index("def run(argv=None)")
        ]
        self.assertIn('"--observe-facing-only"', source)
        self.assertIn('"actions_executed": 0', block)
        self.assertIn("perception.next_observation()", block)
        self.assertNotIn("gateway.execute", block)
        self.assertNotIn("target_command_gateway", block)

    def test_risky_aggro_retreat_refreshes_after_handoff_parsing(self):
        source = RUNNER.read_text(encoding="utf-8")
        block = source[
            source.index("def _run_risky_aggro_retreat") :
            source.index("def _run_facing_probe")
        ]
        self.assertIn("observation = perception.next_observation()", block)
        self.assertNotIn("observation = initial_observation\n", block)

    def test_risky_aggro_handoff_delegates_resumed_trail_attachment(self):
        source = RUNNER.read_text(encoding="utf-8")
        block = source[
            source.index("def _retreat_corridor_from_handoff") :
            source.index("def _run_risky_aggro_retreat")
        ]
        self.assertIn("corridor_from_retreat_context", block)
        self.assertNotIn("pose.x - float(final_world[0])", block)

    def test_risky_aggro_deadline_is_derived_from_verified_corridor(self):
        source = RUNNER.read_text(encoding="utf-8")
        block = source[
            source.index("def _run_risky_aggro_retreat") :
            source.index("def _run_facing_probe")
        ]
        self.assertIn("safe_retreat_deadline_seconds(corridor)", block)
        self.assertNotIn("started_s > 18.0", block)


if __name__ == "__main__":
    unittest.main()
