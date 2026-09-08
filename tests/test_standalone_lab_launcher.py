from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "launch_standalone_lab.py"
BOOTSTRAP = ROOT / "scripts" / "Run-StandaloneLabBootstrap.ps1"
STARTER = ROOT / "scripts" / "Start-StandaloneLab.ps1"


def _load_launcher():
    spec = importlib.util.spec_from_file_location("launch_standalone_lab", LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StandaloneLabLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = _load_launcher()

    def test_detached_flags_break_out_of_caller_job(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows-only launcher")
        flags = self.launcher.detached_creation_flags()
        self.assertTrue(flags & subprocess.CREATE_BREAKAWAY_FROM_JOB)
        self.assertTrue(flags & subprocess.CREATE_NEW_PROCESS_GROUP)
        self.assertTrue(flags & subprocess.CREATE_NO_WINDOW)

    def test_bootstrap_command_is_absolute_and_noninteractive(self) -> None:
        repository = Path(r"E:\Workspace")
        command = self.launcher.build_bootstrap_command(
            repository_root=repository,
            lab_root=Path(r"E:\TBC-LAB"),
            powershell_executable=Path(r"C:\Windows\powershell.exe"),
        )
        self.assertEqual(command[0], r"C:\Windows\powershell.exe")
        self.assertIn("-NonInteractive", command)
        self.assertIn(str(repository / "scripts" / BOOTSTRAP.name), command)
        self.assertEqual(command[-2:], ("-LabRoot", r"E:\TBC-LAB"))

    def test_bootstrap_starts_full_lab_before_control_center(self) -> None:
        source = BOOTSTRAP.read_text(encoding="utf-8")
        launch = source[source.index("try {") :]
        database = launch.index("& (Join-Path $RepositoryRoot 'scripts\\Start-LabDatabase.ps1')")
        realm = launch.index("& (Join-Path $RepositoryRoot 'scripts\\Start-LabRealm.ps1')")
        world = launch.index("& (Join-Path $RepositoryRoot 'scripts\\Start-LabWorld.ps1')")
        control = launch.index("Start-Process -FilePath $pythonw")
        self.assertLess(database, realm)
        self.assertLess(realm, world)
        self.assertLess(world, control)
        self.assertIn("standalone-lab-status.json", source)

    def test_user_facing_starter_uses_detached_launcher(self) -> None:
        source = STARTER.read_text(encoding="utf-8")
        self.assertIn("launch_standalone_lab.py", source)
        self.assertIn("--lab-root", source)


if __name__ == "__main__":
    unittest.main()
