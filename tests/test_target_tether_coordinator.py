from __future__ import annotations

from threading import Event
import time
import unittest

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.target_tether_coordinator import (
    AsyncTargetTetherCoordinator,
)


class GatedNavigator:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.calls = 0

    def find_corridor(self, *, map_name, start, stop_x, stop_y):
        self.calls += 1
        self.started.set()
        if not self.release.wait(1.0):
            raise RuntimeError("fixture query timed out")
        stop = NavPoint(stop_x, stop_y, start.z)
        return NavCorridor(
            map_name=map_name,
            adt_x=31,
            adt_y=31,
            start=start,
            stop=stop,
            points=(start, stop),
        )


class AsyncTargetTetherCoordinatorTests(unittest.TestCase):
    def update(self, coordinator, *, identity=22, observed=1.0):
        return coordinator.update(
            target_identity_crc16=identity,
            player=NavPoint(0.0, 0.0, 0.0),
            player_heading_rad=0.0,
            target_bearing_error_x_normalized=0.0,
            client_in_melee=False,
            observed_monotonic_s=observed,
        )

    def test_native_query_is_async_and_then_becomes_direct_guidance(self) -> None:
        navigator = GatedNavigator()
        coordinator = AsyncTargetTetherCoordinator(navigator)
        try:
            first = self.update(coordinator)
            self.assertEqual(first.state, "WAITING_NAVMESH")
            self.assertTrue(navigator.started.wait(0.5))
            navigator.release.set()
            intent = first
            for index in range(50):
                intent = self.update(coordinator, observed=1.01 + index * 0.01)
                if intent.state != "WAITING_NAVMESH":
                    break
                time.sleep(0.002)
            self.assertEqual(intent.state, "DIRECT")
            self.assertEqual(navigator.calls, 1)
        finally:
            navigator.release.set()
            coordinator.close()

    def test_target_identity_change_never_reuses_old_corridor(self) -> None:
        navigator = GatedNavigator()
        coordinator = AsyncTargetTetherCoordinator(navigator)
        try:
            self.update(coordinator, identity=22)
            self.assertTrue(navigator.started.wait(0.5))
            changed = self.update(coordinator, identity=23, observed=1.1)
            self.assertEqual(changed.state, "WAITING_NAVMESH")
        finally:
            navigator.release.set()
            coordinator.close()


if __name__ == "__main__":
    unittest.main()
