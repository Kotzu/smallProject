from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import time
from typing import Callable
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
from continuous_provider import (
    ContinuousCaptureConfig,
    ContinuousCaptureStats,
    _finite_monotonic,
)
from window_locator import WindowQuery, WindowSnapshot


PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0
BI_RGB = 0


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = (
        ("size", wintypes.DWORD),
        ("width", wintypes.LONG),
        ("height", wintypes.LONG),
        ("planes", wintypes.WORD),
        ("bit_count", wintypes.WORD),
        ("compression", wintypes.DWORD),
        ("size_image", wintypes.DWORD),
        ("x_pels_per_meter", wintypes.LONG),
        ("y_pels_per_meter", wintypes.LONG),
        ("colors_used", wintypes.DWORD),
        ("colors_important", wintypes.DWORD),
    )


class _BitmapInfo(ctypes.Structure):
    _fields_ = (("header", _BitmapInfoHeader), ("colors", wintypes.DWORD * 3))


class Win32PrintWindowSurface:
    """Persistent top-down BGRA surface for one exact HWND.

    This is intentionally a read-only window renderer. It neither foregrounds
    the target nor sends input, and it keeps pixels only until the next frame.
    """

    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self._memory_dc: int = 0
        self._bitmap: int = 0
        self._previous_bitmap: int = 0
        self._bits = ctypes.c_void_p()
        self._pixels = None
        self._shape = (0, 0, 4)
        self._strides = (0, 4, 1)

        self._user32.GetDC.argtypes = [wintypes.HWND]
        self._user32.GetDC.restype = wintypes.HDC
        self._user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self._user32.ReleaseDC.restype = ctypes.c_int
        self._user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
        self._user32.PrintWindow.restype = wintypes.BOOL
        self._gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self._gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self._gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC, ctypes.POINTER(_BitmapInfo), wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
        ]
        self._gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        self._gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self._gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self._gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self._gdi32.DeleteObject.restype = wintypes.BOOL
        self._gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self._gdi32.DeleteDC.restype = wintypes.BOOL

    @property
    def shape(self) -> tuple[int, int, int]:
        return self._shape

    @property
    def strides(self) -> tuple[int, int, int]:
        return self._strides

    @property
    def data(self):
        return self._pixels

    def _create(self, hwnd: int, width: int, height: int) -> None:
        self.release()
        window_dc = self._user32.GetDC(hwnd)
        if not window_dc:
            raise OSError(ctypes.get_last_error(), "GetDC failed for target window")
        try:
            memory_dc = self._gdi32.CreateCompatibleDC(window_dc)
            if not memory_dc:
                raise OSError(ctypes.get_last_error(), "CreateCompatibleDC failed")
            info = _BitmapInfo()
            info.header = _BitmapInfoHeader(
                size=ctypes.sizeof(_BitmapInfoHeader),
                width=width,
                # Negative height requests the top-down BGRA order required by
                # the capture contract and all existing visual detectors.
                height=-height,
                planes=1,
                bit_count=32,
                compression=BI_RGB,
                size_image=width * height * 4,
                x_pels_per_meter=0,
                y_pels_per_meter=0,
                colors_used=0,
                colors_important=0,
            )
            bits = ctypes.c_void_p()
            bitmap = self._gdi32.CreateDIBSection(
                window_dc, ctypes.byref(info), DIB_RGB_COLORS,
                ctypes.byref(bits), None, 0,
            )
            if not bitmap or not bits.value:
                self._gdi32.DeleteDC(memory_dc)
                raise OSError(ctypes.get_last_error(), "CreateDIBSection failed")
            previous = self._gdi32.SelectObject(memory_dc, bitmap)
            if not previous:
                self._gdi32.DeleteObject(bitmap)
                self._gdi32.DeleteDC(memory_dc)
                raise OSError(ctypes.get_last_error(), "SelectObject failed")
            self._memory_dc = int(memory_dc)
            self._bitmap = int(bitmap)
            self._previous_bitmap = int(previous)
            self._bits = bits
            self._pixels = (ctypes.c_ubyte * (width * height * 4)).from_address(
                bits.value
            )
            self._shape = (height, width, 4)
            self._strides = (width * 4, 4, 1)
        finally:
            self._user32.ReleaseDC(hwnd, window_dc)

    def grab(self, window: WindowSnapshot):
        width = window.client_rect.width
        height = window.client_rect.height
        if self._shape[:2] != (height, width) or not self._memory_dc:
            self._create(window.hwnd, width, height)
        if not self._user32.PrintWindow(
            window.hwnd,
            self._memory_dc,
            PW_CLIENTONLY | PW_RENDERFULLCONTENT,
        ):
            return None
        return self

    def release(self) -> None:
        if self._memory_dc and self._previous_bitmap:
            self._gdi32.SelectObject(self._memory_dc, self._previous_bitmap)
        if self._bitmap:
            self._gdi32.DeleteObject(self._bitmap)
        if self._memory_dc:
            self._gdi32.DeleteDC(self._memory_dc)
        self._memory_dc = 0
        self._bitmap = 0
        self._previous_bitmap = 0
        self._bits = ctypes.c_void_p()
        self._pixels = None
        self._shape = (0, 0, 4)
        self._strides = (0, 4, 1)


class Win32PrintWindowCaptureProvider:
    """Exact-window read-only capture which remains valid when occluded."""

    def __init__(
        self,
        config: ContinuousCaptureConfig,
        validator: ContractValidator,
        *,
        window_locator: Callable[[WindowQuery], WindowSnapshot],
        surface_factory: Callable[[], Win32PrintWindowSurface] = Win32PrintWindowSurface,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        frame_id_factory: Callable[[], str] = lambda: f"capture:{uuid4()}",
    ) -> None:
        if config.backend != "printwindow":
            raise ValueError("PrintWindow provider requires backend=printwindow")
        if config.query.require_foreground:
            raise ValueError("PrintWindow provider is only for read-only background observation")
        self.config = config
        self.validator = validator
        self._window_locator = window_locator
        self._surface_factory = surface_factory
        self._monotonic = monotonic
        self._utc_now = utc_now
        self._frame_id_factory = frame_id_factory
        self._surface: Win32PrintWindowSurface | None = None
        self._last_region: CaptureRegion | None = None
        self.buffer = CaptureRingBuffer(config.buffer_capacity)
        self.stats = ContinuousCaptureStats()

    def open(self) -> None:
        if self._surface is None:
            self._surface = self._surface_factory()

    def next_frame(self) -> CapturePacket:
        if self._surface is None:
            raise RuntimeError("PrintWindow capture provider is not open")
        before = self._window_locator(self.config.query)
        started = _finite_monotonic(self._monotonic(), "capture start")
        captured_at = self._utc_now()
        frame = self._surface.grab(before)
        captured = _finite_monotonic(self._monotonic(), "capture completion")
        if captured < started:
            raise CaptureSourceChangedError("capture monotonic clock moved backwards")
        try:
            enforce_capture_deadline(
                (captured - started) * 1000.0, self.config.capture_deadline_ms,
            )
        except CaptureDeadlineExceededError:
            self.stats.deadline_failures += 1
            raise
        if frame is None:
            self.stats.no_fresh_frame_failures += 1
            raise NoFreshCaptureFrameError("PrintWindow returned no client frame")
        after = self._window_locator(self.config.query)
        if before != after:
            self.stats.source_change_failures += 1
            raise CaptureSourceChangedError(
                "window identity or geometry changed during PrintWindow capture"
            )
        height, width, channels = frame.shape
        if channels != 4 or width != before.client_rect.width or height != before.client_rect.height:
            self.stats.source_change_failures += 1
            raise CaptureSourceChangedError("PrintWindow frame geometry is invalid")
        region = CaptureRegion(
            left=before.client_rect.left,
            top=before.client_rect.top,
            width=width,
            height=height,
        )
        if self._last_region is not None and self._last_region != region:
            self.stats.region_changes += 1
        published = _finite_monotonic(self._monotonic(), "capture publication")
        if published < captured:
            raise CaptureSourceChangedError(
                "capture monotonic clock moved backwards before publication"
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
            binding_assurance_evidence_refs=self.config.binding_assurance_evidence_refs,
            authorization_sha256=self.config.authorization_sha256,
            client_build=self.config.client_build,
            build_signature=self.config.build_signature,
            provider_id="win32_print_window_capture",
            provider_version="0.1.0",
            backend="win32_print_window",
            device_index=self.config.device_index,
            output_index=self.config.output_index,
            region=region,
            window_ref=before.window_ref,
            width=width,
            height=height,
            row_stride_bytes=int(frame.strides[0]),
            captured_at=captured_at.isoformat(),
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
        packet = CapturePacket(manifest=manifest, pixels=memoryview(frame.data))
        self.buffer.append(packet)
        self._last_region = region
        self.stats.accepted_frames += 1
        return packet

    def close(self) -> None:
        if self._surface is not None:
            self._surface.release()
            self._surface = None
        self.buffer.clear()
        self._last_region = None
