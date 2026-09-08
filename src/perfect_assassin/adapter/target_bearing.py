from __future__ import annotations

import math
from typing import Any

from perfect_assassin.domain.combat import TARGET_BEARING_CENTER_TOLERANCE


class SelectedTargetBearingError(ValueError):
    pass


def validate_selected_target_bearing_semantics(record: dict[str, Any]) -> None:
    if record.get("execution_authority") is not False:
        raise SelectedTargetBearingError(
            "bearing observation cannot carry execution authority"
        )
    timing = record.get("timing")
    if type(timing) is not dict:
        raise SelectedTargetBearingError("bearing timing is missing")
    values = tuple(
        timing.get(name)
        for name in (
            "monotonic_timestamp_s",
            "frame_age_ms",
            "observed_monotonic_s",
            "age_at_observation_ms",
            "expires_monotonic_s",
        )
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in values
    ):
        raise SelectedTargetBearingError("bearing timing is non-finite")
    captured, frame_age, observed, observed_age, expires = map(float, values)
    if (
        observed < captured
        or observed_age + 1e-6 < frame_age
        or expires < observed
        or expires - captured > 0.450001
    ):
        raise SelectedTargetBearingError("bearing timing is inconsistent")
    visible = record.get("tracking_state") == "VISIBLE"
    visual_fields = (
        record.get("detection_method"),
        record.get("direction"),
        record.get("offset_x_normalized"),
        record.get("center_x_px"),
        record.get("center_y_px"),
    )
    if visible:
        if any(value is None for value in visual_fields):
            raise SelectedTargetBearingError("visible bearing is incomplete")
        offset = record["offset_x_normalized"]
        if (
            isinstance(offset, bool)
            or not isinstance(offset, (int, float))
            or not math.isfinite(offset)
        ):
            raise SelectedTargetBearingError("bearing offset is invalid")
        tolerance = TARGET_BEARING_CENTER_TOLERANCE
        expected = (
            "LEFT"
            if offset < -tolerance
            else "RIGHT"
            if offset > tolerance
            else "CENTER"
        )
        if record.get("direction") != expected:
            raise SelectedTargetBearingError("bearing direction and offset diverge")
        if record.get("target_identity_crc16") is None:
            raise SelectedTargetBearingError(
                "visible bearing lacks target continuity"
            )
        center_y = record["center_y_px"]
        frame_height = record["frame_height_px"]
        if (
            isinstance(center_y, bool)
            or not isinstance(center_y, (int, float))
            or not math.isfinite(center_y)
            or isinstance(frame_height, bool)
            or not isinstance(frame_height, (int, float))
            or not math.isfinite(frame_height)
            or frame_height <= 0
            or not 0 <= center_y <= frame_height
        ):
            raise SelectedTargetBearingError("bearing vertical geometry is invalid")
    elif any(value is not None for value in visual_fields) or record.get("confidence") != 0:
        raise SelectedTargetBearingError(
            "non-visible bearing contains visual facts"
        )
