from __future__ import annotations

from math import hypot
from typing import Callable

from perfect_assassin.domain.combat import CombatObservationState, TargetBearingState
from perfect_assassin.domain.motion import ContinuousMotionFrame
from perfect_assassin.movement.client_navmesh import NavCorridor
from perfect_assassin.movement.combat_motion import CombatMotionIntent
from perfect_assassin.movement.predictive_steering import (
    PredictiveSteeringController,
    SteeringState,
)


MINIMUM_RETREAT_DEADLINE_S = 18.0
MAXIMUM_RETREAT_DEADLINE_S = 90.0
RETREAT_TURN_AND_CAPTURE_ALLOWANCE_S = 8.0
MINIMUM_SUSTAINED_RETREAT_SPEED_YPS = 4.0


def safe_retreat_deadline_seconds(corridor: NavCorridor) -> float:
    """Bound retreat time from verified path length, never map identity."""

    distance_yards = sum(
        hypot(right.x - left.x, right.y - left.y)
        for left, right in zip(corridor.points, corridor.points[1:])
    )
    return min(
        MAXIMUM_RETREAT_DEADLINE_S,
        max(
            MINIMUM_RETREAT_DEADLINE_S,
            RETREAT_TURN_AND_CAPTURE_ALLOWANCE_S
            + distance_yards / MINIMUM_SUSTAINED_RETREAT_SPEED_YPS,
        ),
    )


class BreadcrumbCombatRetreatController:
    """Follow a freshly traversed corridor backwards under combat authority."""

    def __init__(
        self,
        *,
        corridor: NavCorridor,
        pose_source: Callable[[], tuple[float, float, float | None]],
    ) -> None:
        if corridor.source != "fresh_client_visible_reverse_breadcrumbs":
            raise ValueError("combat retreat requires verified reverse breadcrumbs")
        self._corridor = corridor
        self._pose_source = pose_source
        self._steering = PredictiveSteeringController(arrival_radius_world=1.25)
        self._last_pose: tuple[float, float] | None = None
        self._last_observed_s: float | None = None
        self._no_progress_s = 0.0
        self._terminal_state: str | None = None

    @property
    def terminal_state(self) -> str | None:
        return self._terminal_state

    def reset(self) -> None:
        self._last_pose = None
        self._last_observed_s = None
        self._no_progress_s = 0.0
        self._terminal_state = None

    def decide(
        self,
        observation: CombatObservationState,
        bearing: TargetBearingState | None,
    ) -> CombatMotionIntent:
        del bearing
        if not observation.player_alive:
            raise RuntimeError("safe retreat stopped because Predator is dead")
        x, y, heading = self._pose_source()
        if heading is None:
            raise RuntimeError("safe retreat has no fresh client-visible heading")
        if self._last_pose is not None and self._last_observed_s is not None:
            dt_s = max(0.0, observation.observed_monotonic_s - self._last_observed_s)
            moved = hypot(x - self._last_pose[0], y - self._last_pose[1])
            self._no_progress_s = 0.0 if moved >= 0.20 else self._no_progress_s + dt_s
        self._last_pose = (x, y)
        self._last_observed_s = observation.observed_monotonic_s
        if not observation.in_combat:
            self._terminal_state = "ESCAPED"
            return CombatMotionIntent(
                frame=ContinuousMotionFrame(observation.observed_monotonic_s),
                state="ESCAPED",
                aligned=True,
                target_identity_crc16=(
                    None if observation.target is None else observation.target.identity_crc16
                ),
                reason="fresh_hud_confirms_out_of_combat",
            )
        intent = self._steering.decide(
            SteeringState(x, y, heading, 7.0, self._no_progress_s),
            self._corridor,
        )
        if intent.state == "REPLAN":
            raise RuntimeError(f"safe retreat corridor failed: {intent.reason}")
        if intent.state == "ARRIVED":
            self._terminal_state = "CORRIDOR_EXHAUSTED_IN_COMBAT"
            return CombatMotionIntent(
                frame=ContinuousMotionFrame(observation.observed_monotonic_s),
                state=self._terminal_state,
                aligned=True,
                target_identity_crc16=(
                    None if observation.target is None else observation.target.identity_crc16
                ),
                reason="verified_retreat_corridor_exhausted_while_still_in_combat",
            )
        return CombatMotionIntent(
            frame=ContinuousMotionFrame(
                observed_monotonic_s=observation.observed_monotonic_s,
                movement="MOVE_FORWARD" if intent.forward_hold_ms else None,
                mouse_look=True,
                mouse_velocity_x_px_s=float(
                    intent.mouse_delta_x
                    * PredictiveSteeringController.MOUSE_COMMAND_VELOCITY_SCALE_HZ
                ),
                reason="follow_verified_reverse_breadcrumb_corridor",
            ),
            state=f"RETREAT_{intent.state}",
            aligned=intent.forward_hold_ms > 0,
            target_identity_crc16=(
                None if observation.target is None else observation.target.identity_crc16
            ),
            reason="risk_reducing_backtrack_over_freshly_traversed_corridor",
        )
