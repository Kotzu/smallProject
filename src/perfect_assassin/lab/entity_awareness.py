"""LAB-only scoring for client-visible entity awareness.

The evaluator intentionally accepts server ground truth only at the LAB
boundary.  Its output is a score/report, never an ObservationEnvelope and
never a navigation or combat input.  A client witness without coordinates is
counted for identity coverage but is not given an inferred world position.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
import re
from typing import Iterable


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:/._-]{0,159}$")
_KINDS = frozenset({"hostile_mob", "friendly_npc", "neutral_npc", "player", "unknown"})


def _identifier(label: str, value: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is not a bounded identifier")
    return value


def _position(label: str, value: tuple[float, float, float] | None) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError(f"{label} must be a 3D tuple or null")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not isfinite(float(item)) for item in value):
        raise ValueError(f"{label} contains a non-finite coordinate")
    return tuple(float(item) for item in value)


@dataclass(frozen=True, slots=True)
class LabGroundTruthEntity:
    entity_id: str
    kind: str
    world_position: tuple[float, float, float]

    def __post_init__(self) -> None:
        _identifier("ground truth entity_id", self.entity_id)
        if self.kind not in _KINDS:
            raise ValueError("ground truth entity kind is invalid")
        if _position("ground truth world_position", self.world_position) is None:
            raise ValueError("ground truth world_position is required")


@dataclass(frozen=True, slots=True)
class ClientEntityWitness:
    entity_id: str | None
    kind: str
    world_position: tuple[float, float, float] | None = None
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.entity_id is not None:
            _identifier("client witness entity_id", self.entity_id)
        if self.kind not in _KINDS:
            raise ValueError("client witness entity kind is invalid")
        _position("client witness world_position", self.world_position)
        if isinstance(self.confidence, bool) or not isfinite(float(self.confidence)) or not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("client witness confidence must be in [0, 1]")


def evaluate_entity_awareness(
    *,
    evaluation_id: str,
    map_name: str,
    ground_truth: Iterable[LabGroundTruthEntity],
    witnesses: Iterable[ClientEntityWitness],
) -> dict[str, object]:
    """Score identity and optional witnessed positions without inference.

    Matching is exact by client-visible entity ID.  Anonymous screen-space
    witnesses therefore contribute to neither identity precision nor recall;
    they remain visible evidence but cannot be assigned a server entity.
    """

    _identifier("evaluation_id", evaluation_id)
    if not isinstance(map_name, str) or not map_name or len(map_name) > 160:
        raise ValueError("map_name is invalid")
    truth = tuple(ground_truth)
    observed = tuple(witnesses)
    if any(not isinstance(item, LabGroundTruthEntity) for item in truth):
        raise ValueError("ground_truth contains an invalid entity")
    if any(not isinstance(item, ClientEntityWitness) for item in observed):
        raise ValueError("witnesses contains an invalid entity")
    truth_by_id = {item.entity_id: item for item in truth}
    if len(truth_by_id) != len(truth):
        raise ValueError("ground truth entity IDs must be unique")
    witness_ids = [item.entity_id for item in observed if item.entity_id is not None]
    if len(set(witness_ids)) != len(witness_ids):
        raise ValueError("client witness entity IDs must be unique")
    matches = [
        (truth_by_id[item.entity_id], item)
        for item in observed
        if item.entity_id is not None and item.entity_id in truth_by_id
    ]
    localized = [pair for pair in matches if pair[1].world_position is not None]
    errors = [
        hypot(
            hypot(
                pair[0].world_position[0] - pair[1].world_position[0],
                pair[0].world_position[1] - pair[1].world_position[1],
            ),
            pair[0].world_position[2] - pair[1].world_position[2],
        )
        for pair in localized
    ]
    truth_count = len(truth)
    witness_count = len(observed)
    matched_count = len(matches)
    localized_count = len(localized)
    return {
        "record_type": "lab_entity_awareness_evaluation",
        "schema_version": "1.0",
        "evaluation_id": evaluation_id,
        "map_name": map_name,
        "evaluation_scope": "LAB_EVALUATION_ONLY",
        "ground_truth_origin": "server_ground_truth",
        "witness_origin": "client_observed",
        "ground_truth_count": truth_count,
        "witness_count": witness_count,
        "matched_identity_count": matched_count,
        "identity_recall": matched_count / truth_count if truth_count else 1.0,
        "identity_precision": matched_count / witness_count if witness_count else 1.0,
        "localized_match_count": localized_count,
        "unlocalized_match_count": matched_count - localized_count,
        "position_coverage": localized_count / matched_count if matched_count else 0.0,
        "mean_position_error_yards": sum(errors) / len(errors) if errors else None,
        "max_position_error_yards": max(errors) if errors else None,
        "execution_authority": False,
    }


__all__ = [
    "ClientEntityWitness",
    "LabGroundTruthEntity",
    "evaluate_entity_awareness",
]
