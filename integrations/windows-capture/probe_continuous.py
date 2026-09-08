from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from perfect_assassin.contract_validation import ContractValidator
from continuous_provider import (
    MAX_BUFFER_CAPACITY,
    MAX_CAPTURE_DEADLINE_MS,
    ContinuousCaptureConfig,
    DxcamWindowCaptureProvider,
)
from target_identity import (
    SCREEN_CAPTURE_READ_ONLY,
    load_capture_target_identity,
    run_process_bound_capture,
    verify_capture_process_identity,
)
from window_locator import WindowQuery, locate_window


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAB_LAUNCH_RECEIPT = (
    ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
)
LAB_LAUNCH_RECEIPT_SCHEMA = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
MAX_SAMPLES = 600
MAX_TARGET_FPS = 60.0
MAX_WALL_DURATION_S = 30.0


def bounded_integer(value: str, *, label: str, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{label} must be an integer") from error
    if parsed < 1 or parsed > maximum:
        raise argparse.ArgumentTypeError(f"{label} must be in [1, {maximum}]")
    return parsed


def bounded_float(value: str, *, label: str, maximum: float) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{label} must be a number") from error
    if not math.isfinite(parsed) or parsed <= 0 or parsed > maximum:
        raise argparse.ArgumentTypeError(f"{label} must be finite and in (0, {maximum}]")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a bounded in-memory continuous window capture probe."
    )
    parser.add_argument("--backend", choices=("dxgi", "winrt"), default="dxgi")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--output-index", type=int, default=0)
    parser.add_argument("--window-pid", type=int, required=True)
    parser.add_argument("--window-hwnd", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--window-title-exact", required=True)
    parser.add_argument("--window-class-exact", required=True)
    parser.add_argument(
        "--samples",
        type=lambda value: bounded_integer(value, label="samples", maximum=MAX_SAMPLES),
        default=30,
    )
    parser.add_argument(
        "--target-fps",
        type=lambda value: bounded_float(
            value,
            label="target FPS",
            maximum=MAX_TARGET_FPS,
        ),
        default=10.0,
    )
    parser.add_argument(
        "--deadline-ms",
        type=lambda value: bounded_float(
            value,
            label="capture deadline",
            maximum=MAX_CAPTURE_DEADLINE_MS,
        ),
        default=250.0,
    )
    parser.add_argument(
        "--buffer-capacity",
        type=lambda value: bounded_integer(
            value,
            label="buffer capacity",
            maximum=MAX_BUFFER_CAPACITY,
        ),
        default=3,
    )
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--client-build", required=True)
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--client-executable", type=Path, required=True)
    parser.add_argument(
        "--lab-launch-receipt",
        type=Path,
        default=DEFAULT_LAB_LAUNCH_RECEIPT,
    )
    return parser


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def probe(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.samples / args.target_fps > MAX_WALL_DURATION_S:
        raise SystemExit("bounded probe duration may not exceed 30 seconds")

    schema_path = ROOT / "contracts" / "capture-frame.schema.json"
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
    config = ContinuousCaptureConfig(
        query=WindowQuery(
            pid=args.window_pid,
            hwnd=args.window_hwnd,
            title_exact=args.window_title_exact,
            class_exact=args.window_class_exact,
        ),
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
        binding_assurance_evidence_refs=identity.binding_assurance_evidence_refs,
        authorization_sha256=identity.authorization_sha256,
        client_build=identity.client_build,
        build_signature=identity.build_signature,
        identity_evidence_ref=identity.evidence_ref,
        actor_evidence_ref=identity.actor_evidence_ref,
        backend=args.backend,
        device_index=args.device_index,
        output_index=args.output_index,
        buffer_capacity=args.buffer_capacity,
        capture_deadline_ms=args.deadline_ms,
    )
    provider = DxcamWindowCaptureProvider(
        config,
        ContractValidator(schema_path),
        window_locator=locate_window,
    )

    call_durations_ms: list[float] = []
    latest_manifest = None
    started = time.monotonic()
    wall_deadline_s = started + MAX_WALL_DURATION_S
    interval_s = 1.0 / args.target_fps

    def verify_process_identity() -> None:
        verify_capture_process_identity(
            args.window_pid,
            args.client_executable,
            identity,
            hwnd=args.window_hwnd,
            expected_title=args.window_title_exact,
            expected_class=args.window_class_exact,
            receipt_path=args.lab_launch_receipt,
            receipt_schema_path=LAB_LAUNCH_RECEIPT_SCHEMA,
            window_resolver=lambda: locate_window(config.query),
        )

    try:
        provider.open()
        for _index in range(args.samples):
            cycle_started = time.monotonic()
            if cycle_started >= wall_deadline_s:
                raise TimeoutError("continuous capture exceeded its 30 second wall deadline")
            packet = run_process_bound_capture(
                provider.next_frame,
                verify_process_identity,
            )
            cycle_finished = time.monotonic()
            if cycle_finished > wall_deadline_s:
                raise TimeoutError("continuous capture exceeded its 30 second wall deadline")
            call_durations_ms.append((cycle_finished - cycle_started) * 1000.0)
            latest_manifest = packet.manifest
            remaining = interval_s - (cycle_finished - cycle_started)
            if _index + 1 < args.samples and remaining > 0:
                if time.monotonic() + remaining > wall_deadline_s:
                    raise TimeoutError(
                        "continuous capture would exceed its 30 second wall deadline"
                    )
                time.sleep(remaining)
        finished = time.monotonic()
        if finished > wall_deadline_s:
            raise TimeoutError(
                "continuous capture exceeded its 30 second wall deadline before emission"
            )
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "continuous_capture_failed",
                    "backend": args.backend,
                    "error_type": type(error).__name__,
                    "detail": str(error),
                    "stats": asdict(provider.stats),
                    "persisted": False,
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 1
    finally:
        provider.close()

    elapsed_ms = (finished - started) * 1000.0
    print(
        json.dumps(
            {
                "status": "continuous_capture_complete",
                "backend": args.backend,
                "requested_samples": args.samples,
                "target_fps": args.target_fps,
                "elapsed_ms": round(elapsed_ms, 3),
                "call_duration_ms": {
                    "min": round(min(call_durations_ms), 3),
                    "p50": round(percentile(call_durations_ms, 0.50), 3),
                    "p95": round(percentile(call_durations_ms, 0.95), 3),
                    "max": round(max(call_durations_ms), 3),
                },
                "stats": asdict(provider.stats),
                "latest_manifest": latest_manifest,
                "buffer_capacity": args.buffer_capacity,
                "buffer_cleared_on_close": len(provider.buffer) == 0,
                "persisted": False,
                "execution_authority": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(probe())
