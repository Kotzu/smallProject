from __future__ import annotations

from dataclasses import replace
import unittest

from perfect_assassin.execution.continuous_motion_gateway import (
    CONTINUOUS_NAVIGATION_ALLOWED_CONTROLS,
    CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
    ContinuousMotionAuthority,
    ContinuousMotionAuthorityError,
    ContinuousMotionExecutionGateway,
)
from tests.test_windows_send_input_sink import FakeClock, target_binding
from perfect_assassin.execution.contracts import AuthorityBinding
from perfect_assassin.execution.continuous_motion import ContinuousMotionFrame
from perfect_assassin.execution.ports import CooperativeCancellation
from tests.test_windows_continuous_motion import FakeContinuousBackend


def authority_for_target(
    target,
    *,
    clock_id: str = "clock:test",
    expires_at_monotonic_ms: float = 30_000.0,
    authorization_sha256: str = "A" * 64,
    renewal_parent_sha256: str | None = None,
):
    binding = AuthorityBinding(
        actor_id="actor:predator:lab-clone-01",
        actor_instance_id="instance:tbc243-lab:predator-clone-01",
        actor_role="lab_clone",
        decision_context="lab_clone",
        target_profile="tbc_243_lab",
        target_instance_id=(
            f"client:windows:{target.pid}:{target.process_creation_time_100ns}"
        ),
        authorization_id=CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
        authorization_sha256=authorization_sha256,
    )
    return ContinuousMotionAuthority(
        binding=binding,
        authorization_id=CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
        authorization_sha256=authorization_sha256,
        clock_id=clock_id,
        issued_at_monotonic_ms=0.0,
        expires_at_monotonic_ms=expires_at_monotonic_ms,
        allowed_controls=CONTINUOUS_NAVIGATION_ALLOWED_CONTROLS,
        renewal_parent_sha256=renewal_parent_sha256,
    )


class ContinuousMotionGatewayTests(unittest.TestCase):
    def test_authority_rejects_the_old_single_pulse_profile(self) -> None:
        target = target_binding()
        with self.assertRaisesRegex(ContinuousMotionAuthorityError, "profile"):
            ContinuousMotionAuthority(
                binding=authority_for_target(target).binding,
                authorization_id="execution:tbc243-lab:movement-f3a-single-pulse",
                authorization_sha256="A" * 64,
                clock_id="clock:test",
                issued_at_monotonic_ms=0.0,
                expires_at_monotonic_ms=30_000.0,
                allowed_controls=frozenset({"MOVE_FORWARD"}),
            )

    def test_gateway_rejects_missing_arm_before_touching_the_backend(self) -> None:
        target = target_binding()
        with self.assertRaisesRegex(ContinuousMotionAuthorityError, "dedicated runtime arm"):
            ContinuousMotionExecutionGateway(
                authority=None,
                target=target,
                backend=object(),
                clock=FakeClock(current_ms=1_000.0),
            )

    def test_authority_rejects_a_control_outside_the_reviewed_profile(self) -> None:
        target = target_binding()
        with self.assertRaisesRegex(ContinuousMotionAuthorityError, "controls"):
            ContinuousMotionAuthority(
                binding=authority_for_target(target).binding,
                authorization_id=CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
                authorization_sha256="A" * 64,
                clock_id="clock:test",
                issued_at_monotonic_ms=0.0,
                expires_at_monotonic_ms=30_000.0,
                allowed_controls=frozenset({"TURN_LEFT"}),
            )

    def test_authority_is_bound_to_the_continuous_profile_id(self) -> None:
        self.assertEqual(
            CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
            "execution:tbc243-lab:movement-f4a-continuous-navmesh",
        )

    def test_new_exact_arm_extends_live_hold_without_key_chatter(self) -> None:
        clock = FakeClock(current_ms=1_000.0)
        backend = FakeContinuousBackend()
        initial_authority = authority_for_target(
            backend.target,
            clock_id=clock.clock_id,
            expires_at_monotonic_ms=2_000.0,
        )
        target = replace(
            backend.target, authority_binding=initial_authority.binding
        )
        backend.target = target
        gateway = ContinuousMotionExecutionGateway(
            authority=initial_authority,
            target=target,
            backend=backend,
            clock=clock,
        )
        backend.events.clear()
        gateway.apply_frame(
            ContinuousMotionFrame(
                1.0, movement="MOVE_FORWARD", mouse_look=True
            ),
            CooperativeCancellation(),
        )
        clock.current_ms = 1_500.0
        self.assertTrue(
            gateway.renew_authority(
                authority_for_target(
                    target,
                    clock_id=clock.clock_id,
                    expires_at_monotonic_ms=20_000.0,
                )
            )
        )
        clock.current_ms = 2_500.0
        gateway.apply_frame(
            ContinuousMotionFrame(
                2.5, movement="MOVE_FORWARD", mouse_look=True
            ),
            CooperativeCancellation(),
        )

        names = [name for name, _ in backend.events]
        self.assertEqual(names.count("key_down"), 1)
        self.assertEqual(names.count("key_up"), 0)
        self.assertEqual(names.count("rmb_down"), 1)
        self.assertEqual(names.count("rmb_up"), 0)
        gateway.close()

    def test_temporal_authorization_rollover_keeps_live_hold(self) -> None:
        clock = FakeClock(current_ms=1_000.0)
        backend = FakeContinuousBackend()
        initial = authority_for_target(backend.target, clock_id=clock.clock_id)
        target = replace(backend.target, authority_binding=initial.binding)
        backend.target = target
        gateway = ContinuousMotionExecutionGateway(
            authority=initial, target=target, backend=backend, clock=clock
        )
        backend.events.clear()
        gateway.apply_frame(
            ContinuousMotionFrame(1.0, movement="MOVE_FORWARD", mouse_look=True),
            CooperativeCancellation(),
        )
        renewed = authority_for_target(
            target,
            clock_id=clock.clock_id,
            expires_at_monotonic_ms=40_000.0,
            authorization_sha256="B" * 64,
            renewal_parent_sha256="A" * 64,
        )
        self.assertTrue(gateway.renew_authority(renewed))
        clock.current_ms = 2_000.0
        gateway.apply_frame(
            ContinuousMotionFrame(2.0, movement="MOVE_FORWARD", mouse_look=True),
            CooperativeCancellation(),
        )
        names = [name for name, _ in backend.events]
        self.assertEqual(names.count("key_down"), 1)
        self.assertEqual(names.count("key_up"), 0)
        gateway.close()

    def test_temporal_authorization_rollover_rejects_wrong_parent(self) -> None:
        clock = FakeClock(current_ms=1_000.0)
        backend = FakeContinuousBackend()
        initial = authority_for_target(backend.target, clock_id=clock.clock_id)
        target = replace(backend.target, authority_binding=initial.binding)
        backend.target = target
        gateway = ContinuousMotionExecutionGateway(
            authority=initial, target=target, backend=backend, clock=clock
        )
        forged = authority_for_target(
            target,
            clock_id=clock.clock_id,
            authorization_sha256="B" * 64,
            renewal_parent_sha256="C" * 64,
        )
        with self.assertRaisesRegex(
            ContinuousMotionAuthorityError, "reviewed binding"
        ):
            gateway.renew_authority(forged)
        gateway.close()


if __name__ == "__main__":
    unittest.main()
