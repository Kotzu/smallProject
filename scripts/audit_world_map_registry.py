"""Build a deterministic, read-only audit of every TBC world-map profile."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.world_map_registry import (
    inspect_world_map_profile,
    load_world_map_registry,
)


REGISTRY_SCHEMA = ROOT / "contracts" / "world-map-registry.schema.json"
INVENTORY_SCHEMA = ROOT / "contracts" / "client-world-asset-inventory.schema.json"
QUEUE_SCHEMA = ROOT / "contracts" / "client-world-bake-queue.schema.json"
AUDIT_SCHEMA = ROOT / "contracts" / "world-map-registry-audit.schema.json"


# A registry audit may combine queues produced for separate, immutable
# WorldPack roots (for example the continental pack and a dungeon pack).  When
# the same map is present in more than one queue, the most complete state wins;
# equal but different records are rejected instead of being guessed together.
_QUEUE_STATE_RANK = {
    "READY_FOR_EXTRACTION": 0,
    "EXTRACTION_PARTIAL": 1,
    "READY_FOR_SEMANTICS": 2,
    "SEMANTICS_PARTIAL": 3,
    "READY_FOR_NAVMESH": 4,
    "NAVMESH_PARTIAL": 5,
    "INCONSISTENT_DOWNSTREAM_ARTIFACTS": 6,
    "COMPLETE": 7,
}

_QUEUE_STATE_FIELDS = (
    "map_id", "internal_name", "adt_count", "adt_bounds",
    "asset_complete", "road_semantics_complete", "navmesh_complete",
    "state", "next_action", "execution_authority",
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _relative_reference(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _atomic_write_json(path: Path, value: object) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def build_registry_audit_record(
    registry_path: Path,
    *,
    queue_path: Path | None = None,
    queue_paths: Sequence[Path] | None = None,
) -> dict[str, object]:
    """Load and inspect all profiles without changing any runtime state."""

    if queue_paths is None:
        if queue_path is None:
            raise ValueError("at least one bake queue is required")
        resolved_queue_paths = (queue_path.resolve(),)
    else:
        resolved_queue_paths = tuple(path.resolve() for path in queue_paths)
        if queue_path is not None:
            resolved_queue_paths = (queue_path.resolve(),) + resolved_queue_paths
        if not resolved_queue_paths:
            raise ValueError("at least one bake queue is required")
    if len(set(resolved_queue_paths)) != len(resolved_queue_paths):
        raise ValueError("bake queue paths must be unique")

    profiles = load_world_map_registry(
        registry_path,
        schema_path=REGISTRY_SCHEMA,
    )
    inventory_reference = _read_object(registry_path).get("client_world_inventory")
    if not isinstance(inventory_reference, str):
        raise ValueError("registry does not declare a client world inventory")
    inventory_path = (registry_path.parent / inventory_reference).resolve()
    inventory = _read_object(inventory_path)
    ContractValidator(INVENTORY_SCHEMA).validate(inventory)
    queue_by_id: dict[int, dict[str, Any]] = {}
    for queue_path_item in resolved_queue_paths:
        queue = _read_object(queue_path_item)
        ContractValidator(QUEUE_SCHEMA).validate(queue)
        if queue.get("client_build") != "2.4.3.8606":
            raise ValueError("bake queue is bound to a different client build")
        for item in queue["maps"]:
            map_id = int(item["map_id"])
            existing = queue_by_id.get(map_id)
            if existing is None:
                queue_by_id[map_id] = item
                continue
            if all(existing[field] == item[field] for field in _QUEUE_STATE_FIELDS):
                continue
            if existing["internal_name"] != item["internal_name"]:
                raise ValueError(
                    "bake queues contain different names for the same map id"
                )
            existing_rank = _QUEUE_STATE_RANK[str(existing["state"])]
            candidate_rank = _QUEUE_STATE_RANK[str(item["state"])]
            if candidate_rank == existing_rank:
                raise ValueError(
                    "bake queues contain conflicting records at the same state"
                )
            if candidate_rank > existing_rank:
                queue_by_id[map_id] = item

    audited_maps: list[dict[str, object]] = []
    for profile in profiles:
        readiness = inspect_world_map_profile(profile)
        queued = queue_by_id.get(profile.map_id)
        audited_maps.append({
            "map_id": profile.map_id,
            "internal_name": profile.internal_name,
            "runtime_profile_declared": profile.runtime_profile is not None,
            "runtime_profile_ready": readiness.runtime_profile_ready,
            "semantic_catalog_declared": profile.semantic_catalog is not None,
            "semantic_catalog_ready": readiness.semantic_catalog_ready,
            "structure_index_declared": profile.structure_index is not None,
            "structure_index_ready": readiness.structure_index_ready,
            "structure_access_graph_declared": profile.structure_access_graph is not None,
            "structure_access_graph_ready": readiness.structure_access_graph_ready,
            "topographic_ready": readiness.topographic_ready,
            "autonomous_ready": readiness.autonomous_ready,
            "queue_known": queued is not None,
            "queue_state": None if queued is None else str(queued["state"]),
        })

    return {
        "record_type": "world_map_registry_audit",
        "schema_version": "1.0",
        "client_build": "2.4.3.8606",
        "registry_reference": _relative_reference(registry_path),
        "queue_reference": ";".join(
            _relative_reference(path) for path in resolved_queue_paths
        ),
        "queue_references": [
            _relative_reference(path) for path in resolved_queue_paths
        ],
        "inventory_map_count": int(inventory["map_count"]),
        "registry_map_count": len(profiles),
        "queue_map_count": len(queue_by_id),
        "queue_complete_map_count": sum(
            item["state"] == "COMPLETE" for item in queue_by_id.values()
        ),
        "topographic_ready_map_count": sum(
            bool(item["topographic_ready"]) for item in audited_maps
        ),
        "autonomous_ready_map_count": sum(
            bool(item["autonomous_ready"]) for item in audited_maps
        ),
        "maps": audited_maps,
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--queue", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_registry_audit_record(
        arguments.registry.resolve(), queue_paths=tuple(arguments.queue),
    )
    ContractValidator(AUDIT_SCHEMA).validate(record)
    if arguments.check:
        if not arguments.output.is_file():
            raise SystemExit(f"audit output is missing: {arguments.output}")
        existing = _read_object(arguments.output)
        if existing != record:
            raise SystemExit("audit output is stale")
    else:
        _atomic_write_json(arguments.output, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
