from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LabRuntimeConfigTests(unittest.TestCase):
    @staticmethod
    def _create_fixture(temporary: str, *, include_afk_key: bool) -> tuple[Path, Path]:
        lab_root = Path(temporary) / "TBC-LAB"
        runtime = lab_root / "runtime" / "core-playerbots"
        database = lab_root / "database"
        runtime.mkdir(parents=True)
        database.mkdir(parents=True)
        (lab_root / "client-data").mkdir()
        (lab_root / "logs").mkdir()
        (database / "secrets.local.json").write_text(
            json.dumps(
                {
                    "host": "127.0.0.1",
                    "port": 3307,
                    "mangos_user": "fixture_user",
                    "mangos_password": "fixture_password",
                }
            ),
            encoding="utf-8",
        )

        mangos_lines = [
            'DataDir = "."',
            'LogsDir = ""',
            'BindIP = "0.0.0.0"',
            "Console.Enable = 1",
            "Ra.Enable = 0",
            "Ra.IP = 0.0.0.0",
            "Ra.Restricted = 1",
        ]
        if include_afk_key:
            mangos_lines.append("Player.AFK.DisconnectTimeout = 15")
            mangos_lines.append("MaxOverspeedPings = 2")
        mangos_lines.extend(
            (
                'LoginDatabaseInfo = "fixture"',
                'WorldDatabaseInfo = "fixture"',
                'CharacterDatabaseInfo = "fixture"',
                'LogsDatabaseInfo = "fixture"',
            )
        )
        (runtime / "mangosd.conf.dist").write_text("\n".join(mangos_lines), encoding="utf-8")
        (runtime / "realmd.conf.dist").write_text(
            '\n'.join(('LogsDir = ""', 'BindIP = "0.0.0.0"', 'LoginDatabaseInfo = "fixture"')),
            encoding="utf-8",
        )
        (runtime / "aiplayerbot.conf.dist").write_text(
            "\n".join(
                (
                    "AiPlayerbot.RandomBotAutologin = 1",
                    "AiPlayerbot.RandomBotLoginAtStartup = 1",
                    "AiPlayerbot.RandomBotJoinLfg = 1",
                    "AiPlayerbot.RandomBotJoinBG = 1",
                    "AiPlayerbot.MinRandomBots = 1",
                    "AiPlayerbot.MaxRandomBots = 1",
                    "AiPlayerbot.RandomBotAccountCount = 1",
                )
            ),
            encoding="utf-8",
        )
        (runtime / "anticheat.conf.dist").write_text(
            "\n".join(("Enable = 1", "Warden.Enable = 1", "Warden.Timeout = 30")),
            encoding="utf-8",
        )
        return lab_root, runtime

    @staticmethod
    def _run_writer(lab_root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-File",
                str(ROOT / "scripts" / "Write-LabRuntimeConfig.ps1"),
                "-LabRoot",
                str(lab_root),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_runtime_config_disables_afk_disconnect_fail_closed(self) -> None:
        script = ROOT / "scripts" / "Write-LabRuntimeConfig.ps1"
        source = script.read_text(encoding="utf-8")
        self.assertIn("Player.AFK.DisconnectTimeout = 0", source)
        self.assertIn("MaxOverspeedPings = 0", source)
        self.assertIn("MaxOverspeedPings is missing", source)
        self.assertIn("Player.AFK.DisconnectTimeout is missing", source)

        with tempfile.TemporaryDirectory() as temporary:
            lab_root, runtime = self._create_fixture(temporary, include_afk_key=True)
            completed = self._run_writer(lab_root)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            generated = (runtime / "mangosd.conf").read_text(encoding="utf-8")
            self.assertEqual(generated.count("Player.AFK.DisconnectTimeout = 0"), 1)
            self.assertNotIn("Player.AFK.DisconnectTimeout = 15", generated)
            self.assertEqual(generated.count("MaxOverspeedPings = 0"), 1)
            self.assertNotIn("MaxOverspeedPings = 2", generated)
            anticheat = (runtime / "anticheat.conf").read_text(encoding="utf-8")
            self.assertEqual(anticheat.count("Warden.Enable = 0"), 1)
            self.assertNotIn("Warden.Enable = 1", anticheat)

    def test_runtime_config_refuses_an_unpatched_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lab_root, runtime = self._create_fixture(temporary, include_afk_key=False)
            completed = self._run_writer(lab_root)

            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("Player.AFK.DisconnectTimeout is missing", completed.stderr)
            self.assertNotIn("LAB_RUNTIME_CONFIG_WRITTEN", completed.stdout)
            self.assertFalse((runtime / "mangosd.conf").exists())


if __name__ == "__main__":
    unittest.main()
