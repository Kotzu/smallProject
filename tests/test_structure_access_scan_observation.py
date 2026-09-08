from __future__ import annotations

import json
from math import tau
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.local_environment_awareness import (
    LocalEnvironmentAwareness,
)
from perfect_assassin.movement.structure_access_scan_observation import (
    StructureAccessScanObservationError,
    build_scan_observation_record,
    collision_probe_from_record,
    collision_probe_record,
    load_scan_observation,
    local_environment_from_record,
)


ROOT = Path(__file__).parents[1]


def _plan() -> dict[str, object]:
    return {
        "plan_id": "wow.test.pack:Azeroth:structure-access-scan-v1",
        "content_sha256": "a" * 64,
        "world_pack_id": "wow.test.pack",
        "world_pack_content_sha256": "b" * 64,
        "client_build": "2.4.3.8606",
        "map_id": 0,
        "map_name": "Azeroth",
        "probe_worker_sha256": "c" * 64,
    }


def _task() -> dict[str, object]:
    return {
        "task_id": "0:wmo:7:access-scan-v1",
        "structure_id": "0:wmo:7",
    }


def _seed() -> dict[str, object]:
    return {
        "seed_id": "seed:0123456789abcdef01234567",
        "position": [1.0, 2.0, 3.0],
    }


def _native() -> LocalStaticAwareness:
    return LocalStaticAwareness(
        physical_surfaces=frozenset({"wmo"}),
        probe_radius_yards=12.0,
        overhead_clear=False,
        radial_probes=tuple(RadialClearanceProbe(
            index * tau / 16,
            4.0 if index == 0 else 12.0,
            index != 0,
        ) for index in range(16)),
    )


def _awareness() -> LocalEnvironmentAwareness:
    return LocalEnvironmentAwareness(
        map_name="Azeroth",
        observed_monotonic_s=10.0,
        position=NavPoint(1.0, 2.0, 3.0),
        environment_state="WMO_TRANSITION_OR_UNRESOLVED",
        environment_confidence=0.60,
        physical_surfaces=frozenset({"wmo"}),
        topology_complete=False,
        containing_structures=(),
        boundaries=(),
        verified_egresses=(),
        candidate_opening_bearings_rad=(),
        nearby_wmo_count=1,
        nearby_static_obstacle_count=2,
    )


class StructureAccessScanObservationTests(unittest.TestCase):
    def test_collision_and_local_awareness_round_trip(self) -> None:
        native_record = collision_probe_record(_native())
        native = collision_probe_from_record(native_record)
        self.assertEqual(native.physical_surfaces, frozenset({"wmo"}))
        self.assertEqual(len(native.radial_probes), 16)
        self.assertEqual(native.radial_probes[0].clearance_yards, 4.0)

        local = local_environment_from_record(_awareness().to_record())
        self.assertEqual(local.map_name, "Azeroth")
        self.assertEqual(local.position, NavPoint(1.0, 2.0, 3.0))
        self.assertFalse(local.execution_authority)

    def test_fragment_is_strict_hash_bound_and_non_authoritative(self) -> None:
        record = build_scan_observation_record(
            plan=_plan(),
            task=_task(),
            seed=_seed(),
            status="REJECTED_EXPECTED_STRUCTURE_NOT_CONFIRMED",
            resolved_position=[1.0, 2.0, 3.0],
            actual_structure_ids=[],
            awareness_artifact="seed-fixture.awareness.json",
            awareness_sha256="d" * 64,
            collision_probe=collision_probe_record(_native()),
            failure_reason="expected WMO was not confirmed",
        )
        ContractValidator(
            ROOT / "contracts" / "structure-access-scan-observation.schema.json"
        ).validate(record)
        self.assertFalse(record["execution_authority"])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fragment.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            validation_calls = []
            validator = type("RecordingValidator", (), {
                "validate": lambda self, value: validation_calls.append(value),
            })()
            loaded = load_scan_observation(
                path,
                schema_path=(
                    ROOT / "contracts"
                    / "structure-access-scan-observation.schema.json"
                ),
                plan=_plan(),
                validator=validator,
            )
            self.assertEqual(loaded["seed_id"], _seed()["seed_id"])
            self.assertEqual(validation_calls, [record])

            altered = json.loads(json.dumps(record))
            altered["requested_position"][0] = 99.0
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaisesRegex(
                StructureAccessScanObservationError, "hash mismatch",
            ):
                load_scan_observation(
                    path,
                    schema_path=(
                        ROOT / "contracts"
                        / "structure-access-scan-observation.schema.json"
                    ),
                    plan=_plan(),
                )

    def test_probe_error_cannot_carry_fabricated_awareness(self) -> None:
        with self.assertRaisesRegex(
            StructureAccessScanObservationError, "does not match its status",
        ):
            build_scan_observation_record(
                plan=_plan(),
                task=_task(),
                seed=_seed(),
                status="PROBE_ERROR",
                resolved_position=[1.0, 2.0, 3.0],
                actual_structure_ids=[],
                awareness_artifact=None,
                awareness_sha256=None,
                collision_probe=None,
                failure_reason="probe failed",
            )

    def test_no_nav_polygon_is_a_deterministic_rejection_without_awareness(self) -> None:
        record = build_scan_observation_record(
            plan=_plan(),
            task=_task(),
            seed=_seed(),
            status="REJECTED_NO_NAV_POLYGON",
            resolved_position=None,
            actual_structure_ids=[],
            awareness_artifact=None,
            awareness_sha256=None,
            collision_probe=None,
            failure_reason="corridor endpoint has no polygon",
        )
        ContractValidator(
            ROOT / "contracts" / "structure-access-scan-observation.schema.json"
        ).validate(record)
        self.assertFalse(record["execution_authority"])

    def test_incomplete_static_awareness_is_preserved_without_fabrication(self) -> None:
        record = build_scan_observation_record(
            plan=_plan(),
            task=_task(),
            seed=_seed(),
            status="REJECTED_INCOMPLETE_STATIC_AWARENESS",
            resolved_position=None,
            actual_structure_ids=[],
            awareness_artifact=None,
            awareness_sha256=None,
            collision_probe=None,
            failure_reason="start awareness physical surfaces are empty",
        )
        ContractValidator(
            ROOT / "contracts" / "structure-access-scan-observation.schema.json"
        ).validate(record)
        self.assertIsNone(record["collision_probe"])
        self.assertFalse(record["execution_authority"])


if __name__ == "__main__":
    unittest.main()
