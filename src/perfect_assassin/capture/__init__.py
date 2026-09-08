"""Read-only capture ports and deterministic replay intake."""

from perfect_assassin.capture.ports import CapturePacket, CaptureProvider, CaptureRegion
from perfect_assassin.capture.manifest import InMemoryCaptureFrame
from perfect_assassin.capture.replay import CaptureReplayProvider, CaptureReplayReader
from perfect_assassin.capture.stream import (
    CaptureDeadlineExceededError,
    CaptureRingBuffer,
    CaptureSourceChangedError,
    CaptureStreamError,
    NoFreshCaptureFrameError,
    enforce_capture_deadline,
)

__all__ = [
    "CapturePacket",
    "CaptureProvider",
    "CaptureRegion",
    "InMemoryCaptureFrame",
    "CaptureReplayProvider",
    "CaptureReplayReader",
    "CaptureDeadlineExceededError",
    "CaptureRingBuffer",
    "CaptureSourceChangedError",
    "CaptureStreamError",
    "NoFreshCaptureFrameError",
    "enforce_capture_deadline",
]
