from __future__ import annotations

from dataclasses import replace
import unittest

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.combat_retreat import (
    BreadcrumbCombatRetreatController,
    safe_retreat_deadline_seconds,
)
from tests.test_combat_policy import state


class BreadcrumbCombatRetreatControllerTests(unittest.TestCase):
    @staticmethod
    def corridor() -> NavCorridor:
        points = (
            NavPoint(10.0, 0.0, 1.0),
            NavPoint(6.0, 0.0, 1.0),
            NavPoint(2.0, 0.0, 1.0),
        )
        return NavCorridor(
            map_name="Azeroth",
            adt_x=0,
            adt_y=0,
            start=points[0],
            stop=points[-1],
            points=points,
            source="fresh_client_visible_reverse_breadcrumbs",
        )

    def test_retreat_turns_and_moves_forward_over_reverse_corridor(self) -> None:
        pose = [10.0, 0.0, 3.141592653589793]
        controller = BreadcrumbCombatRetreatController(
            corridor=self.corridor(),
            pose_source=lambda: tuple(pose),
        )
        observed = state(in_combat=True)
        intent = controller.decide(observed, None)
        self.assertEqual(intent.state, "RETREAT_FOLLOW")
        self.assertEqual(intent.frame.movement, "MOVE_FORWARD")
        self.assertTrue(intent.frame.mouse_look)

    def test_fresh_out_of_combat_frame_releases_every_input(self) -> None:
        controller = BreadcrumbCombatRetreatController(
            corridor=self.corridor(),
            pose_source=lambda: (8.0, 0.0, 3.141592653589793),
        )
        observed = replace(state(in_combat=True), in_combat=False)
        intent = controller.decide(observed, None)
        self.assertEqual(intent.state, "ESCAPED")
        self.assertEqual(intent.frame.held_controls, frozenset())
        self.assertFalse(intent.frame.mouse_look)
        self.assertEqual(controller.terminal_state, "ESCAPED")

    def test_missing_heading_fails_closed_without_translation(self) -> None:
        controller = BreadcrumbCombatRetreatController(
            corridor=self.corridor(), pose_source=lambda: (10.0, 0.0, None)
        )
        with self.assertRaisesRegex(RuntimeError, "heading"):
            controller.decide(state(in_combat=True), None)

    def test_deadline_scales_with_verified_corridor_length_and_stays_bounded(self) -> None:
        short = self.corridor()
        long_points = tuple(
            NavPoint(float(x), 0.0, 1.0) for x in range(0, 121, 10)
        )
        long = NavCorridor(
            map_name="Azeroth",
            adt_x=0,
            adt_y=0,
            start=long_points[0],
            stop=long_points[-1],
            points=long_points,
            source="fresh_client_visible_reverse_breadcrumbs",
        )
        self.assertEqual(safe_retreat_deadline_seconds(short), 18.0)
        self.assertEqual(safe_retreat_deadline_seconds(long), 38.0)

        extended_points = tuple(
            NavPoint(float(x), 0.0, 1.0) for x in range(0, 301, 10)
        )
        extended = NavCorridor(
            map_name="Azeroth",
            adt_x=0,
            adt_y=0,
            start=extended_points[0],
            stop=extended_points[-1],
            points=extended_points,
            source="fresh_client_visible_reverse_breadcrumbs",
        )
        self.assertEqual(safe_retreat_deadline_seconds(extended), 83.0)


if __name__ == "__main__":
    unittest.main()
