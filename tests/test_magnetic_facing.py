from __future__ import annotations

import unittest
from dataclasses import replace

from perfect_assassin.domain.facing import (
    ContinuousMagneticFacingController,
    MagneticFacingController,
    bearing_refinement_is_compatible,
)
from tests.test_combat_policy import bearing, state


class MagneticFacingControllerTests(unittest.TestCase):
    def test_facing_has_no_damage_or_hostility_policy(self) -> None:
        observed = state()
        controller = MagneticFacingController()
        left = controller.decide(
            bearing(observed, direction="LEFT", offset_x_normalized=-0.4)
        )
        right = controller.decide(
            bearing(observed, direction="RIGHT", offset_x_normalized=0.4)
        )
        centered = controller.decide(
            bearing(observed, direction="CENTER", offset_x_normalized=0.0)
        )
        self.assertEqual(left.control, "TURN_LEFT")
        self.assertEqual(right.control, "TURN_RIGHT")
        self.assertIsNone(centered.control)

    def test_continuous_servo_uses_small_signed_corrections_and_deadband(self) -> None:
        observed = state()
        controller = ContinuousMagneticFacingController()
        right = controller.decide(
            bearing(observed, direction="RIGHT", offset_x_normalized=0.40)
        )
        self.assertEqual(right.state, "TRACK")
        self.assertGreater(right.mouse_delta_x, 0)
        self.assertLessEqual(abs(right.mouse_delta_x), 16)
        self.assertTrue(right.hold_turn_mode)

        controller.reset()
        left = controller.decide(
            bearing(observed, direction="LEFT", offset_x_normalized=-0.40)
        )
        self.assertLess(left.mouse_delta_x, 0)

        centered = None
        for _ in range(6):
            centered = controller.decide(
                bearing(observed, direction="CENTER", offset_x_normalized=0.01)
            )
        assert centered is not None
        self.assertEqual(centered.state, "ALIGNED")
        self.assertEqual(centered.mouse_delta_x, 0)
        self.assertFalse(centered.hold_turn_mode)

    def test_continuous_servo_releases_on_visual_lock_loss(self) -> None:
        observed = state()
        controller = ContinuousMagneticFacingController()
        controller.decide(
            bearing(observed, direction="LEFT", offset_x_normalized=-0.35)
        )
        lost = bearing(
            observed,
            tracking_state="LOST",
            direction=None,
            offset_x_normalized=None,
        )
        command = controller.decide(lost)
        self.assertEqual(command.state, "LOST")
        self.assertFalse(command.hold_turn_mode)
        self.assertEqual(command.mouse_delta_x, 0)

    def test_continuous_servo_brakes_before_a_fast_center_crossing(self) -> None:
        observed = state()
        controller = ContinuousMagneticFacingController()
        first = controller.decide(
            bearing(
                observed,
                direction="LEFT",
                offset_x_normalized=-0.12,
            )
        )
        later_observation = replace(
            observed,
            observed_monotonic_s=observed.observed_monotonic_s + 0.1,
            expires_monotonic_s=observed.expires_monotonic_s + 0.1,
        )
        braking = controller.decide(
            bearing(
                later_observation,
                direction="LEFT",
                offset_x_normalized=-0.04,
            )
        )

        self.assertLess(first.mouse_delta_x, 0)
        self.assertEqual(
            braking.mouse_delta_x,
            0,
            "A reversing camera correction must brake through zero first",
        )

    def test_continuous_servo_accelerates_instead_of_jumping_to_full_turn(self) -> None:
        observed = state()
        controller = ContinuousMagneticFacingController()

        commands = [
            controller.decide(
                bearing(observed, direction="RIGHT", offset_x_normalized=0.9)
            ).mouse_delta_x
            for _ in range(4)
        ]

        self.assertEqual(commands, [3, 6, 9, 12])

    def test_continuous_servo_can_coast_through_predicted_center(self) -> None:
        observed = state()
        controller = ContinuousMagneticFacingController(
            prediction_horizon_s=0.2,
        )
        controller.decide(
            bearing(observed, direction="LEFT", offset_x_normalized=-0.08)
        )
        later_observation = replace(
            observed,
            observed_monotonic_s=observed.observed_monotonic_s + 0.1,
            expires_monotonic_s=observed.expires_monotonic_s + 0.1,
        )
        coast = controller.decide(
            bearing(
                later_observation,
                direction="LEFT",
                offset_x_normalized=-0.04,
            )
        )

        self.assertEqual(coast.state, "COAST")
        self.assertEqual(coast.mouse_delta_x, 0)
        self.assertTrue(coast.hold_turn_mode)
        self.assertFalse(coast.aligned)

    def test_opposite_pixel_refinement_cannot_reverse_exact_addon_bearing(self) -> None:
        observed = state()
        coarse = bearing(
            observed,
            direction="RIGHT",
            offset_x_normalized=0.75,
        )
        false_colour_arc = bearing(
            observed,
            direction="LEFT",
            offset_x_normalized=-0.35,
        )

        self.assertFalse(
            bearing_refinement_is_compatible(coarse, false_colour_arc)
        )

    def test_near_center_pixel_refinement_can_smooth_a_coarse_bucket_edge(self) -> None:
        observed = state()
        coarse = bearing(
            observed,
            direction="RIGHT",
            offset_x_normalized=0.35,
        )
        near_center = bearing(
            observed,
            direction="LEFT",
            offset_x_normalized=-0.03,
        )

        self.assertTrue(bearing_refinement_is_compatible(coarse, near_center))
