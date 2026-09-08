from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
import re
from typing import Any


CONTRACT_VERSION = "1.0"
POLICY_ID = "hybrid_target_search_v1"
POLICY_VERSION = "1.0.0"

ALLOWED_KNOWLEDGE_ORIGINS = frozenset(
    {
        "client_observed",
        "predator_memory",
        "external_research",
        "route_teacher",
        "quest_observed",
    }
)
FORBIDDEN_KNOWLEDGE_ORIGINS = frozenset(
    {"lab_oracle", "server_ground_truth", "server_spawn_state", "packet_state"}
)
UNIT_GOAL_KINDS = frozenset({"hostile_mob", "friendly_npc"})
VISIBLE_GOAL_KINDS = frozenset(
    {"hostile_mob", "friendly_npc", "quest_object", "herb", "mining_node"}
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _require_identifier(label: str, value: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is not a bounded identifier")


def _require_confidence(label: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    if not isfinite(float(value)) or not 0.0 < float(value) <= 1.0:
        raise ValueError(f"{label} must be in (0, 1]")


def validate_exact_target_name(name: str) -> str:
    """Validate a name before it can enter the allowlisted target command family."""

    if not isinstance(name, str) or name != name.strip() or not 1 <= len(name) <= 64:
        raise ValueError("target name must contain 1 to 64 trimmed characters")
    for character in name:
        if ord(character) > 0xFFFF or not (
            character.isalnum() or character in " '-"
        ):
            raise ValueError("target name contains a command-significant character")
    return name


def compile_target_exact_command(name: str) -> str:
    """Compile one non-generic, injection-resistant TBC exact-name probe."""

    return f"/targetexact {validate_exact_target_name(name)}"


@dataclass(frozen=True)
class SearchPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        for label, value in (("x", self.x), ("y", self.y)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"search point {label} must be numeric")
            if not isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"search point {label} must be normalized")

    def distance_to(self, other: SearchPoint) -> float:
        return hypot(float(self.x) - float(other.x), float(self.y) - float(other.y))

    def to_record(self) -> dict[str, float]:
        return {"x": float(self.x), "y": float(self.y)}


@dataclass(frozen=True)
class SearchRegion:
    region_id: str
    map_id: str
    anchor: SearchPoint
    radius: float
    prior_confidence: float
    source_origin: str
    evidence_refs: tuple[str, ...]
    patrol_points: tuple[SearchPoint, ...] = ()
    confirmed_sightings: int = 0
    negative_sweeps: int = 0

    def __post_init__(self) -> None:
        _require_identifier("region_id", self.region_id)
        _require_identifier("map_id", self.map_id)
        _require_confidence("prior_confidence", self.prior_confidence)
        if self.source_origin in FORBIDDEN_KNOWLEDGE_ORIGINS:
            raise ValueError("server or LAB oracle knowledge cannot guide the Champion")
        if self.source_origin not in ALLOWED_KNOWLEDGE_ORIGINS:
            raise ValueError("search region source origin is not allowed")
        if (
            isinstance(self.radius, bool)
            or not isinstance(self.radius, (int, float))
            or not isfinite(float(self.radius))
            or not 0.0 < float(self.radius) <= 0.25
        ):
            raise ValueError("search region radius must be in (0, 0.25]")
        if not 1 <= len(self.evidence_refs) <= 8 or len(set(self.evidence_refs)) != len(
            self.evidence_refs
        ):
            raise ValueError("search region requires 1 to 8 unique evidence refs")
        if any(not isinstance(ref, str) or not ref or len(ref) > 256 for ref in self.evidence_refs):
            raise ValueError("search region evidence ref is invalid")
        if len(self.patrol_points) > 32:
            raise ValueError("search region patrol route is too large")
        if type(self.confirmed_sightings) is not int or self.confirmed_sightings < 0:
            raise ValueError("confirmed_sightings must be a non-negative integer")
        if type(self.negative_sweeps) is not int or self.negative_sweeps < 0:
            raise ValueError("negative_sweeps must be a non-negative integer")

    @property
    def belief_score(self) -> float:
        positive_factor = 1.0 + min(self.confirmed_sightings, 10) * 0.08
        negative_factor = 1.0 + min(self.negative_sweeps, 20) * 0.35
        return min(1.0, float(self.prior_confidence) * positive_factor / negative_factor)

    def contains(self, point: SearchPoint) -> bool:
        return self.anchor.distance_to(point) <= float(self.radius)


@dataclass(frozen=True)
class VisibleCandidate:
    detection_id: str
    kind: str
    confidence: float
    bearing: str
    name: str | None = None
    is_player: bool = False

    def __post_init__(self) -> None:
        _require_identifier("detection_id", self.detection_id)
        if self.kind not in VISIBLE_GOAL_KINDS | {"player", "unknown"}:
            raise ValueError("visible candidate kind is invalid")
        _require_confidence("visible candidate confidence", self.confidence)
        if self.bearing not in {"LEFT", "CENTER", "RIGHT"}:
            raise ValueError("visible candidate bearing is invalid")
        if self.name is not None:
            validate_exact_target_name(self.name)
        if self.is_player and self.kind != "player":
            raise ValueError("player candidates must use kind=player")


@dataclass(frozen=True)
class TargetSearchState:
    search_id: str
    actor_id: str
    target_profile: str
    map_id: str
    goal_kind: str
    target_names: tuple[str, ...]
    current_position: SearchPoint | None
    regions: tuple[SearchRegion, ...]
    visible_candidates: tuple[VisibleCandidate, ...] = ()
    current_target_name: str | None = None
    current_target_hostile: bool = False
    current_target_is_player: bool = False
    player_safe: bool = True
    in_combat: bool = False
    exact_probed_region_ids: frozenset[str] = frozenset()
    exhausted_region_ids: frozenset[str] = frozenset()
    sweep_step: int = 0
    patrol_index: int = 0

    def __post_init__(self) -> None:
        for label, value in (
            ("search_id", self.search_id),
            ("actor_id", self.actor_id),
            ("target_profile", self.target_profile),
            ("map_id", self.map_id),
        ):
            _require_identifier(label, value)
        if self.goal_kind not in VISIBLE_GOAL_KINDS:
            raise ValueError("goal_kind is invalid")
        if not 1 <= len(self.target_names) <= 8:
            raise ValueError("target search requires 1 to 8 names")
        for name in self.target_names:
            validate_exact_target_name(name)
        if len({name.casefold() for name in self.target_names}) != len(self.target_names):
            raise ValueError("target names must be unique")
        if self.current_target_name is not None:
            validate_exact_target_name(self.current_target_name)
        if type(self.sweep_step) is not int or not 0 <= self.sweep_step <= 8:
            raise ValueError("sweep_step must be in [0, 8]")
        if type(self.patrol_index) is not int or self.patrol_index < 0:
            raise ValueError("patrol_index must be non-negative")


@dataclass(frozen=True)
class TargetSearchDecision:
    decision_id: str
    search_id: str
    action_id: str
    reason_code: str
    explanation: str
    confidence: float
    target_name: str | None
    region_id: str | None
    destination: SearchPoint | None
    sweep_sector: int | None
    command_family: str | None
    command_preview: str | None
    evidence_refs: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "record_type": "target_search_decision",
            "schema_version": CONTRACT_VERSION,
            "decision_id": self.decision_id,
            "search_id": self.search_id,
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "action_id": self.action_id,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "target_name": self.target_name,
            "region_id": self.region_id,
            "destination": None if self.destination is None else self.destination.to_record(),
            "sweep_sector": self.sweep_sector,
            "command_family": self.command_family,
            "command_preview": self.command_preview,
            "evidence_refs": list(self.evidence_refs),
            "execution_authority": False,
        }


class HybridTargetSearchPolicy:
    """Fuse learned habitat, external hints, exact-name probes and visible evidence."""

    MIN_VISIBLE_CONFIDENCE = 0.65

    def decide(self, state: TargetSearchState, *, decision_id: str) -> TargetSearchDecision:
        _require_identifier("decision_id", decision_id)
        common = {"decision_id": decision_id, "search_id": state.search_id}
        if not state.player_safe or state.in_combat:
            return TargetSearchDecision(
                **common,
                action_id="hunting.stop_unsafe",
                reason_code=(
                    "combat_owned_by_combat_controller"
                    if state.in_combat
                    else "player_state_unsafe"
                ),
                explanation=(
                    "Search pauses because combat recovery belongs to the combat controller."
                    if state.in_combat
                    else "Search pauses because the player state is not safe for navigation."
                ),
                confidence=1.0,
                target_name=None,
                region_id=None,
                destination=None,
                sweep_sector=None,
                command_family=None,
                command_preview=None,
                evidence_refs=("client_observed:player_state",),
            )

        target_names = {name.casefold() for name in state.target_names}
        if state.current_target_name is not None:
            exact_match = state.current_target_name.casefold() in target_names
            safe_match = (
                exact_match
                and not state.current_target_is_player
                and (state.current_target_hostile or state.goal_kind != "hostile_mob")
            )
            if safe_match:
                return TargetSearchDecision(
                    **common,
                    action_id="hunting.engage_confirmed_target",
                    reason_code="exact_target_confirmed_by_client",
                    explanation="The client-confirmed target matches the requested name and safety class.",
                    confidence=1.0,
                    target_name=state.current_target_name,
                    region_id=None,
                    destination=None,
                    sweep_sector=None,
                    command_family=None,
                    command_preview=None,
                    evidence_refs=("client_observed:target_snapshot",),
                )
            return TargetSearchDecision(
                **common,
                action_id="hunting.reject_current_target",
                reason_code="current_target_does_not_match_safe_goal",
                explanation="The selected unit is not the requested safe target and cannot be engaged.",
                confidence=1.0,
                target_name=state.current_target_name,
                region_id=None,
                destination=None,
                sweep_sector=None,
                command_family=None,
                command_preview=None,
                evidence_refs=("client_observed:target_snapshot",),
            )

        visible = [
            candidate
            for candidate in state.visible_candidates
            if not candidate.is_player
            and candidate.kind == state.goal_kind
            and candidate.confidence >= self.MIN_VISIBLE_CONFIDENCE
            and (candidate.name is None or candidate.name.casefold() in target_names)
        ]
        if visible:
            candidate = max(visible, key=lambda item: (item.confidence, item.detection_id))
            return TargetSearchDecision(
                **common,
                action_id="hunting.inspect_visible_candidate",
                reason_code="matching_candidate_visible_in_client_pixels",
                explanation="A current visible detection outranks map priors and name probes.",
                confidence=float(candidate.confidence),
                target_name=candidate.name,
                region_id=None,
                destination=None,
                sweep_sector=None,
                command_family=None,
                command_preview=None,
                evidence_refs=(f"client_observed:{candidate.detection_id}",),
            )

        candidates = [
            region
            for region in state.regions
            if region.map_id == state.map_id
            and region.region_id not in state.exhausted_region_ids
        ]
        current_regions = (
            []
            if state.current_position is None
            else [region for region in candidates if region.contains(state.current_position)]
        )
        region_pool = current_regions or candidates
        if not region_pool:
            return TargetSearchDecision(
                **common,
                action_id="hunting.request_route_knowledge",
                reason_code="no_unexhausted_search_region",
                explanation="No eligible region remains; request new quest, research or learned habitat evidence.",
                confidence=1.0,
                target_name=None,
                region_id=None,
                destination=None,
                sweep_sector=None,
                command_family=None,
                command_preview=None,
                evidence_refs=("predator_memory:negative_search_evidence",),
            )
        region = max(region_pool, key=lambda item: (item.belief_score, item.region_id))

        if state.current_position is None or not region.contains(state.current_position):
            return TargetSearchDecision(
                **common,
                action_id="hunting.move_to_search_region",
                reason_code="highest_belief_region_not_reached",
                explanation="Route toward the best supported habitat region before probing locally.",
                confidence=region.belief_score,
                target_name=None,
                region_id=region.region_id,
                destination=region.anchor,
                sweep_sector=None,
                command_family=None,
                command_preview=None,
                evidence_refs=region.evidence_refs,
            )

        if (
            state.goal_kind in UNIT_GOAL_KINDS
            and region.region_id not in state.exact_probed_region_ids
        ):
            target_name = state.target_names[0]
            return TargetSearchDecision(
                **common,
                action_id="hunting.probe_exact_name",
                reason_code="inside_plausible_region_exact_probe_available",
                explanation="Use one exact-name presence probe only after reaching a plausible habitat.",
                confidence=region.belief_score,
                target_name=target_name,
                region_id=region.region_id,
                destination=None,
                sweep_sector=None,
                command_family="target_exact",
                command_preview=compile_target_exact_command(target_name),
                evidence_refs=region.evidence_refs,
            )

        if state.sweep_step < 8:
            return TargetSearchDecision(
                **common,
                action_id="hunting.visual_sweep",
                reason_code="local_probe_unconfirmed_scan_visible_scene",
                explanation="Sweep one bounded camera sector and refresh visible detections.",
                confidence=region.belief_score,
                target_name=None,
                region_id=region.region_id,
                destination=None,
                sweep_sector=state.sweep_step,
                command_family=None,
                command_preview=None,
                evidence_refs=region.evidence_refs,
            )

        if region.patrol_points:
            destination = region.patrol_points[state.patrol_index % len(region.patrol_points)]
            return TargetSearchDecision(
                **common,
                action_id="hunting.patrol_search_region",
                reason_code="static_sweep_complete_follow_observed_patrol_route",
                explanation="Move to the next evidence-backed patrol point and repeat local sensing.",
                confidence=region.belief_score,
                target_name=None,
                region_id=region.region_id,
                destination=destination,
                sweep_sector=None,
                command_family=None,
                command_preview=None,
                evidence_refs=region.evidence_refs,
            )

        return TargetSearchDecision(
            **common,
            action_id="hunting.mark_region_negative",
            reason_code="region_sweep_complete_without_confirmation",
            explanation="Record bounded negative evidence and replan instead of searching forever.",
            confidence=region.belief_score,
            target_name=None,
            region_id=region.region_id,
            destination=None,
            sweep_sector=None,
            command_family=None,
            command_preview=None,
            evidence_refs=region.evidence_refs,
        )
