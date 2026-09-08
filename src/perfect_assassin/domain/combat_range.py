from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Mapping


class RangeBand(str, Enum):
    """Target position relative to one ability's legal casting envelope."""

    TOO_CLOSE = "TOO_CLOSE"
    IN_RANGE = "IN_RANGE"
    TOO_FAR = "TOO_FAR"
    OUTSIDE_UNKNOWN = "OUTSIDE_UNKNOWN"
    UNKNOWN = "UNKNOWN"


class MeleeRangeRelation(str, Enum):
    """Fused selected-target relation to the reviewed Rogue melee envelope."""

    IN_RANGE_0_TO_5 = "IN_RANGE_0_TO_5"
    TOO_FAR_OVER_5 = "TOO_FAR_OVER_5"
    INCONSISTENT = "INCONSISTENT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SpellRangeEnvelope:
    ability_id: str
    min_yards: float
    max_yards: float

    def __post_init__(self) -> None:
        if not self.ability_id or len(self.ability_id) > 96:
            raise ValueError("ability id is invalid")
        if (
            not isfinite(self.min_yards)
            or not isfinite(self.max_yards)
            or self.min_yards < 0
            or self.max_yards <= self.min_yards
            or self.max_yards > 100
        ):
            raise ValueError("spell range envelope is invalid")

    def classify(
        self,
        *,
        client_in_range: bool | None,
        distance_yards: float | None = None,
    ) -> RangeBand:
        """Fuse exact client range truth with an optional portable distance estimate.

        The client witness is authoritative for whether a cast may be attempted.
        A distance estimate only explains *which side* of the envelope the target
        occupies; it never turns a client rejection into permission to cast.
        """

        if client_in_range is not None and type(client_in_range) is not bool:
            raise ValueError("client range witness must be boolean or null")
        if distance_yards is not None and (
            not isfinite(distance_yards) or distance_yards < 0 or distance_yards > 500
        ):
            raise ValueError("target distance estimate is invalid")

        if client_in_range is True:
            return RangeBand.IN_RANGE
        if distance_yards is not None:
            if distance_yards < self.min_yards:
                return RangeBand.TOO_CLOSE
            if distance_yards > self.max_yards:
                return RangeBand.TOO_FAR
            # A disagreement is fail-closed: the client owns cast permission.
            return RangeBand.OUTSIDE_UNKNOWN
        if client_in_range is False:
            # Zero-minimum abilities have only one possible outside direction.
            return (
                RangeBand.TOO_FAR
                if self.min_yards == 0
                else RangeBand.OUTSIDE_UNKNOWN
            )
        return RangeBand.UNKNOWN


ROGUE_MELEE_RANGE = SpellRangeEnvelope(
    ability_id="rogue.melee",
    min_yards=0.0,
    max_yards=5.0,
)


# Range is an ability fact, not a property of an action-bar slot.  Keeping the
# envelopes keyed by semantic ability id lets later profiles bind the same
# spell to any bar/page without silently changing its movement contract.
ROGUE_ABILITY_RANGE_ENVELOPES: Mapping[str, SpellRangeEnvelope] = MappingProxyType(
    {
        "rogue.auto_attack": SpellRangeEnvelope(
            ability_id="rogue.auto_attack",
            min_yards=0.0,
            max_yards=5.0,
        ),
        "rogue.sinister_strike": SpellRangeEnvelope(
            ability_id="rogue.sinister_strike",
            min_yards=0.0,
            max_yards=5.0,
        ),
        "rogue.eviscerate": SpellRangeEnvelope(
            ability_id="rogue.eviscerate",
            min_yards=0.0,
            max_yards=5.0,
        ),
    }
)


def rogue_ability_range(ability_id: str) -> SpellRangeEnvelope:
    """Return the reviewed range contract for one semantic Rogue ability.

    Unknown abilities fail closed.  A newly learned spell therefore cannot be
    pressed until its own minimum/maximum range has been added and tested.
    """

    try:
        return ROGUE_ABILITY_RANGE_ENVELOPES[ability_id]
    except KeyError as exc:
        raise ValueError("rogue ability range is not reviewed") from exc


def selected_target_melee_range_awareness(
    *,
    target_identity_crc16: int,
    observed_monotonic_s: float,
    expires_monotonic_s: float,
    ability_witnesses: Mapping[str, bool | None],
) -> dict[str, object]:
    """Build read-only range evidence without pretending an exact distance.

    TBC's action-range API supplies a tri-state witness per reviewed ability,
    not a yard measurement.  Equal melee envelopes can therefore prove only
    ``0..5 yd``, ``over 5 yd``, inconsistency, or unknown.
    """

    if (
        type(target_identity_crc16) is not int
        or not 1 <= target_identity_crc16 <= 65_535
    ):
        raise ValueError("target identity fingerprint is invalid")
    if (
        not isfinite(observed_monotonic_s)
        or not isfinite(expires_monotonic_s)
        or observed_monotonic_s < 0.0
        or not observed_monotonic_s
        <= expires_monotonic_s
        <= observed_monotonic_s + 0.600001
    ):
        raise ValueError("target range witness timing is invalid")
    if not ability_witnesses:
        raise ValueError("at least one reviewed range witness is required")
    witnesses: list[dict[str, object]] = []
    known_values: list[bool] = []
    for ability_id, client_in_range in sorted(ability_witnesses.items()):
        if client_in_range is not None and type(client_in_range) is not bool:
            raise ValueError("client range witness must be boolean or null")
        envelope = rogue_ability_range(ability_id)
        if (envelope.min_yards, envelope.max_yards) != (
            ROGUE_MELEE_RANGE.min_yards,
            ROGUE_MELEE_RANGE.max_yards,
        ):
            raise ValueError("selected target witness is not a melee envelope")
        witnesses.append({
            "ability_id": ability_id,
            "minimum_yards": envelope.min_yards,
            "maximum_yards": envelope.max_yards,
            "client_in_range": client_in_range,
        })
        if client_in_range is not None:
            known_values.append(client_in_range)
    if True in known_values and False in known_values:
        relation = MeleeRangeRelation.INCONSISTENT
    elif True in known_values:
        relation = MeleeRangeRelation.IN_RANGE_0_TO_5
    elif False in known_values:
        relation = MeleeRangeRelation.TOO_FAR_OVER_5
    else:
        relation = MeleeRangeRelation.UNKNOWN
    return {
        "record_type": "selected_target_range_awareness",
        "schema_version": "1.0",
        "observed_monotonic_s": observed_monotonic_s,
        "expires_monotonic_s": expires_monotonic_s,
        "target_identity_crc16": target_identity_crc16,
        "range_source": "CLIENT_ACTION_RANGE_WITNESSES",
        "melee_minimum_yards": ROGUE_MELEE_RANGE.min_yards,
        "melee_maximum_yards": ROGUE_MELEE_RANGE.max_yards,
        "derived_relation": relation.value,
        "witnesses": witnesses,
        "exact_distance_yards": None,
        "execution_authority": False,
    }
