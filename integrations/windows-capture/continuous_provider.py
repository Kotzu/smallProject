from __future__ import annotations

import time
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol
from uuid import uuid4

from perfect_assassin.capture import (
    CaptureDeadlineExceededError,
    CapturePacket,
    CaptureRegion,
    CaptureRingBuffer,
    CaptureSourceChangedError,
    InMemoryCaptureFrame,
    NoFreshCaptureFrameError,
    enforce_capture_deadline,
)
from perfect_assassin.contract_validation import ContractValidator
from window_locator import ScreenRect, WindowQuery, WindowSnapshot


MAX_CAPTURE_DEADLINE_MS = 1000.0
MAX_BUFFER_CAPACITY = 16


def _finite_monotonic(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise CaptureSourceChangedError(
            f"{label} must be a finite non-negative monotonic timestamp"
        )
    return float(value)


class FrameArray(Protocol):
    shape: tuple[int, int, int]
    strides: tuple[int, ...]
    data: object


class CaptureCamera(Protocol):
    _output: object

    def grab(
        self,
        region: tuple[int, int, int, int],
        *,
        copy: bool,
        new_frame_only: bool,
    ) -> FrameArray | None: ...

    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ContinuousCaptureConfig:
    query: WindowQuery
    session_id: str
    target_profile: str
    instance_id: str
    actor_role: str
    actor_id: str
    decision_context: str
    memory_namespace: str
    expected_character_name: str
    credential_alias: str
    binding_assurance_state: str
    binding_assurance_evidence_refs: tuple[str, ...]
    authorization_sha256: str
    client_build: str
    build_signature: str
    identity_evidence_ref: str
    actor_evidence_ref: str
    backend: str = "dxgi"
    device_index: int = 0
    output_index: int = 0
    buffer_capacity: int = 3
    capture_deadline_ms: float = 250.0

    def __post_init__(self) -> None:
        if self.backend not in {"dxgi", "winrt", "printwindow"}:
            raise ValueError(
                "continuous capture backend must be dxgi, winrt or printwindow"
            )
        if self.decision_context not in {"champion", "lab_clone"}:
            raise ValueError("invalid decision context")
        expected_context = {
            "champion_journey": "champion",
            "lab_clone": "lab_clone",
        }.get(self.actor_role)
        if expected_context is None or self.decision_context != expected_context:
            raise ValueError("capture actor role and decision context are inconsistent")
        expected_namespace_prefix = (
            "memory:champion:"
            if self.actor_role == "champion_journey"
            else "memory:lab:"
        )
        if not self.memory_namespace.startswith(expected_namespace_prefix):
            raise ValueError("capture memory namespace does not match actor role")
        if any(
            not value
            for value in (
                self.instance_id,
                self.actor_id,
                self.memory_namespace,
                self.expected_character_name,
                self.credential_alias,
            )
        ):
            raise ValueError("capture actor binding fields must not be empty")
        if (
            self.binding_assurance_state != "configured_expected_only"
            or not self.binding_assurance_evidence_refs
            or len(self.binding_assurance_evidence_refs) > 4
            or len(set(self.binding_assurance_evidence_refs))
            != len(self.binding_assurance_evidence_refs)
            or any(
                not isinstance(reference, str)
                or not reference
                or len(reference) > 256
                for reference in self.binding_assurance_evidence_refs
            )
        ):
            raise ValueError("capture actor binding assurance must remain configured-only")
        if (
            not isinstance(self.authorization_sha256, str)
            or len(self.authorization_sha256) != 64
            or any(character not in "0123456789ABCDEF" for character in self.authorization_sha256)
        ):
            raise ValueError("capture authorization SHA-256 must be 64 uppercase hex characters")
        if self.device_index < 0 or self.output_index < 0:
            raise ValueError("capture device/output indexes must be non-negative")
        if (
            not isinstance(self.buffer_capacity, int)
            or isinstance(self.buffer_capacity, bool)
            or self.buffer_capacity < 1
            or self.buffer_capacity > MAX_BUFFER_CAPACITY
        ):
            raise ValueError(
                f"capture buffer capacity must be an integer in [1, {MAX_BUFFER_CAPACITY}]"
            )
        if (
            isinstance(self.capture_deadline_ms, bool)
            or not isinstance(self.capture_deadline_ms, (int, float))
            or not math.isfinite(float(self.capture_deadline_ms))
            or self.capture_deadline_ms <= 0
            or self.capture_deadline_ms > MAX_CAPTURE_DEADLINE_MS
        ):
            raise ValueError(
                "capture deadline must be finite and in "
                f"(0, {MAX_CAPTURE_DEADLINE_MS}] milliseconds"
            )
        if not self.identity_evidence_ref or not self.actor_evidence_ref:
            raise ValueError("capture identity evidence refs must not be empty")


@dataclass(slots=True)
class ContinuousCaptureStats:
    accepted_frames: int = 0
    no_fresh_frame_failures: int = 0
    source_change_failures: int = 0
    deadline_failures: int = 0
    region_changes: int = 0


def output_desktop_rect(camera: CaptureCamera) -> ScreenRect:
    """Read geometry from the pinned DXcam 0.3 output descriptor."""

    try:
        coordinates = camera._output.desc.DesktopCoordinates
        rect = ScreenRect(
            left=int(coordinates.left),
            top=int(coordinates.top),
            right=int(coordinates.right),
            bottom=int(coordinates.bottom),
        )
    except AttributeError as error:
        raise CaptureSourceChangedError("DXcam output geometry is unavailable") from error
    if not rect.valid:
        raise CaptureSourceChangedError("DXcam output geometry is invalid")
    return rect


class DxcamWindowCaptureProvider:
    """Synchronous, bounded provider with per-frame source revalidation."""

    def __init__(
        self,
        config: ContinuousCaptureConfig,
        validator: ContractValidator,
        *,
        window_locator: Callable[[WindowQuery], WindowSnapshot],
        camera_factory: Callable[..., CaptureCamera] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] | None = None,
        frame_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if config.backend not in {"dxgi", "winrt"}:
            raise ValueError("DXcam provider requires backend=dxgi or backend=winrt")
        self.config = config
        self.validator = validator
        self._window_locator = window_locator
        self._camera_factory = camera_factory or self._default_camera_factory
        self._monotonic = monotonic
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._frame_id_factory = frame_id_factory or (lambda: f"capture:{uuid4()}")
        self._camera: CaptureCamera | None = None
        self._last_region: CaptureRegion | None = None
        self.buffer = CaptureRingBuffer(config.buffer_capacity)
        self.stats = ContinuousCaptureStats()

    @staticmethod
    def _default_camera_factory(**kwargs: object) -> CaptureCamera:
        try:
            import dxcam
        except ImportError as error:
            raise RuntimeError("DXcam capture dependency is not installed") from error
        return dxcam.create(**kwargs)

    def open(self) -> None:
        if self._camera is not None:
            return
        self._camera = self._camera_factory(
            device_idx=self.config.device_index,
            output_idx=self.config.output_index,
            backend=self.config.backend,
            processor_backend="numpy",
            output_color="BGRA",
        )

    def next_frame(self) -> CapturePacket:
        if self._camera is None:
            raise RuntimeError("capture provider is not open")

        before = self._window_locator(self.config.query)
        output_before = output_desktop_rect(self._camera)
        relative_before = before.client_rect.relative_to(output_before)
        region_edges = (
            relative_before.left,
            relative_before.top,
            relative_before.right,
            relative_before.bottom,
        )

        started = _finite_monotonic(
            self._monotonic(),
            "capture start",
        )
        # Pair UTC and monotonic time at the same pre-grab boundary. The
        # monotonic value remains authoritative for freshness calculations;
        # UTC is the corresponding human/audit timestamp.
        capture_started_at = self._utc_now()
        frame = self._camera.grab(
            region_edges,
            copy=True,
            new_frame_only=True,
        )
        captured = _finite_monotonic(
            self._monotonic(),
            "capture completion",
        )
        if captured < started:
            raise CaptureSourceChangedError(
                "capture monotonic clock moved backwards"
            )
        latency_ms = (captured - started) * 1000.0
        try:
            enforce_capture_deadline(latency_ms, self.config.capture_deadline_ms)
        except CaptureDeadlineExceededError:
            self.stats.deadline_failures += 1
            raise
        if frame is None:
            self.stats.no_fresh_frame_failures += 1
            raise NoFreshCaptureFrameError("capture backend returned no new frame")

        after = self._window_locator(self.config.query)
        output_after = output_desktop_rect(self._camera)
        relative_after = after.client_rect.relative_to(output_after)
        if before != after or output_before != output_after or relative_before != relative_after:
            self.stats.source_change_failures += 1
            raise CaptureSourceChangedError(
                "window identity, foreground state or geometry changed during capture"
            )

        height, width, channels = frame.shape
        if channels != 4 or width != relative_before.width or height != relative_before.height:
            self.stats.source_change_failures += 1
            raise CaptureSourceChangedError("captured frame dimensions do not match client rectangle")

        region = CaptureRegion(
            left=relative_before.left,
            top=relative_before.top,
            width=relative_before.width,
            height=relative_before.height,
        )
        if self._last_region is not None and self._last_region != region:
            self.stats.region_changes += 1

        published = _finite_monotonic(
            self._monotonic(),
            "capture publication",
        )
        if published < captured:
            raise CaptureSourceChangedError(
                "capture monotonic clock moved backwards before publication"
            )
        backend_id = (
            "dxgi_desktop_duplication"
            if self.config.backend == "dxgi"
            else "winrt_monitor_capture"
        )
        manifest = InMemoryCaptureFrame(
            frame_id=self._frame_id_factory(),
            session_id=self.config.session_id,
            target_profile=self.config.target_profile,
            instance_id=self.config.instance_id,
            actor_role=self.config.actor_role,
            actor_id=self.config.actor_id,
            decision_context=self.config.decision_context,
            memory_namespace=self.config.memory_namespace,
            expected_character_name=self.config.expected_character_name,
            credential_alias=self.config.credential_alias,
            binding_assurance_state=self.config.binding_assurance_state,
            binding_assurance_evidence_refs=(
                self.config.binding_assurance_evidence_refs
            ),
            authorization_sha256=self.config.authorization_sha256,
            client_build=self.config.client_build,
            build_signature=self.config.build_signature,
            provider_id="dxcam_windows_continuous_capture",
            provider_version="0.1.0",
            backend=backend_id,
            device_index=self.config.device_index,
            output_index=self.config.output_index,
            region=region,
            window_ref=before.window_ref,
            width=int(width),
            height=int(height),
            row_stride_bytes=int(frame.strides[0]),
            captured_at=capture_started_at.isoformat(),
            # DXcam exposes no source timestamp. Conservatively timestamp the
            # frame at the start of the blocking grab interval so freshness
            # includes acquisition latency instead of treating it as age zero.
            monotonic_timestamp_s=started,
            source_timestamp_s=None,
            frame_age_ms=(published - started) * 1000.0,
            evidence_refs=(
                before.window_ref,
                self.config.identity_evidence_ref,
                self.config.actor_evidence_ref,
            ),
        ).to_manifest()
        self.validator.validate(manifest)

        pixels = memoryview(frame.data)
        packet = CapturePacket(manifest=manifest, pixels=pixels)
        self.buffer.append(packet)
        self._last_region = region
        self.stats.accepted_frames += 1
        return packet

    def reset(self) -> None:
        self.buffer.clear()
        self._last_region = None
        self.stats = ContinuousCaptureStats()

    def close(self) -> None:
        if self._camera is not None:
            self._camera.release()
            self._camera = None
        self.buffer.clear()
        self._last_region = None

    def __enter__(self) -> DxcamWindowCaptureProvider:
        self.open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
