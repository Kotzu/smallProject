from __future__ import annotations

from typing import Any, Iterable

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.records import fact_value


class EncounterAssemblyError(ValueError):
    pass


class EncounterAssembler:
    def __init__(self, validator: ContractValidator) -> None:
        self.validator = validator

    def assemble(
        self,
        observations: Iterable[dict[str, Any]],
        replay_ref: str,
        brain_version: str,
    ) -> dict[str, Any]:
        ordered = list(observations)
        start_index = next(
            (index for index, record in enumerate(ordered) if fact_value(record, "combat.state") == "started"),
            None,
        )
        if start_index is None:
            raise EncounterAssemblyError("Cannot assemble encounter without an observed combat start")
        active = ordered[start_index:]
        end_index = next(
            (
                index
                for index, record in enumerate(active)
                if fact_value(record, "target.dead") is True or fact_value(record, "player.dead") is True
            ),
            len(active) - 1,
        )
        encounter_observations = active[: end_index + 1]
        final = encounter_observations[-1]
        if fact_value(final, "target.dead") is True:
            result = "victory"
        elif fact_value(final, "player.dead") is True:
            result = "defeat"
        else:
            result = "incomplete"

        participants = sorted(
            {
                str(target_id)
                for record in encounter_observations
                if (target_id := fact_value(record, "target.id")) is not None
            }
        )
        first = encounter_observations[0]
        encounter = {
            "record_type": "encounter",
            "schema_version": "0.1",
            "encounter_id": f"encounter:{first['session_id']}:{first['event_id']}",
            "session_id": first["session_id"],
            "champion_id": first["champion_id"],
            "encounter_type": "pve",
            "started_at": first["captured_at"],
            "ended_at": final["captured_at"],
            "observation_event_ids": [record["event_id"] for record in encounter_observations],
            "participant_ids": participants,
            "brain_version": brain_version,
            "adapter": first["adapter"],
            "result": result,
            "decision_quality": "unassessed",
            "estimated_external_factors": [],
            "mistakes": [],
            "lessons": [],
            "replay_ref": replay_ref,
            "clip_refs": [],
        }
        self.validator.validate(encounter)
        return encounter
