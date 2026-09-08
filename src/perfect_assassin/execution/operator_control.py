from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Callable


VALID_OPERATOR_COMMANDS = frozenset({"RUN", "PAUSE", "STOP"})


class OperatorStopRequested(RuntimeError):
    """The visible operator UI requested a clean bounded stop."""


def read_operator_command(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise OperatorStopRequested("operator control file is missing") from error
    except OSError as error:
        # A sharing/access failure cannot authorize continued movement. Use
        # the normal stopped-result path, not an unhandled child exception.
        raise OperatorStopRequested("operator control file is unreadable") from error
    if not 1 <= len(raw) <= 4096 or raw.startswith(b"\xef\xbb\xbf"):
        raise OperatorStopRequested("operator control file is invalid")
    try:
        record = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperatorStopRequested("operator control file is invalid") from error
    if (
        type(record) is not dict
        or record.get("schema_version") != "1.0"
        or set(record) != {"schema_version", "command", "revision"}
        or record.get("command") not in VALID_OPERATOR_COMMANDS
        or type(record.get("revision")) is not int
        or record["revision"] < 1
    ):
        raise OperatorStopRequested("operator control command is not exact")
    return str(record["command"])


class FileOperatorCombatControl:
    """Pause/resume/stop gate controlled by the visible local UI."""

    def __init__(
        self,
        path: Path,
        *,
        poll_seconds: float = 0.05,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(path, Path) or not path.is_absolute():
            raise ValueError("operator control path must be absolute")
        if not 0.02 <= poll_seconds <= 0.25:
            raise ValueError("operator control poll interval is invalid")
        self._path = path
        self._poll_seconds = poll_seconds
        self._sleeper = sleeper
        self._paused_seconds = 0.0

    @property
    def total_paused_ms(self) -> float:
        return self._paused_seconds * 1_000.0

    def checkpoint(self, release_motion: Callable[[], None]) -> bool:
        try:
            command = read_operator_command(self._path)
        except OperatorStopRequested:
            release_motion()
            raise
        if command == "STOP":
            release_motion()
            raise OperatorStopRequested("operator pressed Stop")
        if command == "RUN":
            return False
        release_motion()
        paused_at = time.monotonic()
        try:
            while True:
                self._sleeper(self._poll_seconds)
                command = read_operator_command(self._path)
                if command == "RUN":
                    return True
                if command == "STOP":
                    raise OperatorStopRequested("operator pressed Stop")
        finally:
            self._paused_seconds += max(0.0, time.monotonic() - paused_at)
