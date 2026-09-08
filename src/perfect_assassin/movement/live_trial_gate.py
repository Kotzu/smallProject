from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from perfect_assassin.movement.live_trace_quality import evaluate_live_steering_trace


@dataclass(frozen=True, slots=True)
class MovementLiveTrialGateReport:
    baseline_id: str
    required_trial_count: int
    declared_trial_count: int
    valid_trial_count: int
    promotion_eligible: bool
    failures: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": "movement_live_trial_gate",
            "schema_version": "1.0",
            **asdict(self),
            "failures": list(self.failures),
            "execution_authority": False,
        }


def verify_movement_live_trials(
    record: Mapping[str, Any],
    *,
    repository_root: Path,
    expected_baseline_id: str,
) -> MovementLiveTrialGateReport:
    root = repository_root.resolve()
    failures: list[str] = []
    trials = record.get("trials")
    baseline_id = str(record.get("baseline_id", ""))
    required = record.get("required_trial_count")
    if (
        record.get("record_type") != "movement_live_trial_set"
        or record.get("schema_version") != "1.0"
        or record.get("execution_authority") is not False
        or baseline_id != expected_baseline_id
        or required != 10
        or not isinstance(trials, list)
        or len(trials) > 100
    ):
        return MovementLiveTrialGateReport(
            baseline_id=baseline_id,
            required_trial_count=10,
            declared_trial_count=0,
            valid_trial_count=0,
            promotion_eligible=False,
            failures=("invalid_trial_set",),
        )

    seen_ids: set[str] = set()
    seen_artifacts: set[str] = set()
    valid_count = 0
    for index, raw_trial in enumerate(trials):
        prefix = f"trial_{index}"
        before = len(failures)
        if not isinstance(raw_trial, Mapping):
            failures.append(f"{prefix}:invalid_record")
            continue
        trial_id = raw_trial.get("trial_id")
        if not isinstance(trial_id, str) or not trial_id or trial_id in seen_ids:
            failures.append(f"{prefix}:invalid_or_duplicate_id")
        else:
            seen_ids.add(trial_id)
        if raw_trial.get("operator_review") != "PASS":
            failures.append(f"{prefix}:operator_review_not_passed")
        if raw_trial.get("no_blockage") is not True:
            failures.append(f"{prefix}:blockage_not_rejected")
        if raw_trial.get("no_regression_against_reference") is not True:
            failures.append(f"{prefix}:baseline_regression_not_rejected")

        result_path = _verify_artifact(
            raw_trial.get("result"), root, seen_artifacts, prefix, "result", failures,
        )
        video_path = _verify_artifact(
            raw_trial.get("video"), root, seen_artifacts, prefix, "video", failures,
        )
        stationary_path = _verify_artifact(
            raw_trial.get("stationary_validation"), root, seen_artifacts,
            prefix, "stationary", failures,
        )
        if video_path is not None and video_path.suffix.lower() != ".mp4":
            failures.append(f"{prefix}:video_not_mp4")
        if result_path is not None:
            _verify_result(result_path, prefix, failures)
        if stationary_path is not None:
            _verify_stationary(stationary_path, prefix, failures)
        if len(failures) == before:
            valid_count += 1

    if valid_count < required:
        failures.append("minimum_filmed_trials_not_met")
    return MovementLiveTrialGateReport(
        baseline_id=baseline_id,
        required_trial_count=required,
        declared_trial_count=len(trials),
        valid_trial_count=valid_count,
        promotion_eligible=valid_count >= required and not failures,
        failures=tuple(failures),
    )


def _verify_artifact(
    raw: object,
    root: Path,
    seen: set[str],
    prefix: str,
    label: str,
    failures: list[str],
) -> Path | None:
    if not isinstance(raw, Mapping):
        failures.append(f"{prefix}:{label}_artifact_invalid")
        return None
    relative = raw.get("path")
    expected_bytes = raw.get("bytes")
    expected_hash = raw.get("sha256")
    if (
        not isinstance(relative, str)
        or not relative
        or not isinstance(expected_bytes, int)
        or expected_bytes <= 0
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
    ):
        failures.append(f"{prefix}:{label}_artifact_invalid")
        return None
    normalized = PurePosixPath(relative.replace("\\", "/"))
    key = normalized.as_posix()
    if normalized.is_absolute() or ".." in normalized.parts or key in seen:
        failures.append(f"{prefix}:{label}_artifact_path_invalid")
        return None
    seen.add(key)
    path = (root / Path(*normalized.parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        failures.append(f"{prefix}:{label}_artifact_path_invalid")
        return None
    if not path.is_file():
        failures.append(f"{prefix}:{label}_artifact_missing")
        return None
    if path.stat().st_size != expected_bytes or _sha256(path) != expected_hash:
        failures.append(f"{prefix}:{label}_artifact_changed")
        return None
    return path


def _verify_result(path: Path, prefix: str, failures: list[str]) -> None:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        quality = evaluate_live_steering_trace(
            result,
            require_client_facing_source=True,
            require_body_camera_separation=True,
            require_camera_integrity=True,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        failures.append(f"{prefix}:result_invalid")
        return
    if result.get("status") != "ARRIVED":
        failures.append(f"{prefix}:destination_not_reached")
    recovery_attempts = result.get("recovery_attempts")
    if not isinstance(recovery_attempts, int) or recovery_attempts > 1:
        failures.append(f"{prefix}:more_recoveries_than_baseline")
    if not quality.passed:
        failures.append(f"{prefix}:steering_quality_failed")


def _verify_stationary(path: Path, prefix: str, failures: list[str]) -> None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        failures.append(f"{prefix}:stationary_validation_invalid")
        return
    if (
        record.get("record_type") != "stationary_pose_validation"
        or record.get("passed") is not True
        or record.get("position_source") != "COORDINATE_HUD"
        or record.get("facing_source") not in {
            "COORDINATE_HUD_EXACT",
            "MINIMAP_VISION_FALLBACK",
        }
        or record.get("expected_location_id") != "landmark:deathknell-crypt"
        or record.get("expected_map_name") != "Azeroth"
        or record.get("expected_coordinate_system") != "tbc243_client_world_xy"
        or record.get("within_expected_location") is not True
        or record.get("execution_authority") is not False
    ):
        failures.append(f"{prefix}:stationary_validation_failed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["MovementLiveTrialGateReport", "verify_movement_live_trials"]
