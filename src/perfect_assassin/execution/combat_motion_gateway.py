from __future__ import annotations

from typing import Any, Protocol

from perfect_assassin.domain.combat import CombatObservationState, TargetBearingState
from perfect_assassin.execution.ports import CooperativeCancellation
from perfect_assassin.execution.windows_continuous_motion import WindowsContinuousMotionSession


class CombatMotionController(Protocol):
    def decide(
        self,
        observation: CombatObservationState,
        bearing: TargetBearingState | None,
    ): ...

    def reset(self) -> None: ...


class CombatMotionGateway:
    """Binds pure combat motion to one exact continuous input session."""

    def __init__(
        self,
        *,
        controller: CombatMotionController,
        session: WindowsContinuousMotionSession,
        tether_source=None,
    ) -> None:
        self._controller = controller
        self._session = session
        self._tether_source = tether_source
        self._cancellation = CooperativeCancellation()
        self._closed = False

    def update(
        self,
        observation: CombatObservationState,
        bearing: TargetBearingState | None,
    ) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("combat motion gateway is closed")
        setter = getattr(self._controller, "set_tether_guidance", None)
        tether_intent = None
        if setter is not None:
            tether_intent = (
                None
                if self._tether_source is None
                else self._tether_source(observation, bearing)
            )
            setter(tether_intent)
        intent = self._controller.decide(observation, bearing)
        receipt = self._session.apply_frame(intent.frame, self._cancellation)
        return {
            "record_type": "continuous_combat_motion",
            "schema_version": "0.1",
            "observation_id": observation.observation_id,
            "target_identity_crc16": intent.target_identity_crc16,
            "state": intent.state,
            "aligned": intent.aligned,
            "bearing_tracking_state": (
                None if bearing is None else bearing.tracking_state
            ),
            "bearing_direction": None if bearing is None else bearing.direction,
            "bearing_offset_x_normalized": (
                None if bearing is None else bearing.offset_x_normalized
            ),
            "observed_monotonic_s": observation.observed_monotonic_s,
            "held_controls": list(receipt.held_controls),
            "mouse_look_held": receipt.mouse_look_held,
            "input_state_changed": receipt.state_changed,
            "mouse_delta_x": receipt.mouse_delta_x,
            "mouse_delta_y": receipt.mouse_delta_y,
            "mouse_velocity_x_px_s": receipt.mouse_velocity_x_px_s,
            "mouse_velocity_y_px_s": receipt.mouse_velocity_y_px_s,
            "lease_deadline_monotonic_ms": receipt.lease_deadline_monotonic_ms,
            "tether_state": (
                None if tether_intent is None else tether_intent.state
            ),
            "tether_reason": (
                None if tether_intent is None else tether_intent.reason
            ),
            "tether_corridor_edge_clearance_world": (
                None
                if tether_intent is None
                else tether_intent.corridor_edge_clearance_world
            ),
            "tether_corridor_edge_safe": (
                None
                if tether_intent is None
                else tether_intent.corridor_edge_safe
            ),
            "reason": intent.reason,
            "execution_authority": False,
        }

    def cancel_for_manual_takeover(self) -> None:
        self._cancellation.cancel()
        self._session.release_all()

    def release(self) -> None:
        self._session.release_all()
        self._controller.reset()

    def replace_controller(self, controller: CombatMotionController) -> None:
        """Switch motion policy only after atomically releasing held input."""

        if self._closed:
            raise RuntimeError("combat motion gateway is closed")
        self._session.release_all()
        self._controller.reset()
        self._controller = controller

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancellation.cancel()
        self._session.close()
