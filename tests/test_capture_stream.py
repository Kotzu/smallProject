from __future__ import annotations

import unittest

from perfect_assassin.capture import (
    CaptureDeadlineExceededError,
    CapturePacket,
    CaptureRingBuffer,
    enforce_capture_deadline,
)


def packet(frame_id: str) -> CapturePacket:
    return CapturePacket(
        manifest={"frame_id": frame_id, "execution_authority": False},
        pixels=memoryview(bytearray(b"BGRA")),
    )


class CaptureStreamCoreTests(unittest.TestCase):
    def test_ring_buffer_is_bounded_and_keeps_latest_packet(self) -> None:
        buffer = CaptureRingBuffer(capacity=2)
        buffer.append(packet("one"))
        buffer.append(packet("two"))
        buffer.append(packet("three"))

        self.assertEqual(len(buffer), 2)
        self.assertEqual(
            [item.manifest["frame_id"] for item in buffer.snapshot()],
            ["two", "three"],
        )
        self.assertEqual(buffer.latest().manifest["frame_id"], "three")

        buffer.clear()
        self.assertEqual(len(buffer), 0)
        self.assertIsNone(buffer.latest())

    def test_capture_deadline_is_fail_closed(self) -> None:
        enforce_capture_deadline(9.5, 10.0)
        with self.assertRaises(CaptureDeadlineExceededError):
            enforce_capture_deadline(10.1, 10.0)
        with self.assertRaises(ValueError):
            enforce_capture_deadline(1.0, 0.0)


if __name__ == "__main__":
    unittest.main()
