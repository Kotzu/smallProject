from __future__ import annotations

import argparse
import json
from pathlib import Path

from perfect_assassin.application.observer_slice import RunObserverFixture
from perfect_assassin.application.tbc243_intake import RunTbc243SavedVariablesIntake
from perfect_assassin.contract_validation import ContractValidator


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="perfect-assassin")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run-fixture", help="Run the observe-only M0/M1 slice")
    run.add_argument("--fixture", type=Path, required=True)
    run.add_argument("--telemetry", type=Path, required=True)
    run.add_argument("--journal", type=Path, required=True)

    intake = commands.add_parser(
        "import-tbc243-saved-variables",
        help="Import a stopped-client TBC 2.4.3 observer export in OBSERVE_ONLY mode",
    )
    intake.add_argument("--input", type=Path, required=True)
    intake.add_argument("--telemetry", type=Path, required=True)
    intake.add_argument("--journal", type=Path, required=True)

    validate = commands.add_parser("validate", help="Validate one core telemetry record")
    validate.add_argument("record", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = repository_root()
    if args.command == "validate":
        record = json.loads(args.record.read_text(encoding="utf-8"))
        ContractValidator(root / "contracts" / "core.schema.json").validate(record)
        print("CONTRACT_VALID")
        return 0

    if args.command == "import-tbc243-saved-variables":
        result = RunTbc243SavedVariablesIntake(root).run(
            saved_variables_path=args.input.resolve(),
            telemetry_path=args.telemetry.resolve(),
            journal_path=args.journal.resolve(),
        )
        print(
            json.dumps(
                {
                    "status": "TBC243_OFFLINE_INTAKE_COMPLETE",
                    "execution_mode": "OBSERVE_ONLY",
                    "synthetic": result.synthetic,
                    "observations": result.pipeline.observations,
                    "decisions": result.pipeline.decisions,
                    "encounters": result.pipeline.encounters,
                    "archived_raw_combat_events": result.archived_raw_combat_events,
                    "interpreted_raw_combat_events": result.interpreted_raw_combat_events,
                    "replay_hash": result.pipeline.replay_hash,
                    "telemetry": str(result.pipeline.telemetry_path),
                    "journal": str(result.pipeline.journal_path),
                },
                indent=2,
            )
        )
        return 0

    result = RunObserverFixture(root).run(
        fixture_path=args.fixture.resolve(),
        telemetry_path=args.telemetry.resolve(),
        journal_path=args.journal.resolve(),
    )
    print(
        json.dumps(
            {
                "status": "OBSERVE_ONLY_SLICE_COMPLETE",
                "fixture": result.fixture_label,
                "observations": result.observations,
                "decisions": result.decisions,
                "encounters": result.encounters,
                "replay_hash": result.replay_hash,
                "telemetry": str(result.telemetry_path),
                "journal": str(result.journal_path),
            },
            indent=2,
        )
    )
    return 0
