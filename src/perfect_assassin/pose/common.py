from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any, Sequence


class PoseFusionError(ValueError):
    """Raised when pose evidence cannot be fused without inventing state."""


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise PoseFusionError(f"Invalid timestamp: {value!r}") from error
    if parsed.tzinfo is None:
        raise PoseFusionError(f"Timestamp must include a timezone: {value!r}")
    return parsed


def freshness(
    observed_at: str,
    published_at: str,
    stale_after_ms: float,
) -> dict[str, Any]:
    observed = parse_timestamp(observed_at)
    published = parse_timestamp(published_at)
    age_ms = (published - observed).total_seconds() * 1000.0
    if age_ms < 0:
        raise PoseFusionError("published_at cannot precede observed_at")
    if not isfinite(stale_after_ms) or stale_after_ms <= 0:
        raise PoseFusionError("stale_after_ms must be finite and positive")
    if age_ms <= stale_after_ms:
        status = "FRESH"
    elif age_ms <= stale_after_ms * 4:
        status = "STALE"
    else:
        status = "EXPIRED"
    return {
        "observed_at": observed_at,
        "published_at": published_at,
        "age_ms": age_ms,
        "stale_after_ms": stale_after_ms,
        "status": status,
    }


def diagonal_covariance(
    ordering: Sequence[str], diagonal: Sequence[float]
) -> dict[str, Any]:
    if len(ordering) != 4 or len(diagonal) != 4:
        raise PoseFusionError("Pose covariance v0.1 must have four dimensions")
    matrix = [0.0] * 16
    for index, value in enumerate(diagonal):
        if not isfinite(value) or value <= 0:
            raise PoseFusionError("Covariance diagonal must be finite and positive")
        matrix[index * 4 + index] = value
    return {
        "dimension": 4,
        "ordering": list(ordering),
        "matrix_row_major": matrix,
    }
