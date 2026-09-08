from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations/windows-input"))
from stay_online_control import GuardStatus, StayOnlineControl, StayOnlinePanel


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.control = StayOnlineControl(Path(self.folder.name))
        self.control.runtime.mkdir(parents=True)

    def write_state(self, **changes):
        record = dict(status="RUNNING", pid=42, updated_at=datetime.now(timezone.utc).isoformat(),
                      afk_observation=dict(known=True, predator_in_world=True))
        record.update(changes)
        (self.control.runtime / "state.json").write_text(json.dumps(record), encoding="utf-8")

    def process(self):
        return Mock(cmdline=lambda: [str(self.control.root / "integrations/windows-input/run_stay_online_guard.py")],
                    create_time=lambda: 1)

    def test_live_and_waiting_and_stale(self):
        with patch("stay_online_control.psutil.Process", return_value=self.process()):
            self.write_state()
            self.assertIn("Space", self.control.status().text)
            self.write_state(afk_observation=None)
            self.assertIn("așteaptă", self.control.status().text)
            self.write_state(updated_at=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat())
            self.assertTrue(self.control.status().running)
            self.assertIn("nu se mai", self.control.status().text)

    def test_wrong_pid_and_reused_pid(self):
        self.write_state()
        with patch("stay_online_control.psutil.Process", return_value=Mock(cmdline=lambda: ["other.py"])):
            self.assertFalse(self.control.status().running)
        proc = self.process()
        proc.create_time = lambda: datetime.now(timezone.utc).timestamp() + 10
        with patch("stay_online_control.psutil.Process", return_value=proc):
            self.assertFalse(self.control.status().running)

    def test_unknown_state_denies_duplicate(self):
        (self.control.runtime / "state.json").write_text("broken", encoding="utf-8")
        with patch("stay_online_control.subprocess.run") as run:
            with self.assertRaises(RuntimeError):
                self.control.set_enabled(True)
            run.assert_not_called()

    def test_start_and_stop_confirmed(self):
        off, on = GuardStatus(False, "off"), GuardStatus(True, "on")
        with patch.object(self.control, "status", side_effect=[off, on, on, off]), patch(
            "stay_online_control.subprocess.run", return_value=Mock(returncode=0)
        ) as run:
            self.control.set_enabled(True)
            self.assertTrue(self.control.opt_in.exists())
            self.assertEqual(run.call_args.args[0][-2:], ["-MaxHours", "24"])
            self.assertEqual(run.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)
            self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)
            self.control.set_enabled(False)
            self.assertFalse(self.control.opt_in.exists())
            self.assertIn("Stop-LabStayOnlineGuard.ps1", " ".join(run.call_args.args[0]))

    def test_failed_stop_disables_autostart_but_reports_process(self):
        self.control.opt_in.write_text("{}", encoding="utf-8")
        with patch.object(self.control, "status", return_value=GuardStatus(True, "on")), patch(
            "stay_online_control.subprocess.run", return_value=Mock(returncode=1)
        ):
            with self.assertRaises(RuntimeError):
                self.control.set_enabled(False)
            self.assertFalse(self.control.opt_in.exists())

    def test_failed_start_confirmation_does_not_persist(self):
        with patch.object(self.control, "status", return_value=GuardStatus(False, "off")), patch(
            "stay_online_control.subprocess.run", return_value=Mock(returncode=0)
        ):
            with self.assertRaises(RuntimeError):
                self.control.set_enabled(True)
            self.assertFalse(self.control.opt_in.exists())

    def test_ui_ignores_poll_result_from_before_command(self):
        panel = StayOnlinePanel.__new__(StayOnlinePanel)
        panel.control = self.control
        panel.revision = 1
        panel.enabled, panel.text, panel.checkbox = Mock(), Mock(), Mock()
        self.control.results.put((0, GuardStatus(False, "old")))
        panel.refresh()
        panel.checkbox.configure.assert_not_called()
        self.control.results.put((1, GuardStatus(True, "new")))
        panel.refresh()
        panel.enabled.set.assert_called_once_with(True)
        panel.text.set.assert_called_once_with("new")

    def test_closing_panel_does_not_stop_guard(self):
        panel = StayOnlinePanel.__new__(StayOnlinePanel)
        panel.control = self.control
        panel.close()
        self.assertTrue(self.control.closed.is_set())
        self.assertTrue(self.control.commands.empty())


if __name__ == "__main__":
    unittest.main()
