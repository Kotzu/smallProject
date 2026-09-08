from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from perfect_assassin.adapter.tbc243_saved_variables import (
    Tbc243SavedVariablesObservationSource,
)
from perfect_assassin.application.observer_slice import (
    ObserverSliceResult,
    RunObservationSource,
)
from perfect_assassin.contract_validation import ContractValidator


@dataclass(frozen=True, slots=True)
class Tbc243IntakeResult:
    pipeline: ObserverSliceResult
    synthetic: bool
    archived_raw_combat_events: int
    interpreted_raw_combat_events: int


class RunTbc243SavedVariablesIntake:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root

    def run(
        self,
        saved_variables_path: Path,
        telemetry_path: Path,
        journal_path: Path,
    ) -> Tbc243IntakeResult:
        source = Tbc243SavedVariablesObservationSource(
            saved_variables_path,
            self.repository_root / "config" / "semantic-ids" / "rogue-level-1.json",
            ContractValidator(
                self.repository_root / "contracts" / "tbc243-addon-export.schema.json"
            ),
        )
        pipeline = RunObservationSource(self.repository_root).run(
            source,
            saved_variables_path.name,
            telemetry_path,
            journal_path,
            require_encounter=False,
            synthetic=source.synthetic,
        )
        return Tbc243IntakeResult(
            pipeline=pipeline,
            synthetic=source.synthetic,
            archived_raw_combat_events=source.archived_raw_events,
            interpreted_raw_combat_events=source.interpreted_raw_events,
        )
