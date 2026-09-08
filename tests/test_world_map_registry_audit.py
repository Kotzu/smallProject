from __future__ import annotations

import unittest
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidator
from scripts.audit_world_map_registry import (
    AUDIT_SCHEMA,
    build_registry_audit_record,
)


ROOT = Path(__file__).parents[1]


class WorldMapRegistryAuditTests(unittest.TestCase):
    def test_current_audit_covers_inventory_and_separates_readiness(self) -> None:
        record = build_registry_audit_record(
            ROOT / "config" / "navigation" / "world-map-registry-tbc243.json",
            queue_path=ROOT / "data" / "runtime" / "navigation-f3b"
            / "client-world-bake-queue-audit-20260831.json",
        )
        ContractValidator(AUDIT_SCHEMA).validate(record)
        self.assertEqual(record["inventory_map_count"], 83)
        self.assertEqual(record["registry_map_count"], 83)
        self.assertEqual(record["queue_map_count"], 35)
        self.assertEqual(record["queue_complete_map_count"], 4)
        self.assertEqual(record["topographic_ready_map_count"], 16)
        self.assertEqual(record["autonomous_ready_map_count"], 1)
        by_id = {item["map_id"]: item for item in record["maps"]}
        self.assertTrue(by_id[0]["autonomous_ready"])
        self.assertTrue(by_id[0]["topographic_ready"])
        self.assertEqual(by_id[0]["queue_state"], "COMPLETE")
        self.assertTrue(by_id[1]["topographic_ready"])
        self.assertFalse(by_id[33]["autonomous_ready"])
        self.assertTrue(by_id[33]["topographic_ready"])
        self.assertFalse(by_id[33]["semantic_catalog_ready"])
        self.assertTrue(by_id[36]["topographic_ready"])
        self.assertFalse(by_id[36]["autonomous_ready"])
        self.assertTrue(by_id[47]["topographic_ready"])
        self.assertFalse(by_id[47]["autonomous_ready"])
        self.assertTrue(by_id[129]["topographic_ready"])
        self.assertFalse(by_id[129]["autonomous_ready"])
        self.assertTrue(by_id[189]["topographic_ready"])
        self.assertFalse(by_id[189]["autonomous_ready"])
        self.assertTrue(by_id[209]["topographic_ready"])
        self.assertFalse(by_id[209]["autonomous_ready"])
        self.assertTrue(by_id[289]["topographic_ready"])
        self.assertFalse(by_id[289]["autonomous_ready"])
        self.assertTrue(by_id[329]["topographic_ready"])
        self.assertFalse(by_id[329]["autonomous_ready"])
        self.assertTrue(by_id[543]["topographic_ready"])
        self.assertFalse(by_id[543]["autonomous_ready"])
        self.assertTrue(by_id[568]["topographic_ready"])
        self.assertFalse(by_id[568]["autonomous_ready"])
        self.assertTrue(by_id[580]["topographic_ready"])
        self.assertFalse(by_id[580]["autonomous_ready"])
        self.assertTrue(by_id[585]["topographic_ready"])
        self.assertFalse(by_id[585]["autonomous_ready"])
        self.assertFalse(by_id[13]["queue_known"])

    def test_audit_merges_separate_worldpack_queues_by_best_state(self) -> None:
        registry = ROOT / "config" / "navigation" / "world-map-registry-tbc243.json"
        full_queue = (
            ROOT / "data" / "runtime" / "client-catalog" / "tbc243-8606"
            / "bake-queue-full-v1.json"
        )
        deadmines_queue = (
            ROOT / "data" / "runtime" / "client-catalog" / "tbc243-8606"
            / "bake-queue-deadmines-v2.json"
        )
        record = build_registry_audit_record(
            registry,
            queue_paths=(full_queue, deadmines_queue),
        )
        ContractValidator(AUDIT_SCHEMA).validate(record)
        self.assertEqual(record["queue_references"], [
            "data/runtime/client-catalog/tbc243-8606/bake-queue-full-v1.json",
            "data/runtime/client-catalog/tbc243-8606/bake-queue-deadmines-v2.json",
        ])
        self.assertEqual(record["queue_complete_map_count"], 5)
        deadmines = next(item for item in record["maps"] if item["map_id"] == 36)
        self.assertTrue(deadmines["queue_known"])
        self.assertEqual(deadmines["queue_state"], "COMPLETE")

    def test_audit_accepts_four_immutable_queue_references(self) -> None:
        registry = ROOT / "config" / "navigation" / "world-map-registry-tbc243.json"
        queue_root = ROOT / "data" / "runtime" / "client-catalog" / "tbc243-8606"
        queues = (
            queue_root / "bake-queue-full-v1-karazahn-partial-20260902.json",
            queue_root / "bake-queue-proof-worldpack-v3-20260903.json",
            queue_root / "bake-queue-deadmines-v2.json",
            queue_root / "bake-queue-monastery-candidate-v1.json",
        )
        record = build_registry_audit_record(registry, queue_paths=queues)
        ContractValidator(AUDIT_SCHEMA).validate(record)
        self.assertEqual(record["queue_map_count"], 35)
        self.assertEqual(record["queue_complete_map_count"], 8)
        monastery = next(item for item in record["maps"] if item["map_id"] == 189)
        self.assertEqual(monastery["queue_state"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
