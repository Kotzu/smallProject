from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.structure_access_scan_observation import (
    canonical_sha256,
    file_sha256,
    load_scan_observation,
)
from perfect_assassin.movement.structure_access_scan_plan import (
    load_structure_access_scan_plan,
)
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    load_world_structure_index,
)


PLAN_SCHEMA = ROOT / "contracts" / "structure-access-scan-plan.schema.json"
OBSERVATION_SCHEMA = (
    ROOT / "contracts" / "structure-access-scan-observation.schema.json"
)
LOCAL_AWARENESS_SCHEMA = (
    ROOT / "contracts" / "local-environment-awareness.schema.json"
)
PROGRESS_SCHEMA = ROOT / "contracts" / "structure-access-scan-progress.schema.json"


def _atomic_json(path: Path, value: object) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _fragment_path(fragment_dir: Path, seed_id: str) -> Path:
    return fragment_dir / f"seed-{seed_id.removeprefix('seed:')}.observation.json"


def _verified_fragment(
    fragment_path: Path,
    *,
    plan: Mapping[str, Any],
    task: Mapping[str, Any],
    seed: Mapping[str, Any],
    local_validator: ContractValidator,
    fragment_validator: ContractValidator,
) -> Mapping[str, Any]:
    fragment = load_scan_observation(
        fragment_path,
        schema_path=OBSERVATION_SCHEMA,
        plan=plan,
        validator=fragment_validator,
    )
    if (
        fragment["task_id"] != task["task_id"]
        or fragment["seed_id"] != seed["seed_id"]
        or fragment["expected_structure_id"] != task["structure_id"]
        or fragment["requested_position"] != seed["position"]
    ):
        raise ValueError("scan progress fragment does not match its seed")
    artifact = fragment["awareness_artifact"]
    if artifact is not None:
        awareness_path = fragment_path.parent / str(artifact)
        awareness = json.loads(awareness_path.read_text(encoding="utf-8"))
        local_validator.validate(awareness)
        if file_sha256(awareness_path) != fragment["awareness_sha256"]:
            raise ValueError("scan progress awareness hash mismatch")
    return fragment


def build_progress_record(
    *,
    plan: Mapping[str, Any],
    fragment_dir: Path,
) -> dict[str, Any]:
    local_validator = ContractValidator(LOCAL_AWARENESS_SCHEMA)
    fragment_validator = ContractValidator(OBSERVATION_SCHEMA)
    task_records = []
    for task in plan["tasks"]:
        counts = {
            "ACCEPTED_CONTAINED_WMO": 0,
            "REJECTED_EXPECTED_STRUCTURE_NOT_CONFIRMED": 0,
            "REJECTED_NO_NAV_POLYGON": 0,
            "REJECTED_INCOMPLETE_STATIC_AWARENESS": 0,
            "PROBE_ERROR": 0,
        }
        missing = 0
        for seed in task["initial_seeds"]:
            path = _fragment_path(fragment_dir, str(seed["seed_id"]))
            if not path.is_file():
                missing += 1
                continue
            fragment = _verified_fragment(
                path,
                plan=plan,
                task=task,
                seed=seed,
                local_validator=local_validator,
                fragment_validator=fragment_validator,
            )
            counts[str(fragment["status"])] += 1
        completed = int(task["initial_seed_count"]) - missing
        if counts["PROBE_ERROR"]:
            state = "RETRY_REQUIRED"
        elif missing == int(task["initial_seed_count"]):
            state = "PENDING"
        elif missing:
            state = "IN_PROGRESS"
        elif counts["ACCEPTED_CONTAINED_WMO"]:
            state = "COMPLETE_WITH_OBSERVATIONS"
        else:
            state = "COMPLETE_NO_CONFIRMED_WMO"
        task_records.append({
            "task_id": task["task_id"],
            "structure_id": task["structure_id"],
            "planned_seed_count": task["initial_seed_count"],
            "completed_seed_count": completed,
            "accepted_seed_count": counts["ACCEPTED_CONTAINED_WMO"],
            "outside_structure_count": counts[
                "REJECTED_EXPECTED_STRUCTURE_NOT_CONFIRMED"
            ],
            "no_nav_polygon_count": counts["REJECTED_NO_NAV_POLYGON"],
            "incomplete_static_awareness_count": counts[
                "REJECTED_INCOMPLETE_STATIC_AWARENESS"
            ],
            "probe_error_count": counts["PROBE_ERROR"],
            "missing_seed_count": missing,
            "state": state,
            "execution_authority": False,
        })
    aggregate_fields = (
        "planned_seed_count", "completed_seed_count", "accepted_seed_count",
        "outside_structure_count", "no_nav_polygon_count", "probe_error_count",
        "incomplete_static_awareness_count", "missing_seed_count",
    )
    record: dict[str, Any] = {
        "record_type": "structure_access_scan_progress",
        "schema_version": "1.0",
        "plan_id": plan["plan_id"],
        "plan_content_sha256": plan["content_sha256"],
        "world_pack_id": plan["world_pack_id"],
        "world_pack_content_sha256": plan["world_pack_content_sha256"],
        "client_build": plan["client_build"],
        "map_id": plan["map_id"],
        "map_name": plan["map_name"],
        "eligible_structure_count": len(task_records),
        **{
            field: sum(int(item[field]) for item in task_records)
            for field in aggregate_fields
        },
        "complete_structure_count": sum(
            str(item["state"]).startswith("COMPLETE_") for item in task_records
        ),
        "tasks": task_records,
        "execution_authority": False,
    }
    record["content_sha256"] = canonical_sha256(record)
    return record


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a strict progress report for a resumable structure scan."
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--fragment-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    binding = load_world_pack_runtime_profile(
        args.profile,
        store_root=args.store_root,
        profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
    )
    loaded_index = load_world_structure_index(
        args.index,
        schema_path=ROOT / "contracts" / "world-structure-index.schema.json",
        pack=binding.pack,
    )
    worker_sha256 = file_sha256(args.worker)
    plan = load_structure_access_scan_plan(
        args.plan,
        schema_path=PLAN_SCHEMA,
        pack=binding.pack,
        structure_index_record=loaded_index.record,
        expected_probe_worker_sha256=worker_sha256,
    )
    fragment_dir = args.fragment_dir.resolve()
    if not fragment_dir.is_dir() or fragment_dir.is_symlink():
        raise ValueError("scan fragment directory is unavailable")
    record = build_progress_record(plan=plan, fragment_dir=fragment_dir)
    ContractValidator(PROGRESS_SCHEMA).validate(record)
    _atomic_json(args.output, record)
    print(json.dumps({
        "status": "VERIFIED_SCAN_PROGRESS",
        "plan_id": record["plan_id"],
        "eligible_structure_count": record["eligible_structure_count"],
        "complete_structure_count": record["complete_structure_count"],
        "planned_seed_count": record["planned_seed_count"],
        "completed_seed_count": record["completed_seed_count"],
        "accepted_seed_count": record["accepted_seed_count"],
        "incomplete_static_awareness_count": record[
            "incomplete_static_awareness_count"
        ],
        "probe_error_count": record["probe_error_count"],
        "missing_seed_count": record["missing_seed_count"],
        "content_sha256": record["content_sha256"],
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
