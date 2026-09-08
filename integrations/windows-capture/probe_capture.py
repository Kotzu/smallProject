from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from perfect_assassin.capture import (
    CaptureRegion,
    CaptureSourceChangedError,
    InMemoryCaptureFrame,
)
from perfect_assassin.contract_validation import ContractValidator
from target_identity import (
    CaptureTargetIdentity,
    SCREEN_CAPTURE_READ_ONLY,
    load_capture_target_identity,
    run_process_bound_capture,
    verify_capture_process_identity,
)
from window_locator import ScreenRect, WindowQuery, locate_window


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAB_LAUNCH_RECEIPT = (
    ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
)
LAB_LAUNCH_RECEIPT_SCHEMA = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"


def parse_region(value: str) -> tuple[int, int, int, int]:
    try:
        left, top, right, bottom = (int(part.strip()) for part in value.split(","))
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("region must be left,top,right,bottom") from error
    if right <= left or bottom <= top:
        raise argparse.ArgumentTypeError("region right/bottom must exceed left/top")
    return left, top, right, bottom


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one in-memory BGRA frame and print metadata only."
    )
    parser.add_argument("--backend", choices=("dxgi", "winrt"), default="dxgi")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--output-index", type=int, default=0)
    parser.add_argument("--region", type=parse_region)
    parser.add_argument("--window-pid", type=int)
    parser.add_argument("--window-hwnd", type=lambda value: int(value, 0))
    parser.add_argument("--window-title-exact")
    parser.add_argument("--window-class-exact")
    parser.add_argument("--emit-manifest", action="store_true")
    parser.add_argument("--session-id")
    parser.add_argument("--client-build")
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--client-executable", type=Path)
    parser.add_argument(
        "--lab-launch-receipt",
        type=Path,
        default=DEFAULT_LAB_LAUNCH_RECEIPT,
    )
    return parser


def output_desktop_rect(camera: object) -> ScreenRect:
    """Read the pinned DXcam output descriptor and fail if its shape changed."""

    try:
        coordinates = camera._output.desc.DesktopCoordinates
        rect = ScreenRect(
            left=int(coordinates.left),
            top=int(coordinates.top),
            right=int(coordinates.right),
            bottom=int(coordinates.bottom),
        )
    except AttributeError as error:
        raise RuntimeError("DXcam output geometry is unavailable") from error
    if not rect.valid:
        raise RuntimeError("DXcam output geometry is invalid")
    return rect


def capture_start_clock_boundary() -> tuple[float, str]:
    """Snapshot both clocks immediately before a blocking frame acquisition."""

    monotonic_timestamp_s = time.monotonic()
    captured_at = datetime.now(timezone.utc).isoformat()
    return monotonic_timestamp_s, captured_at


def probe(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.device_index < 0 or args.output_index < 0:
        raise SystemExit("device and output indexes must be non-negative")
    if args.region is not None and args.window_pid is not None:
        raise SystemExit("--region and --window-pid are mutually exclusive")
    if (
        args.window_hwnd is not None
        or args.window_title_exact
        or args.window_class_exact
    ) and args.window_pid is None:
        raise SystemExit("window HWND/title/class filters require --window-pid")
    manifest_fields = (
        args.session_id,
        args.client_build,
        args.authorization_file,
        args.client_executable,
    )
    if args.emit_manifest and any(value is None for value in manifest_fields):
        raise SystemExit(
            "--emit-manifest requires session-id, client-build, authorization-file and client-executable"
        )
    if args.emit_manifest and args.window_pid is None:
        raise SystemExit("--emit-manifest requires --window-pid for process binding")
    if args.emit_manifest and (
        args.window_hwnd is None
        or not args.window_title_exact
        or not args.window_class_exact
    ):
        raise SystemExit(
            "--emit-manifest requires exact window HWND, title and class filters"
        )

    try:
        import dxcam
    except ImportError:
        print(
            json.dumps(
                {
                    "status": "dependency_missing",
                    "detail": "Install the pinned Windows capture wheel set first.",
                    "execution_authority": False,
                }
            )
        )
        return 2

    camera = None
    selected_window = None
    identity: CaptureTargetIdentity | None = None
    started = time.monotonic()
    try:
        if args.emit_manifest:
            authorization_schema = (
                ROOT
                / "contracts"
                / "execution-target-authorization.schema.json"
            )
            identity = load_capture_target_identity(
                args.authorization_file,
                authorization_schema,
                args.client_executable,
                args.client_build,
                required_capabilities=(SCREEN_CAPTURE_READ_ONLY,),
            )

        camera = dxcam.create(
            device_idx=args.device_index,
            output_idx=args.output_index,
            backend=args.backend,
            processor_backend="numpy",
            output_color="BGRA",
        )
        capture_region = args.region
        output_rect = output_desktop_rect(camera)
        window_query = None
        if args.window_pid is not None:
            window_query = WindowQuery(
                pid=args.window_pid,
                hwnd=args.window_hwnd,
                title_exact=args.window_title_exact,
                class_exact=args.window_class_exact,
            )
            selected_window = locate_window(
                window_query
            )
            relative = selected_window.client_rect.relative_to(output_rect)
            capture_region = (
                relative.left,
                relative.top,
                relative.right,
                relative.bottom,
            )

        capture_started = 0.0
        captured_at = ""

        def grab_revalidated_frame() -> object:
            nonlocal capture_started, captured_at
            capture_started, captured_at = capture_start_clock_boundary()
            captured_frame = camera.grab(
                region=capture_region,
                new_frame_only=False,
            )

            # Bind the returned pixels to the exact source snapshot adjacent to
            # the grab. Process verification remains an independent outer
            # layer when a manifest is requested.
            output_after = output_desktop_rect(camera)
            if output_after != output_rect:
                raise CaptureSourceChangedError(
                    "capture output geometry changed during one-shot capture"
                )
            if window_query is not None:
                window_after = locate_window(window_query)
                relative_after = window_after.client_rect.relative_to(output_after)
                if (
                    selected_window != window_after
                    or relative_after != relative
                ):
                    raise CaptureSourceChangedError(
                        "window identity, foreground state or geometry changed "
                        "during one-shot capture"
                    )

            if captured_frame is not None:
                height, width, channels = captured_frame.shape
                if capture_region is None:
                    expected_width = output_rect.width
                    expected_height = output_rect.height
                else:
                    left, top, right, bottom = capture_region
                    expected_width = right - left
                    expected_height = bottom - top
                if (
                    channels != 4
                    or width != expected_width
                    or height != expected_height
                ):
                    raise CaptureSourceChangedError(
                        "captured frame dimensions do not match the pinned source region"
                    )
            return captured_frame

        if identity is None:
            frame = grab_revalidated_frame()
        else:
            frame = run_process_bound_capture(
                grab_revalidated_frame,
                lambda: verify_capture_process_identity(
                    args.window_pid,
                    args.client_executable,
                    identity,
                    hwnd=args.window_hwnd,
                    expected_title=args.window_title_exact,
                    expected_class=args.window_class_exact,
                    receipt_path=args.lab_launch_receipt,
                    receipt_schema_path=LAB_LAUNCH_RECEIPT_SCHEMA,
                    window_resolver=lambda: locate_window(
                        window_query
                    ),
                ),
            )
        finished = time.monotonic()
        if frame is None:
            raise RuntimeError("capture backend returned no frame")

        height, width, channels = frame.shape
        result = {
            "status": "captured_in_memory",
            "backend": args.backend,
            "device_index": args.device_index,
            "output_index": args.output_index,
            "region_output_relative": list(capture_region) if capture_region else None,
            "region_coordinate_space": "output_physical_pixels",
            "output_rect_screen": [
                output_rect.left,
                output_rect.top,
                output_rect.right,
                output_rect.bottom,
            ],
            "window_ref": selected_window.window_ref if selected_window else None,
            "window_client_rect_screen": (
                [
                    selected_window.client_rect.left,
                    selected_window.client_rect.top,
                    selected_window.client_rect.right,
                    selected_window.client_rect.bottom,
                ]
                if selected_window
                else None
            ),
            "window_dpi": selected_window.dpi if selected_window else None,
            "captured_at": captured_at,
            "monotonic_timestamp_s": capture_started,
            "probe_duration_ms": round((finished - started) * 1000.0, 3),
            "image": {
                "width": int(width),
                "height": int(height),
                "channels": int(channels),
                "row_stride_bytes": int(frame.strides[0]),
                "pixel_format": "BGRA8",
                "dtype": str(frame.dtype),
            },
            "persisted": False,
            "execution_authority": False,
        }
        if args.emit_manifest:
            if identity is None:
                raise RuntimeError("capture target identity was not loaded")
            region = None
            if capture_region is not None:
                left, top, right, bottom = capture_region
                region = CaptureRegion(left, top, right - left, bottom - top)
            backend_id = (
                "dxgi_desktop_duplication"
                if args.backend == "dxgi"
                else "winrt_monitor_capture"
            )
            manifest = InMemoryCaptureFrame(
                frame_id=f"capture:{uuid4()}",
                session_id=args.session_id,
                target_profile=identity.target_profile,
                instance_id=identity.instance_id,
                actor_role=identity.actor_role,
                actor_id=identity.actor_id,
                decision_context=identity.decision_context,
                memory_namespace=identity.memory_namespace,
                expected_character_name=identity.expected_character_name,
                credential_alias=identity.credential_alias,
                binding_assurance_state=identity.binding_assurance_state,
                binding_assurance_evidence_refs=(
                    identity.binding_assurance_evidence_refs
                ),
                authorization_sha256=identity.authorization_sha256,
                client_build=identity.client_build,
                build_signature=identity.build_signature,
                provider_id="dxcam_windows_capture",
                provider_version="0.1.0",
                backend=backend_id,
                device_index=args.device_index,
                output_index=args.output_index,
                region=region,
                window_ref=selected_window.window_ref if selected_window else None,
                width=int(width),
                height=int(height),
                row_stride_bytes=int(frame.strides[0]),
                captured_at=captured_at,
                # No backend source timestamp is available. Use the beginning
                # of the capture/identity-bound interval so its full latency is
                # conservatively included in freshness age.
                monotonic_timestamp_s=capture_started,
                source_timestamp_s=None,
                frame_age_ms=max(
                    0.0,
                    (time.monotonic() - capture_started) * 1000.0,
                ),
                evidence_refs=(
                    (
                        selected_window.window_ref
                        if selected_window
                        else f"output:{args.device_index}:{args.output_index}"
                    ),
                    identity.evidence_ref,
                    identity.actor_evidence_ref,
                ),
            ).to_manifest()
            schema_path = ROOT / "contracts" / "capture-frame.schema.json"
            ContractValidator(schema_path).validate(manifest)
            print(json.dumps(manifest, sort_keys=True))
            return 0
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "capture_failed",
                    "backend": args.backend,
                    "error_type": type(error).__name__,
                    "detail": str(error),
                    "persisted": False,
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 1
    finally:
        if camera is not None:
            camera.release()


if __name__ == "__main__":
    sys.exit(probe())
