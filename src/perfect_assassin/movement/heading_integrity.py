"""Fail-closed policy for fresh, client-visible navigation heading evidence.

The movement controller may predict camera yaw between observations, but a
missing minimap/HUD facing signal must never become an unlimited permission to
keep walking.  This module is client-neutral: it consumes only the versioned
heading labels and timestamps supplied by an adapter and returns a proposal.
It does not read a client, know a map, or grant execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


EXACT_CLIENT_FACING_SOURCE = "COORDINATE_HUD_EXACT"
MINIMAP_CLIENT_FACING_SOURCE = "MINIMAP_VISION_FALLBACK"
KNOWN_CLIENT_FACING_SOURCES = frozenset(
    {EXACT_CLIENT_FACING_SOURCE, MINIMAP_CLIENT_FACING_SOURCE}
)

# Six 20 Hz observations is a deliberately short bridge for one missed
# capture.  It is below the 450 ms input watchdog and cannot turn a stale
# heading into a long autonomous stride.
MAX_HEADING_EVIDENCE_AGE_S = 0.30

_EXACT_HEADING_SOURCES = frozenset({EXACT_CLIENT_FACING_SOURCE})
_MINIMAP_HEADING_SOURCES = frozenset(
    {
        "VISIBLE_CLIENT_HEADING_INITIAL",
        "VISIBLE_CLIENT_HEADING_FUSED",
        "VISIBLE_CLIENT_HEADING_AXIAL_FLIP_FUSED",
        "DISPLACEMENT_VISIBLE_HEADING_FUSED",
        "DISPLACEMENT_VISIBLE_HEADING_AXIAL_FLIP_FUSED",
        "MINIMAP_AXIS_FLIP_ORIENTED_TO_CORRIDOR",
    }
)


@dataclass(frozen=True, slots=True)
class HeadingIntegrityDecision:
    """Whether one control frame has enough recent visual heading evidence."""

    allow_control: bool
    state: str
    client_facing_source: str
    heading_source: str
    evidence_age_s: float | None
    reason: str

    def __post_init__(self) -> None:
        if type(self.allow_control) is not bool:
            raise ValueError("heading integrity allow_control must be boolean")
        if self.state not in {"VISIBLE", "HELD", "MISSING", "STALE", "INVALID"}:
            raise ValueError("heading integrity state is invalid")
        if not isinstance(self.client_facing_source, str):
            raise ValueError("heading integrity client source is invalid")
        if not isinstance(self.heading_source, str):
            raise ValueError("heading integrity heading source is invalid")
        if self.evidence_age_s is not None and (
            not isfinite(self.evidence_age_s) or self.evidence_age_s < 0.0
        ):
            raise ValueError("heading integrity evidence age is invalid")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("heading integrity reason is invalid")


def assess_heading_integrity(
    *,
    heading_rad: float | None,
    heading_source: str | None,
    client_facing_source: str | None,
    observed_monotonic_s: float,
    last_visible_observed_s: float | None,
    maximum_evidence_age_s: float = MAX_HEADING_EVIDENCE_AGE_S,
) -> HeadingIntegrityDecision:
    """Check whether the current heading may authorize another control frame.

    A current exact HUD value or a current minimap value fused by
    ``VisibleHeadingObserver`` is ``VISIBLE``.  If the current frame has no
    facing value, a previously visible value may be held only within the
    bounded age.  The held value is a safety bridge, not a new observation.
    """

    source = _text(client_facing_source)
    computed_source = _text(heading_source)
    if (
        not _finite_nonnegative(observed_monotonic_s)
        or not _finite_nonnegative(maximum_evidence_age_s)
        or maximum_evidence_age_s > 2.0
    ):
        return _decision(
            allow=False,
            state="INVALID",
            source=source,
            computed_source=computed_source,
            age=None,
            reason="heading_integrity_clock_or_bound_invalid",
        )
    if heading_rad is None or not _finite_number(heading_rad):
        return _decision(
            allow=False,
            state="INVALID",
            source=source,
            computed_source=computed_source,
            age=None,
            reason="heading_integrity_heading_missing_or_non_finite",
        )

    current_visual = _source_pair_is_current_visual(
        source=source,
        computed_source=computed_source,
    )
    if current_visual:
        return _decision(
            allow=True,
            state="VISIBLE",
            source=source,
            computed_source=computed_source,
            age=0.0,
            reason="current_client_facing_heading_is_visible_and_bounded",
        )

    if last_visible_observed_s is None or not _finite_nonnegative(
        last_visible_observed_s
    ):
        return _decision(
            allow=False,
            state="MISSING",
            source=source,
            computed_source=computed_source,
            age=None,
            reason="no_prior_visible_heading_to_hold",
        )
    age = float(observed_monotonic_s) - float(last_visible_observed_s)
    if not isfinite(age) or age < 0.0:
        return _decision(
            allow=False,
            state="INVALID",
            source=source,
            computed_source=computed_source,
            age=None,
            reason="heading_integrity_observation_time_reversed",
        )
    if age <= float(maximum_evidence_age_s):
        return _decision(
            allow=True,
            state="HELD",
            source=source,
            computed_source=computed_source,
            age=age,
            reason="current_facing_missing_but_previous_visual_heading_is_fresh",
        )
    return _decision(
        allow=False,
        state="STALE",
        source=source,
        computed_source=computed_source,
        age=age,
        reason="previous_visual_heading_exceeded_bounded_age",
    )


def is_current_visual_heading(
    *, heading_source: str | None, client_facing_source: str | None
) -> bool:
    """Return whether a heading result is backed by the current client frame."""

    return (
        _source_pair_is_current_visual(
            source=_text(client_facing_source),
            computed_source=_text(heading_source),
        )
    )


def _source_pair_is_current_visual(*, source: str, computed_source: str) -> bool:
    """Require the computed heading label to match its raw client source."""

    if source == EXACT_CLIENT_FACING_SOURCE:
        return computed_source in _EXACT_HEADING_SOURCES
    if source == MINIMAP_CLIENT_FACING_SOURCE:
        return computed_source in _MINIMAP_HEADING_SOURCES
    return False


def _decision(
    *,
    allow: bool,
    state: str,
    source: str,
    computed_source: str,
    age: float | None,
    reason: str,
) -> HeadingIntegrityDecision:
    return HeadingIntegrityDecision(
        allow_control=allow,
        state=state,
        client_facing_source=source,
        heading_source=computed_source,
        evidence_age_s=None if age is None else float(age),
        reason=reason,
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else "UNAVAILABLE"


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _finite_nonnegative(value: object) -> bool:
    return _finite_number(value) and float(value) >= 0.0


__all__ = [
    "EXACT_CLIENT_FACING_SOURCE",
    "HeadingIntegrityDecision",
    "KNOWN_CLIENT_FACING_SOURCES",
    "MAX_HEADING_EVIDENCE_AGE_S",
    "MINIMAP_CLIENT_FACING_SOURCE",
    "assess_heading_integrity",
    "is_current_visual_heading",
]
