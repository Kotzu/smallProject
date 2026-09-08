from __future__ import annotations

import json
from typing import Any, Iterable

from perfect_assassin.domain.records import apply_observation_to_state


class MarkdownJournalProjection:
    def render(
        self, records: Iterable[dict[str, Any]], replay_hash: str, *, synthetic: bool = True
    ) -> str:
        ordered = list(records)
        observations = [record for record in ordered if record["record_type"] == "observation"]
        decisions = [record for record in ordered if record["record_type"] == "decision"]
        encounters = [record for record in ordered if record["record_type"] == "encounter"]
        if not observations:
            raise ValueError("Journal requires at least one observation")

        title = (
            "# Predator Journal — synthetic M0/M1 replay"
            if synthetic
            else "# Predator Journal — offline client intake"
        )
        evidence = (
            "> Evidence: `contract_tested`, `replay_tested`. This is not Champion lived memory."
            if synthetic
            else "> Evidence: offline client export; not yet `controlled_live_verified` and not automatically Champion lived memory."
        )
        lines = [
            title,
            "",
            evidence,
            "",
            f"- Session: `{observations[0]['session_id']}`",
            f"- Target profile: `{observations[0]['target_profile']}`",
            "- Execution: `OBSERVE_ONLY`",
            f"- Replay SHA-256: `{replay_hash}`",
            "",
            "## Timeline",
            "",
            "| game_time_ms | event | facts | decision |",
            "|---:|---|---|---|",
        ]
        decisions_by_event = {
            decision["observation_event_ids"][-1]: decision for decision in decisions
        }
        for observation in observations:
            fact_keys = ", ".join(fact["key"] for fact in observation["facts"])
            decision = decisions_by_event.get(observation["event_id"])
            action = decision["chosen_action_id"] if decision else "—"
            lines.append(
                f"| {observation['game_time_ms']} | `{observation['event_id']}` | "
                f"{fact_keys} | `{action}` |"
            )

        lines.extend(["", "## Known state at replay end", ""])
        fact_state: dict[str, dict[str, Any]] = {}
        for observation in observations:
            apply_observation_to_state(fact_state, observation)
        for key in sorted(fact_state):
            lines.append(
                f"- `{key}` = `{json.dumps(fact_state[key]['value'], ensure_ascii=False)}`"
            )

        lines.extend(["", "## Encounters", ""])
        if not encounters:
            lines.append("No completed encounter assembled.")
        for encounter in encounters:
            lines.append(
                f"- `{encounter['encounter_id']}`: {encounter['encounter_type']} / "
                f"{encounter['result']} / decision quality `{encounter['decision_quality']}`"
            )
        lines.extend(["", "## Safety", "", "No input, movement or combat command was emitted.", ""])
        return "\n".join(lines)
