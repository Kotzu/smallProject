from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from math import isfinite
from threading import Lock

from perfect_assassin.movement.client_navmesh import (
    ClientNavmeshQuery,
    NavCorridor,
    NavPoint,
)
from perfect_assassin.movement.target_tether import (
    TargetTetherIntent,
    TargetTetherPlanner,
    TargetTetherProjection,
)


@dataclass(frozen=True, slots=True)
class _PlannedTether:
    target_identity_crc16: int
    projection: TargetTetherProjection
    corridor: NavCorridor
    requested_monotonic_s: float


class AsyncTargetTetherCoordinator:
    """Keep native Detour queries off the 20 Hz combat perception loop."""

    def __init__(
        self,
        navigator: ClientNavmeshQuery,
        *,
        planner: TargetTetherPlanner | None = None,
        maximum_start_drift_world: float = 2.0,
        maximum_target_drift_world: float = 2.0,
        maximum_corridor_age_s: float = 1.20,
    ) -> None:
        for label, value in (
            ("tether start drift", maximum_start_drift_world),
            ("tether target drift", maximum_target_drift_world),
            ("tether corridor age", maximum_corridor_age_s),
        ):
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{label} is invalid")
        self._navigator = navigator
        self._planner = planner or TargetTetherPlanner()
        self._maximum_start_drift_world = maximum_start_drift_world
        self._maximum_target_drift_world = maximum_target_drift_world
        self._maximum_corridor_age_s = maximum_corridor_age_s
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="pa-target-tether",
        )
        self._future: Future[_PlannedTether] | None = None
        self._cached: _PlannedTether | None = None
        self._target_identity_crc16: int | None = None
        self._closed = False
        self._lock = Lock()

    def update(
        self,
        *,
        target_identity_crc16: int,
        player: NavPoint,
        player_heading_rad: float,
        target_bearing_error_x_normalized: float,
        client_in_melee: bool | None,
        observed_monotonic_s: float,
    ) -> TargetTetherIntent:
        if self._closed:
            raise RuntimeError("target tether coordinator is closed")
        if type(target_identity_crc16) is not int or not 1 <= target_identity_crc16 <= 65_535:
            raise ValueError("target tether identity is invalid")
        if not isfinite(observed_monotonic_s) or observed_monotonic_s < 0:
            raise ValueError("target tether observation time is invalid")
        projection = self._planner.project(
            player=player,
            player_heading_rad=player_heading_rad,
            target_bearing_error_x_normalized=target_bearing_error_x_normalized,
            client_in_melee=client_in_melee,
        )
        with self._lock:
            if target_identity_crc16 != self._target_identity_crc16:
                if self._future is not None:
                    self._future.cancel()
                self._future = None
                self._cached = None
                self._target_identity_crc16 = target_identity_crc16
            self._consume_ready_locked()
            compatible = self._compatible_locked(
                target_identity_crc16,
                projection,
                observed_monotonic_s,
            )
            if client_in_melee is not True and self._future is None and not compatible:
                self._future = self._executor.submit(
                    self._query,
                    target_identity_crc16,
                    projection,
                    observed_monotonic_s,
                )
            corridor = self._cached.corridor if compatible and self._cached else None
        return self._planner.decide(projection, corridor)

    def _query(
        self,
        target_identity_crc16: int,
        projection: TargetTetherProjection,
        observed_monotonic_s: float,
    ) -> _PlannedTether:
        corridor = self._navigator.find_corridor(
            map_name="Azeroth",
            start=projection.player,
            stop_x=projection.projected_target.x,
            stop_y=projection.projected_target.y,
        )
        return _PlannedTether(
            target_identity_crc16=target_identity_crc16,
            projection=projection,
            corridor=corridor,
            requested_monotonic_s=observed_monotonic_s,
        )

    def _consume_ready_locked(self) -> None:
        if self._future is None or not self._future.done():
            return
        future = self._future
        self._future = None
        try:
            planned = future.result()
        except Exception:
            self._cached = None
            return
        if planned.target_identity_crc16 == self._target_identity_crc16:
            self._cached = planned

    def _compatible_locked(
        self,
        target_identity_crc16: int,
        projection: TargetTetherProjection,
        observed_monotonic_s: float,
    ) -> bool:
        cached = self._cached
        return bool(
            cached is not None
            and cached.target_identity_crc16 == target_identity_crc16
            and projection.player.distance_2d(cached.projection.player)
            <= self._maximum_start_drift_world
            and projection.projected_target.distance_2d(
                cached.projection.projected_target
            ) <= self._maximum_target_drift_world
            and 0 <= observed_monotonic_s - cached.requested_monotonic_s
            <= self._maximum_corridor_age_s
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._future is not None:
                self._future.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
