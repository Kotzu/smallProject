from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from perfect_assassin.execution.operator_control import (
    FileOperatorCombatControl, OperatorStopRequested,
    read_operator_command,
)


class OperatorControlTests(unittest.TestCase):
    def test_unreadable_control_releases_motion_and_requests_recorded_stop(self) -> None:
        path = Path("control.json").resolve()
        for error in (PermissionError("sharing violation"), OSError("read failed")):
            with self.subTest(error=type(error).__name__):
                release = Mock()
                with patch.object(Path, "read_bytes", side_effect=error) as read:
                    with self.assertRaisesRegex(OperatorStopRequested, "unreadable"):
                        FileOperatorCombatControl(path).checkpoint(release)
                release.assert_called_once_with()
                read.assert_called_once_with()  # No retry with stale RUN authority.

    def test_unreadable_control_while_paused_never_resumes(self) -> None:
        path = Path("control.json").resolve()
        release = Mock()
        pause = json.dumps({"schema_version": "1.0", "command": "PAUSE", "revision": 1}).encode()
        with patch.object(Path, "read_bytes", side_effect=[pause, PermissionError("locked")]):
            with self.assertRaisesRegex(OperatorStopRequested, "unreadable"):
                FileOperatorCombatControl(path, sleeper=lambda _: None).checkpoint(release)
        release.assert_called_once_with()

    def test_exact_commands_are_accepted(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "control.json"
            for revision, command in enumerate(("RUN", "PAUSE", "STOP"), 1):
                path.write_text(json.dumps({"schema_version": "1.0", "command": command,
                    "revision": revision}), encoding="utf-8")
                self.assertEqual(read_operator_command(path), command)

    def test_missing_or_extra_fields_fail_closed(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "control.json"
            with self.assertRaises(OperatorStopRequested):
                read_operator_command(path)

    def test_checkpoint_reports_whether_resume_requires_a_fresh_observation(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "control.json"
            path.write_text(json.dumps({
                "schema_version": "1.0", "command": "RUN", "revision": 1,
            }), encoding="utf-8")
            control = FileOperatorCombatControl(path.resolve())
            self.assertFalse(control.checkpoint(lambda: None))

            writes = iter(("PAUSE", "RUN"))
            def sleeper(_seconds: float) -> None:
                command = next(writes)
                path.write_text(json.dumps({
                    "schema_version": "1.0", "command": command, "revision": 2,
                }), encoding="utf-8")

            path.write_text(json.dumps({
                "schema_version": "1.0", "command": "PAUSE", "revision": 2,
            }), encoding="utf-8")
            resumed = FileOperatorCombatControl(
                path.resolve(), sleeper=sleeper,
            ).checkpoint(lambda: None)
            self.assertTrue(resumed)
            path.write_text(json.dumps({"schema_version": "1.0", "command": "RUN",
                "revision": 1, "extra": True}), encoding="utf-8")
            with self.assertRaises(OperatorStopRequested):
                read_operator_command(path)
