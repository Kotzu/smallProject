from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from perfect_assassin.adapter.fixture import FixtureObservationSource
from perfect_assassin.contract_validation import ContractValidator


ROOT = Path(__file__).resolve().parents[1]


class SemanticPortabilityTests(unittest.TestCase):
    def test_two_fixture_adapters_map_different_raw_ids_to_same_semantic_id(self) -> None:
        validator = ContractValidator(ROOT / "contracts" / "raw-fixture.schema.json")
        fixture = json.loads(
            (ROOT / "data" / "fixtures" / "level_1_first_kill.raw.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            fixture_path = temp / "fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            registry_a = temp / "registry-a.json"
            registry_b = temp / "registry-b.json"
            registry_a.write_text(
                json.dumps(
                    {
                        "facts": {"unit_level": "player.level", "spell_used": "action.ability_used"},
                        "abilities": {"spell_1752": "rogue.sinister_strike"},
                    }
                ),
                encoding="utf-8",
            )
            registry_b.write_text(
                json.dumps(
                    {
                        "facts": {"player_level": "player.level", "spell_used": "action.ability_used"},
                        "abilities": {"sinister_strike": "rogue.sinister_strike"},
                    }
                ),
                encoding="utf-8",
            )

            source_a = FixtureObservationSource(fixture_path, registry_a, validator)
            source_b = FixtureObservationSource(fixture_path, registry_b, validator)
            self.assertEqual(source_a.semantic_key("unit_level"), source_b.semantic_key("player_level"))
            self.assertEqual(
                source_a.semantic_value("spell_used", "spell_1752"),
                source_b.semantic_value("spell_used", "sinister_strike"),
            )


if __name__ == "__main__":
    unittest.main()
