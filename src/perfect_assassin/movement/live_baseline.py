from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MovementLiveBaselineReport:
    baseline_id: str
    artifact_count: int
    checked_bytes: int
    passed: bool
    failures: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": "movement_live_baseline_verification",
            "schema_version": "1.0",
            "baseline_id": self.baseline_id,
            "artifact_count": self.artifact_count,
            "checked_bytes": self.checked_bytes,
            "passed": self.passed,
            "failures": list(self.failures),
            "execution_authority": False,
        }


def verify_movement_live_baseline(
    record: Mapping[str, Any], *, repository_root: Path
) -> MovementLiveBaselineReport:
    """Verify that reviewed live evidence remains byte-for-byte immutable."""

    root = repository_root.resolve()
    baseline_id = str(record.get("baseline_id", ""))
    failures: list[str] = []
    artifacts = record.get("artifacts")
    if (
        record.get("record_type") != "movement_live_baseline"
        or record.get("schema_version") != "1.0"
        or record.get("review_state") != "OPERATOR_REVIEWED_REFERENCE"
        or record.get("execution_authority") is not False
        or not baseline_id
        or not isinstance(artifacts, list)
        or not artifacts
    ):
        return MovementLiveBaselineReport(
            baseline_id=baseline_id,
            artifact_count=0,
            checked_bytes=0,
            passed=False,
            failures=("invalid_baseline_record",),
        )

    promotion = record.get("promotion_requirements")
    if not isinstance(promotion, Mapping) or (
        promotion.get("minimum_filmed_crypt_exits") != 10
        or promotion.get("require_no_blockage") is not True
        or promotion.get("require_no_regression_against_reference") is not True
        or promotion.get("require_operator_review") is not True
    ):
        failures.append("invalid_promotion_requirements")

    checked_bytes = 0
    seen_paths: set[str] = set()
    for index, raw in enumerate(artifacts):
        if not isinstance(raw, Mapping):
            failures.append(f"artifact_{index}:invalid_record")
            continue
        relative = raw.get("path")
        if not isinstance(relative, str) or not relative:
            failures.append(f"artifact_{index}:invalid_path")
            continue
        normalized = PurePosixPath(relative.replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            failures.append(f"artifact_{index}:path_outside_repository")
            continue
        relative_key = normalized.as_posix()
        if relative_key in seen_paths:
            failures.append(f"artifact_{index}:duplicate_path")
            continue
        seen_paths.add(relative_key)
        path = (root / Path(*normalized.parts)).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            failures.append(f"artifact_{index}:path_outside_repository")
            continue
        if not path.is_file():
            failures.append(f"artifact_{index}:missing")
            continue
        expected_bytes = raw.get("bytes")
        expected_hash = raw.get("sha256")
        if not isinstance(expected_bytes, int) or expected_bytes <= 0:
            failures.append(f"artifact_{index}:invalid_size")
            continue
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            failures.append(f"artifact_{index}:invalid_sha256")
            continue
        actual_bytes = path.stat().st_size
        checked_bytes += actual_bytes
        if actual_bytes != expected_bytes:
            failures.append(f"artifact_{index}:size_mismatch")
            continue
        if _sha256(path) != expected_hash:
            failures.append(f"artifact_{index}:sha256_mismatch")
            continue
        if raw.get("role") == "LIVE_RESULT":
            _verify_result_expectations(raw, path, index, failures)
        elif raw.get("role") != "REVIEW_VIDEO":
            failures.append(f"artifact_{index}:invalid_role")

    return MovementLiveBaselineReport(
        baseline_id=baseline_id,
        artifact_count=len(artifacts),
        checked_bytes=checked_bytes,
        passed=not failures,
        failures=tuple(failures),
    )


def _verify_result_expectations(
    artifact: Mapping[str, Any],
    path: Path,
    index: int,
    failures: list[str],
) -> None:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        failures.append(f"artifact_{index}:invalid_result_json")
        return
    expected = (
        ("status", "expected_status"),
        ("control_frames", "expected_control_frames"),
        ("recovery_attempts", "expected_recovery_attempts"),
    )
    for result_field, baseline_field in expected:
        if result.get(result_field) != artifact.get(baseline_field):
            failures.append(f"artifact_{index}:{result_field}_mismatch")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["MovementLiveBaselineReport", "verify_movement_live_baseline"]
