"""Audit retained screenshots against candidate player-anchor profiles.

This is an offline diagnostic.  It uses ffmpeg only to decode image files and
never opens WoW, sends input, or changes a profile.  A live profile is not
promoted by this command; it only reports the detector state and errors.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations" / "windows-capture"))

from player_actor_detector import (  # type: ignore[import-not-found]
    PlayerActorAnchorDetector,
    PlayerActorAnchorError,
    load_profile,
)


def audit_frames(
    frames: Iterable[tuple[str, np.ndarray]],
    profile_paths: Iterable[Path],
) -> dict[str, Any]:
    """Run one or more profiles over already-decoded BGRA frames."""

    frame_list = list(frames)
    profiles = []
    for path in profile_paths:
        profile = load_profile(path)
        profiles.append((str(path), profile, PlayerActorAnchorDetector(profile)))
    records: dict[str, dict[str, Any]] = {
        path: {
            "profile": profile["profile"],
            "profile_version": profile["profile_version"],
            "detector_deadline_ms": profile["detector_deadline_ms"],
            "state_counts": Counter(),
            "error_counts": Counter(),
            "error_frames": [],
            "frame_count": 0,
        }
        for path, profile, _detector in profiles
    }
    for frame_name, frame in frame_list:
        for path, _profile, detector in profiles:
            record = records[path]
            record["frame_count"] += 1
            try:
                observation = detector.detect(frame, observed_at_s=0.0)
            except PlayerActorAnchorError as error:
                record["error_counts"][type(error).__name__] += 1
                record["error_frames"].append(frame_name)
            else:
                record["state_counts"][observation["tracking_state"]] += 1
    for record in records.values():
        record["state_counts"] = dict(record["state_counts"])
        record["error_counts"] = dict(record["error_counts"])
    return {
        "record_type": "player_actor_frame_audit",
        "schema_version": "0.1",
        "frame_names": [name for name, _frame in frame_list],
        "profiles": records,
        "input_emitted": False,
        "execution_authority": False,
        "server_truth_used": False,
    }


def _input_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    extensions = {".png", ".jpg", ".jpeg"}
    for path in paths:
        if path.is_dir():
            files.extend(
                item
                for item in sorted(path.rglob("*"))
                if item.is_file() and item.suffix.lower() in extensions
            )
        elif path.is_file() and path.suffix.lower() in extensions:
            files.append(path)
    return files


def _decode_image(path: Path) -> np.ndarray:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    width, height = (int(value) for value in probe.stdout.strip().split(","))
    decoded = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgra",
            "-vframes",
            "1",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    ).stdout
    expected = width * height * 4
    if len(decoded) != expected:
        raise RuntimeError(f"decoded image size mismatch for {path}")
    return np.frombuffer(decoded, dtype=np.uint8).reshape((height, width, 4))


def audit_files(paths: Iterable[Path], profile_paths: Iterable[Path]) -> dict[str, Any]:
    """Decode files one at a time and audit them without retaining pixels."""

    files = _input_files(paths)
    profiles = []
    for path in profile_paths:
        profile = load_profile(path)
        profiles.append((str(path), profile, PlayerActorAnchorDetector(profile)))
    records: dict[str, dict[str, Any]] = {
        path: {
            "profile": profile["profile"],
            "profile_version": profile["profile_version"],
            "detector_deadline_ms": profile["detector_deadline_ms"],
            "state_counts": Counter(),
            "error_counts": Counter(),
            "error_frames": [],
            "frame_count": 0,
        }
        for path, profile, _detector in profiles
    }
    errors: Counter[str] = Counter()
    for path in files:
        try:
            frame = _decode_image(path)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
            errors[type(error).__name__] += 1
            continue
        for profile_path, _profile, detector in profiles:
            record = records[profile_path]
            record["frame_count"] += 1
            try:
                observation = detector.detect(frame, observed_at_s=0.0)
            except PlayerActorAnchorError as error:
                record["error_counts"][type(error).__name__] += 1
                record["error_frames"].append(path.name)
            else:
                record["state_counts"][observation["tracking_state"]] += 1
    for record in records.values():
        record["state_counts"] = dict(record["state_counts"])
        record["error_counts"] = dict(record["error_counts"])
    return {
        "record_type": "player_actor_frame_audit",
        "schema_version": "0.1",
        "input_file_count": len(files),
        "decode_error_counts": dict(errors),
        "profiles": records,
        "input_emitted": False,
        "execution_authority": False,
        "server_truth_used": False,
    }


def audit_files_with_deadline(
    paths: Iterable[Path],
    profile_paths: Iterable[Path],
    *,
    deadline_override_ms: float | None = None,
) -> dict[str, Any]:
    """Audit files, optionally overriding the deadline for offline comparison."""

    if deadline_override_ms is not None and (
        not isinstance(deadline_override_ms, (int, float))
        or isinstance(deadline_override_ms, bool)
        or not math.isfinite(float(deadline_override_ms))
        or not 0.1 <= float(deadline_override_ms) <= 100.0
    ):
        raise ValueError("deadline override must be between 0.1 and 100 ms")
    if deadline_override_ms is None:
        return audit_files(paths, profile_paths)

    files = _input_files(paths)
    profiles = []
    for path in profile_paths:
        loaded = load_profile(path)
        profile = dict(loaded)
        profile["detector_deadline_ms"] = float(deadline_override_ms)
        profiles.append((str(path), profile, PlayerActorAnchorDetector(profile)))
    records: dict[str, dict[str, Any]] = {
        path: {
            "profile": profile["profile"],
            "profile_version": profile["profile_version"],
            "configured_deadline_ms": profile["detector_deadline_ms"],
            "source_profile_deadline_ms": load_profile(Path(path))["detector_deadline_ms"],
            "state_counts": Counter(),
            "error_counts": Counter(),
            "error_frames": [],
            "frame_count": 0,
        }
        for path, profile, _detector in profiles
    }
    errors: Counter[str] = Counter()
    for path in files:
        try:
            frame = _decode_image(path)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
            errors[type(error).__name__] += 1
            continue
        for profile_path, _profile, detector in profiles:
            record = records[profile_path]
            record["frame_count"] += 1
            try:
                observation = detector.detect(frame, observed_at_s=0.0)
            except PlayerActorAnchorError as error:
                record["error_counts"][type(error).__name__] += 1
                record["error_frames"].append(path.name)
            else:
                record["state_counts"][observation["tracking_state"]] += 1
    for record in records.values():
        record["state_counts"] = dict(record["state_counts"])
        record["error_counts"] = dict(record["error_counts"])
    return {
        "record_type": "player_actor_frame_audit",
        "schema_version": "0.1",
        "input_file_count": len(files),
        "decode_error_counts": dict(errors),
        "deadline_override_ms": float(deadline_override_ms),
        "profiles": records,
        "input_emitted": False,
        "execution_authority": False,
        "server_truth_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit player-anchor screenshots offline.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        type=Path,
        required=True,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--deadline-ms", type=float)
    arguments = parser.parse_args()
    report = audit_files_with_deadline(
        arguments.paths,
        arguments.profiles,
        deadline_override_ms=arguments.deadline_ms,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
