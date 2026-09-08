from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

from perfect_assassin.movement.client_continuity import ContinuityPolicy


ROOT = Path(__file__).resolve().parents[1]
RUNNER = (
    ROOT / "integrations" / "windows-input" / "run_navigation_continuity.py"
)
SPEC = importlib.util.spec_from_file_location("run_navigation_continuity", RUNNER)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _visible_result(state: str, confidence: float = 1.0) -> dict[str, object]:
    return {
        "record_type": "navmesh_roaming_result",
        "status": state,
        "visible_client_state": {
            "state": state,
            "confidence": confidence,
            "evidence": {"fixture": True},
        },
    }


class NavigationContinuitySupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ContinuityPolicy(maximum_recovery_actions=3)

    def _action(
        self,
        result: dict[str, object],
        *,
        used: int = 0,
        reset: bool = False,
        death_reset: bool = False,
    ) -> str:
        return MODULE.decide_supervisor_action(
            result,
            policy=self.policy,
            recovery_actions_used=used,
            allow_lab_reset=reset,
            allow_lab_death_reset=death_reset,
        )

    def test_exact_login_flow_states_map_to_bounded_actions(self) -> None:
        self.assertEqual(
            self._action(_visible_result("DISCONNECTED_DIALOG")),
            "ACKNOWLEDGE_DISCONNECT",
        )
        self.assertEqual(
            self._action(_visible_result("LOGIN_SCREEN")),
            "LOGIN",
        )
        self.assertEqual(
            self._action(_visible_result("CHARACTER_SELECT")),
            "ENTER_WORLD",
        )

    def test_unknown_and_low_confidence_wait_without_input(self) -> None:
        self.assertEqual(
            self._action(_visible_result("UNKNOWN", confidence=0.0)),
            "WAIT_FOR_STABLE_FRAME",
        )
        self.assertEqual(
            self._action(_visible_result("LOGIN_SCREEN", confidence=0.4)),
            "WAIT_FOR_STABLE_FRAME",
        )

    def test_recovery_budget_stops_before_another_ui_action(self) -> None:
        self.assertEqual(
            self._action(_visible_result("LOGIN_SCREEN"), used=3),
            "STOP_FAIL_CLOSED",
        )

    def test_portable_death_flow_precedes_explicit_lab_reset_fallback(self) -> None:
        self.assertEqual(
            self._action(_visible_result("DEAD_IN_WORLD")),
            "RELEASE_SPIRIT",
        )
        self.assertEqual(
            self._action(_visible_result("GHOST_IN_WORLD")),
            "RECOVER_CORPSE",
        )
        self.assertEqual(
            self._action(_visible_result("DEAD_IN_WORLD"), death_reset=True),
            "RESET_LAB_DEATH",
        )
        self.assertEqual(
            self._action({"status": "RESET_REQUIRED"}),
            "STOP_STUCK",
        )
        self.assertEqual(
            self._action({"status": "RESET_REQUIRED"}, reset=True),
            "RESET_LAB_STUCK",
        )

    def test_runner_slice_and_arrival_continue_without_recovery_action(self) -> None:
        self.assertEqual(
            self._action({"status": "CONTROL_FRAME_BUDGET_EXHAUSTED"}),
            "RESUME_NAVIGATION",
        )
        self.assertEqual(self._action({"status": "ARRIVED"}), "COMPLETE")
        self.assertEqual(
            MODULE.decide_supervisor_action(
                {"status": "ARRIVED"},
                policy=self.policy,
                recovery_actions_used=0,
                allow_lab_reset=False,
                allow_lab_death_reset=False,
                recovering_corpse=True,
            ),
            "RETRIEVE_CORPSE",
        )
        self.assertEqual(
            MODULE.decide_supervisor_action(
                _visible_result("IN_WORLD"),
                policy=self.policy,
                recovery_actions_used=0,
                allow_lab_reset=False,
                allow_lab_death_reset=False,
                recovering_corpse=True,
            ),
            "RESUME_MISSION",
        )

    def test_corpse_goal_requires_exact_finite_client_visible_position(self) -> None:
        self.assertEqual(
            MODULE._corpse_goal_from_result({"final_world": [1912.5, 1579.25]}),
            (1912.5, 1579.25),
        )
        for invalid in (None, [], [1.0], [float("nan"), 2.0], [True, 2.0]):
            with self.subTest(invalid=invalid):
                with self.assertRaises(MODULE.NavigationContinuityError):
                    MODULE._corpse_goal_from_result({"final_world": invalid})

    def test_stdout_parser_ignores_noise_and_uses_exact_result(self) -> None:
        expected = {
            "record_type": "navmesh_roaming_result",
            "status": "ARRIVED",
        }
        stdout = "diagnostic\n" + json.dumps(expected) + "\n"
        self.assertEqual(MODULE._result_from_stdout(stdout), expected)

    def test_source_keeps_ui_recovery_state_bound_and_input_bounded(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('"-ConfirmedVisualState", confirmed_visual_state', source)
        self.assertIn('"-Action", "ArmSession"', source)
        self.assertIn('"--acknowledge-navigation-continuity"', source)
        self.assertNotIn('"--require-exact-body-heading"', source)
        self.assertIn('"execution_authority": False', source)
        self.assertNotIn("SetForegroundWindow", source)
        self.assertIn('action = "STOP_RELEASE_SPIRIT_FAILED"', source)
        self.assertIn('action = "STOP_RETRIEVE_CORPSE_FAILED"', source)

    def test_corpse_runner_is_exact_goal_ghost_only(self) -> None:
        args = MODULE.build_parser().parse_args([
            "--session-authorization-file", "authorization.json",
            "--semantic-destination-id", "brill_inn",
        ])
        command = MODULE._navigation_command(
            args,
            corpse_goal_world=(1912.5, 1579.25),
        )
        self.assertIn("--allow-ghost-navigation", command)
        self.assertIn("--goal-normalized-x", command)
        self.assertIn("--goal-normalized-y", command)
        self.assertNotIn("--semantic-destination-id", command)

        source = MODULE.NAVIGATION_RUNNER.read_text(encoding="utf-8")
        self.assertIn(
            "client_state.state is VisibleClientState.GHOST_IN_WORLD\n"
            "                    if self._allow_ghost_navigation",
            source,
        )

    def test_corpse_runner_uses_selected_map_transform(self) -> None:
        args = MODULE.build_parser().parse_args([
            "--session-authorization-file", "authorization.json",
            "--semantic-destination-id", "durotar_in",
            "--map-id", "1",
            "--expected-zone-index", "14",
        ])
        command = MODULE._navigation_command(
            args,
            corpse_goal_world=(0.0, -4500.0),
        )
        self.assertEqual(command[command.index("--map-id") + 1], "1")
        self.assertEqual(
            command[command.index("--expected-zone-index") + 1], "14",
        )
        self.assertIn("--zone-transform-catalog", command)


if __name__ == "__main__":
    unittest.main()
