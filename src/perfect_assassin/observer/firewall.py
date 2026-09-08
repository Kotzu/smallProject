from __future__ import annotations

from typing import ClassVar

from perfect_assassin.domain.capabilities import CapabilityProfile
from perfect_assassin.domain.records import RawFact


class InformationPolicyError(ValueError):
    """A raw fact is not legitimate input for Predator Brain."""


class ProvenanceFirewall:
    _allowed_sources: ClassVar[frozenset[str]] = frozenset({
        "client_observed",
        "legitimate_inspect",
        "external_cached",
        "route_guidance",
        "predator_memory",
        "lab_skill",
    })
    _restricted_sources: ClassVar[frozenset[str]] = frozenset({
        "legitimate_inspect", "route_guidance",
    })

    def __init__(self, profile: CapabilityProfile) -> None:
        if profile.default != "deny":
            raise InformationPolicyError("Capability profile must be deny-by-default")
        self.profile = profile

    def authorize(self, fact: RawFact) -> None:
        if fact.source == "server_ground_truth":
            raise InformationPolicyError("server_ground_truth can never enter ObservationEnvelope")
        if fact.source not in self._allowed_sources:
            raise InformationPolicyError(f"Unknown or forbidden provenance source: {fact.source}")
        if not 0 <= fact.confidence <= 1:
            raise InformationPolicyError("Fact confidence must be between 0 and 1")

        status = self.profile.status_for(fact.capability)
        if status == "available":
            return
        if status == "restricted":
            if fact.source not in self._restricted_sources:
                raise InformationPolicyError(
                    f"Restricted capability {fact.capability} has incompatible source {fact.source}"
                )
            if not fact.restriction_evidence:
                raise InformationPolicyError(
                    f"Restricted capability {fact.capability} requires restriction_evidence"
                )
            return
        raise InformationPolicyError(
            f"Capability {fact.capability} is denied with status {status!r}"
        )
