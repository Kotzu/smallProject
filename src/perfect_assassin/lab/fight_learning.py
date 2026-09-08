from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from perfect_assassin.contract_validation import ContractValidator


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "contracts" / "fight-learning-bundle.schema.json"


class FightLearningBundleError(ValueError):
    """The bundle shape passed JSON Schema but its timeline is inconsistent."""


_EXPECTED_SOURCE = {
    "OBSERVATION": "CLIENT_VISIBLE",
    "DECISION": "DECISION_BRAIN",
    "AUTHORIZATION": "EXECUTION_GATEWAY",
    "INPUT": "WINDOW_INPUT",
    "EFFECT": "CLIENT_VISIBLE",
    "POST_FIGHT_SCORE": "LAB_SCORER_POST_FIGHT",
}


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_fight_learning_bundle(
    value: Mapping[str, Any],
    *,
    validator: ContractValidator | None = None,
) -> dict[str, Any]:
    """Validate the complete observation-to-effect chain of one fight."""

    owned = dict(value)
    (validator or ContractValidator(SCHEMA)).validate(owned)
    manifest = owned["manifest"]
    if _utc(manifest["ended_at"]) < _utc(manifest["started_at"]):
        raise FightLearningBundleError("fight ended before it started")

    timeline = owned["timeline"]
    by_id: dict[str, dict[str, Any]] = {}
    previous_ms = -1.0
    post_fight_seen = False
    for expected_sequence, event in enumerate(timeline, start=1):
        if event["sequence"] != expected_sequence:
            raise FightLearningBundleError("timeline sequence is not contiguous")
        event_id = event["event_id"]
        if event_id in by_id:
            raise FightLearningBundleError("timeline event_id is not unique")
        if event["monotonic_ms"] < previous_ms:
            raise FightLearningBundleError("timeline time moved backwards")
        if event["source"] != _EXPECTED_SOURCE[event["kind"]]:
            raise FightLearningBundleError("timeline kind has an invalid evidence source")
        if post_fight_seen and event["kind"] != "POST_FIGHT_SCORE":
            raise FightLearningBundleError("live evidence appeared after post-fight scoring")
        post_fight_seen = post_fight_seen or event["kind"] == "POST_FIGHT_SCORE"
        by_id[event_id] = event
        previous_ms = event["monotonic_ms"]

    expected_kinds = {
        "observation_ref": "OBSERVATION",
        "decision_ref": "DECISION",
        "authorization_ref": "AUTHORIZATION",
        "input_ref": "INPUT",
        "effect_ref": "EFFECT",
    }
    seen_actions: set[str] = set()
    for chain in owned["action_chains"]:
        if chain["action_id"] in seen_actions:
            raise FightLearningBundleError("action_id is not unique")
        seen_actions.add(chain["action_id"])
        chain_events: list[dict[str, Any]] = []
        for field, expected_kind in expected_kinds.items():
            event_ref = chain[field]
            if field == "effect_ref" and event_ref is None:
                if chain["effect_status"] == "CONFIRMED":
                    raise FightLearningBundleError("confirmed action has no effect evidence")
                continue
            event = by_id.get(event_ref)
            if event is None or event["kind"] != expected_kind:
                raise FightLearningBundleError(f"{field} does not reference {expected_kind}")
            chain_events.append(event)
        if any(
            later["monotonic_ms"] < earlier["monotonic_ms"]
            for earlier, later in zip(chain_events, chain_events[1:])
        ):
            raise FightLearningBundleError("action chain time moved backwards")
        if chain["effect_status"] == "CONFIRMED" and chain["effect_ref"] is None:
            raise FightLearningBundleError("confirmed action requires an effect_ref")

    return owned


__all__ = ["FightLearningBundleError", "validate_fight_learning_bundle"]
