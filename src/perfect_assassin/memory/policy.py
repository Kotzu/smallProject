from __future__ import annotations

from typing import Any


class MemoryIsolationError(ValueError):
    pass


class MemoryWritePolicy:
    def authorize(self, record: dict[str, Any]) -> None:
        if record["namespace"] == "champion_identity" and record["origin"] == "lab_derived":
            raise MemoryIsolationError("LAB-derived evidence cannot become Champion identity")
