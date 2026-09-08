from __future__ import annotations

from typing import Any

from perfect_assassin.domain.records import fact_value


class ReadOnlyDecisionPolicy:
    version = "observer-stub-0.1.0"

    def decide(self, observation: dict[str, Any]) -> dict[str, Any]:
        action_id, reason = self._candidate_for(observation)
        decision = {
            "record_type": "decision",
            "schema_version": "0.1",
            "decision_id": f"decision:{observation['event_id']}",
            "session_id": observation["session_id"],
            "champion_id": observation["champion_id"],
            "target_profile": observation["target_profile"],
            "game_time_ms": observation["game_time_ms"],
            "created_at": observation["captured_at"],
            "observation_event_ids": [observation["event_id"]],
            "intent": "intent.observe",
            "candidates": [
                {
                    "action_id": action_id,
                    "score": 1.0,
                    "reasons": [reason],
                    "constraints": ["execution_disabled", "fixture_evidence_only"],
                }
            ],
            "chosen_action_id": action_id,
            "latency_ms": 0.0,
            "brain_version": self.version,
            "execution_mode": "OBSERVE_ONLY",
        }
        return decision

    @staticmethod
    def _candidate_for(observation: dict[str, Any]) -> tuple[str, str]:
        if fact_value(observation, "player.dead") is True:
            return "observe.record_death", "player death was legitimately observed"
        if fact_value(observation, "target.dead") is True:
            return "observe.await_loot", "target death was legitimately observed"
        if fact_value(observation, "combat.state") == "started":
            return "observe.track_combat", "combat start was legitimately observed"
        return "observe.continue", "no executable response is permitted in M1"
