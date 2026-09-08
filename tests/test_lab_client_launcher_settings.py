"""Exercise only the launcher's config writer, never the live client or input."""
from pathlib import Path
import json
import tempfile
import unittest

from test_lab_client_operator import OPERATOR, powershell_function, run_powershell_source


class LauncherAccountSettingsTests(unittest.TestCase):
    def configure(self, original):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "WTF" / "Config.wtf"
            config.parent.mkdir()
            config.write_text(original, encoding="utf-8")
            source = powershell_function(
                OPERATOR.read_text(encoding="utf-8"), "Set-PreferredClientGraphicsConfig",
            )
            source += "\n$ClientRoot = '" + str(root).replace("'", "''") + "'\n"
            source += """
$expectedAccount = 'ADMIN'
$Profile = [pscustomobject]@{
    windowed = $true
    render_resolution = [pscustomobject]@{width=1920; height=1080; refresh_hz=60}
}
Set-PreferredClientGraphicsConfig -Profile $Profile
$first = [IO.File]::ReadAllText((Join-Path $ClientRoot 'WTF/Config.wtf'))
Set-PreferredClientGraphicsConfig -Profile $Profile
$second = [IO.File]::ReadAllText((Join-Path $ClientRoot 'WTF/Config.wtf'))
@{ first=$first; second=$second } | ConvertTo-Json -Compress
"""
            result = run_powershell_source(source)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_launch_config_remembers_name_without_password(self):
        result = self.configure('SET Sound_EnableAllSound "0"\nSET gxWindow "0"\n')
        self.assertIn('SET accountName "ADMIN"', result["first"])
        self.assertIn('SET Sound_EnableAllSound "0"', result["first"])
        self.assertNotIn("password", result["first"].lower())
        self.assertEqual(result["first"], result["second"])

    def test_existing_account_entries_are_replaced_once(self):
        result = self.configure('SET accountName "OTHER"\nSET accountName "STALE"\n')
        self.assertEqual(result["first"].count('SET accountName "ADMIN"'), 1)
        self.assertNotIn("OTHER", result["first"])
        self.assertNotIn("STALE", result["first"])
        self.assertEqual(result["first"], result["second"])

    def test_local_credentials_and_visual_login_gate_remain_separate(self):
        script = OPERATOR.read_text(encoding="utf-8")
        self.assertIn(r"E:\WoWserver\TBC-LAB\database\predator-login.local.json", script)
        branch = script[script.index("        'Login' {"):script.index("        'InspectAddons' {")]
        self.assertIn("$ConfirmedVisualState -ne 'LoginScreen'", branch)
        self.assertIn("Assert-RuntimeArm -Name $Action -Process $process", branch)
        self.assertIn("$credential = Read-ObserverCredential", branch)
        launch = script[script.index("        'Launch' {"):script.index("        'BindOperatorLaunch' {")]
        self.assertLess(launch.index("$null -ne $process"), launch.index("Set-PreferredClientGraphicsConfig"))
        self.assertLess(launch.index("Set-PreferredClientGraphicsConfig"), launch.index("Start-Process"))


if __name__ == "__main__":
    unittest.main()
