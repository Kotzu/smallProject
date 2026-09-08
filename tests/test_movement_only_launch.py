from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations" / "windows-input"))
import run_movement_engine_client as ui
import run_journey_combat_supervisor as supervisor


def _client(root: Path):
    client = ui.MovementEngineClient.__new__(ui.MovementEngineClient)
    client.state = "STARTING"
    client.motion_arm_renew_stop = Event()
    client.process = None
    client.log_stream = None
    client.root = Mock()
    client.active_world_map_profile = SimpleNamespace(
        semantic_catalog=root / "destinations.json",
        internal_name="Azeroth",
        structure_access_graph=root / "access.json",
        map_id=0,
        runtime_profile=root / "world-pack.json",
        structure_index=root / "structures.json",
    )
    client._set_semantic_live_authority = Mock()
    client._prepare_leveling_plan = Mock(return_value=None)
    client._run_hidden_checked = Mock()
    client._renew_continuous_motion_arm_once = Mock()
    client._semantic_catalog_zone_index = Mock(return_value=25)
    client._maintain_continuous_motion_arm = Mock()
    client._set_running = Mock()
    client._set_error = Mock()
    return client


class MovementOnlyLaunchTests(unittest.TestCase):
    def test_ui_allows_aggro_but_never_starts_a_combat_child(self) -> None:
        """Exercise UI launch -> real parser/supervisor, with all processes fake."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = _client(root)
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"authorization_sha256": "fixture"}), encoding="utf-8")
            with (
                patch.object(ui, "SESSION_RECEIPT", receipt),
                patch.object(ui, "LOG_PATH", root / "movement.log"),
                # Worker selection has separate graph/hash tests. This test
                # exercises launch/combat policy without a real graph.
                patch.object(ui, "_structure_awareness_worker", return_value=root / "worker.exe"),
                patch.object(ui, "Thread") as thread,
                patch.object(ui.subprocess, "Popen") as launch,
            ):
                try:
                    client._prepare_and_launch(
                        "settlement:brill", "autonomous_destination", True,
                        client.motion_arm_renew_stop,
                    )
                finally:
                    if client.log_stream is not None:
                        client.log_stream.close()
            launch.assert_called_once()
            command = launch.call_args.args[0]
            self.assertEqual(command[1], str(ui.JOURNEY_COMBAT_SUPERVISOR))
            self.assertEqual(command[command.index("--maximum-combat-handoffs") + 1], "0")
            self.assertIn("--continue-through-routine-aggro", command)
            self.assertEqual(
                command[command.index("--steering-controller") + 1],
                "adaptive_trajectory_v1",
            )
            godmode_commands = [
                call.args[0] for call in client._run_hidden_checked.call_args_list
                if str(ui.GODMODE) in call.args[0]
            ]
            self.assertEqual(godmode_commands, [[
                "pwsh", "-NoProfile", "-NonInteractive", "-File", str(ui.GODMODE),
                "-State", "On", "-PlayerName", "Predator",
            ]])
            client._set_semantic_live_authority.assert_called_once_with(True)
            client._renew_continuous_motion_arm_once.assert_called_once()
            thread.return_value.start.assert_called_once()

            # A normal navigation continuation must not re-enable combat.
            children = [subprocess.CompletedProcess(
                args=[], returncode=5,
                stdout=json.dumps({
                    "record_type": "navmesh_roaming_result",
                    "run_id": f"nav:{index}", "status": status,
                    "final_world": [1.0, 2.0],
                }) + "\n", stderr="",
            ) for index, status in enumerate((
                "CONTROL_FRAME_BUDGET_EXHAUSTED", "COMBAT_HANDOFF_REQUIRED",
            ))]
            result_path = root / "result.json"
            with (
                patch.object(supervisor.subprocess, "run", side_effect=children) as run_child,
                patch.object(sys, "stdout", io.StringIO()),
            ):
                code = supervisor.run(command[2:] + ["--result-file", str(result_path)])
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 5)
            self.assertEqual(result["status"], "STOPPED_COMBAT_BUDGET")
            self.assertEqual(result["combat_handoffs_used"], 0)
            self.assertEqual(run_child.call_count, 2)
            for call in run_child.call_args_list:
                self.assertEqual(call.args[0][1], str(supervisor.NAVIGATION_RUNNER))
                self.assertIn("--continue-through-routine-aggro", call.args[0])

    def test_unconfirmed_godmode_prevents_movement_arm_and_child_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = _client(root)
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"authorization_sha256": "fixture"}), encoding="utf-8")

            def fail_on_protection(command):
                if str(ui.GODMODE) in command:
                    raise subprocess.CalledProcessError(1, command)

            client._run_hidden_checked.side_effect = fail_on_protection
            with (
                patch.object(ui, "SESSION_RECEIPT", receipt),
                patch.object(ui.subprocess, "Popen") as launch,
                patch.object(ui, "Thread") as thread,
            ):
                client._prepare_and_launch(
                    "settlement:brill", "autonomous_destination", True,
                    client.motion_arm_renew_stop,
                )
            launch.assert_not_called()
            thread.assert_not_called()
            client._renew_continuous_motion_arm_once.assert_not_called()
            client.root.after.assert_called_once()
            self.assertIsNone(client.log_stream)

    def test_ui_has_no_automatic_lab_godmode_off_command(self) -> None:
        source = (ROOT / "integrations" / "windows-input" /
                  "run_movement_engine_client.py").read_text(encoding="utf-8")
        self.assertNotIn("_disable_lab_protection_after_combat", source)
        self.assertNotIn('"-State", "Off"', source)

    def test_unarmed_movement_launch_does_not_prepare_or_start_a_process(self) -> None:
        client = _client(Path("unused"))
        with patch.object(ui.subprocess, "Popen") as launch:
            client._prepare_and_launch(
                "settlement:brill", "autonomous_destination", False,
                client.motion_arm_renew_stop,
            )
        launch.assert_not_called()
        client._run_hidden_checked.assert_not_called()
        client._set_semantic_live_authority.assert_not_called()
        client.root.after.assert_called_once()

    def test_cancelled_or_replaced_launch_does_not_start_a_process(self) -> None:
        for scenario in ("stopped", "cancelled", "replaced"):
            with self.subTest(scenario=scenario):
                client = _client(Path("unused"))
                event = client.motion_arm_renew_stop
                if scenario == "stopped":
                    client.state = "STOPPED"
                elif scenario == "cancelled":
                    event.set()
                else:
                    client.motion_arm_renew_stop = Event()
                with patch.object(ui.subprocess, "Popen") as launch:
                    client._prepare_and_launch(
                        "settlement:brill", "autonomous_destination", True, event,
                    )
                launch.assert_not_called()
                client._run_hidden_checked.assert_not_called()
                client._set_semantic_live_authority.assert_not_called()


if __name__ == "__main__":
    unittest.main()
