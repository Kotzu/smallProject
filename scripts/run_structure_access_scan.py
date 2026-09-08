from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import json
import os
from pathlib import Path
from queue import Queue
import sys
import tempfile
import time
from typing import Any, Callable, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "integrations" / "windows-input"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from client_navmesh_backend import ClientAssetNavmeshQuery
from persistent_navmesh_awareness import PersistentNavmeshAwarenessService
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    NavCorridor,
    NavPoint,
)
from perfect_assassin.movement.local_environment_awareness import (
    build_local_environment_awareness,
)
from perfect_assassin.movement.structure_access_scan_observation import (
    build_scan_observation_record,
    collision_probe_record,
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
INCOMPLETE_STATIC_AWARENESS_ERRORS = frozenset({
    "start awareness physical surfaces are empty",
    "local surface transition semantics are invalid",
})
MAX_PROBES_PER_RUN = 100_000


class PersistentAwarenessPool:
    """Bound concurrent queries to long-lived, map-loaded worker processes."""

    def __init__(
        self, *, worker: Path, nav_root: Path, map_name: str, size: int,
    ) -> None:
        if not 1 <= size <= 4:
            raise ValueError("persistent awareness pool size is invalid")
        self._services: list[PersistentNavmeshAwarenessService] = []
        self._available: Queue[PersistentNavmeshAwarenessService] = Queue()
        try:
            for _ in range(size):
                service = PersistentNavmeshAwarenessService(
                    worker=worker, nav_root=nav_root, map_name=map_name,
                )
                self._services.append(service)
                self._available.put(service)
        except Exception:
            self.close()
            raise

    def sample(
        self, requested: NavPoint,
    ) -> tuple[NavPoint, LocalStaticAwareness]:
        service = self._available.get()
        try:
            sample = service.sample(requested.x, requested.y, requested.z)
            return sample.resolved, sample.awareness
        finally:
            self._available.put(service)

    def close(self) -> None:
        for service in self._services:
            service.close()
        self._services.clear()


def _bounded_parallel_results(
    executor: ThreadPoolExecutor,
    items: Sequence[Any],
    function: Callable[[Any], Any],
    *,
    maximum_in_flight: int,
) -> Iterator[tuple[Any, Any]]:
    """Yield completed work without scheduling an entire world scan at once."""
    if maximum_in_flight < 1:
        raise ValueError("maximum in-flight work is invalid")
    iterator = iter(items)
    active: dict[Future[Any], Any] = {}

    def submit_one() -> bool:
        try:
            item = next(iterator)
        except StopIteration:
            return False
        active[executor.submit(function, item)] = item
        return True

    while len(active) < maximum_in_flight and submit_one():
        pass
    while active:
        completed, _ = wait(tuple(active), return_when=FIRST_COMPLETED)
        for future in completed:
            item = active.pop(future)
            yield item, future.result()
            submit_one()


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


def _fragment_paths(output_dir: Path, seed_id: str) -> tuple[Path, Path]:
    suffix = seed_id.removeprefix("seed:")
    if len(suffix) != 24 or any(character not in "0123456789abcdef" for character in suffix):
        raise ValueError("scan seed ID is invalid")
    return (
        output_dir / f"seed-{suffix}.observation.json",
        output_dir / f"seed-{suffix}.awareness.json",
    )


def _verify_existing(
    fragment_path: Path,
    *,
    plan: Mapping[str, Any],
    task: Mapping[str, Any],
    seed: Mapping[str, Any],
    local_validator: ContractValidator,
    fragment_validator: ContractValidator,
) -> Mapping[str, Any]:
    record = load_scan_observation(
        fragment_path,
        schema_path=OBSERVATION_SCHEMA,
        plan=plan,
        validator=fragment_validator,
    )
    if (
        record["task_id"] != task["task_id"]
        or record["seed_id"] != seed["seed_id"]
        or record["expected_structure_id"] != task["structure_id"]
        or record["requested_position"] != seed["position"]
    ):
        raise ValueError("existing scan fragment does not match its planned seed")
    artifact = record["awareness_artifact"]
    if artifact is not None:
        awareness_path = fragment_path.parent / str(artifact)
        awareness_record = json.loads(awareness_path.read_text(encoding="utf-8"))
        local_validator.validate(awareness_record)
        if file_sha256(awareness_path) != record["awareness_sha256"]:
            raise ValueError("existing scan awareness hash mismatch")
    return record


def _query_corridor(
    navigator: ClientAssetNavmeshQuery,
    *,
    map_name: str,
    requested: NavPoint,
) -> tuple[NavCorridor | None, Exception | None]:
    try:
        return (
            navigator.find_corridor(
                map_name=map_name,
                start=requested,
                stop_x=requested.x + 1.0,
                stop_y=requested.y,
            ),
            None,
        )
    except Exception as error:
        return None, error


def _query_static_awareness(
    navigator: ClientAssetNavmeshQuery,
    *,
    persistent_pool: PersistentAwarenessPool | None,
    map_name: str,
    requested: NavPoint,
) -> tuple[NavPoint | None, LocalStaticAwareness | None, Exception | None, str]:
    """Resolve one seed while preserving exact one-shot error classification."""
    if persistent_pool is not None:
        try:
            resolved, awareness = persistent_pool.sample(requested)
            return resolved, awareness, None, "PERSISTENT_AWARENESS"
        except Exception:
            # The persistent protocol intentionally exposes no internal error
            # detail. Retry once through the strict corridor adapter so a
            # genuine no-nav seed cannot be hidden as a generic worker error.
            fallback_source = "ONE_SHOT_CLASSIFICATION_FALLBACK"
    else:
        fallback_source = "ONE_SHOT_CORRIDOR"

    corridor, error = _query_corridor(
        navigator, map_name=map_name, requested=requested,
    )
    if error is not None:
        return None, None, error, fallback_source
    if corridor is None:
        return (
            None, None, ValueError("Detour worker returned no corridor"),
            fallback_source,
        )
    if corridor.start_awareness is None:
        return (
            corridor.start, None,
            ValueError("Detour worker returned no local awareness"),
            fallback_source,
        )
    return corridor.start, corridor.start_awareness, None, fallback_source


def _failure_status(error: Exception) -> str:
    detail = str(error)
    if (
        "corridor endpoint has no polygon" in detail
        or "find_heights failed with result 84" in detail
    ):
        return "REJECTED_NO_NAV_POLYGON"
    if detail in INCOMPLETE_STATIC_AWARENESS_ERRORS:
        return "REJECTED_INCOMPLETE_STATIC_AWARENESS"
    return "PROBE_ERROR"


def _scan_exit_code(*, probe_error_count: int, fail_on_probe_error: bool) -> int:
    return 2 if fail_on_probe_error and probe_error_count else 0


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a bounded, resumable, read-only Detour/BVH batch from a "
            "generic structure access scan plan."
        )
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-probes", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--structure-id")
    parser.add_argument("--nearby-radius", type=float, default=100.0)
    parser.add_argument("--retry-probe-errors", action="store_true")
    parser.add_argument("--fail-on-probe-error", action="store_true")
    parser.add_argument(
        "--persistent-awareness-worker", action="store_true",
        help=(
            "keep one map-loaded read-only awareness worker per job; every "
            "persistent failure is classified by the one-shot adapter"
        ),
    )
    args = parser.parse_args(argv)
    if not 1 <= args.max_probes <= MAX_PROBES_PER_RUN:
        parser.error(
            f"--max-probes must be between 1 and {MAX_PROBES_PER_RUN}"
        )
    if not 1 <= args.jobs <= 4:
        parser.error("--jobs must be between 1 and 4")
    if not 1.0 <= args.nearby_radius <= 1_000.0:
        parser.error("--nearby-radius must be between 1 and 1000 yards")

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
    tasks = [
        item for item in plan["tasks"]
        if args.structure_id is None or item["structure_id"] == args.structure_id
    ]
    if not tasks:
        raise ValueError("requested structure has no eligible scan task")

    output_dir = args.output_dir.resolve()
    if output_dir.exists() and (not output_dir.is_dir() or output_dir.is_symlink()):
        raise ValueError("scan output must be a real directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    navigator = ClientAssetNavmeshQuery(
        worker=args.worker,
        nav_root=binding.pack.nav_root,
    )
    local_validator = ContractValidator(LOCAL_AWARENESS_SCHEMA)
    fragment_validator = ContractValidator(OBSERVATION_SCHEMA)
    records: list[Mapping[str, Any]] = []
    pending: list[
        tuple[Mapping[str, Any], Mapping[str, Any], Path, Path, NavPoint]
    ] = []

    for task in tasks:
        for seed in task["initial_seeds"]:
            fragment_path, awareness_path = _fragment_paths(
                output_dir, str(seed["seed_id"]),
            )
            if fragment_path.exists():
                existing = _verify_existing(
                    fragment_path,
                    plan=plan,
                    task=task,
                    seed=seed,
                    local_validator=local_validator,
                    fragment_validator=fragment_validator,
                )
                if not (
                    args.retry_probe_errors
                    and existing["status"] == "PROBE_ERROR"
                ):
                    records.append(existing)
                    continue
            if len(pending) >= args.max_probes:
                continue
            requested = NavPoint(*(float(value) for value in seed["position"]))
            pending.append((task, seed, fragment_path, awareness_path, requested))

    def query_pending(
        item: tuple[Mapping[str, Any], Mapping[str, Any], Path, Path, NavPoint],
    ) -> tuple[
        NavPoint | None, LocalStaticAwareness | None, Exception | None, str,
    ]:
        return _query_static_awareness(
            navigator,
            persistent_pool=persistent_pool,
            map_name=str(plan["map_name"]),
            requested=item[4],
        )

    parallel_job_count = min(args.jobs, len(pending))
    worker_count = max(1, parallel_job_count)
    persistent_pool: PersistentAwarenessPool | None = None
    query_source_counts = {
        "PERSISTENT_AWARENESS": 0,
        "ONE_SHOT_CLASSIFICATION_FALLBACK": 0,
        "ONE_SHOT_CORRIDOR": 0,
    }
    try:
        if args.persistent_awareness_worker and pending:
            persistent_pool = PersistentAwarenessPool(
                worker=args.worker,
                nav_root=binding.pack.nav_root,
                map_name=str(plan["map_name"]),
                size=worker_count,
            )
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            completed = _bounded_parallel_results(
                executor,
                pending,
                query_pending,
                maximum_in_flight=max(1, worker_count * 2),
            )
            for item, query_result in completed:
                resolved, nav_awareness, query_error, query_source = query_result
                query_source_counts[query_source] += 1
                task, seed, fragment_path, awareness_path, requested = item
                try:
                    if query_error is not None:
                        raise query_error
                    if resolved is None:
                        raise ValueError("Detour worker returned no resolved point")
                    if nav_awareness is None:
                        raise ValueError("Detour worker returned no local awareness")
                    awareness = build_local_environment_awareness(
                        map_name=str(plan["map_name"]),
                        observed_monotonic_s=time.monotonic(),
                        position=resolved,
                        nav_awareness=nav_awareness,
                        structures=loaded_index.spatial,
                        nearby_radius_yards=args.nearby_radius,
                    )
                    awareness_record = awareness.to_record()
                    local_validator.validate(awareness_record)
                    _atomic_json(awareness_path, awareness_record)
                    actual_structure_ids = sorted(
                        item.structure_id for item in awareness.containing_structures
                    )
                    accepted = (
                        str(task["structure_id"]) in actual_structure_ids
                        and awareness.environment_state == "INSIDE_STATIC_WMO"
                    )
                    record = build_scan_observation_record(
                        plan=plan,
                        task=task,
                        seed=seed,
                        status=(
                            "ACCEPTED_CONTAINED_WMO"
                            if accepted
                            else "REJECTED_EXPECTED_STRUCTURE_NOT_CONFIRMED"
                        ),
                        resolved_position=[resolved.x, resolved.y, resolved.z],
                        actual_structure_ids=actual_structure_ids,
                        awareness_artifact=awareness_path.name,
                        awareness_sha256=file_sha256(awareness_path),
                        collision_probe=collision_probe_record(nav_awareness),
                        failure_reason=(
                            None if accepted
                            else "resolved nav point is not confirmed inside the planned WMO"
                        ),
                    )
                except Exception as error:
                    detail = f"{type(error).__name__}: {str(error)[:400]}"
                    record = build_scan_observation_record(
                        plan=plan,
                        task=task,
                        seed=seed,
                        status=_failure_status(error),
                        resolved_position=None,
                        actual_structure_ids=[],
                        awareness_artifact=None,
                        awareness_sha256=None,
                        collision_probe=None,
                        failure_reason=detail,
                    )
                fragment_validator.validate(record)
                _atomic_json(fragment_path, record)
                records.append(record)
    finally:
        if persistent_pool is not None:
            persistent_pool.close()

    processed_now = len(pending)

    total_seed_count = sum(int(item["initial_seed_count"]) for item in tasks)
    completed_seed_count = len(records)
    counts = {
        status: sum(item["status"] == status for item in records)
        for status in (
            "ACCEPTED_CONTAINED_WMO",
            "REJECTED_EXPECTED_STRUCTURE_NOT_CONFIRMED",
            "REJECTED_NO_NAV_POLYGON",
            "REJECTED_INCOMPLETE_STATIC_AWARENESS",
            "PROBE_ERROR",
        )
    }
    remaining = total_seed_count - completed_seed_count
    print(json.dumps({
        "status": (
            "COMPLETE_FOR_SELECTED_SCOPE"
            if remaining == 0 else "PAUSED_AT_PROBE_BUDGET"
        ),
        "plan_id": plan["plan_id"],
        "selected_structure_count": len(tasks),
        "total_seed_count": total_seed_count,
        "completed_seed_count": completed_seed_count,
        "processed_now": processed_now,
        "parallel_job_count": parallel_job_count,
        "query_mode": (
            "PERSISTENT_AWARENESS_WITH_ONE_SHOT_ERROR_CLASSIFICATION"
            if args.persistent_awareness_worker
            else "ONE_SHOT_CORRIDOR"
        ),
        "query_source_counts": query_source_counts,
        "maximum_in_flight": max(1, worker_count * 2),
        "remaining_seed_count": remaining,
        "accepted_seed_count": counts["ACCEPTED_CONTAINED_WMO"],
        "rejected_seed_count": counts[
            "REJECTED_EXPECTED_STRUCTURE_NOT_CONFIRMED"
        ] + counts["REJECTED_NO_NAV_POLYGON"] + counts[
            "REJECTED_INCOMPLETE_STATIC_AWARENESS"
        ],
        "no_nav_polygon_count": counts["REJECTED_NO_NAV_POLYGON"],
        "incomplete_static_awareness_count": counts[
            "REJECTED_INCOMPLETE_STATIC_AWARENESS"
        ],
        "probe_error_count": counts["PROBE_ERROR"],
        "output_dir": str(output_dir),
        "execution_authority": False,
    }, sort_keys=True))
    return _scan_exit_code(
        probe_error_count=counts["PROBE_ERROR"],
        fail_on_probe_error=args.fail_on_probe_error,
    )


if __name__ == "__main__":
    raise SystemExit(run())
