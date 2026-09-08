from __future__ import annotations

from dataclasses import replace
import unittest

from perfect_assassin.movement.adaptive_steering import (
    AdaptiveTrajectorySteeringController,
)
from perfect_assassin.movement.client_navmesh import (
    NavCorridor,
    NavPoint,
    NavPolygon,
    NavPortal,
)
from perfect_assassin.movement.predictive_steering import SteeringState


def _corridor(points: tuple[tuple[float, float], ...], width: float) -> NavCorridor:
    nav = tuple(NavPoint(x, y, 0.0) for x, y in points)
    polygons = tuple(
        NavPolygon(
            index,
            0,
            0,
            0.0,
            point,
            (
                NavPoint(point.x - 0.25, point.y - 0.25, 0.0),
                NavPoint(point.x + 0.25, point.y - 0.25, 0.0),
                NavPoint(point.x, point.y + 0.25, 0.0),
            ),
            frozenset({"ground"}),
        )
        for index, point in enumerate(nav)
    )
    portals = tuple(
        NavPortal(index, index + 1, stop, stop, width)
        for index, stop in enumerate(nav[1:])
    )
    return NavCorridor(
        "Fixture",
        0,
        0,
        nav[0],
        nav[-1],
        nav,
        polygons=polygons,
        portals=portals,
    )


class AdaptiveTrajectorySteeringTests(unittest.TestCase):
    def test_narrow_sharp_turn_selects_mppi(self) -> None:
        corridor = _corridor(
            ((0.0, 0.0), (15.0, 0.0), (4.0, -12.0)),
            width=2.2,
        )
        self.assertTrue(AdaptiveTrajectorySteeringController.needs_mppi(corridor))

    def test_narrow_steep_transition_without_large_turn_stays_geometric(self) -> None:
        corridor = _corridor(
            ((0.0, 0.0), (20.0, 0.0), (23.0, 8.0)),
            width=3.0,
        )
        corridor = replace(
            corridor,
            polygons=tuple(
                replace(polygon, slope_degrees=35.0)
                for polygon in corridor.polygons
            ),
            clearance_inset_count=1,
        )
        self.assertFalse(AdaptiveTrajectorySteeringController.needs_mppi(corridor))

    def test_wide_turn_stays_deterministic(self) -> None:
        corridor = _corridor(
            ((0.0, 0.0), (12.0, 0.0), (15.0, 3.0), (15.0, 8.0)),
            width=6.0,
        )
        self.assertFalse(AdaptiveTrajectorySteeringController.needs_mppi(corridor))

    def test_without_geometry_never_guesses_mppi(self) -> None:
        points = tuple(NavPoint(x, y, 0.0) for x, y in ((0.0, 0.0), (15.0, 0.0), (4.0, -12.0)))
        corridor = NavCorridor("Fixture", 0, 0, points[0], points[-1], points)
        self.assertFalse(AdaptiveTrajectorySteeringController.needs_mppi(corridor))

    def test_fallback_preserves_mppi_controller_state(self) -> None:
        class FallbackMppi:
            mppi_telemetry = None

            def decide_with_environment(self, state, corridor, **kwargs):
                return type(
                    "FallbackIntent",
                    (),
                    {"reason": "planner_not_ready"},
                )()

            def close(self):
                pass

        corridor = _corridor(
            ((0.0, 0.0), (15.0, 0.0), (4.0, -12.0)),
            width=2.2,
        )
        controller = AdaptiveTrajectorySteeringController(
            mppi_factory=FallbackMppi,
        )
        intent = controller.decide(SteeringState(0.0, 0.0, 0.0, 7.0), corridor)
        self.assertEqual(intent.reason, "planner_not_ready")
        controller.close()

    def test_stationary_pivot_is_forwarded_to_selected_mppi_child(self) -> None:
        corridor = _corridor(
            ((0.0, 0.0), (15.0, 0.0), (4.0, -12.0)),
            width=2.2,
        )
        controller = AdaptiveTrajectorySteeringController()
        controller.request_stationary_pivot()

        intent = controller.decide(
            SteeringState(0.0, 0.0, 1.20, 7.0),
            corridor,
        )

        self.assertEqual(intent.state, "PIVOT")
        self.assertEqual(intent.forward_hold_ms, 0)
        controller.close()

    def test_stationary_pivot_is_forwarded_to_geometric_child(self) -> None:
        corridor = _corridor(((0.0, 0.0), (12.0, 0.0)), width=6.0)
        controller = AdaptiveTrajectorySteeringController()
        controller.request_stationary_pivot()

        intent = controller.decide(
            SteeringState(0.0, 0.0, 1.20, 7.0),
            corridor,
        )

        self.assertEqual(intent.state, "PIVOT")
        self.assertEqual(intent.forward_hold_ms, 0)
        controller.close()

    def test_confined_forward_stall_realigns_before_collision_learning(self) -> None:
        corridor = replace(
            _corridor(((0.0, 0.0), (12.0, 0.0)), width=2.2),
            doodad_avoidance_applied=True,
            doodad_detour_count=1,
        )
        controller = AdaptiveTrajectorySteeringController()

        intent = controller.decide(
            SteeringState(0.0, 0.0, 0.0, 7.0, 0.61),
            corridor,
        )

        self.assertEqual(intent.state, "REPLAN")
        self.assertEqual(intent.reason, "confined_forward_stall_realign")
        controller.close()


if __name__ == "__main__":
    unittest.main()
