from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence
from uuid import uuid4

import numpy as np

from perfect_assassin.adapter.coordinate_hud import (
    validate_sequence_summary_semantics,
    validate_valid_observation_semantics,
)
from continuous_provider import ContinuousCaptureConfig, DxcamWindowCaptureProvider
from coordinate_hud_detector import CoordinateHudDetector
from perfect_assassin.capture import CapturePacket, CaptureProvider
from perfect_assassin.contract_validation import ContractValidator
from target_identity import (
    CaptureTargetIdentity,
    SCREEN_CAPTURE_READ_ONLY,
    VISIBLE_COORDINATE_HUD_READ_ONLY,
    load_capture_target_identity,
    verify_capture_process_identity,
)
from window_locator import WindowQuery, locate_window


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_PATH = ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
PROFILE_SCHEMA_PATH = ROOT / "contracts" / "coordinate-hud-profile.schema.json"
CAPTURE_SCHEMA_PATH = ROOT / "contracts" / "capture-frame.schema.json"
OBSERVATION_SCHEMA_PATH = ROOT / "contracts" / "coordinate-hud.schema.json"
SEQUENCE_SUMMARY_SCHEMA_PATH = (
    ROOT / "contracts" / "coordinate-hud-sequence-summary.schema.json"
)
AUTHORIZATION_SCHEMA_PATH = (
    ROOT / "contracts" / "execution-target-authorization.schema.json"
)
LAB_LAUNCH_RECEIPT_SCHEMA_PATH = (
    ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
)
DEFAULT_LAB_LAUNCH_RECEIPT_PATH = (
    ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
)

# Controlled-live probes accept only the reviewed detector profile. Its hash is
# computed from canonical JSON, so line endings cannot weaken or break the pin.
SUPPORTED_PROFILE_SHA256 = (
    "7A7475EF6CAFEB272640E1B609B85ED4B742F5B311112CC8C17CA36A74ADFEB4"
)

MIN_SAMPLES = 1
MAX_SAMPLES = 30
MIN_TARGET_FPS = 1.0
MAX_TARGET_FPS = 30.0
FRESHNESS_LIMIT_MS = 600.0
MAX_SEQUENCE_RATE_HZ = 20.0
SEQUENCE_BURST_ALLOWANCE = 2
SEQUENCE_ORCHESTRATION_BUDGET_MS = 250.0
MAX_SEQUENCE_SAMPLE_WALL_MS = 2000.0


class CoordinateHudProbeError(RuntimeError):
    pass


def _finite_non_negative(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise CoordinateHudProbeError(f"{label} must be finite and non-negative")
    return float(value)


@dataclass(frozen=True, slots=True)
class DecodedHudSample:
    observation: dict[str, Any]
    captured_monotonic_s: float


def load_pinned_profile(
    path: Path,
    *,
    expected_sha256: str = SUPPORTED_PROFILE_SHA256,
    schema_path: Path = PROFILE_SCHEMA_PATH,
) -> tuple[dict[str, Any], str]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoordinateHudProbeError("coordinate HUD profile cannot be loaded") from error
    ContractValidator(schema_path).validate(profile)
    canonical = json.dumps(
        profile,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    actual_sha256 = hashlib.sha256(canonical).hexdigest().upper()
    if actual_sha256 != expected_sha256.upper():
        raise CoordinateHudProbeError(
            "coordinate HUD profile SHA-256 does not match the reviewed profile"
        )
    if profile["marker_low_threshold"] >= profile["marker_high_threshold"]:
        raise CoordinateHudProbeError("coordinate HUD marker thresholds are invalid")
    return profile, actual_sha256


def validate_profile_binding(
    profile: dict[str, Any],
    identity: CaptureTargetIdentity,
    requested_client_build: str,
) -> None:
    if requested_client_build != identity.client_build:
        raise CoordinateHudProbeError("requested client build does not match identity")
    if profile["client_build"] != identity.client_build:
        raise CoordinateHudProbeError("client build does not match coordinate HUD profile")
    if profile["target_profile"] != identity.target_profile:
        raise CoordinateHudProbeError("target profile does not match coordinate HUD profile")
    expected_hash_suffix = f":sha256:{identity.executable_sha256}"
    if not identity.build_signature.endswith(expected_hash_suffix):
        raise CoordinateHudProbeError("capture identity does not carry the verified hash")


def bgra_view_from_packet(
    packet: CapturePacket,
    *,
    maximum_frame_pixels: int,
    validator: ContractValidator,
) -> np.ndarray:
    manifest = dict(packet.manifest)
    validator.validate(manifest)
    if manifest["artifact"]["persisted"]:
        raise CoordinateHudProbeError("persisted capture pixels are not accepted")
    if manifest["privacy"]["retention"] != "none":
        raise CoordinateHudProbeError("capture pixel retention must be none")
    if manifest["execution_authority"] is not False:
        raise CoordinateHudProbeError("capture manifest has execution authority")
    if packet.pixels is None:
        raise CoordinateHudProbeError("capture packet has no in-memory BGRA pixels")

    image = manifest["image"]
    width = int(image["width"])
    height = int(image["height"])
    stride = int(image["row_stride_bytes"])
    if width * height > maximum_frame_pixels:
        raise CoordinateHudProbeError("capture frame exceeds the pinned pixel budget")
    expected_bytes = height * stride
    if packet.pixels.nbytes != expected_bytes:
        raise CoordinateHudProbeError("capture byte length does not match the manifest")

    flat = np.frombuffer(packet.pixels, dtype=np.uint8, count=expected_bytes)
    rows = flat.reshape(height, stride)
    return rows[:, : width * 4].reshape(height, width, 4)


class CoordinateHudOneShotProbe:
    """Decode exactly one caller-owned frame and release its pixel view."""

    def __init__(
        self,
        profile: dict[str, Any],
        profile_sha256: str,
        capture_validator: ContractValidator,
        observation_validator: ContractValidator,
        detector: CoordinateHudDetector,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        process_identity_verifier: Callable[[], None] | None = None,
    ) -> None:
        self.profile = copy.deepcopy(profile)
        canonical_profile = json.dumps(
            self.profile,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        owned_profile_sha256 = hashlib.sha256(canonical_profile).hexdigest().upper()
        if owned_profile_sha256 != profile_sha256.upper():
            raise CoordinateHudProbeError(
                "coordinate HUD one-shot profile does not match its pinned SHA-256"
            )
        if (
            detector.profile_sha256 != owned_profile_sha256
            or detector.profile != self.profile
        ):
            raise CoordinateHudProbeError(
                "coordinate HUD detector and one-shot profiles are not identical"
            )
        self.profile_sha256 = owned_profile_sha256
        self.capture_validator = capture_validator
        self.observation_validator = observation_validator
        self.detector = detector
        self.monotonic = monotonic
        self.process_identity_verifier = process_identity_verifier

    def observe_once(
        self,
        provider: CaptureProvider,
        *,
        observation_id: str,
    ) -> dict[str, Any]:
        return self.observe_sample(
            provider,
            observation_id=observation_id,
        ).observation

    def observe_sample(
        self,
        provider: CaptureProvider,
        *,
        observation_id: str,
    ) -> DecodedHudSample:
        packet: CapturePacket | None = None
        frame: np.ndarray | None = None
        try:
            if self.process_identity_verifier is None:
                packet = provider.next_frame()
            else:
                self.process_identity_verifier()
                try:
                    packet = provider.next_frame()
                finally:
                    self.process_identity_verifier()
            if packet is None:
                raise CoordinateHudProbeError("capture provider returned no frame")
            manifest = dict(packet.manifest)
            if (
                manifest.get("backend") != "replay_fixture"
                and self.process_identity_verifier is None
            ):
                raise CoordinateHudProbeError(
                    "live coordinate HUD capture requires process-bound identity verification"
                )
            if manifest.get("client_build") != self.profile["client_build"]:
                raise CoordinateHudProbeError(
                    "capture client build does not match coordinate HUD profile"
                )
            if manifest.get("target_profile") != self.profile["target_profile"]:
                raise CoordinateHudProbeError(
                    "capture target does not match coordinate HUD profile"
                )
            if manifest.get("backend") != "replay_fixture" and ":sha256:" not in str(
                manifest.get("build_signature", "")
            ):
                raise CoordinateHudProbeError(
                    "live capture build signature has no verified executable hash"
                )
            frame = bgra_view_from_packet(
                packet,
                maximum_frame_pixels=int(self.profile["maximum_frame_pixels"]),
                validator=self.capture_validator,
            )
            started = _finite_non_negative(
                self.monotonic(),
                "detector start monotonic timestamp",
            )
            observation = self.detector.detect(
                manifest,
                frame,
                observation_id=observation_id,
            )
            observed_monotonic_s = _finite_non_negative(
                self.monotonic(),
                "detector completion monotonic timestamp",
            )
            if observed_monotonic_s < started:
                raise CoordinateHudProbeError(
                    "detector monotonic clock moved backwards"
                )
            detector_ms = (observed_monotonic_s - started) * 1000.0
            if detector_ms > float(self.profile["detector_deadline_ms"]):
                raise CoordinateHudProbeError(
                    "coordinate HUD detector exceeded the pinned deadline"
                )
            timing = observation["timing"]
            captured_monotonic_s = _finite_non_negative(
                timing["monotonic_timestamp_s"],
                "capture monotonic timestamp",
            )
            frame_age_ms = _finite_non_negative(
                timing["frame_age_ms"],
                "capture frame age",
            )
            if manifest["backend"] == "replay_fixture":
                timing["observed_monotonic_s"] = (
                    captured_monotonic_s
                    + frame_age_ms / 1000.0
                    + detector_ms / 1000.0
                )
                age_at_observation_ms = frame_age_ms + detector_ms
            else:
                if observed_monotonic_s < captured_monotonic_s:
                    raise CoordinateHudProbeError(
                        "live capture monotonic timestamp is in the future"
                    )
                timing["observed_monotonic_s"] = observed_monotonic_s
                age_at_observation_ms = max(
                    frame_age_ms,
                    (observed_monotonic_s - captured_monotonic_s) * 1000.0,
                )
            timing["age_at_observation_ms"] = age_at_observation_ms
            if (
                timing["age_at_observation_ms"]
                > float(timing["freshness_limit_ms"])
                and observation["tracking_state"] == "VALID"
            ):
                observation["tracking_state"] = "DEGRADED"
                observation["reason"] = "capture_frame_stale_at_observation"
                observation["confidence"] = 0.0
                observation["position"] = None
                observation["map_position_available"] = False
            profile_ref = (
                f"profile:{self.profile['profile']}:sha256:{self.profile_sha256}"
            )
            evidence_refs = observation["provenance"]["evidence_refs"]
            if profile_ref not in evidence_refs:
                evidence_refs.append(profile_ref)
            self.observation_validator.validate(observation)
            if observation["tracking_state"] == "VALID":
                validate_valid_observation_semantics(observation)
            return DecodedHudSample(
                observation=observation,
                captured_monotonic_s=captured_monotonic_s,
            )
        finally:
            if frame is not None:
                del frame
            if packet is not None and packet.pixels is not None:
                packet.pixels.release()


class CoordinateHudSequenceProbe:
    """Apply a bounded freshness gate to contract-valid in-memory frames."""

    def __init__(
        self,
        one_shot: CoordinateHudOneShotProbe,
        summary_validator: ContractValidator,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.one_shot = one_shot
        self.summary_validator = summary_validator
        self.monotonic = monotonic
        self.sleep = sleep
        capture_deadline_ms = _finite_non_negative(
            one_shot.profile["capture_deadline_ms"],
            "sequence capture deadline",
        )
        detector_deadline_ms = _finite_non_negative(
            one_shot.profile["detector_deadline_ms"],
            "sequence detector deadline",
        )
        self.sample_wall_budget_s = (
            capture_deadline_ms
            + detector_deadline_ms
            + SEQUENCE_ORCHESTRATION_BUDGET_MS
        ) / 1000.0
        if (
            self.sample_wall_budget_s <= 0
            or self.sample_wall_budget_s * 1000.0 > MAX_SEQUENCE_SAMPLE_WALL_MS
        ):
            raise CoordinateHudProbeError(
                "coordinate HUD sample wall budget exceeds the hard maximum"
            )

    def observe_sequence(
        self,
        provider: CaptureProvider,
        *,
        samples: int,
        target_fps: float,
        observation_id_prefix: str,
    ) -> dict[str, Any]:
        validate_probe_bounds(samples, target_fps)
        if samples < 2:
            raise CoordinateHudProbeError(
                "sequence freshness gate requires at least two samples"
            )

        interval_s = 1.0 / target_fps
        observed_samples = 0
        valid_observations = 0
        advances = 0
        duplicates = 0
        maximum_forward_delta = 0
        maximum_unchanged_ms = 0.0
        maximum_frame_age_ms = 0.0
        first_sequence: int | None = None
        last_sequence: int | None = None
        previous_sequence: int | None = None
        first_timestamp: float | None = None
        previous_timestamp: float | None = None
        last_advance_timestamp: float | None = None
        first_observation: dict[str, Any] | None = None
        last_observation: dict[str, Any] | None = None
        failure_reason: str | None = None
        sequence_started_s: float | None = None
        sequence_wall_deadline_s: float | None = None
        last_cycle_started_s: float | None = None

        for index in range(samples):
            cycle_started = _finite_non_negative(
                self.monotonic(),
                "sequence cycle monotonic timestamp",
            )
            last_cycle_started_s = cycle_started
            if sequence_started_s is None:
                sequence_started_s = cycle_started
                sequence_wall_deadline_s = sequence_started_s + samples * max(
                    interval_s,
                    self.sample_wall_budget_s,
                )
            elif cycle_started > float(sequence_wall_deadline_s):
                raise CoordinateHudProbeError(
                    "coordinate HUD sequence exceeded its monotonic wall deadline"
                )
            sample = self.one_shot.observe_sample(
                provider,
                observation_id=f"{observation_id_prefix}:{index + 1:02d}",
            )
            observation = sample.observation
            self.one_shot.observation_validator.validate(observation)
            sample_captured_monotonic_s = _finite_non_negative(
                sample.captured_monotonic_s,
                "sequence sample capture timestamp",
            )
            if observation["tracking_state"] == "VALID":
                validate_valid_observation_semantics(observation)
            observed_samples += 1
            frame_age_ms = _finite_non_negative(
                observation["timing"]["frame_age_ms"],
                "sequence frame age",
            )
            maximum_frame_age_ms = max(
                maximum_frame_age_ms,
                frame_age_ms,
            )
            if first_observation is None:
                first_observation = observation
                first_timestamp = sample_captured_monotonic_s
                last_advance_timestamp = sample_captured_monotonic_s
            last_observation = observation

            if not self._same_source(first_observation, observation):
                failure_reason = "source_binding_changed"
            elif observation["tracking_state"] != "VALID":
                failure_reason = "observation_not_valid"
            elif not self._same_map_context(first_observation, observation):
                failure_reason = "map_context_changed"
            else:
                valid_observations += 1
                protocol = observation["protocol"]
                if not isinstance(protocol, dict):
                    failure_reason = "observation_not_valid"
                else:
                    sequence = int(protocol["sequence"])
                    if first_sequence is None:
                        first_sequence = sequence
                    last_sequence = sequence
                    if previous_sequence is not None and previous_timestamp is not None:
                        elapsed_s = sample_captured_monotonic_s - previous_timestamp
                        if elapsed_s <= 0:
                            failure_reason = "non_monotonic_frame_time"
                        else:
                            delta = (sequence - previous_sequence) & 0xFF
                            if delta == 0:
                                duplicates += 1
                                unchanged_ms = (
                                    sample_captured_monotonic_s
                                    - float(last_advance_timestamp)
                                ) * 1000.0
                                maximum_unchanged_ms = max(
                                    maximum_unchanged_ms,
                                    unchanged_ms,
                                )
                                if unchanged_ms > FRESHNESS_LIMIT_MS:
                                    failure_reason = "sequence_stale"
                            elif delta >= 128:
                                failure_reason = "sequence_reverse"
                            else:
                                plausible_delta = min(
                                    127,
                                    max(
                                        1,
                                        math.ceil(elapsed_s * MAX_SEQUENCE_RATE_HZ)
                                        + SEQUENCE_BURST_ALLOWANCE,
                                    ),
                                )
                                if delta > plausible_delta:
                                    failure_reason = "sequence_jump_too_large"
                                else:
                                    advances += 1
                                    maximum_forward_delta = max(
                                        maximum_forward_delta,
                                        delta,
                                    )
                                    last_advance_timestamp = sample_captured_monotonic_s
                    previous_sequence = sequence
                    previous_timestamp = sample_captured_monotonic_s

            if failure_reason is not None:
                break
            if index + 1 < samples:
                cycle_completed = _finite_non_negative(
                    self.monotonic(),
                    "sequence cycle completion timestamp",
                )
                if cycle_completed < cycle_started:
                    raise CoordinateHudProbeError(
                        "sequence monotonic clock moved backwards"
                    )
                cycle_elapsed_s = cycle_completed - cycle_started
                if cycle_elapsed_s > self.sample_wall_budget_s:
                    raise CoordinateHudProbeError(
                        "coordinate HUD sample exceeded its monotonic wall deadline"
                    )
                if cycle_completed > float(sequence_wall_deadline_s):
                    raise CoordinateHudProbeError(
                        "coordinate HUD sequence exceeded its monotonic wall deadline"
                    )
                remaining_s = interval_s - cycle_elapsed_s
                if remaining_s > 0:
                    self.sleep(remaining_s)

        if failure_reason is None and advances == 0:
            failure_reason = "sequence_not_advanced"

        if first_observation is None or last_observation is None or first_timestamp is None:
            raise CoordinateHudProbeError("sequence probe produced no observation")
        evaluation_clock_s = _finite_non_negative(
            self.monotonic(),
            "sequence evaluation monotonic timestamp",
        )
        if (
            last_cycle_started_s is None
            or sequence_started_s is None
            or sequence_wall_deadline_s is None
        ):
            raise CoordinateHudProbeError("sequence wall deadline was not initialized")
        if evaluation_clock_s < last_cycle_started_s:
            raise CoordinateHudProbeError(
                "sequence monotonic clock moved backwards before evaluation"
            )
        if evaluation_clock_s - last_cycle_started_s > self.sample_wall_budget_s:
            raise CoordinateHudProbeError(
                "coordinate HUD sample exceeded its monotonic wall deadline"
            )
        if evaluation_clock_s > sequence_wall_deadline_s:
            raise CoordinateHudProbeError(
                "coordinate HUD sequence exceeded its monotonic wall deadline"
            )
        last_observed_monotonic_s = _finite_non_negative(
            last_observation["timing"]["observed_monotonic_s"],
            "last observation monotonic timestamp",
        )
        evaluated_monotonic_s = max(
            evaluation_clock_s,
            last_observed_monotonic_s,
        )
        last_observation_age_at_summary_ms = float(
            last_observation["timing"]["age_at_observation_ms"]
        ) + max(
            0.0,
            (
                evaluated_monotonic_s
                - last_observed_monotonic_s
            )
            * 1000.0,
        )
        if (
            failure_reason is None
            and last_observation_age_at_summary_ms
            > float(last_observation["timing"]["freshness_limit_ms"])
        ):
            failure_reason = "last_observation_expired"
        last_timestamp = _finite_non_negative(
            last_observation["timing"]["monotonic_timestamp_s"],
            "last capture monotonic timestamp",
        )
        if last_timestamp < first_timestamp:
            raise CoordinateHudProbeError(
                "sequence capture timestamps moved backwards"
            )
        duration_ms = (last_timestamp - first_timestamp) * 1000.0
        gate_state = "FAIL" if failure_reason is not None else "PASS"
        summary = {
            "record_type": "coordinate_hud_sequence_summary",
            "schema_version": "2.0",
            "session_id": first_observation["session_id"],
            "target_profile": first_observation["target_profile"],
            "actor_binding": copy.deepcopy(first_observation["actor_binding"]),
            "authorization_sha256": first_observation["authorization_sha256"],
            "decision_context": first_observation["decision_context"],
            "client_build": first_observation["client_build"],
            "build_signature": first_observation["build_signature"],
            "gate_state": gate_state,
            "reason": failure_reason or "fresh_sequence_verified",
            "requested_samples": samples,
            "observed_samples": observed_samples,
            "valid_observations": valid_observations,
            "all_observations_contract_valid": True,
            "all_observations_valid": valid_observations == observed_samples,
            "target_fps": target_fps,
            "sequence": {
                "first": first_sequence,
                "last": last_sequence,
                "advances": advances,
                "duplicates": duplicates,
                "maximum_forward_delta": maximum_forward_delta,
                "maximum_unchanged_ms": round(maximum_unchanged_ms, 3),
            },
            "timing": {
                "first_captured_at": first_observation["timing"]["captured_at"],
                "last_captured_at": last_observation["timing"]["captured_at"],
                "first_monotonic_timestamp_s": first_observation["timing"][
                    "monotonic_timestamp_s"
                ],
                "last_monotonic_timestamp_s": last_observation["timing"][
                    "monotonic_timestamp_s"
                ],
                "evaluated_monotonic_s": evaluated_monotonic_s,
                "duration_ms": round(duration_ms, 3),
                "maximum_frame_age_ms": round(maximum_frame_age_ms, 3),
                "last_observation_age_at_summary_ms": round(
                    last_observation_age_at_summary_ms,
                    3,
                ),
                "freshness_limit_ms": int(
                    self.one_shot.profile["freshness_limit_ms"]
                ),
            },
            "provenance": {
                "origin": "visible_addon_hud",
                "capture_origin": first_observation["provenance"]["capture_origin"],
                "capability": "self_map_position_freshness",
                "scope": first_observation["provenance"]["scope"],
                "profile_id": first_observation["provenance"]["profile_id"],
                "profile_version": first_observation["provenance"][
                    "profile_version"
                ],
                "profile_sha256": first_observation["provenance"]["profile_sha256"],
                "profile_calibration_state": first_observation["provenance"][
                    "profile_calibration_state"
                ],
                "evidence_refs": self._summary_evidence_refs(
                    first_observation,
                    last_observation,
                ),
            },
            "artifact": {"persisted": False},
            "privacy": {"pixels_in_output": False, "retention": "none"},
            "execution_authority": False,
        }
        self.summary_validator.validate(summary)
        validate_sequence_summary_semantics(summary)
        return summary

    @staticmethod
    def _same_source(
        first: dict[str, Any],
        current: dict[str, Any],
    ) -> bool:
        keys = (
            "session_id",
            "target_profile",
            "authorization_sha256",
            "client_build",
            "build_signature",
            "decision_context",
        )
        if not all(first[key] == current[key] for key in keys):
            return False
        if first["actor_binding"] != current["actor_binding"]:
            return False
        provenance_keys = (
            "origin",
            "capture_origin",
            "scope",
            "profile_id",
            "profile_version",
            "profile_sha256",
            "profile_calibration_state",
        )
        return all(
            first["provenance"][key] == current["provenance"][key]
            for key in provenance_keys
        )

    @staticmethod
    def _same_map_context(
        first: dict[str, Any],
        current: dict[str, Any],
    ) -> bool:
        first_position = first.get("position")
        current_position = current.get("position")
        if not isinstance(first_position, dict) or not isinstance(current_position, dict):
            return False
        keys = ("coordinate_space", "continent_index", "zone_index")
        return all(first_position.get(key) == current_position.get(key) for key in keys)

    @staticmethod
    def _summary_evidence_refs(
        first: dict[str, Any],
        last: dict[str, Any],
    ) -> list[str]:
        candidates = [
            first["frame_id"],
            last["frame_id"],
            *first["provenance"]["evidence_refs"],
            *last["provenance"]["evidence_refs"],
        ]
        result: list[str] = []
        for reference in candidates:
            if reference not in result:
                result.append(reference)
            if len(result) == 8:
                break
        return result


def bounded_samples(value: str) -> int:
    try:
        samples = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("samples must be an integer") from error
    if not MIN_SAMPLES <= samples <= MAX_SAMPLES:
        raise argparse.ArgumentTypeError(
            f"samples must be between {MIN_SAMPLES} and {MAX_SAMPLES}"
        )
    return samples


def bounded_target_fps(value: str) -> float:
    try:
        target_fps = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("target FPS must be a number") from error
    if not math.isfinite(target_fps) or not MIN_TARGET_FPS <= target_fps <= MAX_TARGET_FPS:
        raise argparse.ArgumentTypeError(
            f"target FPS must be between {MIN_TARGET_FPS:g} and {MAX_TARGET_FPS:g}"
        )
    return target_fps


def validate_probe_bounds(samples: int, target_fps: float) -> None:
    if not MIN_SAMPLES <= samples <= MAX_SAMPLES:
        raise CoordinateHudProbeError(
            f"samples must be between {MIN_SAMPLES} and {MAX_SAMPLES}"
        )
    if not math.isfinite(target_fps) or not MIN_TARGET_FPS <= target_fps <= MAX_TARGET_FPS:
        raise CoordinateHudProbeError(
            f"target FPS must be between {MIN_TARGET_FPS:g} and {MAX_TARGET_FPS:g}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a bounded set of exact WoW client-region frames in RAM "
            "and decode the visible Perfect Assassin coordinate HUD."
        )
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
    parser.add_argument("--samples", type=bounded_samples, default=1)
    parser.add_argument("--target-fps", type=bounded_target_fps, default=10.0)
    parser.add_argument("--client-build", required=True)
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--client-executable", type=Path, required=True)
    parser.add_argument(
        "--lab-launch-receipt",
        type=Path,
        default=DEFAULT_LAB_LAUNCH_RECEIPT_PATH,
    )
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE_PATH)
    return parser


def probe(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.device_index < 0 or args.output_index < 0:
        raise SystemExit("device and output indexes must be non-negative")
    validate_probe_bounds(args.samples, args.target_fps)

    provider: DxcamWindowCaptureProvider | None = None
    try:
        profile, profile_sha256 = load_pinned_profile(args.profile)
        identity = load_capture_target_identity(
            args.authorization_file,
            AUTHORIZATION_SCHEMA_PATH,
            args.client_executable,
            args.client_build,
            required_capabilities=(
                SCREEN_CAPTURE_READ_ONLY,
                VISIBLE_COORDINATE_HUD_READ_ONLY,
            ),
        )
        validate_profile_binding(profile, identity, args.client_build)

        capture_validator = ContractValidator(CAPTURE_SCHEMA_PATH)
        observation_validator = ContractValidator(OBSERVATION_SCHEMA_PATH)
        summary_validator = ContractValidator(SEQUENCE_SUMMARY_SCHEMA_PATH)
        detector = CoordinateHudDetector(
            profile,
            capture_validator,
            observation_validator,
        )
        provider = DxcamWindowCaptureProvider(
            ContinuousCaptureConfig(
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
                binding_assurance_evidence_refs=(
                    identity.binding_assurance_evidence_refs
                ),
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
        one_shot = CoordinateHudOneShotProbe(
            profile,
            profile_sha256,
            capture_validator,
            observation_validator,
            detector,
            process_identity_verifier=lambda: verify_capture_process_identity(
                args.window_pid,
                args.client_executable,
                identity,
                hwnd=args.window_hwnd,
                expected_title=args.window_title_exact,
                expected_class=args.window_class_exact,
                receipt_path=args.lab_launch_receipt,
                receipt_schema_path=LAB_LAUNCH_RECEIPT_SCHEMA_PATH,
                window_resolver=lambda: locate_window(
                    WindowQuery(
                        pid=args.window_pid,
                        hwnd=args.window_hwnd,
                        title_exact=args.window_title_exact,
                        class_exact=args.window_class_exact,
                    )
                ),
            ),
        )
        provider.open()
        observation_id = args.observation_id or f"coordinate-hud:{uuid4()}"
        if args.samples == 1:
            observation = one_shot.observe_once(
                provider,
                observation_id=observation_id,
            )
            print(json.dumps(observation, sort_keys=True))
            return 0 if observation["tracking_state"] == "VALID" else 3

        summary = CoordinateHudSequenceProbe(
            one_shot,
            summary_validator,
        ).observe_sequence(
            provider,
            samples=args.samples,
            target_fps=args.target_fps,
            observation_id_prefix=observation_id,
        )
        print(json.dumps(summary, sort_keys=True))
        return 0 if summary["gate_state"] == "PASS" else 3
    except Exception as error:
        print(
            json.dumps(
                {
                    "record_type": "coordinate_hud_probe_failure",
                    "status": "failed_closed",
                    "error_type": type(error).__name__,
                    "detail": str(error),
                    "map_position_available": False,
                    "persisted": False,
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 1
    finally:
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    sys.exit(probe())
