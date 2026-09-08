from __future__ import annotations

import json
import unittest
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_capability_profiles_are_valid_and_deny_by_default(self) -> None:
        validator = ContractValidator(ROOT / "contracts" / "capability-profile.schema.json")
        for path in sorted((ROOT / "config" / "capabilities").glob("*.json")):
            profile = json.loads(path.read_text(encoding="utf-8"))
            validator.validate(profile)
            self.assertEqual(profile["default"], "deny")

    def test_raw_fixtures_are_explicitly_synthetic_and_valid(self) -> None:
        validator = ContractValidator(ROOT / "contracts" / "raw-fixture.schema.json")
        paths = sorted((ROOT / "data" / "fixtures").glob("*.raw.json"))
        self.assertGreaterEqual(len(paths), 3)
        for path in paths:
            fixture = json.loads(path.read_text(encoding="utf-8"))
            validator.validate(fixture)
            self.assertIs(fixture["synthetic"], True)
            self.assertEqual(fixture["champion_id"], "fixture-not-champion")

    def test_core_contract_rejects_observation_without_provenance(self) -> None:
        validator = ContractValidator(ROOT / "contracts" / "core.schema.json")
        invalid = {
            "record_type": "observation",
            "schema_version": "0.1",
            "event_id": "event:invalid",
        }
        with self.assertRaises(ContractValidationError):
            validator.validate(invalid)

    def test_external_integration_manifests_are_valid(self) -> None:
        validator = ContractValidator(ROOT / "contracts" / "external-integration.schema.json")
        paths = sorted((ROOT / "config" / "external-integrations").glob("*.json"))
        self.assertGreaterEqual(len(paths), 2)
        for path in paths:
            validator.validate(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
