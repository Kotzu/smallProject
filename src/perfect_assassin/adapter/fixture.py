from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.records import RawEvent, RawFact


class FixtureAdapterError(ValueError):
    pass


class FixtureObservationSource:
    def __init__(
        self,
        fixture_path: Path,
        semantic_registry_path: Path,
        fixture_validator: ContractValidator,
    ) -> None:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture_validator.validate(fixture)
        if fixture["synthetic"] is not True:
            raise FixtureAdapterError("Fixture source must remain explicitly synthetic")

        registry = json.loads(semantic_registry_path.read_text(encoding="utf-8"))
        self._semantic_facts = dict(registry["facts"])
        self._semantic_abilities = dict(registry.get("abilities", {}))
        self.fixture_label = str(fixture["label"])
        self.target_profile = str(fixture["target_profile"])
        self.adapter_name = str(fixture["adapter"])
        self.session_id = str(fixture["session_id"])
        self.champion_id = str(fixture["champion_id"])
        self._events = tuple(self._parse_event(event) for event in fixture["events"])

    @staticmethod
    def _parse_event(value: dict[str, object]) -> RawEvent:
        facts = tuple(
            RawFact(
                raw_key=str(fact["raw_key"]),
                value=fact["value"],
                source=str(fact["source"]),
                capability=str(fact["capability"]),
                confidence=float(fact["confidence"]),
                observed_at=str(fact["observed_at"]),
                expires_at=str(fact["expires_at"]) if "expires_at" in fact else None,
                restriction_evidence=(
                    str(fact["restriction_evidence"]) if "restriction_evidence" in fact else None
                ),
            )
            for fact in value["facts"]  # type: ignore[index]
        )
        return RawEvent(
            raw_event_id=str(value["raw_event_id"]),
            kind=str(value["kind"]),
            game_time_ms=int(value["game_time_ms"]),
            captured_at=str(value["captured_at"]),
            facts=facts,
        )

    def events(self) -> Iterable[RawEvent]:
        return iter(self._events)

    def semantic_key(self, raw_key: str) -> str:
        try:
            return self._semantic_facts[raw_key]
        except KeyError as error:
            raise FixtureAdapterError(f"Unknown raw fact key: {raw_key}") from error

    def semantic_value(self, raw_key: str, raw_value: Any) -> Any:
        if raw_key != "spell_used":
            return raw_value
        try:
            return self._semantic_abilities[str(raw_value)]
        except KeyError as error:
            raise FixtureAdapterError(f"Unknown raw ability ID: {raw_value}") from error
