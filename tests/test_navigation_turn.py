from __future__ import annotations

import unittest

from perfect_assassin.execution.contracts import AuthorityBinding
from perfect_assassin.execution.navigation_turn import NavigationTurnPrimitive


class NavigationTurnPrimitiveTests(unittest.TestCase):
    def binding(self) -> AuthorityBinding:
        return AuthorityBinding(
            actor_id="actor:test", actor_instance_id="instance:test",
            actor_role="lab_clone", decision_context="lab_clone",
            target_profile="tbc_243_lab", target_instance_id="client:test",
            authorization_id="execution:test", authorization_sha256="A" * 64,
        )

    def test_exact_navigation_turn_profile(self) -> None:
        primitive = NavigationTurnPrimitive(
            primitive_id="primitive:test", lease_id="lease:test", binding=self.binding(),
            owner_id="controller:test", runtime_arm_nonce="arm:test",
            mode="MOVEMENT_ONLY", capability="MOVEMENT_EXECUTION", sequence=1,
            controls=("TURN_RIGHT",), hold_duration_ms=30,
            max_execution_envelope_ms=130, mouse_delta_x=8,
            clock_id="clock:test", issued_at_monotonic_ms=10.0,
            expires_at_monotonic_ms=150.0,
        )
        self.assertEqual(primitive.mouse_delta_x, 8)

    def test_unreviewed_delta_fails(self) -> None:
        with self.assertRaises(ValueError):
            NavigationTurnPrimitive(
                primitive_id="primitive:test", lease_id="lease:test", binding=self.binding(),
                owner_id="controller:test", runtime_arm_nonce="arm:test",
                mode="MOVEMENT_ONLY", capability="MOVEMENT_EXECUTION", sequence=1,
                controls=("TURN_RIGHT",), hold_duration_ms=30,
                max_execution_envelope_ms=130, mouse_delta_x=9,
                clock_id="clock:test", issued_at_monotonic_ms=10.0,
                expires_at_monotonic_ms=150.0,
            )


if __name__ == "__main__":
    unittest.main()
