from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from math import atan2, ceil, cos, hypot, isfinite, pi, sin
from random import Random

from perfect_assassin.movement.client_navmesh import NavCorridor
from perfect_assassin.movement.predictive_steering import (
    PredictiveSteeringController,
    SteeringState,
)


@dataclass(frozen=True, slots=True)
class SteeringSimulationScenario:
    scenario_id: str
    corridor: NavCorridor
    runs: int = 100
    maximum_observations: int = 1200
    initial_lateral_jitter_world: float = 0.8
    initial_heading_jitter_rad: float = 0.35
    minimum_speed_world_per_s: float = 6.5
    maximum_speed_world_per_s: float = 7.5
    minimum_observation_interval_s: float = 0.065
    maximum_observation_interval_s: float = 0.120
    maximum_allowed_cross_track_world: float = 2.5
    maximum_allowed_pivot_fraction: float = 0.15
    maximum_allowed_steering_sign_changes: int = 4
    static_obstacles: tuple[tuple[float, float, float], ...] = ()
    actor_radius_world: float = 0.75

    def __post_init__(self) -> None:
        if (
            not self.scenario_id.strip()
            or not 100 <= self.runs <= 100_000
            or not 50 <= self.maximum_observations <= 20_000
            or not 0.0 <= self.initial_lateral_jitter_world <= 5.0
            or not 0.0 <= self.initial_heading_jitter_rad <= pi
            or not 0.5 <= self.minimum_speed_world_per_s
            <= self.maximum_speed_world_per_s <= 20.0
            or not 0.01 <= self.minimum_observation_interval_s
            <= self.maximum_observation_interval_s <= 0.5
            or not isfinite(self.maximum_allowed_cross_track_world)
            or not 0.1 <= self.maximum_allowed_cross_track_world <= 10.0
            or not 0.0 <= self.maximum_allowed_pivot_fraction <= 1.0
            or not 0 <= self.maximum_allowed_steering_sign_changes <= 100
            or not 0.1 <= self.actor_radius_world <= 2.0
            or any(
                len(item) != 3
                or not all(isfinite(value) for value in item)
                or item[2] <= 0.0
                or item[2] > 10.0
                for item in self.static_obstacles
            )
        ):
            raise ValueError("steering simulation scenario is invalid")


@dataclass(frozen=True, slots=True)
class SteeringSimulationRun:
    completed: bool
    observations: int
    pivot_observations: int
    steering_sign_changes: int
    maximum_cross_track_world: float
    traveled_world: float
    final_goal_distance_world: float
    terminal_state: str
    minimum_obstacle_clearance_world: float | None
    mppi_active_observations: int
    geometric_fallback_observations: int

    @property
    def pivot_fraction(self) -> float:
        return self.pivot_observations / max(1, self.observations)


@dataclass(frozen=True, slots=True)
class SteeringSimulationObservation:
    index: int
    x: float
    y: float
    heading_rad: float
    controller_state: str
    controller_reason: str
    mouse_delta_x: int
    progress_world: float
    cross_track_world: float
    lookahead_x: float | None
    lookahead_y: float | None


@dataclass(frozen=True, slots=True)
class SteeringSimulationSummary:
    scenario_id: str
    runs: int
    completed_runs: int
    quality_passed_runs: int
    quality_pass_rate: float
    maximum_steering_sign_changes: int
    p95_steering_sign_changes: int
    maximum_pivot_fraction: float
    p95_pivot_fraction: float
    maximum_cross_track_world: float
    p95_cross_track_world: float
    maximum_path_stretch: float
    collision_runs: int
    minimum_obstacle_clearance_world: float | None
    mppi_active_observations: int
    geometric_fallback_observations: int
    mppi_active_fraction: float


def steering_run_passes_quality(
    scenario: SteeringSimulationScenario,
    run: SteeringSimulationRun,
) -> bool:
    """Require both arrival and human-like closed-loop control quality."""

    return (
        run.completed
        and run.maximum_cross_track_world
        <= scenario.maximum_allowed_cross_track_world
        and run.pivot_fraction <= scenario.maximum_allowed_pivot_fraction
        and run.steering_sign_changes
        <= scenario.maximum_allowed_steering_sign_changes
        and run.terminal_state != "COLLISION"
    )


def _p95(values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    return ordered[max(0, ceil(0.95 * len(ordered)) - 1)]


def _initial_path_heading(corridor: NavCorridor) -> float:
    points = corridor.guidance_points()
    for start, stop in pairwise(points):
        if start.distance_2d(stop) > 1.0e-6:
            return PredictiveSteeringController._wrap(
                atan2(stop.y - start.y, stop.x - start.x)
            )
    raise ValueError("steering simulation corridor has no length")


def _corridor_length(corridor: NavCorridor) -> float:
    points = corridor.guidance_points()
    return sum(first.distance_2d(second) for first, second in pairwise(points))


def simulate_steering_run(
    scenario: SteeringSimulationScenario, *, seed: int,
    controller_factory: Callable[[], PredictiveSteeringController] = (
        PredictiveSteeringController
    ),
    observation_sink: Callable[[SteeringSimulationObservation], None] | None = None,
) -> SteeringSimulationRun:
    """Run the production controller through one deterministic kinematic trial.

    This is deliberately not a second steering implementation.  It closes the
    real controller around a small actor model using the same calibrated RMB
    yaw conversion as the Windows input sink.  Randomness changes only initial
    pose, speed and observation cadence and is fully reproducible by ``seed``.
    """

    random = Random(seed)
    corridor = scenario.corridor
    path_heading = _initial_path_heading(corridor)
    lateral = random.uniform(
        -scenario.initial_lateral_jitter_world,
        scenario.initial_lateral_jitter_world,
    )
    x = corridor.start.x - sin(path_heading) * lateral
    y = corridor.start.y + cos(path_heading) * lateral
    heading = PredictiveSteeringController._wrap(
        path_heading + random.uniform(
            -scenario.initial_heading_jitter_rad,
            scenario.initial_heading_jitter_rad,
        )
    )
    speed = random.uniform(
        scenario.minimum_speed_world_per_s,
        scenario.maximum_speed_world_per_s,
    )
    controller = controller_factory()
    if not isinstance(controller, PredictiveSteeringController):
        raise TypeError("controller factory returned an incompatible controller")
    traveled = 0.0
    pivots = 0
    sign_changes = 0
    prior_nonzero_sign = 0
    maximum_cross_track = 0.0
    terminal_state = "LIMIT"
    observations = 0
    minimum_obstacle_clearance: float | None = None
    mppi_active_observations = 0
    geometric_fallback_observations = 0

    for observations in range(1, scenario.maximum_observations + 1):
        intent = controller.decide(
            SteeringState(x, y, heading, speed, 0.0), corridor,
        )
        if observation_sink is not None:
            observation_sink(SteeringSimulationObservation(
                index=observations,
                x=x,
                y=y,
                heading_rad=heading,
                controller_state=intent.state,
                controller_reason=intent.reason,
                mouse_delta_x=intent.mouse_delta_x,
                progress_world=intent.progress_world,
                cross_track_world=intent.cross_track_error_world,
                lookahead_x=None if intent.lookahead is None else intent.lookahead.x,
                lookahead_y=None if intent.lookahead is None else intent.lookahead.y,
            ))
        if intent.reason.startswith("pa_mppi_"):
            mppi_active_observations += 1
        else:
            geometric_fallback_observations += 1
        maximum_cross_track = max(
            maximum_cross_track, intent.cross_track_error_world,
        )
        if intent.state == "ARRIVED":
            terminal_state = intent.state
            break
        if intent.state == "REPLAN":
            terminal_state = intent.state
            break
        if intent.state == "PIVOT":
            pivots += 1
        command_sign = (
            1 if intent.mouse_delta_x > 0
            else -1 if intent.mouse_delta_x < 0
            else 0
        )
        if command_sign:
            if prior_nonzero_sign and command_sign != prior_nonzero_sign:
                sign_changes += 1
            prior_nonzero_sign = command_sign
        interval = random.uniform(
            scenario.minimum_observation_interval_s,
            scenario.maximum_observation_interval_s,
        )
        yaw_rate = (
            -intent.mouse_delta_x
            * PredictiveSteeringController.MOUSE_COMMAND_VELOCITY_SCALE_HZ
            * PredictiveSteeringController.MOUSE_YAW_RAD_PER_PIXEL
        )
        heading = PredictiveSteeringController._wrap(
            heading + yaw_rate * interval,
        )
        if intent.forward_hold_ms > 0:
            displacement = speed * interval
            forward_x, forward_y = cos(heading), sin(heading)
            lateral_sign = (
                1.0 if intent.strafe == "STRAFE_RIGHT"
                else -1.0 if intent.strafe == "STRAFE_LEFT"
                else 0.0
            )
            if lateral_sign:
                # WoW normalizes diagonal movement; strafe right is the
                # heading's clockwise perpendicular.
                normalization = 2.0 ** -0.5
                move_x = (
                    forward_x + lateral_sign * sin(heading)
                ) * normalization
                move_y = (
                    forward_y - lateral_sign * cos(heading)
                ) * normalization
            else:
                move_x, move_y = forward_x, forward_y
            next_x = x + move_x * displacement
            next_y = y + move_y * displacement
            for obstacle_x, obstacle_y, obstacle_radius in scenario.static_obstacles:
                clearance = (
                    hypot(next_x - obstacle_x, next_y - obstacle_y)
                    - obstacle_radius
                    - scenario.actor_radius_world
                )
                minimum_obstacle_clearance = (
                    clearance
                    if minimum_obstacle_clearance is None
                    else min(minimum_obstacle_clearance, clearance)
                )
                if clearance <= 0.0:
                    terminal_state = "COLLISION"
                    break
            if terminal_state == "COLLISION":
                break
            x, y = next_x, next_y
            traveled += displacement

    final_distance = hypot(corridor.stop.x - x, corridor.stop.y - y)
    completed = terminal_state == "ARRIVED"
    return SteeringSimulationRun(
        completed=completed,
        observations=observations,
        pivot_observations=pivots,
        steering_sign_changes=sign_changes,
        maximum_cross_track_world=maximum_cross_track,
        traveled_world=traveled,
        final_goal_distance_world=final_distance,
        terminal_state=terminal_state,
        minimum_obstacle_clearance_world=minimum_obstacle_clearance,
        mppi_active_observations=mppi_active_observations,
        geometric_fallback_observations=geometric_fallback_observations,
    )


def simulate_steering_batch(
    scenario: SteeringSimulationScenario, *, seed_offset: int = 0,
    controller_factory: Callable[[], PredictiveSteeringController] = (
        PredictiveSteeringController
    ),
) -> tuple[SteeringSimulationSummary, tuple[SteeringSimulationRun, ...]]:
    runs = tuple(
        simulate_steering_run(
            scenario,
            seed=seed_offset + index,
            controller_factory=controller_factory,
        )
        for index in range(scenario.runs)
    )
    corridor_length = _corridor_length(scenario.corridor)
    quality_passed_runs = sum(
        steering_run_passes_quality(scenario, item) for item in runs
    )
    mppi_active_observations = sum(
        item.mppi_active_observations for item in runs
    )
    geometric_fallback_observations = sum(
        item.geometric_fallback_observations for item in runs
    )
    return SteeringSimulationSummary(
        scenario_id=scenario.scenario_id,
        runs=len(runs),
        completed_runs=sum(item.completed for item in runs),
        quality_passed_runs=quality_passed_runs,
        quality_pass_rate=quality_passed_runs / len(runs),
        maximum_steering_sign_changes=max(
            item.steering_sign_changes for item in runs
        ),
        p95_steering_sign_changes=int(_p95(tuple(
            float(item.steering_sign_changes) for item in runs
        ))),
        maximum_pivot_fraction=max(
            item.pivot_fraction for item in runs
        ),
        p95_pivot_fraction=_p95(tuple(item.pivot_fraction for item in runs)),
        maximum_cross_track_world=max(
            item.maximum_cross_track_world for item in runs
        ),
        p95_cross_track_world=_p95(tuple(
            item.maximum_cross_track_world for item in runs
        )),
        maximum_path_stretch=max(
            item.traveled_world / corridor_length for item in runs
        ),
        collision_runs=sum(
            item.terminal_state == "COLLISION" for item in runs
        ),
        minimum_obstacle_clearance_world=(
            min(
                item.minimum_obstacle_clearance_world
                for item in runs
                if item.minimum_obstacle_clearance_world is not None
            )
            if any(
                item.minimum_obstacle_clearance_world is not None
                for item in runs
            )
            else None
        ),
        mppi_active_observations=mppi_active_observations,
        geometric_fallback_observations=geometric_fallback_observations,
        mppi_active_fraction=(
            mppi_active_observations
            / max(
                1,
                mppi_active_observations + geometric_fallback_observations,
            )
        ),
    ), runs
