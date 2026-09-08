from __future__ import annotations

import importlib
import sys
import unittest
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from perfect_assassin.capture import (
    CaptureDeadlineExceededError,
    CaptureSourceChangedError,
    NoFreshCaptureFrameError,
)
from perfect_assassin.contract_validation import ContractValidator


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))

locator = importlib.import_module("window_locator")
provider_module = importlib.import_module("continuous_provider")
print_window_module = importlib.import_module("print_window_provider")


class FakeCoordinates:
    def __init__(self, rect) -> None:
        self.left, self.top, self.right, self.bottom = rect


class FakeDescription:
    def __init__(self, rect) -> None:
        self.DesktopCoordinates = FakeCoordinates(rect)


class FakeOutput:
    def __init__(self, rect) -> None:
        self.desc = FakeDescription(rect)


class FakeFrame:
    def __init__(self, width: int, height: int) -> None:
        self.shape = (height, width, 4)
        self.strides = (width * 4, 4, 1)
        self.data = bytearray(width * height * 4)


class FakeCamera:
    def __init__(self, frames, output=(0, 0, 1920, 1080)) -> None:
        self._output = FakeOutput(output)
        self.frames = deque(frames)
        self.regions = []
        self.released = False

    def grab(self, region, *, copy, new_frame_only):
        self.regions.append(region)
        if not copy or not new_frame_only:
            raise AssertionError("provider must request caller-owned new frames")
        return self.frames.popleft()

    def release(self) -> None:
        self.released = True


class SequenceClock:
    def __init__(self, values) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


def snapshot(*, left=100, top=50, width=640, height=480, foreground=True):
    return locator.WindowSnapshot(
        hwnd=0x1234,
        pid=42,
        title="World of Warcraft",
        class_name="GxWindowClassD3d",
        visible=True,
        minimized=False,
        foreground=foreground,
        client_rect=locator.ScreenRect(left, top, left + width, top + height),
        dpi=96,
    )


class LocatorSequence:
    def __init__(self, values) -> None:
        self.values = deque(values)

    def __call__(self, _query):
        return self.values.popleft()


class FakePrintWindowSurface:
    def __init__(self, frames) -> None:
        self.frames = deque(frames)
        self.windows = []
        self.released = False

    def grab(self, window):
        self.windows.append(window)
        return self.frames.popleft()

    def release(self) -> None:
        self.released = True


def make_provider(
    *,
    camera,
    windows,
    clock_values=None,
    monotonic=None,
    utc_now=None,
    capacity=2,
    deadline_ms=100.0,
):
    config = provider_module.ContinuousCaptureConfig(
        query=locator.WindowQuery(
            pid=42,
            hwnd=0x1234,
            title_exact="World of Warcraft",
            class_exact="GxWindowClassD3d",
        ),
        session_id="session:stream:test",
        target_profile="tbc_243_lab",
        instance_id="instance:tbc243-lab:fixture-champion",
        actor_role="champion_journey",
        actor_id="actor:predator:fixture-champion",
        decision_context="champion",
        memory_namespace="memory:champion:fixture",
        expected_character_name="Predator",
        credential_alias="credential:fixture:champion",
        binding_assurance_state="configured_expected_only",
        binding_assurance_evidence_refs=(
            "authorization:fixture:actor-expected",
        ),
        authorization_sha256="A" * 64,
        client_build="2.4.3.8606",
        build_signature="wow-tbc-2.4.3.8606-enGB:sha256:fixture",
        identity_evidence_ref="authorization:fixture",
        actor_evidence_ref="actor-binding:actor:fixture@instance:fixture",
        buffer_capacity=capacity,
        capture_deadline_ms=deadline_ms,
    )
    frame_ids = iter(f"capture:test:{index}" for index in range(20))
    return provider_module.DxcamWindowCaptureProvider(
        config,
        ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
        window_locator=LocatorSequence(windows),
        camera_factory=lambda **_kwargs: camera,
        monotonic=monotonic or SequenceClock(clock_values),
        utc_now=utc_now
        or (lambda: datetime(2026, 8, 22, 18, 0, tzinfo=timezone.utc)),
        frame_id_factory=lambda: next(frame_ids),
    )


class ContinuousCaptureProviderTests(unittest.TestCase):
    def test_background_window_provider_reads_exact_occluded_window_without_input(self) -> None:
        hidden_behind_center = snapshot(foreground=False)
        surface = FakePrintWindowSurface([FakeFrame(640, 480)])
        config = provider_module.ContinuousCaptureConfig(
            query=locator.WindowQuery(
                pid=42,
                hwnd=0x1234,
                title_exact="World of Warcraft",
                class_exact="GxWindowClassD3d",
                require_foreground=False,
            ),
            session_id="session:background-map:test",
            target_profile="tbc_243_lab",
            instance_id="instance:tbc243-lab:fixture-champion",
            actor_role="champion_journey",
            actor_id="actor:predator:fixture-champion",
            decision_context="champion",
            memory_namespace="memory:champion:fixture",
            expected_character_name="Predator",
            credential_alias="credential:fixture:champion",
            binding_assurance_state="configured_expected_only",
            binding_assurance_evidence_refs=("authorization:fixture:actor-expected",),
            authorization_sha256="A" * 64,
            client_build="2.4.3.8606",
            build_signature="wow-tbc-2.4.3.8606-enGB:sha256:fixture",
            identity_evidence_ref="authorization:fixture",
            actor_evidence_ref="actor-binding:actor:fixture@instance:fixture",
            backend="printwindow",
            capture_deadline_ms=100.0,
        )
        stream = print_window_module.Win32PrintWindowCaptureProvider(
            config,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            window_locator=LocatorSequence(
                [hidden_behind_center, hidden_behind_center]
            ),
            surface_factory=lambda: surface,
            monotonic=SequenceClock([10.0, 10.01, 10.011]),
            utc_now=lambda: datetime(2026, 9, 3, 22, 0, tzinfo=timezone.utc),
            frame_id_factory=lambda: "capture:background-map:test",
        )
        # This provider deliberately exposes no input API.
        self.assertFalse(hasattr(stream, "send_input"))
        stream.open()
        packet = stream.next_frame()
        self.assertEqual(packet.manifest["backend"], "win32_print_window")
        self.assertEqual(packet.manifest["source"]["source_kind"], "window_region")
        self.assertFalse(packet.manifest["execution_authority"])
        self.assertIs(surface.windows[0], hidden_behind_center)
        stream.close()
        self.assertTrue(surface.released)

    def test_background_window_provider_rejects_foreground_bound_query(self) -> None:
        base = make_provider(
            camera=FakeCamera([]), windows=[], clock_values=[],
        ).config
        config = replace(base, backend="printwindow")
        with self.assertRaisesRegex(ValueError, "read-only background"):
            print_window_module.Win32PrintWindowCaptureProvider(
                config,
                ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
                window_locator=lambda _query: snapshot(),
            )

    def test_accepts_only_new_caller_owned_frame_and_builds_manifest(self) -> None:
        stable = snapshot()
        camera = FakeCamera([FakeFrame(640, 480)])
        stream = make_provider(
            camera=camera,
            windows=[stable, stable],
            clock_values=[10.0, 10.01, 10.011],
        )
        with stream:
            packet = stream.next_frame()
            self.assertEqual(packet.manifest["image"]["width"], 640)
            self.assertEqual(packet.manifest["schema_version"], "2.0")
            self.assertEqual(
                packet.manifest["actor_binding"]["instance_id"],
                "instance:tbc243-lab:fixture-champion",
            )
            self.assertEqual(
                packet.manifest["actor_binding"]["memory_namespace"],
                "memory:champion:fixture",
            )
            self.assertEqual(packet.manifest["authorization_sha256"], "A" * 64)
            self.assertFalse(packet.manifest["artifact"]["persisted"])
            self.assertIsNotNone(packet.pixels)
            self.assertEqual(stream.stats.accepted_frames, 1)
            self.assertEqual(camera.regions, [(100, 50, 740, 530)])
        self.assertTrue(camera.released)
        self.assertEqual(len(stream.buffer), 0)

    def test_unknown_source_time_conservatively_includes_grab_latency(self) -> None:
        stable = snapshot()
        stream = make_provider(
            camera=FakeCamera([FakeFrame(640, 480)]),
            windows=[stable, stable],
            clock_values=[10.0, 10.05, 10.061],
            deadline_ms=100.0,
        )
        stream.open()
        packet = stream.next_frame()
        timing = packet.manifest["timing"]
        self.assertIsNone(timing["source_timestamp_s"])
        self.assertEqual(timing["monotonic_timestamp_s"], 10.0)
        self.assertAlmostEqual(timing["frame_age_ms"], 61.0)
        stream.close()

    def test_utc_and_monotonic_timestamps_share_pre_grab_boundary(self) -> None:
        events: list[str] = []
        monotonic_values = iter((10.0, 10.05, 10.061))

        def monotonic() -> float:
            value = next(monotonic_values)
            events.append(f"monotonic:{value}")
            return value

        capture_started_at = datetime(
            2026,
            8,
            22,
            18,
            0,
            0,
            125000,
            tzinfo=timezone.utc,
        )

        def utc_now() -> datetime:
            events.append("utc:start")
            return capture_started_at

        class OrderedCamera(FakeCamera):
            def grab(self, region, *, copy, new_frame_only):
                events.append("grab")
                return super().grab(
                    region,
                    copy=copy,
                    new_frame_only=new_frame_only,
                )

        stable = snapshot()
        stream = make_provider(
            camera=OrderedCamera([FakeFrame(640, 480)]),
            windows=[stable, stable],
            monotonic=monotonic,
            utc_now=utc_now,
            deadline_ms=100.0,
        )
        stream.open()
        packet = stream.next_frame()
        self.assertEqual(
            events[:3],
            ["monotonic:10.0", "utc:start", "grab"],
        )
        self.assertEqual(
            packet.manifest["timing"]["captured_at"],
            capture_started_at.isoformat(),
        )
        self.assertEqual(
            packet.manifest["timing"]["monotonic_timestamp_s"],
            10.0,
        )
        self.assertEqual(events.count("utc:start"), 1)
        stream.close()

    def test_rejects_nonfinite_or_backwards_provider_clock(self) -> None:
        stable = snapshot()
        for clock_values in (
            [float("nan")],
            [1.0, float("inf")],
            [2.0, 1.0],
            [1.0, 1.01, 1.0],
        ):
            with self.subTest(clock_values=clock_values):
                stream = make_provider(
                    camera=FakeCamera([FakeFrame(640, 480)]),
                    windows=[stable, stable],
                    clock_values=clock_values,
                )
                stream.open()
                with self.assertRaises(CaptureSourceChangedError):
                    stream.next_frame()
                stream.close()

    def test_ring_buffer_remains_bounded(self) -> None:
        stable = snapshot()
        camera = FakeCamera([FakeFrame(640, 480) for _ in range(3)])
        stream = make_provider(
            camera=camera,
            windows=[stable, stable] * 3,
            clock_values=[1.0, 1.01, 1.011, 2.0, 2.01, 2.011, 3.0, 3.01, 3.011],
            capacity=2,
        )
        stream.open()
        for _ in range(3):
            stream.next_frame()
        self.assertEqual(len(stream.buffer), 2)
        self.assertEqual(
            [packet.manifest["frame_id"] for packet in stream.buffer.snapshot()],
            ["capture:test:1", "capture:test:2"],
        )
        stream.close()

    def test_rejects_geometry_change_during_capture(self) -> None:
        camera = FakeCamera([FakeFrame(640, 480)])
        stream = make_provider(
            camera=camera,
            windows=[snapshot(), snapshot(left=120)],
            clock_values=[1.0, 1.01],
        )
        stream.open()
        with self.assertRaises(CaptureSourceChangedError):
            stream.next_frame()
        self.assertEqual(stream.stats.source_change_failures, 1)
        self.assertEqual(len(stream.buffer), 0)
        stream.close()

    def test_stable_move_between_frames_is_accepted_and_counted(self) -> None:
        first = snapshot()
        moved = snapshot(left=200)
        camera = FakeCamera([FakeFrame(640, 480), FakeFrame(640, 480)])
        stream = make_provider(
            camera=camera,
            windows=[first, first, moved, moved],
            clock_values=[1.0, 1.01, 1.011, 2.0, 2.01, 2.011],
        )
        stream.open()
        stream.next_frame()
        stream.next_frame()
        self.assertEqual(stream.stats.region_changes, 1)
        self.assertEqual(camera.regions[-1], (200, 50, 840, 530))
        stream.close()

    def test_rejects_no_fresh_frame(self) -> None:
        stable = snapshot()
        stream = make_provider(
            camera=FakeCamera([None]),
            windows=[stable],
            clock_values=[1.0, 1.01],
        )
        stream.open()
        with self.assertRaises(NoFreshCaptureFrameError):
            stream.next_frame()
        self.assertEqual(stream.stats.no_fresh_frame_failures, 1)
        stream.close()

    def test_rejects_capture_over_deadline(self) -> None:
        stable = snapshot()
        stream = make_provider(
            camera=FakeCamera([FakeFrame(640, 480)]),
            windows=[stable],
            clock_values=[1.0, 1.2],
            deadline_ms=100.0,
        )
        stream.open()
        with self.assertRaises(CaptureDeadlineExceededError):
            stream.next_frame()
        self.assertEqual(stream.stats.deadline_failures, 1)
        stream.close()

    def test_rejects_window_outside_selected_output(self) -> None:
        outside = snapshot(left=1800)
        stream = make_provider(
            camera=FakeCamera([FakeFrame(640, 480)]),
            windows=[outside],
            clock_values=[],
        )
        stream.open()
        with self.assertRaises(locator.WindowSelectionError):
            stream.next_frame()
        self.assertEqual(len(stream.buffer), 0)
        stream.close()

    def test_direct_config_rejects_nonfinite_or_oversized_resource_bounds(self) -> None:
        stable = snapshot()
        config = make_provider(
            camera=FakeCamera([FakeFrame(640, 480)]),
            windows=[stable, stable],
            clock_values=[1.0, 1.01, 1.02],
        ).config
        for deadline in (float("nan"), float("inf"), 1000.1, True):
            with self.subTest(deadline=deadline), self.assertRaises(ValueError):
                replace(config, capture_deadline_ms=deadline)
        for capacity in (0, 17, 1_000_000, True, 1.5):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                replace(config, buffer_capacity=capacity)
        for authorization_sha256 in (None, "A" * 63, "a" * 64):
            with (
                self.subTest(authorization_sha256=authorization_sha256),
                self.assertRaises(ValueError),
            ):
                replace(config, authorization_sha256=authorization_sha256)


if __name__ == "__main__":
    unittest.main()
