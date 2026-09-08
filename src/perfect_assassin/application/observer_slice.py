from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from perfect_assassin.adapter.fixture import FixtureObservationSource
from perfect_assassin.adapter.ports import ObservationSource
from perfect_assassin.brain.read_only import ReadOnlyDecisionPolicy
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.capabilities import CapabilityProfile
from perfect_assassin.journal.markdown import MarkdownJournalProjection
from perfect_assassin.lab.encounter import EncounterAssembler, EncounterAssemblyError
from perfect_assassin.observer.firewall import ProvenanceFirewall
from perfect_assassin.observer.normalizer import ObservationNormalizer
from perfect_assassin.replay.reader import ReplayReader
from perfect_assassin.telemetry.jsonl import JsonlTelemetrySink


@dataclass(frozen=True, slots=True)
class ObserverSliceResult:
    fixture_label: str
    observations: int
    decisions: int
    encounters: int
    replay_hash: str
    telemetry_path: Path
    journal_path: Path


class RunObservationSource:
    """Shared observe-only pipeline for fixtures and real compatibility adapters."""

    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root
        contracts = repository_root / "contracts"
        self.core_validator = ContractValidator(contracts / "core.schema.json")
        self.capability_validator = ContractValidator(contracts / "capability-profile.schema.json")

    def run(
        self,
        source: ObservationSource,
        label: str,
        telemetry_path: Path,
        journal_path: Path,
        *,
        require_encounter: bool,
        synthetic: bool,
    ) -> ObserverSliceResult:
        profile_path = (
            self.repository_root / "config" / "capabilities" / f"{source.target_profile}.json"
        )
        profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
        self.capability_validator.validate(profile_data)
        profile = CapabilityProfile.from_dict(profile_data)

        firewall = ProvenanceFirewall(profile)
        normalizer = ObservationNormalizer(source, profile, firewall, self.core_validator)
        decision_policy = ReadOnlyDecisionPolicy()
        sink = JsonlTelemetrySink(telemetry_path, self.core_validator)

        observations = []
        decisions = []
        for raw_event in source.events():
            observation = normalizer.normalize(raw_event)
            decision = decision_policy.decide(observation)
            self.core_validator.validate(decision)
            sink.append(observation)
            sink.append(decision)
            observations.append(observation)
            decisions.append(decision)

        if not observations:
            raise ValueError("Observation source produced no semantically accepted events")

        encounters = 0
        try:
            encounter = EncounterAssembler(self.core_validator).assemble(
                observations,
                replay_ref=f"telemetry:{source.session_id}",
                brain_version=decision_policy.version,
            )
        except EncounterAssemblyError:
            if require_encounter:
                raise
        else:
            sink.append(encounter)
            encounters = 1

        replay = ReplayReader(telemetry_path, self.core_validator)
        replay_hash = replay.deterministic_hash()
        replay_records = replay.records()
        journal = MarkdownJournalProjection().render(
            replay_records, replay_hash, synthetic=synthetic
        )
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal_path.write_text(journal, encoding="utf-8", newline="\n")

        return ObserverSliceResult(
            fixture_label=label,
            observations=len(observations),
            decisions=len(decisions),
            encounters=encounters,
            replay_hash=replay_hash,
            telemetry_path=telemetry_path,
            journal_path=journal_path,
        )


class RunObserverFixture:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root
        contracts = repository_root / "contracts"
        self.fixture_validator = ContractValidator(contracts / "raw-fixture.schema.json")

    def run(
        self,
        fixture_path: Path,
        telemetry_path: Path,
        journal_path: Path,
    ) -> ObserverSliceResult:
        semantic_registry = self.repository_root / "config" / "semantic-ids" / "rogue-level-1.json"
        source = FixtureObservationSource(fixture_path, semantic_registry, self.fixture_validator)
        return RunObservationSource(self.repository_root).run(
            source,
            source.fixture_label,
            telemetry_path,
            journal_path,
            require_encounter=True,
            synthetic=True,
        )
