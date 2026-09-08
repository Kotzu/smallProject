from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from coordinate_hud_detector import (
    CoordinateHudDetectionError,
    locate_visible_hud_markers,
)
from perfect_assassin.adapter.combat_hud import (
    MAGIC,
    PROTOCOL_VERSION,
    TARGET_BEARING_CODES,
    CombatHudProtocolError,
    bits_to_packet,
    decode_packet,
    validate_valid_observation_semantics,
)
from perfect_assassin.contract_validation import ContractValidator


class CombatHudDetectionError(ValueError):
    pass


def _finite_number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < minimum
    ):
        raise CombatHudDetectionError(
            f"{label} must be finite and at least {minimum:g}"
        )
    return float(value)


def load_profile(path: Path) -> dict[str, Any]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CombatHudDetectionError("combat HUD profile is unreadable") from error
    if profile.get("protocol_version") != PROTOCOL_VERSION or profile.get("magic") != MAGIC:
        raise CombatHudDetectionError("unsupported combat HUD profile")
    if profile.get("grid_columns") != 16 or profile.get("grid_rows") != 14:
        raise CombatHudDetectionError("combat HUD profile grid is not v2")
    return profile


class CombatHudDetector:
    def __init__(
        self,
        profile: dict[str, Any],
        capture_validator: ContractValidator,
        observation_validator: ContractValidator,
        *,
        search_window_fraction: tuple[float, float, float, float] | None = None,
        reuse_marker_geometry: bool = False,
    ) -> None:
        self.profile = copy.deepcopy(profile)
        canonical = json.dumps(
            self.profile,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        self.profile_sha256 = hashlib.sha256(canonical).hexdigest().upper()
        self.capture_validator = capture_validator
        self.observation_validator = observation_validator
        if search_window_fraction is not None:
            if (
                len(search_window_fraction) != 4
                or any(
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in search_window_fraction
                )
                or not 0 <= float(search_window_fraction[0])
                < float(search_window_fraction[2])
                <= float(self.profile["search_width_fraction"])
                or not 0 <= float(search_window_fraction[1])
                < float(search_window_fraction[3])
                <= float(self.profile["search_height_fraction"])
            ):
                raise CombatHudDetectionError(
                    "combat HUD fast search window is invalid"
                )
            self._search_window_fraction = tuple(
                float(value) for value in search_window_fraction
            )
        else:
            self._search_window_fraction = None
        if not isinstance(reuse_marker_geometry, bool):
            raise CombatHudDetectionError(
                "reuse_marker_geometry must be boolean"
            )
        self._reuse_marker_geometry = reuse_marker_geometry
        self._cached_markers: tuple[tuple[float, float, int], ...] | None = None
        self._cached_frame_shape: tuple[int, ...] | None = None
        _finite_number(self.profile["freshness_limit_ms"], "freshness_limit_ms", minimum=0.000001)
        _finite_number(self.profile["detector_deadline_ms"], "detector_deadline_ms", minimum=0.000001)

    def detect(
        self,
        manifest: dict[str, Any],
        frame: np.ndarray,
        *,
        observation_id: str,
    ) -> dict[str, Any]:
        self.capture_validator.validate(manifest)
        if manifest["client_build"] != self.profile["client_build"]:
            raise CombatHudDetectionError("client_build does not match combat HUD profile")
        expected_shape = (manifest["image"]["height"], manifest["image"]["width"], 4)
        if frame.shape != expected_shape or frame.dtype != np.uint8:
            raise CombatHudDetectionError("BGRA8 frame shape or dtype mismatch")
        if frame.shape[0] * frame.shape[1] > int(self.profile["maximum_frame_pixels"]):
            raise CombatHudDetectionError("capture frame exceeds detector pixel budget")
        timing = manifest["timing"]
        _finite_number(timing["monotonic_timestamp_s"], "capture monotonic timestamp")
        _finite_number(timing["frame_age_ms"], "capture frame age")
        if timing["frame_age_ms"] > self.profile["freshness_limit_ms"]:
            return self._observation(
                manifest,
                observation_id,
                state="DEGRADED",
                reason="capture_frame_stale",
            )

        deadline_s = time.perf_counter() + float(self.profile["detector_deadline_ms"]) / 1000.0
        try:
            markers = self._locate_markers(frame, deadline_s=deadline_s)
        except CoordinateHudDetectionError as error:
            raise CombatHudDetectionError(str(error)) from error
        if markers is None:
            return self._observation(
                manifest,
                observation_id,
                state="NOT_FOUND",
                reason="fiducials_not_found",
            )
        cyan, magenta, yellow, _green = markers
        scale_x = (magenta[0] - cyan[0]) / self.profile["fiducial_dx_px"]
        scale_y = (yellow[1] - cyan[1]) / self.profile["fiducial_dy_px"]
        scale = (scale_x + scale_y) / 2.0
        pitch = self.profile["cell_pitch_px"] * scale
        first_x = cyan[0] + self.profile["first_cell_dx_px"] * scale
        first_y = cyan[1] + self.profile["first_cell_dy_px"] * scale
        bits: list[int] = []
        for row in range(14):
            for column in range(16):
                if time.perf_counter() > deadline_s:
                    raise CombatHudDetectionError("combat HUD detector operation budget exceeded")
                x = int(round(first_x + column * pitch))
                y = int(round(first_y + row * pitch))
                radius = max(0, int(round(scale - 1.0)))
                sample = frame[
                    max(0, y - radius) : y + radius + 1,
                    max(0, x - radius) : x + radius + 1,
                    :3,
                ]
                if sample.size == 0:
                    return self._observation(
                        manifest,
                        observation_id,
                        state="INVALID",
                        reason="payload_out_of_frame",
                    )
                bits.append(
                    int(float(sample.mean()) >= self.profile["bit_luminance_threshold"])
                )
        raw_packet = bits_to_packet(bits)
        try:
            packet = decode_packet(raw_packet)
        except CombatHudProtocolError as error:
            return self._observation(
                manifest,
                observation_id,
                state="INVALID",
                reason=str(error),
            )
        target = None
        if packet.target_exists:
            target = {
                "identity_crc16": packet.target_identity_crc16,
                "hostile": packet.target_hostile,
                "dead": packet.target_dead,
                "is_player": packet.target_player,
                "health_pct": packet.target_health_pct,
                "health_current": packet.target_health_current,
                "health_max": packet.target_health_max,
                "level": packet.target_level,
                "reaction": packet.target_reaction,
                "bearing_code": packet.target_bearing_code,
                "bearing_state": TARGET_BEARING_CODES[packet.target_bearing_code][0],
                "bearing_direction": TARGET_BEARING_CODES[packet.target_bearing_code][1],
                "bearing_offset_x_normalized": (
                    None
                    if packet.target_frame_x_normalized is None
                    else packet.target_frame_x_normalized * 2.0 - 1.0
                ),
                "interact_x_normalized": packet.target_interact_x_normalized,
                "interact_y_normalized": packet.target_interact_y_normalized,
            }
        return self._observation(
            manifest,
            observation_id,
            state="VALID",
            reason="crc_valid_combat_state_observed",
            confidence=1.0,
            protocol={
                "magic": MAGIC,
                "version": PROTOCOL_VERSION,
                "sequence": packet.sequence,
                "crc_valid": True,
                "packet_hex": raw_packet.hex(),
            },
            player={
                "alive": packet.player_alive,
                "health_pct": packet.player_health_pct,
                "energy": packet.player_energy,
                "attack_power": packet.player_attack_power,
                "level": packet.player_level,
            },
            target=target,
            combat={
                "in_combat": packet.in_combat,
                "combo_points": packet.combo_points,
                "loot_event_sequence": packet.loot_event_sequence,
                "acquisition_bearing_code": (
                    0 if packet.target_exists else packet.target_bearing_code
                ),
                "acquisition_bearing_state": (
                    "LOST"
                    if packet.target_exists
                    else TARGET_BEARING_CODES[packet.target_bearing_code][0]
                ),
                "acquisition_bearing_direction": (
                    None
                    if packet.target_exists
                    else TARGET_BEARING_CODES[packet.target_bearing_code][1]
                ),
                "acquisition_bearing_offset_x_normalized": (
                    None
                    if packet.target_exists
                    else TARGET_BEARING_CODES[packet.target_bearing_code][2]
                ),
                "visible_attackable_candidate_count": (
                    0
                    if packet.target_exists
                    else packet.visible_attackable_candidate_count
                ),
                "acquisition_x_normalized": (
                    None if packet.target_exists else packet.acquisition_x_normalized
                ),
                "acquisition_y_normalized": (
                    None if packet.target_exists else packet.acquisition_y_normalized
                ),
            },
            actions={
                "slot1_attack": {
                    "exact_binding": packet.slot1_attack_exact,
                    "usable": packet.slot1_usable,
                    "current": packet.slot1_current,
                    "in_range": packet.slot1_in_range,
                    "cooldown_ready": True,
                    "cooldown_remaining_ms": 0,
                },
                "slot2_sinister_strike": {
                    "exact_binding": packet.slot2_sinister_strike_exact,
                    "usable": packet.slot2_usable,
                    "current": False,
                    "in_range": packet.slot2_in_range,
                    "cooldown_ready": packet.slot2_cooldown_ready,
                    "cooldown_remaining_ms": packet.slot2_cooldown_remaining_ms,
                },
                "slot3_eviscerate": {
                    "exact_binding": packet.slot3_eviscerate_exact,
                    "usable": packet.slot3_usable,
                    "current": False,
                    "in_range": packet.slot3_in_range,
                    "cooldown_ready": packet.slot3_cooldown_ready,
                    "cooldown_remaining_ms": 0,
                },
            },
        )

    def _locate_markers(
        self,
        frame: np.ndarray,
        *,
        deadline_s: float,
    ) -> tuple[tuple[float, float, int], ...] | None:
        if (
            self._reuse_marker_geometry
            and self._cached_markers is not None
            and self._cached_frame_shape == frame.shape
            and self._cached_markers_are_visible(frame)
        ):
            return self._cached_markers
        markers = locate_visible_hud_markers(
            frame,
            self.profile,
            deadline_s=deadline_s,
            search_window_fraction=self._search_window_fraction,
        )
        if self._reuse_marker_geometry:
            self._cached_markers = markers
            self._cached_frame_shape = frame.shape if markers is not None else None
        return markers

    def _cached_markers_are_visible(self, frame: np.ndarray) -> bool:
        assert self._cached_markers is not None
        high = float(self.profile["marker_high_threshold"])
        low = float(self.profile["marker_low_threshold"])
        expected = (
            (True, True, False),
            (True, False, True),
            (False, True, True),
            (False, True, False),
        )
        height, width = frame.shape[:2]
        for marker, channel_high in zip(
            self._cached_markers,
            expected,
            strict=True,
        ):
            x, y = int(round(marker[0])), int(round(marker[1]))
            if not (1 <= x < width - 1 and 1 <= y < height - 1):
                return False
            mean_bgr = frame[
                y - 1 : y + 2,
                x - 1 : x + 2,
                :3,
            ].mean(axis=(0, 1))
            for value, should_be_high in zip(
                mean_bgr,
                channel_high,
                strict=True,
            ):
                if should_be_high and value < high:
                    return False
                if not should_be_high and value > low:
                    return False
        return True

    def _observation(
        self,
        manifest: dict[str, Any],
        observation_id: str,
        *,
        state: str,
        reason: str,
        confidence: float = 0.0,
        protocol: dict[str, Any] | None = None,
        player: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
        combat: dict[str, Any] | None = None,
        actions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        capture_origin = manifest["provenance"]["origin"]
        decision_context = manifest["decision_context"]
        if capture_origin == "replay_fixture":
            scope = "synthetic_fixture"
        elif decision_context == "lab_clone":
            scope = "lab_evaluation_only"
        else:
            scope = "unpromoted_evaluation_only"
        profile_ref = f"profile:{self.profile['profile']}:sha256:{self.profile_sha256}"
        evidence_refs: list[str] = []
        for reference in (
            manifest["frame_id"],
            *manifest["provenance"]["evidence_refs"],
            profile_ref,
        ):
            if reference not in evidence_refs:
                evidence_refs.append(reference)
        captured_s = float(manifest["timing"]["monotonic_timestamp_s"])
        frame_age_ms = float(manifest["timing"]["frame_age_ms"])
        result = {
            "record_type": "combat_hud_observation",
            "schema_version": "1.0",
            "observation_id": observation_id,
            "frame_id": manifest["frame_id"],
            "session_id": manifest["session_id"],
            "target_profile": manifest["target_profile"],
            "actor_binding": copy.deepcopy(manifest["actor_binding"]),
            "authorization_sha256": manifest["authorization_sha256"],
            "decision_context": decision_context,
            "client_build": manifest["client_build"],
            "build_signature": manifest["build_signature"],
            "tracking_state": state,
            "reason": reason,
            "confidence": confidence,
            "timing": {
                "captured_at": manifest["timing"]["captured_at"],
                "monotonic_timestamp_s": captured_s,
                "frame_age_ms": frame_age_ms,
                "observed_monotonic_s": captured_s + frame_age_ms / 1000.0,
                "age_at_observation_ms": frame_age_ms,
                "freshness_limit_ms": self.profile["freshness_limit_ms"],
                "expires_monotonic_s": captured_s + self.profile["freshness_limit_ms"] / 1000.0,
            },
            "protocol": protocol,
            "player": player,
            "target": target,
            "combat": combat,
            "actions": actions,
            "provenance": {
                "origin": "visible_addon_hud",
                "capture_origin": capture_origin,
                "capability": "combat_state_visible_hud",
                "scope": scope,
                "profile_id": self.profile["profile"],
                "profile_version": self.profile["profile_version"],
                "profile_sha256": self.profile_sha256,
                "profile_calibration_state": self.profile["calibration_state"],
                "evidence_refs": evidence_refs,
            },
            "execution_authority": False,
        }
        self.observation_validator.validate(result)
        if state == "VALID":
            validate_valid_observation_semantics(result)
        return result
