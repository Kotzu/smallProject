from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from perfect_assassin.adapter.afk_hud import (
    AfkEpisodeLatch,
    AfkHudPacket,
    decode_afk_packet,
)
from perfect_assassin.adapter.coordinate_hud import crc16_ccitt_false

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations/windows-input"))


def load_module():
    path = ROOT / "integrations/windows-input/run_stay_online_guard.py"
    spec = importlib.util.spec_from_file_location("run_stay_online_guard", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def packet(sequence=1, *, afk=True, blocked=False):
    return AfkHudPacket(sequence, True, afk, True, blocked, False)


class StayOnlineTests(unittest.TestCase):
    def test_cc_opt_in_and_launch_failure_are_isolated(self):
        import tempfile

        from stay_online_control import GuardStatus, StayOnlineControl

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = StayOnlineControl(root)
            with patch("stay_online_control.subprocess.run") as launch:
                self.assertFalse(control.status().running)
                launch.assert_not_called()
                launch.side_effect = OSError("fixture unavailable")
                with self.assertRaises(OSError):
                    control.set_enabled(True)
                self.assertFalse(control.opt_in.exists())
                self.assertIn("-AcknowledgeStayOnline", launch.call_args.args[0])
                self.assertIn(str(root), launch.call_args.args[0])
                with patch.object(control, "status", return_value=GuardStatus(True, "live")):
                    launch.reset_mock()
                    control.set_enabled(True)
                    launch.assert_not_called()
                    self.assertTrue(control.opt_in.exists())

    def test_renewal_accepts_only_same_client_and_actor(self):
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class Target:
            authority_binding: str
            pid: int
            hwnd: int

        module = load_module()
        old = {"actor_binding": {"actor": "Predator"}, "target": Target("old", 10, 20)}
        new = {"actor_binding": {"actor": "Predator"}, "target": Target("new", 10, 20)}
        with patch.object(
            module, "_target_from_receipt", side_effect=lambda r: r["target"]
        ):
            self.assertTrue(module._same_client_renewal(old, new))
            for target in (Target("new", 11, 20), Target("new", 10, 21)):
                self.assertFalse(
                    module._same_client_renewal(old, {**new, "target": target})
                )
            self.assertFalse(
                module._same_client_renewal(
                    old, {**new, "actor_binding": {"actor": "Other"}}
                )
            )

    def test_one_attempt_until_two_confirmed_clear_samples(self):
        latch = AfkEpisodeLatch()
        self.assertFalse(latch.observe(packet(1), movement_busy=False))
        self.assertTrue(latch.observe(packet(2), movement_busy=False))
        latch.mark_attempted()
        for sequence in range(3, 100):
            self.assertFalse(latch.observe(packet(sequence), movement_busy=False))
        self.assertFalse(latch.observe(packet(100, afk=False), movement_busy=False))
        self.assertTrue(latch.handled)
        self.assertFalse(latch.observe(packet(101, afk=False), movement_busy=False))
        self.assertFalse(latch.handled)
        self.assertFalse(latch.observe(packet(102), movement_busy=False))
        self.assertTrue(latch.observe(packet(103), movement_busy=False))

    def test_duplicate_frames_do_not_confirm_afk(self):
        latch = AfkEpisodeLatch()
        for _ in range(5):
            self.assertFalse(latch.observe(packet(1), movement_busy=False))

    def test_unknown_frames_do_not_rearm_or_confirm(self):
        latch = AfkEpisodeLatch(handled=True)
        self.assertFalse(latch.observe(None, movement_busy=False))
        self.assertTrue(latch.handled)
        latch = AfkEpisodeLatch()
        latch.observe(packet(1), movement_busy=False)
        latch.observe(None, movement_busy=False)
        self.assertFalse(latch.observe(packet(2), movement_busy=False))

    def test_chat_and_movement_block_jump(self):
        for busy, blocked in ((True, False), (False, True)):
            latch = AfkEpisodeLatch()
            for sequence in range(1, 5):
                self.assertFalse(
                    latch.observe(packet(sequence, blocked=blocked), movement_busy=busy)
                )

    def test_wrong_actor_or_combat_or_dead_block_jump(self):
        from dataclasses import replace

        for changes in (
            {"predator_in_world": False},
            {"combat_or_dead": True},
            {"known": False},
        ):
            latch = AfkEpisodeLatch()
            for seq in (1, 2, 3):
                self.assertFalse(
                    latch.observe(replace(packet(seq), **changes), movement_busy=False)
                )

    def test_sequence_wrap_is_supported(self):
        latch = AfkEpisodeLatch()
        self.assertFalse(latch.observe(packet(255), movement_busy=False))
        self.assertTrue(latch.observe(packet(0), movement_busy=False))

    def test_codec_rejects_corrupt_or_missing_strip(self):
        body = bytes((175, 1, 40, 7))
        raw = body + crc16_ccitt_false(body).to_bytes(2, "big")
        self.assertTrue(decode_afk_packet(raw).eligible)
        self.assertTrue(decode_afk_packet(raw).afk)
        for data in (b"", bytes(6), raw[:-1] + bytes([raw[-1] ^ 1])):
            with self.assertRaises(ValueError):
                decode_afk_packet(data)

    def test_pulse_is_one_jump_and_never_directional_movement(self):
        module = load_module()
        self.assertEqual(module.PULSE_CONTROLS, ("JUMP",))
        self.assertEqual(module.PULSE_HOLD_MS["JUMP"], 45)

    def test_single_gateway_call_and_focus_restore(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        module = load_module()
        target = SimpleNamespace(hwnd=9, pid=12, authority_binding=Mock())
        sink = Mock()
        manager = Mock()
        manager.current.return_value = 8
        manager.restore.return_value = True
        clock = Mock(clock_id="test-clock")
        clock.now_ms.return_value = 100
        with (
            patch.object(module, "WindowsSendInputSink", return_value=sink),
            patch.object(module, "MovementPrimitive") as primitive,
            patch.object(module, "SinkExecutionBudget"),
            patch.object(module, "_realm_connected", return_value=True),
            patch.object(module.time, "sleep"),
        ):
            self.assertTrue(
                module._execute_pulse(
                    target=target,
                    backend=Mock(),
                    clock=clock,
                    interrupted=lambda: False,
                    foreground_manager=manager,
                )
            )
        self.assertEqual(sink.apply_bounded.call_count, 1)
        self.assertEqual(primitive.call_args.kwargs["controls"], ("JUMP",))
        sink.close.assert_called_once()
        manager.restore.assert_called_once_with(8)

    def test_stopped_guard_never_applies_input(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        module = load_module()
        sink = Mock()
        manager = Mock()
        manager.current.return_value = 9
        with patch.object(module, "WindowsSendInputSink", return_value=sink):  # noqa: SIM117
            with self.assertRaises(module.StayOnlineGuardError):
                module._execute_pulse(
                    target=SimpleNamespace(hwnd=9),
                    backend=Mock(),
                    clock=Mock(),
                    interrupted=lambda: True,
                    foreground_manager=manager,
                )
        sink.apply_bounded.assert_not_called()

    def test_decoder_samples_independent_strip_at_multiple_scales(self):
        import numpy as np

        sys.path.insert(0, str(ROOT / "integrations/windows-capture"))
        from afk_hud_detector import detect_afk_strip

        body = bytes((175, 1, 30, 7))
        raw = body + crc16_ccitt_false(body).to_bytes(2, "big")
        for scale in (1.0, 1.25, 2.0):
            frame = np.zeros((300, 500, 4), dtype=np.uint8)
            cyan = (30.0, 50.0, 36)
            markers = (
                cyan,
                (30 + 92 * scale, 50, 36),
                (30, 50 + 34 * scale, 36),
                (0, 0, 0),
            )
            for index in range(48):
                value = (raw[index // 8] >> (7 - index % 8)) & 1
                x, y = round(30 + (6 + index * 3) * scale), round(50 - 12 * scale)
                frame[y, x, :3] = 255 * value
            self.assertEqual(detect_afk_strip(frame, markers), decode_afk_packet(raw))
        self.assertIsNone(detect_afk_strip(frame, None))

    def test_addon_uses_observed_afk_and_blocks_edit_focus(self):
        source = (
            ROOT
            / "integrations/tbc243-addon/PerfectAssassinObserver/PerfectAssassinObserver.lua"
        ).read_text(encoding="utf-8")
        self.assertIn('UnitIsAFK("player")', source)
        self.assertIn("GetCurrentKeyBoardFocus() ~= nil", source)
        self.assertNotIn("JumpOrAscendStart", source)
        self.assertIn("local PAO_HUD_PROTOCOL_VERSION = 3", source)

    def test_launcher_requires_ack_and_hidden_background_window(self):
        source = (ROOT / "scripts/Start-LabStayOnlineGuard.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("-AcknowledgeStayOnline", source)
        self.assertIn("-WindowStyle Hidden", source)
        self.assertIn("-RedirectStandardError", source)
