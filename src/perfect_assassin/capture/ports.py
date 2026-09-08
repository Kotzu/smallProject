from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class CaptureRegion:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Capture region width and height must be positive")

    @property
    def dxcam_region(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.left + self.width, self.top + self.height)


@dataclass(frozen=True, slots=True)
class CapturePacket:
    """A frame manifest plus an optional caller-owned pixel view.

    Replay providers intentionally return ``pixels=None``. A live sidecar may
    supply a BGRA8 memoryview, but raw pixels never enter telemetry records.
    """

    manifest: Mapping[str, Any]
    pixels: memoryview | None = None


class CaptureProvider(Protocol):
    def next_frame(self) -> CapturePacket | None: ...

    def reset(self) -> None: ...
