from __future__ import annotations

import unittest

from perfect_assassin.execution.combat_authorization import COMBAT_POLICY
from perfect_assassin.execution.combat_runtime_arm import CombatRuntimeArm
from perfect_assassin.execution.ports import ManualMonotonicClock
from perfect_assassin.execution.windows_send_input import (
    WindowsHotTargetSnapshot,
    WindowsInputTargetBinding,
    WindowsTargetIdentityReceipt,
)
from perfect_assassin.execution.windows_target_command import (
    ExactTargetCommandError,
    WindowsExactTargetCommandGateway,
)
from tests.test_windows_send_input_sink import target_binding


def arm(**changes: object) -> CombatRuntimeArm:
    target = target_binding()
    values: dict[str, object] = {
        "arm_nonce": "00000000-0000-0000-0000-000000000001",
        "authorization_sha256": target.authority_binding.authorization_sha256,
        "session_authorization_sha256": "B" * 64,
        "session_receipt_sha256": "C" * 64,
        "realm_revalidation_sha256": "D" * 64,
        "pid": target.pid,
        "hwnd": f"0x{target.hwnd:X}",
        "process_creation_filetime_utc": str(target.process_creation_time_100ns),
        "windows_session_id": 1,
        "window_title": target.window_title_exact,
        "window_class": target.window_class_exact,
        "executable_path": target.executable_path,
        "executable_sha256": target.executable_sha256,
        "actor_id": target.authority_binding.actor_id,
        "actor_instance_id": target.authority_binding.actor_instance_id,
        "client_build": "2.4.3.8606",
        "build_signature": "wow-tbc-2.4.3.8606-enGB",
        "clock_id": "clock:test:target-command",
        "issued_at_monotonic_ms": 900.0,
        "expires_at_monotonic_ms": 2_000.0,
        "policy": dict(COMBAT_POLICY),
    }
    values.update(changes)
    return CombatRuntimeArm(**values)  # type: ignore[arg-type]


class FakeExactTargetBackend:
    def __init__(self, target: WindowsInputTargetBinding) -> None:
        self.target = target
        self.names: list[str] = []
        self.released = 0
        self.foreground_hwnd = target.hwnd
        self.submit_override: int | None = None

    def prevalidate_target(
        self, target: WindowsInputTargetBinding
    ) -> WindowsTargetIdentityReceipt:
        return WindowsTargetIdentityReceipt(
            receipt_id="receipt:exact-target:fixture",
            target=target,
        )

    def inspect_hot(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> WindowsHotTargetSnapshot:
        return WindowsHotTargetSnapshot(
            hwnd=self.target.hwnd,
            foreground_hwnd=self.foreground_hwnd,
            owner_pid=self.target.pid,
            process_creation_time_100ns=self.target.process_creation_time_100ns,
            process_alive=True,
            visible=True,
            minimized=False,
        )

    def send_exact_target_name(self, target_name: str) -> int:
        self.names.append(target_name)
        return (
            self.submit_override
            if self.submit_override is not None
            else 4 + 2 * len(f"/targetexact {target_name}")
        )

    def release_identity_receipt(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> None:
        self.released += 1


class WindowsExactTargetCommandGatewayTests(unittest.TestCase):
    def make_gateway(self):  # type: ignore[no-untyped-def]
        target = target_binding()
        backend = FakeExactTargetBackend(target)
        clock = ManualMonotonicClock("clock:test:target-command", 1_000.0)
        gateway = WindowsExactTargetCommandGateway(
            arm=arm(),
            target=target,
            backend=backend,
            clock=clock,
        )
        return gateway, backend, clock

    def test_submits_only_compiled_exact_target_command(self) -> None:
        gateway, backend, _ = self.make_gateway()
        receipt = gateway.execute("Wretched Zombie")
        self.assertEqual(backend.names, ["Wretched Zombie"])
        self.assertEqual(receipt.command_preview, "/targetexact Wretched Zombie")
        self.assertFalse(receipt.execution_authority)
        gateway.close()
        self.assertEqual(backend.released, 1)

    def test_chat_command_injection_is_rejected_before_submission(self) -> None:
        gateway, backend, _ = self.make_gateway()
        with self.assertRaises(ValueError):
            gateway.execute("Scavenger\n/logout")
        self.assertEqual(backend.names, [])
        gateway.close()

    def test_foreground_mismatch_fails_before_submission(self) -> None:
        gateway, backend, _ = self.make_gateway()
        backend.foreground_hwnd = 0x9999
        with self.assertRaisesRegex(Exception, "hot identity"):
            gateway.execute("Scavenger")
        self.assertEqual(backend.names, [])
        gateway.close()

    def test_partial_batch_fails_closed(self) -> None:
        gateway, backend, _ = self.make_gateway()
        backend.submit_override = 1
        with self.assertRaisesRegex(ExactTargetCommandError, "not submitted completely"):
            gateway.execute("Scavenger")
        gateway.close()

    def test_expired_arm_fails_before_submission(self) -> None:
        target = target_binding()
        backend = FakeExactTargetBackend(target)
        clock = ManualMonotonicClock("clock:test:target-command", 2_001.0)
        gateway = WindowsExactTargetCommandGateway(
            arm=arm(), target=target, backend=backend, clock=clock
        )
        with self.assertRaisesRegex(ExactTargetCommandError, "not active"):
            gateway.execute("Scavenger")
        self.assertEqual(backend.names, [])
        gateway.close()

    def test_profile_without_exact_target_control_is_rejected(self) -> None:
        target = target_binding()
        backend = FakeExactTargetBackend(target)
        policy = dict(COMBAT_POLICY)
        policy["allowed_controls"] = [
            control
            for control in policy["allowed_controls"]
            if control != "TARGET_EXACT_NAME"
        ]
        with self.assertRaisesRegex(ExactTargetCommandError, "does not authorize"):
            WindowsExactTargetCommandGateway(
                arm=arm(policy=policy),
                target=target,
                backend=backend,
                clock=ManualMonotonicClock("clock:test:target-command", 1_000.0),
            )


if __name__ == "__main__":
    unittest.main()
