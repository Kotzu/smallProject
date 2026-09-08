from __future__ import annotations

from collections import deque

from perfect_assassin.capture.ports import CapturePacket


class CaptureStreamError(RuntimeError):
    """Base failure for a read-only capture stream."""


class NoFreshCaptureFrameError(CaptureStreamError):
    """The backend did not provide a newly observed frame."""


class CaptureDeadlineExceededError(CaptureStreamError):
    """Frame acquisition exceeded the configured latency budget."""


class CaptureSourceChangedError(CaptureStreamError):
    """The source identity or geometry changed during one acquisition."""


class CaptureRingBuffer:
    """Caller-owned packets retained only in bounded process memory."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capture buffer capacity must be positive")
        self.capacity = capacity
        self._packets: deque[CapturePacket] = deque(maxlen=capacity)

    def append(self, packet: CapturePacket) -> None:
        self._packets.append(packet)

    def latest(self) -> CapturePacket | None:
        return self._packets[-1] if self._packets else None

    def snapshot(self) -> tuple[CapturePacket, ...]:
        return tuple(self._packets)

    def clear(self) -> None:
        self._packets.clear()

    def __len__(self) -> int:
        return len(self._packets)


def enforce_capture_deadline(latency_ms: float, deadline_ms: float) -> None:
    if deadline_ms <= 0:
        raise ValueError("capture deadline must be positive")
    if latency_ms < 0:
        raise ValueError("capture latency cannot be negative")
    if latency_ms > deadline_ms:
        raise CaptureDeadlineExceededError(
            f"capture latency {latency_ms:.3f} ms exceeded {deadline_ms:.3f} ms deadline"
        )
