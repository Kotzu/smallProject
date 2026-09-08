from __future__ import annotations

from typing import Mapping
import unittest

from perfect_assassin.movement.dynamic_avoidance import ScreenEntityObservation
from perfect_assassin.movement.observation_port import MovementObservationPort
from perfect_assassin.movement.risk_aware_route_policy import TravelCapability


class _ReplayLikeObservationAdapter:
    def __init__(self) -> None:
        self.opened = False
        self.closed = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def next_observation(self) -> Mapping[str, object]:
        return {
            "tracking_state": "VALID",
            "position": {"x": 0.5, "y": 0.5, "facing_rad": 1.25},
        }

    @property
    def latest_facing_source(self) -> str:
        return "REPLAY_EXACT"

    @property
    def latest_travel_capability(self) -> TravelCapability | None:
        return None

    @property
    def latest_dynamic_observations(
        self,
    ) -> tuple[ScreenEntityObservation, ...]:
        return ()

    @property
    def latest_dynamic_detection_error(self) -> str | None:
        return None


class MovementObservationPortTests(unittest.TestCase):
    def test_structural_adapter_satisfies_client_neutral_port(self) -> None:
        adapter = _ReplayLikeObservationAdapter()

        self.assertIsInstance(adapter, MovementObservationPort)
        adapter.open()
        self.assertTrue(adapter.opened)
        self.assertEqual(adapter.next_observation()["tracking_state"], "VALID")
        adapter.close()
        self.assertTrue(adapter.closed)

    def test_missing_live_feedback_fails_protocol_check(self) -> None:
        class OpenLoopOnly:
            def open(self) -> None:
                pass

            def close(self) -> None:
                pass

        self.assertNotIsInstance(OpenLoopOnly(), MovementObservationPort)


if __name__ == "__main__":
    unittest.main()
