from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = (
    Path(r"C:\Users\LabUser\Videos\NVIDIA\Wow.exe"),
    ROOT / "data" / "runtime" / "movement-lab" / "demonstration-video",
)
DEFAULT_OUTPUT = ROOT / "data" / "runtime" / "video-retention" / "latest.json"
VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".webm"}


def _duration_seconds(path: Path) -> float | None:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", "--", str(path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=15.0,
        check=False,
        creationflags=(0x08000000 if os.name == "nt" else 0),
    )
    try:
        return float(completed.stdout.strip()) if completed.returncode == 0 else None
    except ValueError:
        return None


def _documentation_text() -> str:
    chunks: list[str] = []
    for path in (ROOT / "docs").rglob("*.md"):
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def _complete_demonstration_videos() -> set[Path]:
    result: set[Path] = set()
    directory = ROOT / "data" / "runtime" / "movement-lab" / "demonstrations"
    for manifest in directory.glob("*/manifest.json"):
        try:
            record = json.loads(manifest.read_text(encoding="utf-8"))
            if record.get("status") == "COMPLETE" and record.get("video_path"):
                result.add(Path(str(record["video_path"])).resolve())
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return result


def build_manifest(sources: tuple[Path, ...]) -> dict[str, object]:
    files = sorted(
        (
            path
            for source in sources if source.is_dir()
            for path in source.rglob("*")
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
        ),
        key=lambda path: str(path).lower(),
    )
    documentation = _documentation_text()
    complete = _complete_demonstration_videos()
    with ThreadPoolExecutor(max_workers=8) as executor:
        durations = tuple(executor.map(_duration_seconds, files))
    records: list[dict[str, object]] = []
    for path, duration_s in zip(files, durations, strict=True):
        resolved = path.resolve()
        referenced = path.name in documentation
        complete_demonstration = resolved in complete
        if path.stat().st_size == 0:
            decision = "DELETE_ZERO_BYTE"
        elif complete_demonstration:
            decision = "KEEP_COMPLETE_DEMONSTRATION"
        elif referenced:
            decision = "KEEP_REFERENCED_EVIDENCE"
        elif duration_s is not None and duration_s >= 1800.0:
            decision = "REVIEW_OVERSIZED_UNREFERENCED"
        else:
            decision = "REVIEW_UNREFERENCED"
        records.append({
            "path": str(resolved),
            "bytes": path.stat().st_size,
            "duration_s": duration_s,
            "referenced_in_docs": referenced,
            "complete_demonstration": complete_demonstration,
            "decision": decision,
        })
    summary: dict[str, dict[str, int]] = {}
    for record in records:
        bucket = summary.setdefault(
            str(record["decision"]), {"file_count": 0, "bytes": 0},
        )
        bucket["file_count"] += 1
        bucket["bytes"] += int(record["bytes"])
    return {
        "record_type": "movement_video_retention_manifest",
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy": (
            "Nothing is deleted by this audit. COMPLETE demonstrations and "
            "documentation-referenced evidence are retained automatically."
        ),
        "sources": [str(path.resolve()) for path in sources],
        "summary": summary,
        "videos": records,
    }


def _write_json_atomic(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        temporary.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Predator movement videos without deleting them.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_manifest(DEFAULT_SOURCES)
    _write_json_atomic(args.output, manifest)
    print(json.dumps(manifest["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
