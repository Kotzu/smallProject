from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

import numpy as np


class VisibleClientState(str, Enum):
    IN_WORLD = "IN_WORLD"
    DEAD_IN_WORLD = "DEAD_IN_WORLD"
    GHOST_IN_WORLD = "GHOST_IN_WORLD"
    DISCONNECTED_DIALOG = "DISCONNECTED_DIALOG"
    LOGIN_SCREEN = "LOGIN_SCREEN"
    CHARACTER_SELECT = "CHARACTER_SELECT"
    UNKNOWN = "UNKNOWN"


class ContinuityAction(str, Enum):
    RESUME_NAVIGATION = "RESUME_NAVIGATION"
    ACKNOWLEDGE_DISCONNECT = "ACKNOWLEDGE_DISCONNECT"
    LOGIN = "LOGIN"
    ENTER_WORLD = "ENTER_WORLD"
    RELEASE_SPIRIT = "RELEASE_SPIRIT"
    RECOVER_CORPSE = "RECOVER_CORPSE"
    WAIT_FOR_STABLE_FRAME = "WAIT_FOR_STABLE_FRAME"
    STOP_FAIL_CLOSED = "STOP_FAIL_CLOSED"


@dataclass(frozen=True, slots=True)
class VisibleClientStateObservation:
    state: VisibleClientState
    confidence: float
    evidence: dict[str, float | bool]
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("visible client state confidence is invalid")
        if self.execution_authority:
            raise ValueError("visible client state cannot grant execution authority")


def _roi_fraction(mask: np.ndarray, bounds: tuple[float, float, float, float]) -> float:
    height, width = mask.shape
    left, top, right, bottom = bounds
    x0 = max(0, min(width - 1, int(round(left * width))))
    x1 = max(x0 + 1, min(width, int(round(right * width))))
    y0 = max(0, min(height - 1, int(round(top * height))))
    y1 = max(y0 + 1, min(height, int(round(bottom * height))))
    return float(mask[y0:y1, x0:x1].mean())


def classify_visible_client_state(
    frame_bgra: np.ndarray,
    *,
    coordinate_hud_valid: bool,
    player_alive: bool | None,
    player_ghost: bool | None = None,
) -> VisibleClientStateObservation:
    """Classify only UI states that have distinct visible evidence.

    In-world evidence is supplied by the CRC-validated addon HUD.  Login-flow
    states use broad normalized button regions, so the classifier is
    resolution-independent and does not depend on OCR, window titles, memory,
    or a specific private-server implementation.
    """

    if (
        not isinstance(frame_bgra, np.ndarray)
        or frame_bgra.dtype != np.uint8
        or frame_bgra.ndim != 3
        or frame_bgra.shape[2] != 4
        or frame_bgra.shape[0] < 240
        or frame_bgra.shape[1] < 320
    ):
        raise ValueError("visible client state frame must be BGRA8")
    if coordinate_hud_valid:
        if player_alive is False:
            state = (
                VisibleClientState.GHOST_IN_WORLD
                if player_ghost is True
                else VisibleClientState.DEAD_IN_WORLD
            )
        else:
            state = VisibleClientState.IN_WORLD
        return VisibleClientStateObservation(
            state=state,
            confidence=1.0,
            evidence={
                "coordinate_hud_crc_valid": True,
                "player_alive_observed": player_alive is not None,
                "player_ghost_observed": player_ghost is not None,
                "player_ghost": player_ghost is True,
            },
        )

    # TBC's buttons use a dark red fill.  Require red dominance rather than a
    # single RGB value so animation, gamma, antialiasing, and UI scale do not
    # change the state decision.
    blue = frame_bgra[:, :, 0].astype(np.int16)
    green = frame_bgra[:, :, 1].astype(np.int16)
    red = frame_bgra[:, :, 2].astype(np.int16)
    red_button = (
        (red >= 55)
        & (red - green >= 28)
        & (red - blue >= 20)
        & (green <= 115)
    )
    dialog_fraction = _roi_fraction(red_button, (0.36, 0.45, 0.64, 0.58))
    login_fraction = _roi_fraction(red_button, (0.39, 0.64, 0.61, 0.75))
    enter_world_fraction = _roi_fraction(red_button, (0.37, 0.84, 0.63, 0.96))
    evidence: dict[str, float | bool] = {
        "coordinate_hud_crc_valid": False,
        "dialog_red_fraction": dialog_fraction,
        "login_red_fraction": login_fraction,
        "enter_world_red_fraction": enter_world_fraction,
    }
    threshold = 0.025
    if dialog_fraction >= threshold and login_fraction >= threshold:
        state = VisibleClientState.DISCONNECTED_DIALOG
        signal = min(dialog_fraction, login_fraction)
    elif enter_world_fraction >= threshold and login_fraction < threshold:
        state = VisibleClientState.CHARACTER_SELECT
        signal = enter_world_fraction
    elif login_fraction >= threshold:
        state = VisibleClientState.LOGIN_SCREEN
        signal = login_fraction
    else:
        state = VisibleClientState.UNKNOWN
        signal = max(dialog_fraction, login_fraction, enter_world_fraction)
    confidence = 0.0 if state is VisibleClientState.UNKNOWN else min(1.0, signal / 0.12)
    return VisibleClientStateObservation(
        state=state,
        confidence=confidence,
        evidence=evidence,
    )


@dataclass(frozen=True, slots=True)
class ContinuityPolicy:
    minimum_confidence: float = 0.55
    maximum_recovery_actions: int = 8

    def __post_init__(self) -> None:
        if not 0.5 <= self.minimum_confidence <= 1.0:
            raise ValueError("continuity confidence threshold is invalid")
        if not 1 <= self.maximum_recovery_actions <= 32:
            raise ValueError("continuity recovery bound is invalid")

    def decide(
        self,
        observation: VisibleClientStateObservation,
        *,
        recovery_actions_used: int,
    ) -> ContinuityAction:
        if recovery_actions_used < 0:
            raise ValueError("continuity recovery count is invalid")
        if recovery_actions_used >= self.maximum_recovery_actions:
            return ContinuityAction.STOP_FAIL_CLOSED
        if observation.confidence < self.minimum_confidence:
            return ContinuityAction.WAIT_FOR_STABLE_FRAME
        return {
            VisibleClientState.IN_WORLD: ContinuityAction.RESUME_NAVIGATION,
            VisibleClientState.DEAD_IN_WORLD: ContinuityAction.RELEASE_SPIRIT,
            VisibleClientState.GHOST_IN_WORLD: ContinuityAction.RECOVER_CORPSE,
            VisibleClientState.DISCONNECTED_DIALOG:
                ContinuityAction.ACKNOWLEDGE_DISCONNECT,
            VisibleClientState.LOGIN_SCREEN: ContinuityAction.LOGIN,
            VisibleClientState.CHARACTER_SELECT: ContinuityAction.ENTER_WORLD,
            VisibleClientState.UNKNOWN: ContinuityAction.WAIT_FOR_STABLE_FRAME,
        }[observation.state]


def observation_to_record(
    observation: VisibleClientStateObservation,
) -> dict[str, Any]:
    return {
        "record_type": "visible_client_state_observation",
        "schema_version": "1.0",
        "state": observation.state.value,
        "confidence": observation.confidence,
        "evidence": dict(observation.evidence),
        "execution_authority": False,
    }
