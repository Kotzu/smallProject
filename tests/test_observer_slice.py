from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from perfect_assassin.application.observer_slice import RunObserverFixture
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.lab.encounter import EncounterAssembler, EncounterAssemblyError
from perfect_assassin.observer.firewall import InformationPolicyError
from perfect_assassin.replay.reader import ReplayReader


ROOT = Path(__file__).resolve().parents[1]


class ObserverSliceIntegrationTests(unittest.TestCase):
    def test_encounter_requires_an_observed_combat_start(self) -> None:
        validator = ContractValidator(ROOT / "contracts" / "core.schema.json")
        with self.assertRaises(EncounterAssemblyError):
            EncounterAssembler(validator).assemble(
                [{"facts": []}], replay_ref="telemetry:fixture", brain_version="fixture"
            )

    def test_first_kill_runs_end_to_end_in_observe_only_mode(self) -> None:
        fixture = ROOT / "data" / "fixtures" / "level_1_first_kill.raw.json"
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            result = RunObserverFixture(ROOT).run(fixture, temp / "telemetry.jsonl", temp / "journal.md")
            self.assertEqual(result.observations, 8)
            self.assertEqual(result.decisions, 8)
            self.assertEqual(result.encounters, 1)

            validator = ContractValidator(ROOT / "contracts" / "core.schema.json")
            records = ReplayReader(result.telemetry_path, validator).records()
            self.assertEqual(len(records), 17)
            decisions = [record for record in records if record["record_type"] == "decision"]
            encounters = [record for record in records if record["record_type"] == "encounter"]
            self.assertTrue(all(record["execution_mode"] == "OBSERVE_ONLY" for record in decisions))
            self.assertEqual(encounters[0]["result"], "victory")
            self.assertEqual(encounters[0]["decision_quality"], "unassessed")

            journal = result.journal_path.read_text(encoding="utf-8")
            self.assertIn("This is not Champion lived memory", journal)
            self.assertIn("No input, movement or combat command was emitted", journal)
            self.assertNotIn("- `target.health_pct` =", journal)

    def test_death_fixture_is_result_not_decision_quality(self) -> None:
        fixture = ROOT / "data" / "fixtures" / "level_1_death.raw.json"
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            result = RunObserverFixture(ROOT).run(fixture, temp / "death.jsonl", temp / "death.md")
            validator = ContractValidator(ROOT / "contracts" / "core.schema.json")
            encounter = next(
                record
                for record in ReplayReader(result.telemetry_path, validator).records()
                if record["record_type"] == "encounter"
            )
            self.assertEqual(encounter["result"], "defeat")
            self.assertEqual(encounter["decision_quality"], "unassessed")

    def test_server_only_fixture_is_rejected_before_telemetry(self) -> None:
        fixture = ROOT / "data" / "fixtures" / "server_only_fact.raw.json"
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            telemetry = temp / "forbidden.jsonl"
            with self.assertRaises(InformationPolicyError):
                RunObserverFixture(ROOT).run(fixture, telemetry, temp / "forbidden.md")
            self.assertFalse(telemetry.exists())


if __name__ == "__main__":
    unittest.main()
