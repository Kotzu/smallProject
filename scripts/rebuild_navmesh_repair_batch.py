from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence
import uuid


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts.audit_navmesh_geometry import _verify_namigator_adt
from perfect_assassin.contract_validation import ContractValidator


BATCH_EVIDENCE_SCHEMA = ROOT / "contracts" / "navmesh-repair-batch-evidence.schema.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def parse_adt_artifact(name: str) -> tuple[int, int]:
    if not name.endswith(".nav"):
        raise ValueError(f"not a nav artifact: {name!r}")
    parts = name[:-4].split("_")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"nav artifact is not an ADT coordinate: {name!r}")
    return int(parts[0]), int(parts[1])


def validate_nav(path: Path, *, map_name: str) -> tuple[int, int]:
    adt_x, adt_y = parse_adt_artifact(path.name)
    return _verify_namigator_adt(
        map_name=map_name,
        artifact=path.name,
        payload=path.read_bytes(),
        expected_adt_x=adt_x,
        expected_adt_y=adt_y,
    )


def builder_command(
    *, builder: Path, data_root: Path, output_root: Path,
    map_name: str, adt_x: int, adt_y: int, log_level: int,
) -> list[str]:
    return [
        str(builder), "-d", str(data_root), "-m", map_name,
        "-o", str(output_root), "-t", "1", "-l", str(log_level),
        "-x", str(adt_x), "-y", str(adt_y),
    ]


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def process_artifact(
    artifact: str,
    *,
    source_nav_directory: Path,
    destination_nav_directory: Path,
    work_root: Path,
    builder: Path,
    data_root: Path,
    map_name: str,
    log_level: int,
) -> dict[str, Any]:
    started = time.monotonic()
    adt_x, adt_y = parse_adt_artifact(artifact)
    source = source_nav_directory / artifact
    destination = destination_nav_directory / artifact
    if not source.is_file():
        raise FileNotFoundError(f"missing repair source: {source}")

    if destination.is_file():
        detour_count, empty_count = validate_nav(destination, map_name=map_name)
        return {
            "artifact": artifact,
            "action": "resumed_valid",
            "source_sha256": _sha256(source),
            "result_sha256": _sha256(destination),
            "detour_tile_count": detour_count,
            "empty_inner_tile_count": empty_count,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }

    source_sha256 = _sha256(source)
    try:
        detour_count, empty_count = validate_nav(source, map_name=map_name)
    except Exception as source_error:
        previous_candidates = sorted(
            (work_root / artifact[:-4]).glob(
                f"attempt-*/Nav/{map_name}/{artifact}"
            ),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for candidate in previous_candidates:
            try:
                detour_count, empty_count = validate_nav(candidate, map_name=map_name)
            except Exception:
                continue
            _atomic_copy(candidate, destination)
            if _sha256(candidate) != _sha256(destination):
                raise RuntimeError(
                    f"recovered bytes changed for {artifact}"
                ) from source_error
            return {
                "artifact": artifact,
                "action": "recovered_valid",
                "source_sha256": source_sha256,
                "source_failure": str(source_error),
                "result_sha256": _sha256(destination),
                "detour_tile_count": detour_count,
                "empty_inner_tile_count": empty_count,
                "build_log": str((candidate.parents[2] / "build.log").resolve()),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }

        attempt = work_root / artifact[:-4] / f"attempt-{uuid.uuid4().hex}"
        attempt.mkdir(parents=True, exist_ok=False)
        log_path = attempt / "build.log"
        command = builder_command(
            builder=builder,
            data_root=data_root,
            output_root=attempt,
            map_name=map_name,
            adt_x=adt_x,
            adt_y=adt_y,
            log_level=log_level,
        )
        with log_path.open("w", encoding="utf-8", newline="\n") as log:
            completed = subprocess.run(
                command,
                cwd=builder.parent,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if completed.returncode != 0:
            raise RuntimeError(
                f"builder failed for {artifact} with exit {completed.returncode}; "
                f"see {log_path}"
            ) from source_error
        candidate = attempt / "Nav" / map_name / artifact
        if not candidate.is_file():
            raise RuntimeError(
                f"builder emitted no candidate for {artifact}"
            ) from source_error
        detour_count, empty_count = validate_nav(candidate, map_name=map_name)
        _atomic_copy(candidate, destination)
        if _sha256(candidate) != _sha256(destination):
            raise RuntimeError(
                f"promoted bytes changed for {artifact}"
            ) from source_error
        return {
            "artifact": artifact,
            "action": "rebuilt",
            "source_sha256": source_sha256,
            "source_failure": str(source_error),
            "result_sha256": _sha256(destination),
            "detour_tile_count": detour_count,
            "empty_inner_tile_count": empty_count,
            "build_log": str(log_path.resolve()),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }

    _atomic_copy(source, destination)
    if source_sha256 != _sha256(destination):
        raise RuntimeError(f"copied bytes changed for {artifact}")
    return {
        "artifact": artifact,
        "action": "copied_valid",
        "source_sha256": source_sha256,
        "result_sha256": source_sha256,
        "detour_tile_count": detour_count,
        "empty_inner_tile_count": empty_count,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def _write_json_atomic(path: Path, value: object) -> None:
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
        Path(temporary_name).unlink(missing_ok=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild only structurally invalid Namigator ADTs in parallel.",
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--builder", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--map-name", default="Azeroth")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--log-level", type=int, default=2)
    parser.add_argument("--evidence", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must be between 1 and 16")
    if not args.builder.is_file() or not args.data_root.is_dir():
        raise FileNotFoundError("builder or client data root does not exist")
    source_nav = args.source_root.resolve() / "Nav" / args.map_name
    destination_nav = args.destination_root.resolve() / "Nav" / args.map_name
    artifacts = sorted(path.name for path in source_nav.glob("*.nav") if path.is_file())
    if not artifacts:
        raise ValueError("repair source contains no nav artifacts")
    destination_nav.mkdir(parents=True, exist_ok=True)
    args.work_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_artifact,
                artifact,
                source_nav_directory=source_nav,
                destination_nav_directory=destination_nav,
                work_root=args.work_root.resolve(),
                builder=args.builder.resolve(),
                data_root=args.data_root.resolve(),
                map_name=args.map_name,
                log_level=args.log_level,
            ): artifact
            for artifact in artifacts
        }
        completed_count = 0
        for future in as_completed(futures):
            artifact = futures[future]
            completed_count += 1
            try:
                result = future.result()
            except Exception as error:
                failures.append({"artifact": artifact, "error": str(error)})
                print(f"FAIL {artifact}: {error}", flush=True)
            else:
                results.append(result)
                print(
                    f"PASS {artifact}: {result['action']} "
                    f"({completed_count}/{len(artifacts)})",
                    flush=True,
                )

    actual = {path.name for path in destination_nav.glob("*.nav") if path.is_file()}
    expected = set(artifacts)
    if actual != expected:
        for artifact in sorted(expected - actual):
            if not any(item["artifact"] == artifact for item in failures):
                failures.append({"artifact": artifact, "error": "missing destination artifact"})
        for artifact in sorted(actual - expected):
            failures.append({"artifact": artifact, "error": "undeclared destination artifact"})

    evidence = {
        "record_type": "navmesh_repair_batch_evidence",
        "schema_version": "1.0",
        "status": "PASS" if not failures else "FAIL",
        "map_name": args.map_name,
        "source_root": str(args.source_root.resolve()),
        "destination_root": str(args.destination_root.resolve()),
        "builder": str(args.builder.resolve()),
        "builder_sha256": _sha256(args.builder.resolve()),
        "expected_artifact_count": len(artifacts),
        "validated_artifact_count": len(results),
        "results": sorted(results, key=lambda item: item["artifact"]),
        "failures": sorted(failures, key=lambda item: item["artifact"]),
        "execution_authority": False,
    }
    ContractValidator(BATCH_EVIDENCE_SCHEMA).validate(evidence)
    evidence_path = args.evidence or (
        args.destination_root / "navmesh-repair-batch-evidence.json"
    )
    _write_json_atomic(evidence_path.resolve(), evidence)
    print(json.dumps({
        "status": evidence["status"],
        "expected": len(artifacts),
        "validated": len(results),
        "failures": len(failures),
        "evidence": str(evidence_path.resolve()),
    }), flush=True)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
