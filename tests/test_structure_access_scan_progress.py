from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.structure_access_scan_observation import (
    build_scan_observation_record,
    collision_probe_record,
    file_sha256,
)
from scripts.report_structure_access_scan import build_progress_record
from tests.test_structure_access_scan_observation import _awareness, _native


ROOT = Path(__file__).parents[1]


def _seed(suffix: str, position: list[float]) -> dict[str, object]:
    return {"seed_id": f"seed:{suffix}", "position": position}


def _plan() -> dict[str, object]:
    first = _seed("0" * 24, [1.0, 2.0, 3.0])
    second = _seed("1" * 24, [4.0, 5.0, 6.0])
    third = _seed("2" * 24, [7.0, 8.0, 9.0])
    return {
        "plan_id": "wow.test.pack:Azeroth:structure-access-scan-v1",
        "content_sha256": "a" * 64,
        "world_pack_id": "wow.test.pack",
        "world_pack_content_sha256": "b" * 64,
        "client_build": "2.4.3.8606",
        "map_id": 0,
        "map_name": "Azeroth",
        "probe_worker_sha256": "c" * 64,
        "tasks": [
            {
                "task_id": "0:wmo:7:access-scan-v1",
                "structure_id": "0:wmo:7",
                "initial_seed_count": 1,
                "initial_seeds": [first],
            },
            {
                "task_id": "0:wmo:8:access-scan-v1",
                "structure_id": "0:wmo:8",
                "initial_seed_count": 2,
                "initial_seeds": [second, third],
            },
        ],
    }


class StructureAccessScanProgressTests(unittest.TestCase):
    def test_progress_distinguishes_complete_from_partial_tasks(self) -> None:
        plan = _plan()
        first_task, second_task = plan["tasks"]
        first_seed = first_task["initial_seeds"][0]
        second_seed = second_task["initial_seeds"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            awareness_path = root / f"seed-{'0' * 24}.awareness.json"
            awareness_path.write_text(
                json.dumps(_awareness().to_record()), encoding="utf-8",
            )
            accepted = build_scan_observation_record(
                plan=plan,
                task=first_task,
                seed=first_seed,
                status="ACCEPTED_CONTAINED_WMO",
                resolved_position=[1.0, 2.0, 3.0],
                actual_structure_ids=["0:wmo:7"],
                awareness_artifact=awareness_path.name,
                awareness_sha256=file_sha256(awareness_path),
                collision_probe=collision_probe_record(_native()),
                failure_reason=None,
            )
            (root / f"seed-{'0' * 24}.observation.json").write_text(
                json.dumps(accepted), encoding="utf-8",
            )
            no_nav = build_scan_observation_record(
                plan=plan,
                task=second_task,
                seed=second_seed,
                status="REJECTED_NO_NAV_POLYGON",
                resolved_position=None,
                actual_structure_ids=[],
                awareness_artifact=None,
                awareness_sha256=None,
                collision_probe=None,
                failure_reason="corridor endpoint has no polygon",
            )
            (root / f"seed-{'1' * 24}.observation.json").write_text(
                json.dumps(no_nav), encoding="utf-8",
            )

            progress = build_progress_record(plan=plan, fragment_dir=root)
            ContractValidator(
                ROOT / "contracts" / "structure-access-scan-progress.schema.json"
            ).validate(progress)
            self.assertEqual(progress["planned_seed_count"], 3)
            self.assertEqual(progress["completed_seed_count"], 2)
            self.assertEqual(progress["missing_seed_count"], 1)
            self.assertEqual(progress["incomplete_static_awareness_count"], 0)
            self.assertEqual(progress["complete_structure_count"], 1)
            self.assertEqual(
                progress["tasks"][0]["state"], "COMPLETE_WITH_OBSERVATIONS",
            )
            self.assertEqual(progress["tasks"][1]["state"], "IN_PROGRESS")
            self.assertFalse(progress["execution_authority"])


if __name__ == "__main__":
    unittest.main()
