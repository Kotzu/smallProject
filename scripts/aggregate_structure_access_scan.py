from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.structure_access_graph import (
    StructureAccessObservation,
    build_structure_access_graph_record,
    load_structure_access_graph,
)
from perfect_assassin.movement.structure_access_scan_observation import (
    collision_probe_from_record,
    file_sha256,
    load_scan_observation,
    local_environment_from_record,
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
GRAPH_SCHEMA = ROOT / "contracts" / "structure-access-graph.schema.json"


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


def _paths(fragment_dir: Path, seed_id: str) -> tuple[Path, Path]:
    suffix = seed_id.removeprefix("seed:")
    return (
        fragment_dir / f"seed-{suffix}.observation.json",
        fragment_dir / f"seed-{suffix}.awareness.json",
    )


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate one complete resumable structure-scan scope into a "
            "WorldPack-bound Structure Access Graph."
        )
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--fragment-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--structure-id", action="append", default=[])
    parser.add_argument("--completed-tasks-only", action="store_true")
    parser.add_argument("--replace-output", action="store_true")
    args = parser.parse_args(argv)
    if args.completed_tasks_only and args.structure_id:
        parser.error("--completed-tasks-only cannot be combined with --structure-id")

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
    selected_ids = frozenset(args.structure_id)
    tasks = [item for item in plan["tasks"] if (
        not selected_ids or item["structure_id"] in selected_ids
    )]
    fragment_validator = ContractValidator(OBSERVATION_SCHEMA)
    if args.completed_tasks_only:
        completed_tasks = []
        for task in tasks:
            accepted = 0
            complete = True
            for seed in task["initial_seeds"]:
                fragment_path, _ = _paths(fragment_dir, str(seed["seed_id"]))
                if not fragment_path.is_file():
                    complete = False
                    break
                fragment = load_scan_observation(
                    fragment_path,
                    schema_path=OBSERVATION_SCHEMA,
                    plan=plan,
                    validator=fragment_validator,
                )
                if (
                    fragment["task_id"] != task["task_id"]
                    or fragment["seed_id"] != seed["seed_id"]
                    or fragment["status"] == "PROBE_ERROR"
                ):
                    complete = False
                    break
                accepted += fragment["status"] == "ACCEPTED_CONTAINED_WMO"
            if complete and accepted:
                completed_tasks.append(task)
        tasks = completed_tasks
    if not tasks or (
        selected_ids and {item["structure_id"] for item in tasks} != selected_ids
    ):
        raise ValueError("aggregate scope contains an unknown or ineligible structure")
    local_validator = ContractValidator(LOCAL_AWARENESS_SCHEMA)
    observations: list[StructureAccessObservation] = []
    status_counts: dict[str, int] = {}

    for task in tasks:
        for seed in task["initial_seeds"]:
            fragment_path, expected_awareness_path = _paths(
                fragment_dir, str(seed["seed_id"]),
            )
            if not fragment_path.is_file():
                raise ValueError("aggregate scope is incomplete")
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
                raise ValueError("scan fragment does not match aggregate scope")
            status = str(fragment["status"])
            status_counts[status] = status_counts.get(status, 0) + 1
            if status == "PROBE_ERROR":
                raise ValueError("aggregate scope contains unresolved probe errors")
            if status != "ACCEPTED_CONTAINED_WMO":
                continue
            if fragment["awareness_artifact"] != expected_awareness_path.name:
                raise ValueError("scan awareness filename does not match its seed")
            awareness_record = json.loads(
                expected_awareness_path.read_text(encoding="utf-8")
            )
            local_validator.validate(awareness_record)
            if file_sha256(expected_awareness_path) != fragment["awareness_sha256"]:
                raise ValueError("scan awareness artifact hash mismatch")
            observations.append(StructureAccessObservation(
                awareness=local_environment_from_record(awareness_record),
                nav_awareness=collision_probe_from_record(fragment["collision_probe"]),
                probe_worker_sha256=worker_sha256,
            ))
    if not observations:
        raise ValueError("aggregate scope has no confirmed WMO observations")
    graph = build_structure_access_graph_record(
        binding.pack,
        structure_index_record=loaded_index.record,
        observations=observations,
    )
    ContractValidator(GRAPH_SCHEMA).validate(graph)
    if args.output.exists():
        if not args.replace_output:
            raise ValueError("structure access graph output already exists")
        load_structure_access_graph(
            args.output,
            schema_path=GRAPH_SCHEMA,
            pack=binding.pack,
            structure_index_record=loaded_index.record,
            expected_probe_worker_sha256=worker_sha256,
        )
    _atomic_json(args.output, graph)
    print(json.dumps({
        "status": "AGGREGATED_COMPLETE_SELECTED_SCOPE",
        "plan_id": plan["plan_id"],
        "graph_id": graph["graph_id"],
        "graph_content_sha256": graph["content_sha256"],
        "selected_structure_count": len(tasks),
        "planned_seed_count": sum(item["initial_seed_count"] for item in tasks),
        "accepted_observation_count": len(observations),
        "status_counts": status_counts,
        "boundary_chain_count": len(graph["boundary_chains"]),
        "access_opening_count": len(graph["access_openings"]),
        "coverage_state": graph["coverage_state"],
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
