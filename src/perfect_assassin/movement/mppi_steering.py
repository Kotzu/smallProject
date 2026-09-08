from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from math import hypot, isfinite, pi
from threading import Lock
from typing import Protocol, Self

import numpy as np

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.predictive_steering import (
    PredictiveSteeringController,
    SteeringIntent,
    SteeringState,
)


@dataclass(frozen=True, slots=True)
class MppiConfiguration:
    """Bounded PA-MPPI sampling and motion-model parameters.

    The defaults follow the same 50 ms / 56-step shape used by the reference
    Nav2 controller, adapted to WoW's fixed forward speed and RMB yaw input.
    """

    batch_size: int = 1_000
    time_steps: int = 56
    model_dt_s: float = 0.05
    iterations: int = 1
    temperature: float = 0.30
    gamma: float = 0.015
    yaw_noise_std_rad_s: float = 0.40
    maximum_yaw_rate_rad_s: float = 2.20
    # The calibrated 8 rad/s² cap let the camera carry through the final
    # Shadowfang switchback.  12 rad/s² remains below the bounded 30 rad/s²
    # configuration ceiling and gives the closed-loop actuator enough time to
    # settle the observed 60-70 degree turn without a stationary pivot.
    maximum_yaw_acceleration_rad_s2: float = 12.0
    cross_track_weight: float = 6.0
    heading_weight: float = 0.8
    progress_weight: float = 1.2
    terminal_goal_weight: float = 2.5
    yaw_effort_weight: float = 0.10
    yaw_smoothness_weight: float = 1.00
    obstacle_proximity_weight: float = 4.0
    infeasible_cost: float = 1_000_000.0

    def __post_init__(self) -> None:
        numeric = (
            self.model_dt_s,
            self.temperature,
            self.gamma,
            self.yaw_noise_std_rad_s,
            self.maximum_yaw_rate_rad_s,
            self.maximum_yaw_acceleration_rad_s2,
            self.cross_track_weight,
            self.heading_weight,
            self.progress_weight,
            self.terminal_goal_weight,
            self.yaw_effort_weight,
            self.yaw_smoothness_weight,
            self.obstacle_proximity_weight,
            self.infeasible_cost,
        )
        if (
            not 32 <= self.batch_size <= 20_000
            or not 12 <= self.time_steps <= 160
            or not 1 <= self.iterations <= 4
            or any(not isfinite(value) or value <= 0.0 for value in numeric)
            or not 0.02 <= self.model_dt_s <= 0.20
            or not 0.05 <= self.temperature <= 10.0
            or not 0.05 <= self.yaw_noise_std_rad_s <= 3.0
            or not 0.2 <= self.maximum_yaw_rate_rad_s <= 5.0
            or not 0.5 <= self.maximum_yaw_acceleration_rad_s2 <= 30.0
            or self.infeasible_cost < 10_000.0
        ):
            raise ValueError("PA-MPPI configuration is invalid")


@dataclass(frozen=True, slots=True)
class MppiDynamicObstacle:
    x: float
    y: float
    radius_world: float
    velocity_x_world_per_s: float = 0.0
    velocity_y_world_per_s: float = 0.0

    def __post_init__(self) -> None:
        if (
            any(
                not isfinite(value)
                for value in (
                    self.x,
                    self.y,
                    self.radius_world,
                    self.velocity_x_world_per_s,
                    self.velocity_y_world_per_s,
                )
            )
            or not 0.05 <= self.radius_world <= 20.0
            or abs(self.velocity_x_world_per_s) > 30.0
            or abs(self.velocity_y_world_per_s) > 30.0
        ):
            raise ValueError("PA-MPPI dynamic obstacle is invalid")


@dataclass(frozen=True, slots=True)
class MppiPlanningSnapshot:
    snapshot_id: int
    state: SteeringState
    corridor: NavCorridor
    actor_radius_world: float = 0.75
    pose_uncertainty_world: float = 0.0
    obstacles: tuple[MppiDynamicObstacle, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.snapshot_id < 0
            or self.state.heading_rad is None
            or not isfinite(self.state.heading_rad)
            or not self.corridor.complete
            or not 0.2 <= self.actor_radius_world <= 2.0
            or not 0.0 <= self.pose_uncertainty_world <= 3.0
            or len(self.obstacles) > 64
        ):
            raise ValueError("PA-MPPI planning snapshot is invalid")


@dataclass(frozen=True, slots=True)
class MppiControl:
    forward: bool
    yaw_rate_rad_s: float
    duration_s: float


@dataclass(frozen=True, slots=True)
class MppiPlan:
    status: str
    snapshot_id: int
    corridor_signature: str
    start_x: float
    start_y: float
    start_heading_rad: float
    controls: tuple[MppiControl, ...]
    predicted_path: tuple[NavPoint, ...]
    sample_count: int
    feasible_sample_count: int
    minimum_cost: float | None
    planning_duration_ms: float
    reason: str

    def __post_init__(self) -> None:
        if self.status not in {"READY", "NO_FEASIBLE_TRAJECTORY"}:
            raise ValueError("PA-MPPI plan status is invalid")
        if (
            self.snapshot_id < 0
            or len(self.controls) != len(self.predicted_path)
            or self.sample_count < 1
            or not 0 <= self.feasible_sample_count <= self.sample_count
            or not isfinite(self.planning_duration_ms)
            or self.planning_duration_ms < 0.0
            or not self.reason
        ):
            raise ValueError("PA-MPPI plan metadata is invalid")
        if self.status == "READY" and (
            not self.controls
            or self.feasible_sample_count < 1
            or self.minimum_cost is None
            or not isfinite(self.minimum_cost)
        ):
            raise ValueError("ready PA-MPPI plan has no feasible trajectory")
        if self.status != "READY" and (self.controls or self.predicted_path):
            raise ValueError("failed PA-MPPI plan cannot publish controls")


@dataclass(frozen=True, slots=True)
class MppiControllerTelemetry:
    state: str
    snapshot_id: int | None
    plan_age_s: float | None
    planning_duration_ms: float | None
    sample_count: int
    feasible_sample_count: int
    fallback_reason: str | None


class MppiPlanner(Protocol):
    def plan(self, snapshot: MppiPlanningSnapshot) -> MppiPlan: ...


@dataclass(frozen=True, slots=True)
class _PathGeometry:
    x0: np.ndarray
    y0: np.ndarray
    z0: np.ndarray
    dx: np.ndarray
    dy: np.ndarray
    dz: np.ndarray
    length: np.ndarray
    length_squared: np.ndarray
    cumulative: np.ndarray
    heading: np.ndarray
    half_width: np.ndarray
    total_length: float


class PathIntegralSteeringPlanner:
    """Vectorized receding-horizon MPPI optimizer for a Detour corridor."""

    # The nominal trajectory must see beyond the actor's immediate tangent at
    # a narrow switchback.  A 0.90 s preview is adequate for ordinary bends,
    # but it reaches the 60-70 degree Shadowfang apex too late and lets the
    # physical camera carry the actor outside the centre path.  This remains a
    # time-based horizon over the observed corridor, never an executable
    # waypoint or map-specific route.
    NOMINAL_PREVIEW_TIME_S = 1.80

    def __init__(self, configuration: MppiConfiguration | None = None) -> None:
        self.configuration = configuration or MppiConfiguration()
        self._mean_yaw_rates: np.ndarray | None = None
        self._corridor_signature: str | None = None

    @staticmethod
    def corridor_signature(corridor: NavCorridor) -> str:
        digest = hashlib.sha256()
        digest.update(corridor.map_name.encode("utf-8"))
        digest.update(f"|{corridor.adt_x}|{corridor.adt_y}|".encode("ascii"))
        for point in corridor.guidance_points():
            digest.update(f"{point.x:.6f},{point.y:.6f},{point.z:.6f};".encode("ascii"))
        for portal in corridor.portals:
            digest.update(f"p{portal.width:.6f};".encode("ascii"))
        return digest.hexdigest()

    @staticmethod
    def _wrap(values: np.ndarray) -> np.ndarray:
        return (values + pi) % (2.0 * pi) - pi

    @staticmethod
    def _geometry(corridor: NavCorridor) -> _PathGeometry:
        points = corridor.guidance_points()
        if len(points) < 2:
            raise ValueError("PA-MPPI corridor has no movement length")
        xyz = np.asarray(
            [(item.x, item.y, item.z) for item in points], dtype=np.float64
        )
        delta = xyz[1:] - xyz[:-1]
        length = np.hypot(delta[:, 0], delta[:, 1])
        usable = length > 1.0e-6
        if not np.any(usable):
            raise ValueError("PA-MPPI corridor has no movement length")
        xyz0 = xyz[:-1][usable]
        delta = delta[usable]
        length = length[usable]
        cumulative = np.concatenate((np.asarray([0.0]), np.cumsum(length)))
        heading = np.arctan2(delta[:, 1], delta[:, 0])
        if corridor.portals:
            portal_widths = np.asarray(
                [portal.width for portal in corridor.portals],
                dtype=np.float64,
            )
            fractions = (cumulative[:-1] + length * 0.5) / float(cumulative[-1])
            portal_indices = np.minimum(
                len(portal_widths) - 1,
                np.floor(fractions * len(portal_widths)).astype(np.int64),
            )
            # Detour polygons are already eroded for the actor.  Portal width
            # therefore describes remaining centre-path room; do not subtract
            # the capsule radius a second time.
            half_width = np.clip(portal_widths[portal_indices] * 0.5, 0.20, 3.0)
        else:
            half_width = np.full(len(length), 2.5, dtype=np.float64)
        return _PathGeometry(
            x0=xyz0[:, 0],
            y0=xyz0[:, 1],
            z0=xyz0[:, 2],
            dx=delta[:, 0],
            dy=delta[:, 1],
            dz=delta[:, 2],
            length=length,
            length_squared=length * length,
            cumulative=cumulative,
            heading=heading,
            half_width=half_width,
            total_length=float(cumulative[-1]),
        )

    @staticmethod
    def _project(
        x: np.ndarray,
        y: np.ndarray,
        geometry: _PathGeometry,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        offset_x = x[:, None] - geometry.x0[None, :]
        offset_y = y[:, None] - geometry.y0[None, :]
        along = np.clip(
            (offset_x * geometry.dx[None, :] + offset_y * geometry.dy[None, :])
            / geometry.length_squared[None, :],
            0.0,
            1.0,
        )
        projected_x = geometry.x0[None, :] + along * geometry.dx[None, :]
        projected_y = geometry.y0[None, :] + along * geometry.dy[None, :]
        distance_squared = (x[:, None] - projected_x) ** 2 + (
            y[:, None] - projected_y
        ) ** 2
        indices = np.argmin(distance_squared, axis=1)
        rows = np.arange(len(x))
        selected_along = along[rows, indices]
        progress = (
            geometry.cumulative[indices] + selected_along * geometry.length[indices]
        )
        return np.sqrt(distance_squared[rows, indices]), progress, indices

    def _constrain_controls(
        self,
        controls: np.ndarray,
        *,
        initial_yaw_rate_rad_s: float = 0.0,
    ) -> np.ndarray:
        config = self.configuration
        limited = np.clip(
            controls,
            -config.maximum_yaw_rate_rad_s,
            config.maximum_yaw_rate_rad_s,
        ).copy()
        maximum_delta = config.maximum_yaw_acceleration_rad_s2 * config.model_dt_s
        previous = np.full(limited.shape[0], initial_yaw_rate_rad_s, dtype=np.float64)
        for index in range(limited.shape[1]):
            limited[:, index] = np.clip(
                limited[:, index],
                previous - maximum_delta,
                previous + maximum_delta,
            )
            previous = limited[:, index]
        return limited

    def _nominal_controls(
        self,
        snapshot: MppiPlanningSnapshot,
        geometry: _PathGeometry,
        signature: str,
    ) -> np.ndarray:
        config = self.configuration
        start_x = np.asarray([snapshot.state.x], dtype=np.float64)
        start_y = np.asarray([snapshot.state.y], dtype=np.float64)
        _, progress, _ = self._project(start_x, start_y, geometry)
        # Preview enough travel to expose a narrow switchback before the
        # actor reaches its apex.  The previous 0.90 s seed waited until the
        # actor was almost at an S-bend and forced a visibly late, sharp
        # correction even though the optimizer could already see it.
        preview_world = max(
            5.0,
            snapshot.state.speed_world_per_s * self.NOMINAL_PREVIEW_TIME_S,
        )
        distances = np.minimum(
            geometry.total_length,
            progress[0]
            + snapshot.state.speed_world_per_s
            * config.model_dt_s
            * np.arange(1, config.time_steps + 1)
            + preview_world,
        )
        indices = np.minimum(
            len(geometry.length) - 1,
            np.searchsorted(geometry.cumulative[1:], distances, side="left"),
        )
        along = (distances - geometry.cumulative[indices]) / geometry.length[indices]
        target_x = geometry.x0[indices] + geometry.dx[indices] * along
        target_y = geometry.y0[indices] + geometry.dy[indices] * along
        desired = np.empty(config.time_steps, dtype=np.float64)
        predicted_x = snapshot.state.x
        predicted_y = snapshot.state.y
        predicted_heading = float(snapshot.state.heading_rad)
        for index in range(config.time_steps):
            pursuit_heading = np.arctan2(
                target_y[index] - predicted_y,
                target_x[index] - predicted_x,
            )
            heading_error = self._wrap(
                np.asarray(
                    [
                        pursuit_heading - predicted_heading,
                    ]
                )
            )[0]
            desired[index] = np.clip(
                heading_error * 2.5,
                -config.maximum_yaw_rate_rad_s,
                config.maximum_yaw_rate_rad_s,
            )
            predicted_heading = float(
                self._wrap(
                    np.asarray(
                        [
                            predicted_heading + desired[index] * config.model_dt_s,
                        ]
                    )
                )[0]
            )
            predicted_x += (
                np.cos(predicted_heading)
                * snapshot.state.speed_world_per_s
                * config.model_dt_s
            )
            predicted_y += (
                np.sin(predicted_heading)
                * snapshot.state.speed_world_per_s
                * config.model_dt_s
            )
        if self._corridor_signature == signature and self._mean_yaw_rates is not None:
            shifted = np.concatenate(
                (
                    self._mean_yaw_rates[1:],
                    self._mean_yaw_rates[-1:],
                )
            )
            # The fresh pursuit seed is aligned to the newly observed pose;
            # retain only enough of the shifted solution to preserve continuity.
            desired = shifted * 0.25 + desired * 0.75
        return self._constrain_controls(desired[None, :])[0]

    def _rollout(
        self,
        snapshot: MppiPlanningSnapshot,
        geometry: _PathGeometry,
        controls: np.ndarray,
        *,
        collect_path: bool,
    ) -> tuple[np.ndarray, np.ndarray, tuple[NavPoint, ...]]:
        config = self.configuration
        count = controls.shape[0]
        x = np.full(count, snapshot.state.x, dtype=np.float64)
        y = np.full(count, snapshot.state.y, dtype=np.float64)
        heading = np.full(count, float(snapshot.state.heading_rad), dtype=np.float64)
        cost = np.zeros(count, dtype=np.float64)
        feasible = np.ones(count, dtype=bool)
        _, initial_progress, _ = self._project(x, y, geometry)
        prior_control = np.zeros(count, dtype=np.float64)
        path: list[NavPoint] = []
        uncertainty = snapshot.pose_uncertainty_world
        terminal = np.zeros(count, dtype=bool)
        step_distance = snapshot.state.speed_world_per_s * config.model_dt_s
        # A complete local corridor can legitimately be shorter than the MPPI
        # horizon while a rolling continuation is still being queried.  The
        # old fixed-speed model drove every sample beyond the temporary stop,
        # then rejected it as cross-track even though the proven corridor was
        # followed perfectly.  Treat the reached endpoint as an absorbing
        # terminal state.  Receding-horizon control consumes only the leading
        # controls; the runner either advances to the joined continuation or
        # applies its ordinary arrival policy before the frozen suffix matters.
        terminal_capture_world = max(0.35, step_distance * 1.5)
        for index in range(config.time_steps):
            control = controls[:, index]
            moving = ~terminal
            heading[moving] = self._wrap(
                heading[moving] + control[moving] * config.model_dt_s,
            )
            x[moving] += np.cos(heading[moving]) * step_distance
            y[moving] += np.sin(heading[moving]) * step_distance
            cross_track, progress, segments = self._project(x, y, geometry)
            allowed = np.maximum(0.10, geometry.half_width[segments] - uncertainty)
            inside_corridor = cross_track <= allowed
            feasible &= inside_corridor
            reached_terminal = (
                moving
                & inside_corridor
                & (progress >= geometry.total_length - terminal_capture_world)
                & (
                    np.hypot(
                        snapshot.corridor.stop.x - x,
                        snapshot.corridor.stop.y - y,
                    )
                    <= terminal_capture_world
                )
            )
            if np.any(reached_terminal):
                x[reached_terminal] = snapshot.corridor.stop.x
                y[reached_terminal] = snapshot.corridor.stop.y
                terminal |= reached_terminal
                cross_track, progress, segments = self._project(x, y, geometry)
                allowed = np.maximum(
                    0.10,
                    geometry.half_width[segments] - uncertainty,
                )
            heading_error = self._wrap(heading - geometry.heading[segments])
            cost += config.cross_track_weight * (cross_track / allowed) ** 2
            cost += config.heading_weight * heading_error**2
            cost += config.yaw_effort_weight * control**2
            cost += config.yaw_smoothness_weight * (control - prior_control) ** 2
            prior_control = control
            for obstacle in snapshot.obstacles:
                horizon_s = (index + 1) * config.model_dt_s
                obstacle_x = obstacle.x + obstacle.velocity_x_world_per_s * horizon_s
                obstacle_y = obstacle.y + obstacle.velocity_y_world_per_s * horizon_s
                clearance = (
                    np.hypot(x - obstacle_x, y - obstacle_y)
                    - obstacle.radius_world
                    - snapshot.actor_radius_world
                    - uncertainty
                )
                feasible &= clearance > 0.0
                near = np.maximum(0.10, clearance)
                cost += config.obstacle_proximity_weight / (near * near)
            if collect_path:
                segment = int(segments[0])
                along = min(
                    1.0,
                    max(
                        0.0,
                        (float(progress[0]) - geometry.cumulative[segment])
                        / geometry.length[segment],
                    ),
                )
                path.append(
                    NavPoint(
                        float(x[0]),
                        float(y[0]),
                        float(geometry.z0[segment] + geometry.dz[segment] * along),
                    )
                )
        cost -= config.progress_weight * np.maximum(0.0, progress - initial_progress)
        cost += config.terminal_goal_weight * np.hypot(
            snapshot.corridor.stop.x - x,
            snapshot.corridor.stop.y - y,
        )
        cost += (~feasible) * config.infeasible_cost
        return cost, feasible, tuple(path)

    def plan(self, snapshot: MppiPlanningSnapshot) -> MppiPlan:
        started = time.perf_counter()
        config = self.configuration
        signature = self.corridor_signature(snapshot.corridor)
        geometry = self._geometry(snapshot.corridor)
        nominal = self._nominal_controls(snapshot, geometry, signature)
        # Common random numbers make adjacent replans comparable.  Changing the
        # sample cloud every few observations caused control-sign chatter even
        # when the path and physical state changed only slightly.
        seed_material = f"{signature}:pa-mppi-v1".encode("ascii")
        seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "little")
        random = np.random.default_rng(seed)
        feasible_count = 0
        minimum_cost: float | None = None
        selected = nominal
        for _ in range(config.iterations):
            noise = random.normal(
                0.0,
                config.yaw_noise_std_rad_s,
                size=(config.batch_size, config.time_steps),
            )
            noise[0, :] = 0.0
            candidates = self._constrain_controls(nominal[None, :] + noise)
            costs, feasible, _ = self._rollout(
                snapshot,
                geometry,
                candidates,
                collect_path=False,
            )
            # Path-integral control regularization.  Use the perturbation that
            # survives actuator constraints rather than the raw Gaussian draw,
            # otherwise saturated samples receive an incorrect likelihood.
            applied_noise = candidates - nominal[None, :]
            costs += config.gamma * np.sum(
                nominal[None, :] * applied_noise / (config.yaw_noise_std_rad_s**2),
                axis=1,
            )
            feasible_count = int(np.count_nonzero(feasible))
            if feasible_count == 0:
                duration_ms = (time.perf_counter() - started) * 1000.0
                self._corridor_signature = signature
                self._mean_yaw_rates = nominal.copy()
                return MppiPlan(
                    status="NO_FEASIBLE_TRAJECTORY",
                    snapshot_id=snapshot.snapshot_id,
                    corridor_signature=signature,
                    start_x=snapshot.state.x,
                    start_y=snapshot.state.y,
                    start_heading_rad=float(snapshot.state.heading_rad),
                    controls=(),
                    predicted_path=(),
                    sample_count=config.batch_size,
                    feasible_sample_count=0,
                    minimum_cost=None,
                    planning_duration_ms=duration_ms,
                    reason="all_sampled_trajectories_violate_topology_or_clearance",
                )
            feasible_costs = costs[feasible]
            minimum_cost = float(np.min(feasible_costs))
            weights = np.zeros(config.batch_size, dtype=np.float64)
            weights[feasible] = np.exp(
                -(feasible_costs - minimum_cost) / config.temperature,
            )
            weight_sum = float(np.sum(weights))
            if not isfinite(weight_sum) or weight_sum <= 1.0e-12:
                best = int(np.flatnonzero(feasible)[np.argmin(feasible_costs)])
                selected = candidates[best]
            else:
                selected = (
                    nominal
                    + np.sum(
                        weights[:, None] * noise,
                        axis=0,
                    )
                    / weight_sum
                )
                selected = self._constrain_controls(selected[None, :])[0]
            selected_cost, selected_feasible, _ = self._rollout(
                snapshot,
                geometry,
                selected[None, :],
                collect_path=False,
            )
            if not bool(selected_feasible[0]):
                best = int(np.flatnonzero(feasible)[np.argmin(feasible_costs)])
                selected = candidates[best]
                minimum_cost = float(costs[best])
            else:
                minimum_cost = float(selected_cost[0])
            nominal = selected
        _, final_feasible, predicted_path = self._rollout(
            snapshot,
            geometry,
            selected[None, :],
            collect_path=True,
        )
        if not bool(final_feasible[0]):
            raise RuntimeError("PA-MPPI published an infeasible trajectory")
        self._corridor_signature = signature
        self._mean_yaw_rates = np.concatenate((selected[1:], selected[-1:]))
        controls = tuple(
            MppiControl(True, float(value), config.model_dt_s) for value in selected
        )
        return MppiPlan(
            status="READY",
            snapshot_id=snapshot.snapshot_id,
            corridor_signature=signature,
            start_x=snapshot.state.x,
            start_y=snapshot.state.y,
            start_heading_rad=float(snapshot.state.heading_rad),
            controls=controls,
            predicted_path=predicted_path,
            sample_count=config.batch_size,
            feasible_sample_count=feasible_count,
            minimum_cost=minimum_cost,
            planning_duration_ms=(time.perf_counter() - started) * 1000.0,
            reason="path_integral_weighted_receding_horizon",
        )


class _MppiMouseFilter:
    """Convert sampled yaw into continuous, reversal-resistant RMB input."""

    # One-pixel requests on this client are visible camera chatter, not useful
    # steering, while the player is still inside the ordinary road lane.
    # Two-pixel input remains necessary for the shallowest simulated curves.
    DEAD_BAND_PIXELS = 1
    ACCELERATION_PIXELS_PER_TICK = 1
    BRAKING_PIXELS_PER_TICK = 2
    REVERSAL_CONFIRMATION_TICKS = 5

    def __init__(self) -> None:
        self._output = 0
        self._accepted_sign = 0
        self._pending_sign = 0
        self._pending_ticks = 0

    def reset(self) -> None:
        self._output = 0
        self._accepted_sign = 0
        self._pending_sign = 0
        self._pending_ticks = 0

    def apply(self, requested: int, *, allow_micro_correction: bool = False) -> int:
        if abs(requested) <= self.DEAD_BAND_PIXELS and not allow_micro_correction:
            requested = 0
        requested_sign = 1 if requested > 0 else -1 if requested < 0 else 0
        if requested_sign and self._accepted_sign == 0:
            self._accepted_sign = requested_sign
        elif requested_sign and requested_sign != self._accepted_sign:
            if requested_sign == self._pending_sign:
                self._pending_ticks += 1
            else:
                self._pending_sign = requested_sign
                self._pending_ticks = 1
            if self._pending_ticks < self.REVERSAL_CONFIRMATION_TICKS:
                requested = 0
            else:
                self._accepted_sign = requested_sign
                self._pending_sign = 0
                self._pending_ticks = 0
        elif requested_sign:
            self._pending_sign = 0
            self._pending_ticks = 0

        if requested == 0:
            if self._output > 0:
                self._output = max(
                    0,
                    self._output - self.BRAKING_PIXELS_PER_TICK,
                )
            elif self._output < 0:
                self._output = min(
                    0,
                    self._output + self.BRAKING_PIXELS_PER_TICK,
                )
            return self._output

        self._output = max(
            self._output - self.ACCELERATION_PIXELS_PER_TICK,
            min(
                self._output + self.ACCELERATION_PIXELS_PER_TICK,
                requested,
            ),
        )
        return self._output


class MppiSteeringController(PredictiveSteeringController):
    """Synchronous PA-MPPI controller for deterministic LAB/replay evaluation."""

    def __init__(
        self,
        *,
        configuration: MppiConfiguration | None = None,
        replan_interval_ticks: int = 4,
        actor_radius_world: float = 0.75,
        lookahead_world: float | None = None,
        arrival_radius_world: float = 2.0,
    ) -> None:
        super().__init__(
            lookahead_world=lookahead_world,
            arrival_radius_world=arrival_radius_world,
        )
        if not 1 <= replan_interval_ticks <= 20 or not 0.2 <= actor_radius_world <= 2.0:
            raise ValueError("synchronous PA-MPPI controller settings are invalid")
        self._planner = PathIntegralSteeringPlanner(configuration)
        self._replan_interval_ticks = replan_interval_ticks
        self._actor_radius_world = actor_radius_world
        self._snapshot_id = 0
        self._plan: MppiPlan | None = None
        self._ticks_since_plan = replan_interval_ticks
        self._mouse_filter = _MppiMouseFilter()

    @staticmethod
    def _mouse_delta(control: MppiControl) -> int:
        mouse_delta = round(
            -control.yaw_rate_rad_s
            / (
                PredictiveSteeringController.MOUSE_COMMAND_VELOCITY_SCALE_HZ
                * PredictiveSteeringController.MOUSE_YAW_RAD_PER_PIXEL
            )
        )
        return max(
            -PredictiveSteeringController.FOLLOW_MAX_MOUSE_DELTA,
            min(PredictiveSteeringController.FOLLOW_MAX_MOUSE_DELTA, mouse_delta),
        )

    @staticmethod
    def _preview_control(plan: MppiPlan, index: int) -> MppiControl:
        stop = min(len(plan.controls), index + 4)
        controls = plan.controls[index:stop]
        weights = tuple(range(len(controls), 0, -1))
        yaw_rate = sum(
            control.yaw_rate_rad_s * weight
            for control, weight in zip(controls, weights, strict=True)
        ) / sum(weights)
        return MppiControl(True, yaw_rate, controls[0].duration_s)

    def _control_for_state(
        self,
        state: SteeringState,
        corridor: NavCorridor,
    ) -> MppiControl | None:
        plan = self._plan
        if (
            plan is None
            or plan.status != "READY"
            or plan.corridor_signature
            != PathIntegralSteeringPlanner.corridor_signature(corridor)
        ):
            return None
        distances = tuple(
            hypot(state.x - point.x, state.y - point.y) for point in plan.predicted_path
        )
        index = min(range(len(distances)), key=distances.__getitem__)
        if distances[index] > 2.0:
            return None
        return self._preview_control(plan, index)

    def decide_with_environment(
        self,
        state: SteeringState,
        corridor: NavCorridor,
        *,
        obstacles: tuple[MppiDynamicObstacle, ...] = (),
        pose_uncertainty_world: float = 0.0,
    ) -> SteeringIntent:
        baseline = super().decide(state, corridor)
        # A partial Detour corridor is safe to follow only up to its proven
        # frontier.  PA-MPPI deliberately requires a complete horizon, so do
        # not try to manufacture a planning snapshot from an incomplete leg.
        # The geometric controller already understands partial-frontier
        # progress and will hand the runner back to its ordinary replanner.
        if (
            baseline.state != "FOLLOW"
            or state.heading_rad is None
            or not corridor.complete
        ):
            self._plan = None
            self._ticks_since_plan = self._replan_interval_ticks
            self._mouse_filter.reset()
            return baseline
        control = self._control_for_state(state, corridor)
        if control is None or self._ticks_since_plan >= self._replan_interval_ticks:
            self._snapshot_id += 1
            self._plan = self._planner.plan(
                MppiPlanningSnapshot(
                    snapshot_id=self._snapshot_id,
                    state=state,
                    corridor=corridor,
                    actor_radius_world=self._actor_radius_world,
                    pose_uncertainty_world=pose_uncertainty_world,
                    obstacles=obstacles,
                )
            )
            self._ticks_since_plan = 0
            control = self._control_for_state(state, corridor)
        else:
            self._ticks_since_plan += 1
        if control is None:
            return baseline
        if baseline.strafe is not None:
            return baseline
        mouse_delta = self._mouse_filter.apply(
            self._mouse_delta(control),
            allow_micro_correction=(
                baseline.cross_track_error_world
                >= PredictiveSteeringController.OFF_CORRIDOR_RECOVERY_START_WORLD
            ),
        )
        self._previous_mouse_delta = mouse_delta
        return SteeringIntent(
            state="FOLLOW",
            forward_hold_ms=self.CONTROL_TICK_MS,
            mouse_delta_x=mouse_delta,
            lookahead=baseline.lookahead,
            reason="pa_mppi_synchronous_evaluation_trajectory",
            progress_world=baseline.progress_world,
            cross_track_error_world=baseline.cross_track_error_world,
            projected_z_world=baseline.projected_z_world,
            strafe=baseline.strafe,
        )

    def decide(self, state: SteeringState, corridor: NavCorridor) -> SteeringIntent:
        return self.decide_with_environment(state, corridor)


class AsyncMppiSteeringController(PredictiveSteeringController):
    """Non-blocking PA-MPPI facade with the geometric controller as fallback."""

    def __init__(
        self,
        *,
        planner: MppiPlanner | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        maximum_plan_age_s: float = 0.75,
        maximum_plan_deviation_world: float = 2.0,
        actor_radius_world: float = 0.75,
        replan_interval_ticks: int = 1,
        lookahead_world: float | None = None,
        arrival_radius_world: float = 2.0,
    ) -> None:
        super().__init__(
            lookahead_world=lookahead_world,
            arrival_radius_world=arrival_radius_world,
        )
        if (
            not 0.10 <= maximum_plan_age_s <= 2.0
            or not 0.25 <= maximum_plan_deviation_world <= 5.0
            or not 0.2 <= actor_radius_world <= 2.0
            or not 1 <= replan_interval_ticks <= 20
        ):
            raise ValueError("asynchronous PA-MPPI validity window is invalid")
        self._planner = planner or PathIntegralSteeringPlanner()
        self._monotonic = monotonic
        self._maximum_plan_age_s = maximum_plan_age_s
        self._maximum_plan_deviation_world = maximum_plan_deviation_world
        self._actor_radius_world = actor_radius_world
        self._replan_interval_ticks = replan_interval_ticks
        self._ticks_since_submit = replan_interval_ticks
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="pa-mppi",
        )
        self._future: Future[MppiPlan] | None = None
        self._published_plan: MppiPlan | None = None
        self._published_at_s: float | None = None
        self._snapshot_id = 0
        self._closed = False
        self._lock = Lock()
        self._mouse_filter = _MppiMouseFilter()
        self._telemetry = MppiControllerTelemetry(
            "FALLBACK",
            None,
            None,
            None,
            0,
            0,
            "no_plan_yet",
        )

    @property
    def mppi_telemetry(self) -> MppiControllerTelemetry:
        with self._lock:
            return self._telemetry

    def _collect_completed(self) -> None:
        if self._future is None or not self._future.done():
            return
        future = self._future
        self._future = None
        try:
            plan = future.result()
        # A custom planner is an extension seam. Any exception escaping its
        # worker must be contained so realtime control retains a safe fallback.
        except Exception as error:  # noqa: BLE001
            self._published_plan = None
            self._published_at_s = None
            self._telemetry = MppiControllerTelemetry(
                "FALLBACK",
                None,
                None,
                None,
                0,
                0,
                f"planner_error:{type(error).__name__}",
            )
            return
        if plan.status != "READY":
            self._published_plan = None
            self._published_at_s = None
            self._telemetry = MppiControllerTelemetry(
                "FALLBACK",
                plan.snapshot_id,
                None,
                plan.planning_duration_ms,
                plan.sample_count,
                plan.feasible_sample_count,
                plan.reason,
            )
            return
        self._published_plan = plan
        self._published_at_s = self._monotonic()
        self._telemetry = MppiControllerTelemetry(
            "PUBLISHED",
            plan.snapshot_id,
            0.0,
            plan.planning_duration_ms,
            plan.sample_count,
            plan.feasible_sample_count,
            None,
        )

    def _submit_if_idle(
        self,
        state: SteeringState,
        corridor: NavCorridor,
        *,
        obstacles: tuple[MppiDynamicObstacle, ...],
        pose_uncertainty_world: float,
    ) -> None:
        if (
            self._future is not None
            or self._closed
            or (
                self._published_plan is not None
                and self._ticks_since_submit < self._replan_interval_ticks
            )
        ):
            return
        self._snapshot_id += 1
        snapshot = MppiPlanningSnapshot(
            snapshot_id=self._snapshot_id,
            state=state,
            corridor=corridor,
            actor_radius_world=self._actor_radius_world,
            pose_uncertainty_world=pose_uncertainty_world,
            obstacles=obstacles,
        )
        self._future = self._executor.submit(self._planner.plan, snapshot)
        self._ticks_since_submit = 0

    def _active_control(
        self,
        state: SteeringState,
        corridor: NavCorridor,
    ) -> tuple[MppiControl, float] | None:
        plan = self._published_plan
        published_at = self._published_at_s
        if plan is None or published_at is None:
            return None
        age = self._monotonic() - published_at
        signature = PathIntegralSteeringPlanner.corridor_signature(corridor)
        if (
            age < 0.0
            or age > self._maximum_plan_age_s
            or signature != plan.corridor_signature
        ):
            self._published_plan = None
            self._published_at_s = None
            self._telemetry = MppiControllerTelemetry(
                "FALLBACK",
                plan.snapshot_id,
                age,
                plan.planning_duration_ms,
                plan.sample_count,
                plan.feasible_sample_count,
                "stale_or_changed_corridor",
            )
            return None
        distances = tuple(
            hypot(state.x - point.x, state.y - point.y) for point in plan.predicted_path
        )
        index = min(range(len(distances)), key=distances.__getitem__)
        deviation = distances[index]
        if deviation > self._maximum_plan_deviation_world:
            self._published_plan = None
            self._published_at_s = None
            self._telemetry = MppiControllerTelemetry(
                "FALLBACK",
                plan.snapshot_id,
                age,
                plan.planning_duration_ms,
                plan.sample_count,
                plan.feasible_sample_count,
                "observed_pose_left_predicted_trajectory",
            )
            return None
        self._telemetry = MppiControllerTelemetry(
            "ACTIVE",
            plan.snapshot_id,
            age,
            plan.planning_duration_ms,
            plan.sample_count,
            plan.feasible_sample_count,
            None,
        )
        return MppiSteeringController._preview_control(plan, index), age

    def _continuous_fallback_intent(
        self,
        baseline: SteeringIntent,
    ) -> SteeringIntent:
        """Keep one reversal history across MPPI/fallback handoffs.

        A temporary missing/stale plan is not a new camera session. Resetting
        the filter there accepted the opposite mouse sign immediately on the
        next frame and produced the visible left/right gait at every rolling
        corridor handoff.
        """

        mouse_delta = self._mouse_filter.apply(
            baseline.mouse_delta_x,
            allow_micro_correction=(
                baseline.cross_track_error_world
                >= PredictiveSteeringController.OFF_CORRIDOR_RECOVERY_START_WORLD
            ),
        )
        self._previous_mouse_delta = mouse_delta
        return replace(baseline, mouse_delta_x=mouse_delta)

    def decide_with_environment(
        self,
        state: SteeringState,
        corridor: NavCorridor,
        *,
        obstacles: tuple[MppiDynamicObstacle, ...] = (),
        pose_uncertainty_world: float = 0.0,
    ) -> SteeringIntent:
        baseline = super().decide(state, corridor)
        with self._lock:
            if self._closed:
                raise RuntimeError("asynchronous PA-MPPI controller is closed")
            self._collect_completed()
            self._ticks_since_submit = min(
                self._replan_interval_ticks,
                self._ticks_since_submit + 1,
            )
            # Partial corridors occur normally at a Detour frontier in live
            # world traversal.  They are valid geometric guidance but not a
            # valid finite-horizon MPPI snapshot.  Fall back without raising;
            # the journey runner will advance/replan the frontier.
            if (
                baseline.state != "FOLLOW"
                or state.heading_rad is None
                or not corridor.complete
            ):
                self._published_plan = None
                self._published_at_s = None
                self._mouse_filter.reset()
                self._telemetry = MppiControllerTelemetry(
                    "FALLBACK",
                    None,
                    None,
                    None,
                    0,
                    0,
                    (
                        "geometric_state:PARTIAL_CORRIDOR"
                        if not corridor.complete
                        else f"geometric_state:{baseline.state}"
                    ),
                )
                return baseline
            self._submit_if_idle(
                state,
                corridor,
                obstacles=obstacles,
                pose_uncertainty_world=pose_uncertainty_world,
            )
            active = self._active_control(state, corridor)
            if active is None:
                return self._continuous_fallback_intent(baseline)
            if baseline.strafe is not None:
                return self._continuous_fallback_intent(baseline)
            control, _ = active
            mouse_delta = self._mouse_filter.apply(
                MppiSteeringController._mouse_delta(control),
                allow_micro_correction=(
                    baseline.cross_track_error_world
                    >= PredictiveSteeringController.OFF_CORRIDOR_RECOVERY_START_WORLD
                ),
            )
            # super().decide() runs as the safe geometric fallback every
            # frame, but its slew state must track the command that was
            # actually sent by MPPI.  Otherwise a corridor hand-off can make
            # MPPI briefly unavailable and expose a large shadow command that
            # was never applied.  That one stale pulse caused the observed
            # wrong-way camera kick, cross-track growth and stationary pivot.
            self._previous_mouse_delta = mouse_delta
            return SteeringIntent(
                state="FOLLOW",
                forward_hold_ms=self.CONTROL_TICK_MS,
                mouse_delta_x=mouse_delta,
                lookahead=baseline.lookahead,
                reason="pa_mppi_async_published_trajectory",
                progress_world=baseline.progress_world,
                cross_track_error_world=baseline.cross_track_error_world,
                projected_z_world=baseline.projected_z_world,
                strafe=baseline.strafe,
            )

    def decide(self, state: SteeringState, corridor: NavCorridor) -> SteeringIntent:
        return self.decide_with_environment(state, corridor)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            future = self._future
            self._future = None
        if future is not None:
            future.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
