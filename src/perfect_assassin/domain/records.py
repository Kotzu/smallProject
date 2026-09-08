from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RawFact:
    raw_key: str
    value: Any
    source: str
    capability: str
    confidence: float
    observed_at: str
    expires_at: str | None = None
    restriction_evidence: str | None = None


@dataclass(frozen=True, slots=True)
class RawEvent:
    raw_event_id: str
    kind: str
    game_time_ms: int
    captured_at: str
    facts: tuple[RawFact, ...]


def fact_value(record: dict[str, Any], key: str, default: Any = None) -> Any:
    for fact in record.get("facts", []):
        if fact["key"] == key:
            return fact["value"]
    return default


def apply_observation_to_state(
    state: dict[str, dict[str, Any]], record: dict[str, Any]
) -> None:
    """Apply one observation while invalidating facts made stale by terminal state."""
    facts = record.get("facts", [])
    for fact in facts:
        state[fact["key"]] = fact
    if any(fact["key"] == "target.dead" and fact["value"] is True for fact in facts):
        # The client did not necessarily expose a final zero-health UNIT_HEALTH
        # event. Preserve telemetry, but do not present pre-death health as current.
        state.pop("target.health_pct", None)
