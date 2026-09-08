from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Sequence
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from combat_hud_detector import CombatHudDetector, load_profile
from continuous_provider import ContinuousCaptureConfig, DxcamWindowCaptureProvider
from perfect_assassin.adapter.combat_hud import validate_valid_observation_semantics
from perfect_assassin.contract_validation import ContractValidator
from probe_coordinate_hud import bgra_view_from_packet
from target_identity import (
    SCREEN_CAPTURE_READ_ONLY,
    VISIBLE_COMBAT_HUD_READ_ONLY,
    load_capture_target_identity,
    verify_capture_process_identity,
)
from window_locator import WindowQuery, locate_window


PROFILE_PATH = ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
PROFILE_SCHEMA_PATH = ROOT / "contracts" / "combat-hud-profile.schema.json"
CAPTURE_SCHEMA_PATH = ROOT / "contracts" / "capture-frame.schema.json"
OBSERVATION_SCHEMA_PATH = ROOT / "contracts" / "combat-hud.schema.json"
AUTHORIZATION_SCHEMA_PATH = ROOT / "contracts" / "execution-target-authorization.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
DEFAULT_RECEIPT_PATH = ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
SUPPORTED_PROFILE_SHA256 = "9483157F4F7085D00DD82BA4DE219C42225B8733D9AABD15EA68230E2EE690D3"


class CombatHudProbeError(RuntimeError):
    pass


def _load_pinned_profile(path: Path) -> tuple[dict, str]:
    if path.stat().st_size > 64 * 1024:
        raise CombatHudProbeError("combat HUD profile exceeds its byte budget")
    profile = load_profile(path)
    ContractValidator(PROFILE_SCHEMA_PATH).validate(profile)
    canonical = json.dumps(
        profile,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest().upper()
    if digest != SUPPORTED_PROFILE_SHA256:
        raise CombatHudProbeError("combat HUD profile SHA-256 is not reviewed")
    return profile, digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture exactly one in-memory frame and decode the visible combat HUD."
    )
    parser.add_argument("--backend", choices=("dxgi", "winrt"), default="dxgi")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--output-index", type=int, default=0)
    parser.add_argument("--window-pid", type=int, required=True)
    parser.add_argument("--window-hwnd", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--window-title-exact", required=True)
    parser.add_argument("--window-class-exact", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--observation-id")
    parser.add_argument("--client-build", required=True)
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--client-executable", type=Path, required=True)
    parser.add_argument("--lab-launch-receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--profile", type=Path, default=PROFILE_PATH)
    return parser


def probe(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.device_index < 0 or args.output_index < 0:
        raise SystemExit("device and output indexes must be non-negative")
    provider: DxcamWindowCaptureProvider | None = None
    packet = None
    frame = None
    try:
        profile, profile_sha256 = _load_pinned_profile(args.profile)
        identity = load_capture_target_identity(
            args.authorization_file,
            AUTHORIZATION_SCHEMA_PATH,
            args.client_executable,
            args.client_build,
            required_capabilities=(
                SCREEN_CAPTURE_READ_ONLY,
                VISIBLE_COMBAT_HUD_READ_ONLY,
            ),
        )
        if identity.target_profile != profile["target_profile"]:
            raise CombatHudProbeError("authorization target does not match combat HUD profile")
        if identity.client_build != profile["client_build"] or args.client_build != profile["client_build"]:
            raise CombatHudProbeError("authorization build does not match combat HUD profile")
        capture_validator = ContractValidator(CAPTURE_SCHEMA_PATH)
        observation_validator = ContractValidator(OBSERVATION_SCHEMA_PATH)
        detector = CombatHudDetector(profile, capture_validator, observation_validator)
        if detector.profile_sha256 != profile_sha256:
            raise CombatHudProbeError("detector profile snapshot diverges from reviewed hash")
        query = WindowQuery(
            pid=args.window_pid,
            hwnd=args.window_hwnd,
            title_exact=args.window_title_exact,
            class_exact=args.window_class_exact,
        )

        def verify_identity() -> None:
            verify_capture_process_identity(
                args.window_pid,
                args.client_executable,
                identity,
                hwnd=args.window_hwnd,
                expected_title=args.window_title_exact,
                expected_class=args.window_class_exact,
                receipt_path=args.lab_launch_receipt,
                receipt_schema_path=RECEIPT_SCHEMA_PATH,
                window_resolver=lambda: locate_window(query),
            )

        verify_identity()
        provider = DxcamWindowCaptureProvider(
            ContinuousCaptureConfig(
                query=query,
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
                buffer_capacity=1,
                capture_deadline_ms=float(profile["capture_deadline_ms"]),
            ),
            capture_validator,
            window_locator=locate_window,
        )
        verify_identity()
        provider.open()
        packet = provider.next_frame()
        verify_identity()
        if packet is None:
            raise CombatHudProbeError("capture provider returned no frame")
        manifest = dict(packet.manifest)
        frame = bgra_view_from_packet(
            packet,
            maximum_frame_pixels=int(profile["maximum_frame_pixels"]),
            validator=capture_validator,
        )
        started = time.monotonic()
        observation = detector.detect(
            manifest,
            frame,
            observation_id=args.observation_id or f"combat-hud:{uuid4()}",
        )
        completed = time.monotonic()
        if not all(math.isfinite(value) and value >= 0 for value in (started, completed)) or completed < started:
            raise CombatHudProbeError("combat detector monotonic timing is invalid")
        if (completed - started) * 1000.0 > float(profile["detector_deadline_ms"]):
            raise CombatHudProbeError("combat detector exceeded its deadline")
        timing = observation["timing"]
        captured_s = float(timing["monotonic_timestamp_s"])
        frame_age_ms = float(timing["frame_age_ms"])
        if completed < captured_s:
            raise CombatHudProbeError("capture monotonic timestamp is in the future")
        timing["observed_monotonic_s"] = completed
        timing["age_at_observation_ms"] = max(
            frame_age_ms,
            (completed - captured_s) * 1000.0,
        )
        if timing["age_at_observation_ms"] > timing["freshness_limit_ms"] and observation["tracking_state"] == "VALID":
            observation.update(
                {
                    "tracking_state": "DEGRADED",
                    "reason": "capture_frame_stale_at_observation",
                    "confidence": 0.0,
                    "protocol": None,
                    "player": None,
                    "target": None,
                    "combat": None,
                    "actions": None,
                }
            )
        observation_validator.validate(observation)
        if observation["tracking_state"] == "VALID":
            validate_valid_observation_semantics(observation)
        print(json.dumps(observation, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0 if observation["tracking_state"] == "VALID" else 3
    except Exception as error:
        print(
            json.dumps(
                {
                    "record_type": "combat_hud_probe_error",
                    "schema_version": "1.0",
                    "error_type": type(error).__name__,
                    "detail": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    finally:
        if frame is not None:
            del frame
        if packet is not None and packet.pixels is not None:
            packet.pixels.release()
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    raise SystemExit(probe())
