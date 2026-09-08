from __future__ import annotations

from typing import Any

from perfect_assassin.adapter.ports import ObservationSource
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.capabilities import CapabilityProfile
from perfect_assassin.domain.records import RawEvent, RawFact
from perfect_assassin.observer.firewall import ProvenanceFirewall


class ObservationNormalizer:
    def __init__(
        self,
        source: ObservationSource,
        profile: CapabilityProfile,
        firewall: ProvenanceFirewall,
        validator: ContractValidator,
    ) -> None:
        if source.target_profile != profile.profile:
            raise ValueError(
                f"Adapter target {source.target_profile} does not match capability profile {profile.profile}"
            )
        self.source = source
        self.profile = profile
        self.firewall = firewall
        self.validator = validator

    def normalize(self, event: RawEvent) -> dict[str, Any]:
        facts = [self._normalize_fact(fact) for fact in event.facts]
        observation = {
            "record_type": "observation",
            "schema_version": "0.1",
            "event_id": event.raw_event_id,
            "session_id": self.source.session_id,
            "champion_id": self.source.champion_id,
            "target_profile": self.source.target_profile,
            "game_time_ms": event.game_time_ms,
            "captured_at": event.captured_at,
            "adapter": self.source.adapter_name,
            "capabilities_hash": self.profile.canonical_hash(),
            "facts": facts,
        }
        self.validator.validate(observation)
        return observation

    def _normalize_fact(self, fact: RawFact) -> dict[str, Any]:
        self.firewall.authorize(fact)
        normalized: dict[str, Any] = {
            "key": self.source.semantic_key(fact.raw_key),
            "value": self.source.semantic_value(fact.raw_key, fact.value),
            "source": fact.source,
            "capability": fact.capability,
            "confidence": fact.confidence,
            "observed_at": fact.observed_at,
        }
        if fact.expires_at is not None:
            normalized["expires_at"] = fact.expires_at
        if fact.restriction_evidence is not None:
            normalized["restriction_evidence"] = fact.restriction_evidence
        return normalized
