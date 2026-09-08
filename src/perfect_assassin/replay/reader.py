from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.records import apply_observation_to_state


class ReplayReader:
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
                    raise ValueError(f"Invalid replay JSON at line {line_number}") from error
                self.validator.validate(record)
                records.append(record)
        return records

    def deterministic_hash(self) -> str:
        digest = hashlib.sha256()
        for record in self.records():
            canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            digest.update(canonical.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    def known_facts_at(self, game_time_ms: int) -> dict[str, dict[str, Any]]:
        known: dict[str, dict[str, Any]] = {}
        for record in self.records():
            if record["record_type"] != "observation" or record["game_time_ms"] > game_time_ms:
                continue
            apply_observation_to_state(known, record)
        return known
