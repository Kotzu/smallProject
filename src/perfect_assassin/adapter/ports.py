from __future__ import annotations

from typing import Any, Iterable, Protocol

from perfect_assassin.domain.records import RawEvent


class ObservationSource(Protocol):
    target_profile: str
    adapter_name: str
    session_id: str
    champion_id: str

    def events(self) -> Iterable[RawEvent]: ...

    def semantic_key(self, raw_key: str) -> str: ...

    def semantic_value(self, raw_key: str, raw_value: Any) -> Any: ...
