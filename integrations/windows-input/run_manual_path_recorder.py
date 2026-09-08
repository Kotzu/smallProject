from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from perfect_assassin.movement.manual_path_recording import (
    ManualPathRecorder,
)
from perfect_assassin.movement.movement_lab import MovementLabSnapshot
from perfect_assassin.movement.operator_demonstration import (
    OperatorDemonstrationTimeline,
)
from operator_input_observer import Win32OperatorInputObserver
from run_navmesh_roaming import LiveCoordinatePoseSource, _player_facing, _position


DEFAULT_AUTHORIZATION = (
    ROOT / "data" / "runtime" / "operator" / "tbc_243_lab.active.json"
)
DEFAULT_RECEIPT = (
    ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
)
DEFAULT_CONTROL = (
    ROOT / "data" / "runtime" / "operator" / "manual-path-recorder-control.json"
)
DEFAULT_RESULT = (
    ROOT / "data" / "runtime" / "movement-lab" / "manual-path-recording.json"
)
DEFAULT_TIMELINE = (
    ROOT / "data" / "runtime" / "movement-lab"
    / "manual-movement-demonstration.jsonl"
)
DEFAULT_VIDEO_DIRECTORY = (
    ROOT / "data" / "runtime" / "movement-lab" / "demonstration-video"
)
DEFAULT_EVIDENCE_DIRECTORY = (
    ROOT / "data" / "runtime" / "movement-lab" / "demonstrations"
)
DEFAULT_MOVEMENT_STATE = (
    ROOT / "data" / "runtime" / "movement-lab" / "latest.json"
)


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return value


def _atomic_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(
                record,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            stream.flush()
            os.fsync(stream.fileno())
        # The Control Center polls this file while the recorder publishes it.
        # Most Windows opens share deletion, but a short antivirus/indexer or
        # reader race can transiently deny ReplaceFile semantics.  Keep the
        # already-fsynced temp file and retry the exact atomic replacement.
        for attempt in range(12):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 11:
                    raise
                time.sleep(0.025 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def _stop_requested(path: Path, *, minimum_revision: int) -> bool:
    try:
        record = _read_object(path)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        record.get("schema_version") == "1.0"
        and record.get("command") == "STOP"
        and type(record.get("revision")) is int
        and int(record["revision"]) > minimum_revision
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Record an operator-driven in-game path from the visible coordinate HUD. "
            "This process is read-only and never submits client input."
        )
    )
    parser.add_argument("--session-authorization-file", type=Path, default=DEFAULT_AUTHORIZATION)
    parser.add_argument("--session-receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--control-file", type=Path, default=DEFAULT_CONTROL)
    parser.add_argument("--result-file", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--timeline-file", type=Path, default=DEFAULT_TIMELINE)
    parser.add_argument("--video-directory", type=Path, default=DEFAULT_VIDEO_DIRECTORY)
    parser.add_argument(
        "--evidence-directory", type=Path, default=DEFAULT_EVIDENCE_DIRECTORY
    )
    parser.add_argument("--movement-state-file", type=Path, default=DEFAULT_MOVEMENT_STATE)
    parser.add_argument("--video-fps", type=int, choices=(30, 60), default=30)
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--recording-id", default=f"manual:{uuid4()}")
    parser.add_argument("--name", default="Demonstrație manuală")
    parser.add_argument("--start-revision", type=int, required=True)
    parser.add_argument("--expected-zone-index", type=int, choices=(25,), default=25)
    parser.add_argument("--minimum-spacing-world", type=float, default=0.75)
    parser.add_argument("--maximum-duration-s", type=float, default=1800.0)
    return parser


def _parse_hwnd(value: object) -> int:
    if isinstance(value, str):
        return int(value, 0)
    if type(value) is int:
        return value
    raise RuntimeError("session receipt has no exact client HWND")


def _start_window_video(
    *, directory: Path, recording_id: str, title: str, fps: int,
) -> tuple[subprocess.Popen[str], Path]:
    directory.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", recording_id).strip("-")
    output = directory / f"{safe_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"
    common = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "gdigrab", "-framerate", str(fps),
        "-i", f"title={title}", "-an", "-vf", "scale=2560:-2",
    ]
    # The installed FFmpeg build requires NVENC API 13.1 while the pinned
    # NVIDIA driver exposes 13.0.  Use the verified CPU encoder directly;
    # retrying NVENC would only create a failing helper before every session.
    encoders = (
        ("libx264", ("-c:v", "libx264", "-preset", "ultrafast", "-crf", "23")),
    )
    failures: list[str] = []
    for encoder, arguments in encoders:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(
            [*common, *arguments, "-pix_fmt", "yuv420p", str(output)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=0x08000000,
            startupinfo=startupinfo,
        )
        time.sleep(0.45)
        if process.poll() is None:
            setattr(process, "pa_video_encoder", encoder)
            return process, output
        detail = process.stderr.read().strip() if process.stderr else ""
        failures.append(f"{encoder}: {detail[-250:]}")
    raise RuntimeError("game-window video capture failed: " + " | ".join(failures))


def _stop_window_video(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if process.stdin is not None:
            process.stdin.write("q\n")
            process.stdin.flush()
        process.wait(timeout=8.0)
    except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
        process.terminate()
        try:
            process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            process.kill()


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.start_revision < 1:
        raise SystemExit("--start-revision must be positive")
    if not 10.0 <= args.maximum_duration_s <= 7200.0:
        raise SystemExit("--maximum-duration-s must be in [10, 7200]")
    authorization = _read_object(args.session_authorization_file)
    receipt = _read_object(args.session_receipt)
    expiry = datetime.fromisoformat(
        str(authorization["approval"]["expires_at"]).replace("Z", "+00:00")
    )
    if expiry <= datetime.now(timezone.utc):
        raise SystemExit("session authorization is expired")
    if receipt.get("pid") is None:
        raise SystemExit("session receipt has no client pid")
    target_pid = int(receipt["pid"])
    target_hwnd = _parse_hwnd(receipt.get("hwnd"))
    window_title = str(receipt.get("window_title") or "World of Warcraft")
    safe_recording_id = re.sub(
        r"[^A-Za-z0-9_.-]+", "-", args.recording_id
    ).strip("-")
    evidence_directory = (
        args.evidence_directory
        / f"{safe_recording_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    evidence_directory.mkdir(parents=True, exist_ok=False)
    timeline_path = args.timeline_file
    if timeline_path.resolve() == DEFAULT_TIMELINE.resolve():
        timeline_path = evidence_directory / "timeline.jsonl"

    recorder = ManualPathRecorder(
        recording_id=args.recording_id,
        name=args.name,
        minimum_spacing_world=args.minimum_spacing_world,
    )
    pose_source = LiveCoordinatePoseSource(
        authorization_file=args.session_authorization_file,
        receipt_file=args.session_receipt,
        receipt=receipt,
        session_id=f"session:manual-path:{uuid4()}",
        enforce_combat_handoff=False,
    )
    started = time.monotonic()
    started_ns = time.perf_counter_ns()
    last_publish = 0.0
    last_live_publish = 0.0
    summary_publish_error_count = 0
    timeline = OperatorDemonstrationTimeline(
        timeline_path,
        recording_id=args.recording_id,
        target_pid=target_pid,
        target_hwnd=target_hwnd,
        started_monotonic_ns=started_ns,
    )
    input_observer = Win32OperatorInputObserver(target_hwnd, timeline.append)
    video_process: subprocess.Popen[str] | None = None
    video_path: Path | None = None
    failure: BaseException | None = None
    result = None
    pose_source.open()
    try:
        input_observer.start()
        timeline.append(
            "WINDOW",
            monotonic_ns=time.perf_counter_ns(),
            foreground_matches_target=True,
            payload=input_observer.window_metrics(),
        )
        if not args.no_video:
            video_process, video_path = _start_window_video(
                directory=args.video_directory,
                recording_id=args.recording_id,
                title=window_title,
                fps=args.video_fps,
            )
            timeline.append(
                "VIDEO_START",
                monotonic_ns=time.perf_counter_ns(),
                foreground_matches_target=True,
                payload={
                    "path": str(video_path),
                    "fps": args.video_fps,
                    "capture": "ffmpeg_gdigrab_exact_window",
                    "encoder": getattr(video_process, "pa_video_encoder", "unknown"),
                },
            )
        while True:
            if _stop_requested(args.control_file, minimum_revision=args.start_revision):
                break
            if time.monotonic() - started > args.maximum_duration_s:
                raise RuntimeError("manual path recording reached its bounded duration")
            observation = pose_source.next_observation()
            position = observation.get("position")
            if (
                observation.get("map_position_available") is not True
                or not isinstance(position, dict)
                or position.get("continent_index") != 2
                or position.get("zone_index") != args.expected_zone_index
            ):
                raise RuntimeError(
                    "manual path recorder left the exact Tirisfal atlas context"
                )
            _nx, _ny, world_x, world_y = _position(
                observation, expected_zone_index=args.expected_zone_index
            )
            observed_s = float(observation["timing"]["observed_monotonic_s"])
            observed_facing = _player_facing(observation)
            timeline.append(
                "POSE",
                monotonic_ns=time.perf_counter_ns(),
                foreground_matches_target=True,
                payload={
                    "world_x": world_x,
                    "world_y": world_y,
                    "zone_index": args.expected_zone_index,
                    "observation_monotonic_s": observed_s,
                    "heading_rad": observed_facing,
                    "heading_source": pose_source.latest_facing_source,
                    "input_state": input_observer.snapshot(),
                },
            )
            accepted = recorder.observe(
                x=world_x,
                y=world_y,
                observed_monotonic_s=observed_s,
                observed_facing_rad=observed_facing,
            )
            now = time.monotonic()
            if accepted or now - last_publish >= 0.25:
                try:
                    _atomic_json(args.result_file, recorder.snapshot().to_record())
                except OSError as error:
                    # A diagnostic summary must never own the lifetime of the
                    # raw input/video recorder.  The timeline contains every
                    # pose and can reconstruct the summary after the session.
                    summary_publish_error_count += 1
                    timeline.append(
                        "SUMMARY_PUBLISH_ERROR",
                        monotonic_ns=time.perf_counter_ns(),
                        foreground_matches_target=True,
                        payload={
                            "error_type": type(error).__name__,
                            "error_code": getattr(error, "winerror", None),
                            "count": summary_publish_error_count,
                        },
                    )
                last_publish = now
            if accepted or now - last_live_publish >= 0.10:
                trail = recorder.vertices[-4096:]
                try:
                    _atomic_json(
                        args.movement_state_file,
                        MovementLabSnapshot(
                            observed_monotonic_s=observed_s,
                            tracking_state="LOST",
                            target_identity_crc16=None,
                            target_error_x_normalized=None,
                            player_world_x=world_x,
                            player_world_y=world_y,
                            player_facing_rad=(
                                None if not trail else trail[-1].facing_rad
                            ),
                            controller_state="MANUAL_DEMONSTRATION",
                            traversed_path_world=tuple(
                                (vertex.x, vertex.y) for vertex in trail
                            ),
                        ).to_record(),
                    )
                except OSError:
                    # UI publication is optional and must not interrupt the
                    # authoritative video/input/pose timeline.
                    pass
                last_live_publish = now
            time.sleep(0.02)
    except BaseException as error:
        failure = error
        raise
    finally:
        pose_source.close()
        input_observer.close()
        if video_process is not None:
            timeline.append(
                "VIDEO_STOP",
                monotonic_ns=time.perf_counter_ns(),
                foreground_matches_target=False,
                payload={"path": str(video_path)},
            )
            _stop_window_video(video_process)
        timeline.append(
            "SESSION_STOP",
            monotonic_ns=time.perf_counter_ns(),
            foreground_matches_target=False,
            payload={
                "video_path": None if video_path is None else str(video_path),
                "termination": "ERROR" if failure is not None else "OPERATOR_STOP",
                "error_type": None if failure is None else type(failure).__name__,
                "error": None if failure is None else str(failure),
            },
        )
        timeline.close()
        result = recorder.finish(interrupted=failure is not None)
        _atomic_json(args.result_file, result.to_record())
        evidence_path = evidence_directory / "path.json"
        _atomic_json(evidence_path, result.to_record())
        _atomic_json(
            evidence_directory / "manifest.json",
            {
                "schema_version": "1.0",
                "record_type": "operator_movement_demonstration_manifest",
                "recording_id": args.recording_id,
                "status": result.status,
                "termination": "ERROR" if failure is not None else "OPERATOR_STOP",
                "error_type": None if failure is None else type(failure).__name__,
                "timeline_path": str(timeline_path),
                "path_path": str(evidence_path),
                "video_path": None if video_path is None else str(video_path),
                "execution_authority": False,
            },
        )

    assert result is not None
    # The detached Windows process can inherit a legacy cp1252 stdout even
    # though every persisted artifact is UTF-8.  ASCII escaping keeps this
    # optional one-line diagnostic from failing after a successful save.
    print(json.dumps(result.to_record(), ensure_ascii=True, sort_keys=True))
    return 0 if result.status == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(run())
