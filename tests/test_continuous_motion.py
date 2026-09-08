from __future__ import annotations

import unittest

from perfect_assassin.execution.continuous_motion import (
    CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S,
    ContinuousInputStateMachine,
    ContinuousMotionFrame,
)


class ContinuousInputStateMachineTests(unittest.TestCase):
    def test_repeated_frame_holds_keys_and_rmb_without_repeated_down_events(self) -> None:
        machine = ContinuousInputStateMachine()
        frame = ContinuousMotionFrame(
            1.0,
            movement="MOVE_FORWARD",
            strafe="STRAFE_LEFT",
            mouse_look=True,
            mouse_delta_x=3,
        )

        first = machine.step(frame)
        repeated = machine.step(frame)

        self.assertEqual(first.key_down, ("MOVE_FORWARD", "STRAFE_LEFT"))
        self.assertTrue(first.mouse_look_down)
        self.assertEqual(repeated.key_down, ())
        self.assertEqual(repeated.key_up, ())
        self.assertFalse(repeated.mouse_look_down)
        self.assertFalse(repeated.mouse_look_up)
        self.assertEqual(repeated.mouse_delta_x, 3)

    def test_direction_change_releases_conflict_before_pressing_replacement(self) -> None:
        machine = ContinuousInputStateMachine()
        machine.step(ContinuousMotionFrame(1.0, strafe="STRAFE_LEFT", mouse_look=True))

        transition = machine.step(
            ContinuousMotionFrame(1.05, strafe="STRAFE_RIGHT", mouse_look=True)
        )

        self.assertEqual(transition.key_up, ("STRAFE_LEFT",))
        self.assertEqual(transition.key_down, ("STRAFE_RIGHT",))
        self.assertFalse(transition.mouse_look_up)
        self.assertFalse(transition.mouse_look_down)

    def test_neutral_frame_releases_every_held_state(self) -> None:
        machine = ContinuousInputStateMachine()
        machine.step(
            ContinuousMotionFrame(
                1.0, movement="MOVE_FORWARD", strafe="STRAFE_RIGHT", mouse_look=True
            )
        )

        released = machine.step(ContinuousMotionFrame(1.1))

        self.assertEqual(released.key_up, ("MOVE_FORWARD", "STRAFE_RIGHT"))
        self.assertTrue(released.mouse_look_up)
        self.assertEqual(machine.held_controls, frozenset())
        self.assertFalse(machine.mouse_look)

    def test_mouse_delta_without_mouse_look_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires held mouse-look"):
            ContinuousMotionFrame(1.0, mouse_delta_x=1)

    def test_humanlike_pivot_velocity_is_bounded(self) -> None:
        accepted = ContinuousMotionFrame(
            1.0,
            mouse_look=True,
            mouse_velocity_x_px_s=CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S,
        )
        self.assertEqual(
            accepted.mouse_velocity_x_px_s,
            CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S,
        )
        with self.assertRaisesRegex(ValueError, "velocity bound"):
            ContinuousMotionFrame(
                1.0,
                mouse_look=True,
                mouse_velocity_x_px_s=(
                    CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S + 1.0
                ),
            )


if __name__ == "__main__":
    unittest.main()
