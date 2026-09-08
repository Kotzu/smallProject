from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
from threading import Lock
from typing import Any, Mapping, TextIO


SCHEMA_VERSION = "1.0"
RECORD_TYPE = "operator_movement_demonstration_event"
ALLOWED_EVENT_KINDS = {
    "SESSION_START",
    "WINDOW",
    "VIDEO_START",
    "VIDEO_STOP",
    "KEY",
    "MOUSE_BUTTON",
    "MOUSE_MOVE",
    "MOUSE_WHEEL",
    "POSE",
    "SUMMARY_PUBLISH_ERROR",
    "SESSION_STOP",
}


@dataclass(frozen=True, slots=True)
class DemonstrationEvent:
    sequence: int
    kind: str
    monotonic_ns: int
    elapsed_s: float
    foreground_matches_target: bool
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if (
            type(self.sequence) is not int
            or self.sequence < 0
            or self.kind not in ALLOWED_EVENT_KINDS
            or type(self.monotonic_ns) is not int
            or self.monotonic_ns < 0
            or not isfinite(self.elapsed_s)
            or self.elapsed_s < 0
            or type(self.foreground_matches_target) is not bool
            or not isinstance(self.payload, Mapping)
        ):
            raise ValueError("operator demonstration event is invalid")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "record_type": RECORD_TYPE,
            "sequence": self.sequence,
            "kind": self.kind,
            "monotonic_ns": self.monotonic_ns,
            "elapsed_s": self.elapsed_s,
            "foreground_matches_target": self.foreground_matches_target,
            "payload": dict(self.payload),
        }


class OperatorDemonstrationTimeline:
    """Append-only input, pose and video clock shared by one demonstration.

    This class owns no capture or input mechanism. Windows hooks and video live
    at the integration boundary; the movement package only receives timestamped
    observations suitable for replay, comparison and supervised learning.
    """

    def __init__(
        self,
        path: Path,
        *,
        recording_id: str,
        target_pid: int,
        target_hwnd: int,
        started_monotonic_ns: int,
        stream: TextIO | None = None,
    ) -> None:
        if (
            not recording_id
            or type(target_pid) is not int
            or target_pid <= 0
            or type(target_hwnd) is not int
            or target_hwnd <= 0
            or type(started_monotonic_ns) is not int
            or started_monotonic_ns < 0
        ):
            raise ValueError("operator demonstration identity is invalid")
        self.path = path
        self.recording_id = recording_id
        self.target_pid = target_pid
        self.target_hwnd = target_hwnd
        self.started_monotonic_ns = started_monotonic_ns
        self._sequence = 0
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = stream or self.path.open("w", encoding="utf-8", buffering=1)
        self._owns_stream = stream is None
        self.append(
            "SESSION_START",
            monotonic_ns=started_monotonic_ns,
            foreground_matches_target=True,
            payload={
                "recording_id": recording_id,
                "target_pid": target_pid,
                "target_hwnd": f"0x{target_hwnd:X}",
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "clock": "time.perf_counter_ns",
                "execution_authority": False,
            },
        )

    def append(
        self,
        kind: str,
        *,
        monotonic_ns: int,
        foreground_matches_target: bool,
        payload: Mapping[str, Any],
    ) -> DemonstrationEvent:
        elapsed_s = (monotonic_ns - self.started_monotonic_ns) / 1_000_000_000.0
        with self._lock:
            event = DemonstrationEvent(
                sequence=self._sequence,
                kind=kind,
                monotonic_ns=monotonic_ns,
                elapsed_s=max(0.0, elapsed_s),
                foreground_matches_target=foreground_matches_target,
                payload=payload,
            )
            self._stream.write(
                json.dumps(
                    event.to_record(),
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
            self._stream.flush()
            self._sequence += 1
            return event

    def close(self) -> None:
        if self._owns_stream and not self._stream.closed:
            self._stream.close()

    def __enter__(self) -> "OperatorDemonstrationTimeline":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
