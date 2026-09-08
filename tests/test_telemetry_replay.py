from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from perfect_assassin.application.observer_slice import RunObserverFixture
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.replay.reader import ReplayReader
from perfect_assassin.telemetry.jsonl import DuplicateTelemetryRecordError, JsonlTelemetrySink


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "level_1_first_kill.raw.json"


class TelemetryReplayTests(unittest.TestCase):
    def test_round_trip_is_deterministic_and_duplicate_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            first = RunObserverFixture(ROOT).run(FIXTURE, temp / "first.jsonl", temp / "first.md")
            second = RunObserverFixture(ROOT).run(FIXTURE, temp / "second.jsonl", temp / "second.md")
            self.assertEqual(first.replay_hash, second.replay_hash)

            validator = ContractValidator(ROOT / "contracts" / "core.schema.json")
            replay = ReplayReader(first.telemetry_path, validator)
            records = replay.records()
            sink = JsonlTelemetrySink(first.telemetry_path, validator)
            with self.assertRaises(DuplicateTelemetryRecordError):
                sink.append(records[0])

    def test_reconstruction_returns_only_facts_known_at_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            result = RunObserverFixture(ROOT).run(FIXTURE, temp / "replay.jsonl", temp / "journal.md")
            validator = ContractValidator(ROOT / "contracts" / "core.schema.json")
            known = ReplayReader(result.telemetry_path, validator).known_facts_at(2100)
            self.assertEqual(known["combat.state"]["value"], "started")
            self.assertNotIn("target.dead", known)
            self.assertNotIn("loot.item_observed", known)

            after_kill = ReplayReader(result.telemetry_path, validator).known_facts_at(3900)
            self.assertTrue(after_kill["target.dead"]["value"])
            self.assertNotIn("target.health_pct", after_kill)


if __name__ == "__main__":
    unittest.main()
