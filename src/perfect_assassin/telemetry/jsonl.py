from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from perfect_assassin.contract_validation import ContractValidator


class DuplicateTelemetryRecordError(ValueError):
    pass


def record_id(record: dict[str, Any]) -> str:
    fields = {
        "observation": "event_id",
        "decision": "decision_id",
        "encounter": "encounter_id",
        "memory": "memory_id",
    }
    try:
        return f"{record['record_type']}:{record[fields[record['record_type']]]}"
    except KeyError as error:
        raise ValueError("Telemetry record has no recognized identity") from error


class JsonlTelemetrySink:
    def __init__(self, path: Path, validator: ContractValidator) -> None:
        self.path = path
        self.validator = validator
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._known_ids = self._read_existing_ids()

    def _read_existing_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        known: set[str] = set()
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid telemetry JSON at line {line_number}") from error
                self.validator.validate(record)
                identity = record_id(record)
                if identity in known:
                    raise DuplicateTelemetryRecordError(f"Duplicate existing record: {identity}")
                known.add(identity)
        return known

    def append(self, record: dict[str, Any]) -> None:
        self.validator.validate(record)
        identity = record_id(record)
        if identity in self._known_ids:
            raise DuplicateTelemetryRecordError(f"Duplicate record: {identity}")
        serialized = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.write("\n")
            stream.flush()
        self._known_ids.add(identity)

    def append_all(self, records: Iterable[dict[str, Any]]) -> None:
        for record in records:
            self.append(record)
