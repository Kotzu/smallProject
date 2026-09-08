from __future__ import annotations

import unittest

from perfect_assassin.memory.policy import MemoryIsolationError, MemoryWritePolicy


class MemoryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = MemoryWritePolicy()

    @staticmethod
    def record(namespace: str, origin: str) -> dict[str, object]:
        return {
            "record_type": "memory",
            "schema_version": "0.1",
            "memory_id": f"memory:{namespace}:{origin}",
            "namespace": namespace,
            "origin": origin,
            "key": "synthetic.test",
            "value": "fixture",
            "confidence": 1.0,
            "created_at": "2026-08-22T13:00:00Z",
            "evidence_refs": ["fixture:test"],
        }

    def test_lab_evidence_cannot_enter_champion_identity(self) -> None:
        with self.assertRaises(MemoryIsolationError):
            self.policy.authorize(self.record("champion_identity", "lab_derived"))

    def test_lab_evidence_can_enter_skill_namespace(self) -> None:
        self.policy.authorize(self.record("skill", "lab_derived"))


if __name__ == "__main__":
    unittest.main()
