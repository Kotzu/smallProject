from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from perfect_assassin.capture.ports import CapturePacket
from perfect_assassin.contract_validation import ContractValidator


class CaptureReplayReader:
    """Validate and canonicalize capture manifests without loading pixels."""

    def __init__(self, path: Path, validator: ContractValidator) -> None:
        self.path = path
        self.validator = validator

    def records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid capture replay JSON at line {line_number}"
                    ) from error
                self.validator.validate(record)
                records.append(record)
        return records

    def deterministic_hash(self) -> str:
        digest = hashlib.sha256()
        for record in self.records():
            canonical = json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            digest.update(canonical.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()


class CaptureReplayProvider:
    """Finite deterministic provider for fixture and regression replays."""

    def __init__(
        self,
        records: Iterable[Mapping[str, Any]],
        validator: ContractValidator,
    ) -> None:
        validated: list[dict[str, Any]] = []
        for record in records:
            owned = copy.deepcopy(dict(record))
            validator.validate(owned)
            validated.append(owned)
        self._records = tuple(validated)
        self._cursor = 0

    def next_frame(self) -> CapturePacket | None:
        if self._cursor >= len(self._records):
            return None
        manifest = copy.deepcopy(self._records[self._cursor])
        self._cursor += 1
        return CapturePacket(manifest=manifest, pixels=None)

    def reset(self) -> None:
        self._cursor = 0
