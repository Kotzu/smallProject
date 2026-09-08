from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "integrations" / "windows-input"
    / "run_journey_combat_supervisor.py"
)
NAVIGATION_PATH = (
    ROOT / "integrations" / "windows-input" / "run_navmesh_roaming.py"
)


def _load_module():
    module_directory = str(MODULE_PATH.parent)
    if module_directory not in sys.path:
        sys.path.insert(0, module_directory)
    spec = importlib.util.spec_from_file_location(
        "journey_combat_supervisor_test", MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _command_args(root: Path, *, operator_path: Path | None = None):
    return SimpleNamespace(
        session_authorization_file=root / "authorization.json",
        session_receipt=root / "receipt.json",
        worker=root / "worker.exe",
        world_pack_profile=root / "profile.json",
        world_pack_store=root / "worldpacks",
        world_structure_index=root / "structures.json",
        structure_access_graph=root / "access.json",
        semantic_catalog=root / "destinations.json",
        semantic_destination_id=(
            None if operator_path is not None else "settlement:brill"
        ),
        operator_path=operator_path,
        expected_zone_index=25,
        start_world_z_hint=100.0,
        operator_control_file=root / "control.json",
        max_control_frames=12_000,
        dynamic_experience_store=root / "dynamic-experience.sqlite3",
        continue_through_routine_aggro=True,
        activate_stealth=True,
        runtime_arm_wait_seconds=120.0,
    )


class JourneyCombatSupervisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module()

    def test_policy_completes_resumes_and_bounds_combat_handoffs(self) -> None:
        decide = self.module.journey_supervisor_action
        self.assertEqual(
            decide({"status": "ARRIVED"}, combat_handoffs_used=0,
                   maximum_combat_handoffs=2),
            "COMPLETE",
        )
        self.assertEqual(
            decide({"status": "CONTROL_FRAME_BUDGET_EXHAUSTED"},
                   combat_handoffs_used=0, maximum_combat_handoffs=2),
            "RESUME_NAVIGATION",
        )
        self.assertEqual(
            decide({"status": "SEMANTIC_FRONTIER_REPLAN_REQUIRED"},
                   combat_handoffs_used=0, maximum_combat_handoffs=2),
            "RESUME_NAVIGATION",
        )
        self.assertEqual(
            decide({"status": "COMBAT_HANDOFF_REQUIRED"},
                   combat_handoffs_used=1, maximum_combat_handoffs=2),
            "HANDOFF_COMBAT",
        )
        self.assertEqual(
            decide({"status": "COMBAT_HANDOFF_REQUIRED"},
                   combat_handoffs_used=2, maximum_combat_handoffs=2),
            "STOP_COMBAT_BUDGET",
        )
        self.assertEqual(
            decide({"status": "UNRECOGNIZED"}, combat_handoffs_used=0,
                   maximum_combat_handoffs=2),
            "STOP_FAIL_CLOSED",
        )

    def test_navigation_command_preserves_destination_without_waypoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = _command_args(Path(directory))
            command = self.module._navigation_command(args)

        destination_index = command.index("--semantic-destination-id")
        self.assertEqual(command[destination_index + 1], "settlement:brill")
        self.assertNotIn("--operator-path", command)
        self.assertIn("--acknowledge-navmesh-roaming", command)
        self.assertIn("--continue-through-routine-aggro", command)
        threshold_index = command.index("--minimum-travel-health-fraction")
        self.assertEqual(command[threshold_index + 1], "0.55")
        self.assertIn("--activate-stealth", command)
        wait_index = command.index("--runtime-arm-wait-seconds")
        self.assertEqual(command[wait_index + 1], "120.0")

    def test_navigation_command_can_override_destination_for_sequence_leg(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = _command_args(Path(directory))
            command = self.module._navigation_command(args, "settlement:deathknell")
        destination_index = command.index("--semantic-destination-id")
        self.assertEqual(command[destination_index + 1], "settlement:deathknell")

    def test_parser_accepts_routine_aggro_travel_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.module.build_parser().parse_args([
                "--session-authorization-file", str(root / "authorization.json"),
                "--semantic-destination-id", "settlement:deathknell",
                "--continue-through-routine-aggro",
            ])

        self.assertTrue(args.continue_through_routine_aggro)

    def test_navigation_command_does_not_invent_routine_aggro_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = _command_args(Path(directory))
            args.continue_through_routine_aggro = False
            command = self.module._navigation_command(args)

        self.assertNotIn("--continue-through-routine-aggro", command)

    def test_navigation_command_can_resume_from_one_child_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = _command_args(root)
            checkpoint = root / "navmesh-roaming-expired.json"
            command = self.module._navigation_command(
                args,
                "settlement:brill",
                resume_result=checkpoint,
            )

        resume_index = command.index("--resume-result")
        self.assertEqual(command[resume_index + 1], str(checkpoint))

    def test_navigation_command_forwards_normalized_leveling_goal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = _command_args(Path(directory))
            args.semantic_destination_id = None
            args.goal_normalized_x = 0.3022
            args.goal_normalized_y = 0.7165
            args.leveling_plan_file = Path(directory) / "leveling-plan.json"
            command = self.module._navigation_command(args)
        self.assertIn("--goal-normalized-x", command)
        self.assertEqual(command[command.index("--goal-normalized-x") + 1], "0.3022")
        self.assertEqual(command[command.index("--goal-normalized-y") + 1], "0.7165")
        self.assertIn("--leveling-plan-file", command)
        self.assertNotIn("--semantic-destination-id", command)

    def test_destination_sequence_is_bounded_and_transitions_legs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sequence = root / "sequence.json"
            sequence.write_text(json.dumps({
                "record_type": "semantic_destination_sequence",
                "schema_version": "1.0",
                "sequence_id": "deathknell-brill-loop",
                "destination_ids": ["settlement:deathknell", "settlement:brill"],
                "loop_count": 2,
                "map_id": 0,
                "execution_authority": False,
            }), encoding="utf-8")
            catalog = root / "destinations.json"
            catalog.write_text(json.dumps({
                "record_type": "semantic_location_catalog",
                "schema_version": "1.0",
                "locations": [
                    {"id": "settlement:deathknell"},
                    {"id": "settlement:brill"},
                ],
            }), encoding="utf-8")
            result_path = root / "result.json"
            child_results = [
                {"run_id": "nav:1", "status": "ARRIVED", "final_world": [1, 1]},
                {"run_id": "nav:2", "status": "ARRIVED", "final_world": [2, 2]},
                {"run_id": "nav:3", "status": "ARRIVED", "final_world": [3, 3]},
                {"run_id": "nav:4", "status": "ARRIVED", "final_world": [4, 4]},
            ]
            completed = [subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout=json.dumps({
                    "record_type": "navmesh_roaming_result", **record,
                }) + "\n", stderr="",
            ) for record in child_results]
            with patch.object(self.module.subprocess, "run", side_effect=completed) as run_child:
                code = self.module.run([
                    "--session-authorization-file", str(root / "authorization.json"),
                    "--destination-sequence-file", str(sequence),
                    "--semantic-catalog", str(catalog),
                    "--result-file", str(result_path),
                    "--acknowledge-autonomous-journey-combat",
                ])
            result = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(result["destination_mode"], "SEMANTIC_SEQUENCE")
        self.assertEqual(result["semantic_destination_ids"], [
            "settlement:deathknell", "settlement:brill",
        ])
        self.assertEqual(
            [step["to_destination_id"] for step in result["steps"]
             if step["kind"] == "DESTINATION_TRANSITION"],
            ["settlement:brill", "settlement:deathknell", "settlement:brill"],
        )
        navigation_commands = [call.args[0] for call in run_child.call_args_list]
        selected = [
            command[command.index("--semantic-destination-id") + 1]
            for command in navigation_commands
        ]
        self.assertEqual(selected, [
            "settlement:deathknell", "settlement:brill",
            "settlement:deathknell", "settlement:brill",
        ])

    def test_destination_sequence_can_close_each_bounded_loop(self) -> None:
        from perfect_assassin.movement.destination_sequence import DestinationSequence

        sequence = DestinationSequence(
            sequence_id="closed-patrol",
            destination_ids=("a", "b", "c"),
            loop_count=2,
            close_loop=True,
        )
        self.assertEqual(
            sequence.expanded_destination_ids(),
            ("a", "b", "c", "a", "b", "c", "a"),
        )
        self.assertFalse(sequence.to_record()["execution_authority"])

    def test_offline_crypt_brill_crypt_sequence_replays_in_canonical_order(self) -> None:
        """Replay the real identifier-only route without opening the game client."""

        sequence_path = (
            ROOT / "config" / "movement-lab"
            / "semantic-sequence-brill-crypt-brill-crypt.json"
        )
        catalog_path = ROOT / "config" / "movement-lab" / "semantic-destinations-tbc243.json"
        child_results = [
            {"run_id": "offline:crypt", "status": "ARRIVED", "final_world": [1, 1]},
            {"run_id": "offline:brill", "status": "ARRIVED", "final_world": [2, 2]},
            {"run_id": "offline:crypt-return", "status": "ARRIVED", "final_world": [3, 3]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            completed = [
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=json.dumps({
                        "record_type": "navmesh_roaming_result", **record,
                    }) + "\n",
                    stderr="",
                )
                for record in child_results
            ]
            with patch.object(
                self.module.subprocess, "run", side_effect=completed
            ) as run_child:
                code = self.module.run([
                    "--session-authorization-file", str(root / "authorization.json"),
                    "--destination-sequence-file", str(sequence_path),
                    "--semantic-catalog", str(catalog_path),
                    "--result-file", str(result_path),
                    "--maximum-navigation-cycles", "3",
                    "--acknowledge-autonomous-journey-combat",
                ])
            result = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(
            result["semantic_destination_ids"],
            ["landmark:deathknell-crypt", "settlement:brill"],
        )
        self.assertEqual(
            [
                command[command.index("--semantic-destination-id") + 1]
                for command in [call.args[0] for call in run_child.call_args_list]
            ],
            [
                "landmark:deathknell-crypt",
                "settlement:brill",
                "landmark:deathknell-crypt",
            ],
        )
        self.assertEqual(
            [step["to_destination_id"] for step in result["steps"]
             if step["kind"] == "DESTINATION_TRANSITION"],
            ["settlement:brill", "landmark:deathknell-crypt"],
        )

    def test_destination_sequence_rejects_unknown_catalog_id_before_child_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sequence = root / "sequence.json"
            sequence.write_text(json.dumps({
                "record_type": "semantic_destination_sequence",
                "schema_version": "1.0",
                "sequence_id": "unknown-destination",
                "destination_ids": ["settlement:deathknell", "settlement:missing"],
                "loop_count": 1,
                "map_id": 0,
                "execution_authority": False,
            }), encoding="utf-8")
            catalog = root / "destinations.json"
            catalog.write_text(json.dumps({
                "record_type": "semantic_location_catalog",
                "schema_version": "1.0",
                "locations": [{"id": "settlement:deathknell"}],
            }), encoding="utf-8")
            with patch.object(self.module.subprocess, "run") as run_child:
                with self.assertRaises(SystemExit) as error:
                    self.module.run([
                        "--session-authorization-file", str(root / "authorization.json"),
                        "--destination-sequence-file", str(sequence),
                        "--semantic-catalog", str(catalog),
                        "--result-file", str(root / "result.json"),
                        "--acknowledge-autonomous-journey-combat",
                    ])
            self.assertIn("absent from the semantic catalog", str(error.exception))
            run_child.assert_not_called()

    def test_destination_sequence_rejects_map_mismatch_before_child_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sequence = root / "sequence.json"
            sequence.write_text(json.dumps({
                "record_type": "semantic_destination_sequence",
                "schema_version": "1.0",
                "sequence_id": "wrong-map",
                "destination_ids": ["a", "b"],
                "loop_count": 1,
                "map_id": 33,
                "execution_authority": False,
            }), encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.module.run([
                    "--session-authorization-file", str(root / "authorization.json"),
                    "--destination-sequence-file", str(sequence),
                    "--map-id", "0",
                    "--acknowledge-autonomous-journey-combat",
                ])

    def test_runtime_arm_expiry_publishes_contract_safe_fail_closed_status(self) -> None:
        navigation = subprocess.CompletedProcess(
            args=[], returncode=5,
            stdout=json.dumps({
                "record_type": "navmesh_roaming_result",
                "run_id": "nav:expired-arm",
                "status": "RUNTIME_ARM_EXPIRED",
                "final_world": [1665.0, 1685.0],
            }) + "\n", stderr="",
        )
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "result.json"
            with patch.object(self.module.subprocess, "run", return_value=navigation):
                code = self.module.run([
                    "--session-authorization-file", str(Path(directory) / "authorization.json"),
                    "--semantic-destination-id", "settlement:brill",
                    "--result-file", str(result_path),
                    "--acknowledge-autonomous-journey-combat",
                ])
            result = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 5)
        self.assertEqual(result["status"], "STOPPED_FAIL_CLOSED")
        self.assertEqual(result["steps"][0]["status"], "RUNTIME_ARM_EXPIRED")

    def test_runtime_arm_expiry_can_resume_only_with_a_fresh_arm_wait(self) -> None:
        navigation_expired = subprocess.CompletedProcess(
            args=[], returncode=8,
            stdout=json.dumps({
                "record_type": "navmesh_roaming_result",
                "run_id": "nav:expired-arm",
                "status": "RUNTIME_ARM_EXPIRED",
                "result_path": "navigation-expired.json",
                "final_world": [1665.0, 1685.0],
                "resume_policy": "REISSUE_RUNTIME_ARM_AND_REPLAN_FROM_FRESH_LIVE_POSITION",
            }) + "\n",
            stderr="",
        )
        navigation_arrived = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({
                "record_type": "navmesh_roaming_result",
                "run_id": "nav:resumed",
                "status": "ARRIVED",
                "final_world": [1666.0, 1684.0],
            }) + "\n",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            with patch.object(
                self.module.subprocess,
                "run",
                side_effect=[navigation_expired, navigation_arrived],
            ) as run_child:
                code = self.module.run([
                    "--session-authorization-file", str(root / "authorization.json"),
                    "--semantic-destination-id", "settlement:brill",
                    "--runtime-arm-wait-seconds", "30",
                    "--resume-on-runtime-arm-expiry",
                    "--result-file", str(result_path),
                    "--acknowledge-autonomous-journey-combat",
                ])
            result = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "ARRIVED")
        self.assertEqual(result["steps"][0]["action"], "RESUME_NAVIGATION")
        second_command = run_child.call_args_list[1].args[0]
        self.assertIn("--resume-result", second_command)
        self.assertEqual(
            second_command[second_command.index("--resume-result") + 1],
            "navigation-expired.json",
        )

    def test_runtime_arm_resume_requires_a_bounded_wait(self) -> None:
        with self.assertRaises(SystemExit) as error:
            self.module.run([
                "--session-authorization-file", "authorization.json",
                "--semantic-destination-id", "settlement:brill",
                "--resume-on-runtime-arm-expiry",
                "--acknowledge-autonomous-journey-combat",
            ])
        self.assertIn("requires a positive", str(error.exception))

    def test_operator_path_and_combat_use_separate_runner_acknowledgements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = _command_args(root, operator_path=root / "operator-path.json")
            navigation = self.module._navigation_command(args)
            combat = self.module._combat_command(args)

        self.assertIn("--operator-path", navigation)
        self.assertNotIn("--semantic-destination-id", navigation)
        self.assertIn("--acknowledge-navmesh-roaming", navigation)
        self.assertNotIn("--acknowledge-controlled-combat", navigation)
        self.assertIn("--acknowledge-controlled-combat", combat)
        self.assertNotIn("--acknowledge-navmesh-roaming", combat)
        self.assertEqual(
            navigation[navigation.index("--session-authorization-file") + 1],
            combat[combat.index("--session-authorization-file") + 1],
        )

    def test_combat_receives_exact_navigation_handoff_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = self.module._combat_command(
                _command_args(root),
                {"result_path": str(root / "navigation.json")},
            )
        index = command.index("--navigation-handoff-result")
        self.assertEqual(command[index + 1], str(root / "navigation.json"))

    def test_safe_escape_resumes_same_semantic_destination(self) -> None:
        navigation_handoff = subprocess.CompletedProcess(
            args=[], returncode=6,
            stdout=json.dumps({
                "record_type": "navmesh_roaming_result",
                "result_path": "navigation.json",
                "run_id": "nav:one",
                "status": "COMBAT_HANDOFF_REQUIRED",
                "final_world": [1.0, 2.0],
                "final_world_z_hint": 3.0,
                "map": "Azeroth",
                "navmesh_sha256": "A" * 64,
                "resume_policy": "REPLAN_FROM_FRESH_LIVE_POSITION",
            }) + "\n", stderr="",
        )
        combat_escaped = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({
                "record_type": "controlled_combat_result",
                "encounter_id": "combat:escape",
                "status": "ESCAPED_RISKY_AGGRO",
            }) + "\n", stderr="",
        )
        navigation_arrived = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({
                "record_type": "navmesh_roaming_result",
                "run_id": "nav:two", "status": "ARRIVED",
                "final_world": [3.0, 4.0],
            }) + "\n", stderr="",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            with patch.object(
                self.module.subprocess, "run",
                side_effect=[navigation_handoff, combat_escaped, navigation_arrived],
            ) as run_child:
                code = self.module.run([
                    "--session-authorization-file", str(root / "authorization.json"),
                    "--semantic-destination-id", "settlement:brill",
                    "--result-file", str(result_path),
                    "--acknowledge-autonomous-journey-combat",
                ])
            result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "ARRIVED")
        self.assertTrue(result["steps"][1]["escaped_risk_recorded"])
        combat_command = run_child.call_args_list[1].args[0]
        self.assertEqual(
            combat_command[combat_command.index("--navigation-handoff-result") + 1],
            "navigation.json",
        )

    def test_combat_defeat_replans_same_semantic_journey_from_live_pose(self) -> None:
        navigation_handoff = subprocess.CompletedProcess(
            args=[], returncode=6,
            stdout=json.dumps({
                "record_type": "navmesh_roaming_result",
                "run_id": "nav:one",
                "status": "COMBAT_HANDOFF_REQUIRED",
                "final_world": [1.0, 2.0],
                "resume_policy": "REPLAN_FROM_FRESH_LIVE_POSITION",
            }) + "\n",
            stderr="",
        )
        combat_defeated = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({
                "record_type": "controlled_combat_result",
                "encounter_id": "combat:one",
                "status": "TARGET_DEFEATED",
            }) + "\n",
            stderr="",
        )
        navigation_arrived = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({
                "record_type": "navmesh_roaming_result",
                "run_id": "nav:two",
                "status": "ARRIVED",
                "final_world": [3.0, 4.0],
            }) + "\n",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            with patch.object(
                self.module.subprocess,
                "run",
                side_effect=[navigation_handoff, combat_defeated, navigation_arrived],
            ) as run_child:
                code = self.module.run([
                    "--session-authorization-file", str(root / "authorization.json"),
                    "--session-receipt", str(root / "receipt.json"),
                    "--semantic-destination-id", "settlement:brill",
                    "--result-file", str(result_path),
                    "--acknowledge-autonomous-journey-combat",
                ])
            result = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "ARRIVED")
        self.assertEqual(result["combat_handoffs_used"], 1)
        self.assertEqual(
            [step["kind"] for step in result["steps"]],
            ["NAVIGATION_CYCLE", "COMBAT_CYCLE", "NAVIGATION_CYCLE"],
        )
        first_navigation = run_child.call_args_list[0].args[0]
        second_navigation = run_child.call_args_list[2].args[0]
        self.assertEqual(
            first_navigation[first_navigation.index("--semantic-destination-id") + 1],
            second_navigation[second_navigation.index("--semantic-destination-id") + 1],
        )

    def test_missing_child_result_stops_fail_closed(self) -> None:
        child = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="unstructured failure\n", stderr="boom",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            with patch.object(self.module.subprocess, "run", return_value=child):
                code = self.module.run([
                    "--session-authorization-file", str(root / "authorization.json"),
                    "--semantic-destination-id", "settlement:brill",
                    "--result-file", str(result_path),
                    "--acknowledge-autonomous-journey-combat",
                ])
            result = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 5)
        self.assertEqual(result["status"], "STOPPED_CHILD_ERROR")
        self.assertEqual(result["steps"][-1]["kind"], "CHILD_ERROR")

    def test_supervisor_has_no_direct_input_backend(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("SendInput", source)
        self.assertNotIn("CtypesWin32KeyboardBackend", source)
        self.assertNotIn("WindowsMouse", source)
        self.assertIn("NAVIGATION_RUNNER", source)
        self.assertIn("COMBAT_RUNNER", source)

    def test_navigation_observes_combat_before_startup_input(self) -> None:
        source = NAVIGATION_PATH.read_text(encoding="utf-8")
        start = source.index("pose_source.open()", source.index("publish_continuity(\"STARTING\")"))
        end = source.index("_, _, world_x, world_y = _position", start)
        startup = source[start:end]
        self.assertLess(
            startup.index("observation = pose_source.next_observation()"),
            startup.index("backend.send_stand_command()"),
        )
        self.assertLess(
            startup.index("backend.send_stand_command()"),
            startup.index("backend.send_navigation_camera_preferences()"),
        )
        self.assertNotIn("_apply_navigation_camera_profile(", startup)
        self.assertIn('"kind": "START_CAMERA_PREFERENCES_APPLIED"', startup)
        self.assertIn("raise CombatHandoffRequired", source)
        self.assertIn('"resume_policy": "REPLAN_FROM_FRESH_LIVE_POSITION"', source)


if __name__ == "__main__":
    unittest.main()
