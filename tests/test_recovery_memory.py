from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.recovery_memory import (
    LOCAL_CLEARANCE_STRATEGY,
    RecoveryStrategyMemory,
)


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
SCHEMA = Path(__file__).parents[1] / "contracts" / "recovery-strategy-memory.schema.json"


class RecoveryStrategyMemoryTests(unittest.TestCase):
    def test_one_failure_is_provisional_and_does_not_skip(self) -> None:
        memory = RecoveryStrategyMemory.empty(client_build=8606).observe_failure(
            map_name="Azeroth",
            zone_index=25,
            x=1658.0,
            y=1684.0,
            strategy=LOCAL_CLEARANCE_STRATEGY,
            run_id="run:first",
            observed_at=NOW,
        )

        self.assertIsNone(
            memory.should_skip(
                map_name="Azeroth",
                zone_index=25,
                x=1659.0,
                y=1687.0,
                strategy=LOCAL_CLEARANCE_STRATEGY,
                now=NOW,
            )
        )
        self.assertFalse(memory.failures[0].planning_confirmed)

    def test_two_failures_in_same_cell_skip_and_round_trip(self) -> None:
        memory = RecoveryStrategyMemory.empty(client_build=8606)
        memory = memory.observe_failure(
            map_name="Azeroth", zone_index=25, x=1658.0, y=1684.0,
            strategy=LOCAL_CLEARANCE_STRATEGY, run_id="run:first", observed_at=NOW,
        )
        memory = memory.observe_failure(
            map_name="Azeroth", zone_index=25, x=1659.0, y=1687.0,
            strategy=LOCAL_CLEARANCE_STRATEGY, run_id="run:second",
            observed_at=NOW + timedelta(minutes=1),
        )

        failure = memory.should_skip(
            map_name="Azeroth", zone_index=25, x=1660.0, y=1688.0,
            strategy=LOCAL_CLEARANCE_STRATEGY, now=NOW + timedelta(days=365),
        )
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(failure.observations, 2)
        restored = RecoveryStrategyMemory.from_record(
            memory.to_record(), expected_client_build=8606,
        )
        self.assertEqual(restored, memory)
        self.assertFalse(restored.execution_authority)
        ContractValidator(SCHEMA).validate(memory.to_record())

    def test_different_cell_does_not_skip(self) -> None:
        memory = RecoveryStrategyMemory.empty(client_build=8606)
        for index in range(2):
            memory = memory.observe_failure(
                map_name="Azeroth", zone_index=25,
                x=1658.0 + index, y=1684.0,
                strategy=LOCAL_CLEARANCE_STRATEGY,
                run_id=f"run:{index}", observed_at=NOW + timedelta(minutes=index),
            )

        self.assertIsNone(
            memory.should_skip(
                map_name="Azeroth", zone_index=25, x=1672.0, y=1684.0,
                strategy=LOCAL_CLEARANCE_STRATEGY, now=NOW,
            )
        )

    def test_success_resolves_failure_cell(self) -> None:
        memory = RecoveryStrategyMemory.empty(client_build=8606)
        for index in range(2):
            memory = memory.observe_failure(
                map_name="Azeroth", zone_index=25, x=1658.0, y=1684.0,
                strategy=LOCAL_CLEARANCE_STRATEGY,
                run_id=f"run:{index}", observed_at=NOW + timedelta(minutes=index),
            )
        resolved = memory.resolve_success(
            map_name="Azeroth", zone_index=25, x=1659.0, y=1687.0,
            strategy=LOCAL_CLEARANCE_STRATEGY,
        )
        self.assertEqual(resolved.failures, ())

    def test_provisional_failure_expires(self) -> None:
        memory = RecoveryStrategyMemory.empty(client_build=8606).observe_failure(
            map_name="Azeroth", zone_index=25, x=1658.0, y=1684.0,
            strategy=LOCAL_CLEARANCE_STRATEGY, run_id="run:first", observed_at=NOW,
        )
        self.assertIsNone(
            memory.should_skip(
                map_name="Azeroth", zone_index=25, x=1658.0, y=1684.0,
                strategy=LOCAL_CLEARANCE_STRATEGY, now=NOW + timedelta(days=8),
            )
        )

    def test_client_build_mismatch_fails_closed(self) -> None:
        record = RecoveryStrategyMemory.empty(client_build=8606).to_record()
        with self.assertRaisesRegex(ValueError, "client build mismatch"):
            RecoveryStrategyMemory.from_record(record, expected_client_build=12340)


if __name__ == "__main__":
    unittest.main()
