from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from time import monotonic_ns
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
CAPTURE_INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(CAPTURE_INTEGRATION) not in sys.path:
    sys.path.insert(0, str(CAPTURE_INTEGRATION))

from combat_hud_detector import CombatHudDetector, load_profile as load_combat_profile
from coordinate_hud_detector import CoordinateHudDetector
from minimap_detector import (
    MarkerCandidate,
    MinimapVisionDetector,
    load_profile as load_minimap_profile,
    world_heading_from_marker,
)
from selected_target_bearing_detector import (
    SelectedTargetBearingError,
    SelectedTargetBearingDetector,
    load_profile as load_bearing_profile,
)
from continuous_provider import ContinuousCaptureConfig, DxcamWindowCaptureProvider
from pause_hotkey import PauseHotkeySource
from probe_coordinate_hud import bgra_view_from_packet, load_pinned_profile
from send_input_backend import CtypesWin32KeyboardBackend
from target_identity import (
    SCREEN_CAPTURE_READ_ONLY,
    VISIBLE_COMBAT_HUD_READ_ONLY,
    VISIBLE_COORDINATE_HUD_READ_ONLY,
    load_capture_target_identity,
    verify_capture_process_identity,
)
from window_locator import WindowQuery, locate_window
from perfect_assassin.adapter.combat_hud import validate_valid_observation_semantics
from perfect_assassin.capture import NoFreshCaptureFrameError
from perfect_assassin.application.combat_intake import (
    decode_combat_observation,
    decode_crc_target_bearing,
    decode_target_bearing_observation,
)
from perfect_assassin.brain.combat import CombatDecision, RogueLevelOneCombatPolicy
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.combat_range import (
    selected_target_melee_range_awareness,
)
from perfect_assassin.domain.facing import bearing_refinement_is_compatible
from perfect_assassin.execution.combat_authorization import (
    COMBAT_EXECUTION_AUTHORIZATION_ID,
    issue_combat_execution_authorization_snapshot,
)
from perfect_assassin.execution.combat_gateway import (
    CombatActionGateway,
    ControlledCombatEncounter,
    ControlledCombatEncounterFailure,
    TARGET_CHANGE_OBSERVATION_BUDGET,
)
from perfect_assassin.execution.combat_motion_gateway import CombatMotionGateway
from perfect_assassin.execution.operator_control import FileOperatorCombatControl
from perfect_assassin.execution.combat_runtime_arm import (
    issue_combat_runtime_arm_snapshot,
    load_combat_runtime_arm,
)
from perfect_assassin.execution.contracts import AuthorityBinding
from perfect_assassin.execution.ports import SystemMonotonicClock
from perfect_assassin.execution.windows_send_input import (
    WindowsInputTargetBinding,
    WindowsSendInputSink,
)
from perfect_assassin.execution.windows_continuous_motion import (
    WindowsContinuousMotionSession,
)
from perfect_assassin.execution.windows_mouse_turn import (
    WindowsCombatInputSink,
    WindowsMouseTurnSink,
)
from perfect_assassin.execution.windows_target_command import (
    WindowsExactTargetCommandGateway,
)
from perfect_assassin.movement.movement_lab import MovementLabSnapshot
from client_navmesh_backend import ClientAssetNavmeshQuery
from perfect_assassin.movement.client_navmesh import NavPoint
from perfect_assassin.movement.combat_retreat import (
    BreadcrumbCombatRetreatController,
    safe_retreat_deadline_seconds,
)
from perfect_assassin.movement.safe_retreat import corridor_from_retreat_context
from perfect_assassin.movement.target_tether import TargetTetherIntent
from perfect_assassin.movement.target_tether_coordinator import (
    AsyncTargetTetherCoordinator,
)
from perfect_assassin.movement.zone_transform import tbc243_zone_transform
from perfect_assassin.movement.combat_motion import (
    CameraPitchProbeController,
    FacingTransferProbeController,
    HumanlikeCombatMotionController,
)
from perfect_assassin.runtime_paths import external_runtime_root


AUTH_SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
RECEIPT_SCHEMA = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
REALM_SCHEMA = ROOT / "contracts" / "local-realm-revalidation.schema.json"
ARM_SCHEMA = ROOT / "contracts" / "combat-runtime-arm.schema.json"
OBSERVATION_SCHEMA = ROOT / "contracts" / "combat-hud.schema.json"
BEARING_SCHEMA = ROOT / "contracts" / "selected-target-bearing.schema.json"
CAPTURE_SCHEMA = ROOT / "contracts" / "capture-frame.schema.json"
COORDINATE_SCHEMA = ROOT / "contracts" / "coordinate-hud.schema.json"
MINIMAP_SCHEMA = ROOT / "contracts" / "minimap-vision.schema.json"
COMBAT_PROFILE = ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
BEARING_PROFILE = (
    ROOT / "config" / "combat" / "selected-target-bearing-tbc243-v1.json"
)
COORDINATE_PROFILE = ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
MINIMAP_PROFILE = ROOT / "config" / "pose" / "minimap-tbc243-8606.json"
DEFAULT_NAV_ROOT = (
    external_runtime_root(ROOT) / "navigation" / "tbc243-human-road-corridor-v6"
)
DEFAULT_NAV_WORKER = (
    ROOT / "data" / "runtime" / "native-build" / "pa_nav_probe-v26"
    / "Debug" / "pa_nav_probe.exe"
)
COMBAT_TEMPLATE = (
    ROOT
    / "config"
    / "execution-targets"
    / "tbc_243_lab_combat_observer.json"
)
OPERATOR = ROOT / "scripts" / "Invoke-LabClientOperator.ps1"
RUNTIME_ROOT = ROOT / "data" / "runtime" / "combat-f4a"
MOVEMENT_LAB_STATE = ROOT / "data" / "runtime" / "movement-lab" / "latest.json"
OPERATOR_RUNTIME = ROOT / "data" / "runtime" / "operator"
COMBAT_PROFILE_SHA256 = "9483157F4F7085D00DD82BA4DE219C42225B8733D9AABD15EA68230E2EE690D3"
BEARING_PROFILE_SHA256 = "A40D5672814A7555F8901F6445BC3E29E20F9AF26B2379B9C01F4336492DF3A5"
FRESH_FRAME_RETRY_BUDGET = 3
FRESH_FRAME_RETRY_WAIT_S = 0.05
CONTINUOUS_CONTROL_PERIOD_S = 0.05
CONTINUOUS_FACING_MAX_FRAMES = 100
CONTINUOUS_FACING_LOCK_FRAMES = 6


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        for replace_attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if replace_attempt == 5:
                    raise
                # The external MovementEngine UI can briefly hold latest.json
                # without FILE_SHARE_DELETE. Preserve atomic publication and
                # retry the same fsynced snapshot instead of writing in place.
                time.sleep(0.010 * (replace_attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def _exact_json_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _profile_sha256(value: dict[str, object]) -> str:
    import hashlib

    return hashlib.sha256(_exact_json_bytes(value)).hexdigest().upper()


class LiveCombatPerceptionSource:
    def __init__(
        self,
        *,
        arm,
        authorization_file: Path,
        session_authorization_file: Path,
        session_receipt: Path,
        session_id: str,
        tether_coordinator: AsyncTargetTetherCoordinator | None = None,
        start_world_z_hint: float = 100.0,
        movement_lab_state_file: Path | None = MOVEMENT_LAB_STATE,
        selected_target_indicator_color_override: str | None = None,
    ) -> None:
        self._arm = arm
        self._authorization_file = authorization_file
        self._session_receipt = session_receipt
        self._session_id = session_id
        self._movement_lab_state_file = movement_lab_state_file
        self._selected_target_indicator_color_override = (
            selected_target_indicator_color_override
        )
        self._tether_coordinator = tether_coordinator
        self._start_world_z_hint = float(start_world_z_hint)
        self._counter = 0
        self._capture_validator = ContractValidator(CAPTURE_SCHEMA)
        self._combat_validator = ContractValidator(OBSERVATION_SCHEMA)
        self._bearing_validator = ContractValidator(BEARING_SCHEMA)
        self._coordinate_validator = ContractValidator(COORDINATE_SCHEMA)
        self._minimap_validator = ContractValidator(MINIMAP_SCHEMA)
        combat_profile = load_combat_profile(COMBAT_PROFILE)
        if _profile_sha256(combat_profile) != COMBAT_PROFILE_SHA256:
            raise RuntimeError("combat HUD profile is not the reviewed version")
        self._combat_detector = CombatHudDetector(
            combat_profile,
            self._capture_validator,
            self._combat_validator,
        )
        bearing_profile = load_bearing_profile(BEARING_PROFILE)
        if _profile_sha256(bearing_profile) != BEARING_PROFILE_SHA256:
            raise RuntimeError("selected-target bearing profile is not reviewed")
        self._bearing_detector = SelectedTargetBearingDetector(
            bearing_profile,
            self._capture_validator,
            self._combat_validator,
            self._bearing_validator,
        )
        coordinate_profile, _coordinate_profile_sha256 = load_pinned_profile(
            COORDINATE_PROFILE
        )
        self._coordinate_detector = CoordinateHudDetector(
            coordinate_profile,
            self._capture_validator,
            self._coordinate_validator,
            search_window_fraction=(0.015, 0.11, 0.19, 0.24),
            reuse_marker_geometry=True,
        )
        self._minimap_profile = load_minimap_profile(
            MINIMAP_PROFILE,
            self._minimap_validator,
        )
        self._minimap_detector = MinimapVisionDetector(
            self._minimap_profile,
            self._capture_validator,
            self._minimap_validator,
        )
        identity = load_capture_target_identity(
            authorization_file,
            AUTH_SCHEMA,
            Path(arm.executable_path),
            arm.client_build,
            required_capabilities=(
                SCREEN_CAPTURE_READ_ONLY,
                VISIBLE_COMBAT_HUD_READ_ONLY,
            ),
        )
        if identity.authorization_sha256 != arm.authorization_sha256:
            raise RuntimeError("capture identity does not match the combat arm")
        self._identity = identity
        coordinate_identity = load_capture_target_identity(
            session_authorization_file,
            AUTH_SCHEMA,
            Path(arm.executable_path),
            arm.client_build,
            required_capabilities=(
                SCREEN_CAPTURE_READ_ONLY,
                VISIBLE_COORDINATE_HUD_READ_ONLY,
            ),
        )
        if (
            coordinate_identity.actor_id != arm.actor_id
            or coordinate_identity.instance_id != arm.actor_instance_id
            or coordinate_identity.target_profile != identity.target_profile
        ):
            raise RuntimeError("coordinate and combat perception identities diverge")
        self._coordinate_identity = coordinate_identity
        self._query = WindowQuery(
            pid=arm.pid,
            hwnd=int(arm.hwnd, 16),
            title_exact=arm.window_title,
            class_exact=arm.window_class,
        )
        self._provider = DxcamWindowCaptureProvider(
            ContinuousCaptureConfig(
                query=self._query,
                session_id=session_id,
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
                backend="dxgi",
                device_index=0,
                output_index=0,
                buffer_capacity=1,
                capture_deadline_ms=250.0,
            ),
            self._capture_validator,
            window_locator=locate_window,
        )
        self._last_observation = None
        self._last_bearing = None
        self._last_pose: NavPoint | None = None
        self._last_heading_rad: float | None = None
        self._last_tether_intent: TargetTetherIntent | None = None
        self._last_tether_target_identity_crc16: int | None = None
        self._last_tether_observed_monotonic_s: float | None = None
        self._last_tether_observation_id: str | None = None

    def _verify_identity(self) -> None:
        verify_capture_process_identity(
            self._arm.pid,
            Path(self._arm.executable_path),
            self._identity,
            hwnd=int(self._arm.hwnd, 16),
            expected_title=self._arm.window_title,
            expected_class=self._arm.window_class,
            receipt_path=self._session_receipt,
            receipt_schema_path=RECEIPT_SCHEMA,
            window_resolver=lambda: locate_window(self._query),
        )

    def open(self) -> None:
        self._verify_identity()
        self._provider.open()

    def close(self) -> None:
        self._provider.close()
        if self._tether_coordinator is not None:
            self._tether_coordinator.close()

    def next_observation(self):
        self._counter += 1
        packet = None
        frame = None
        try:
            for attempt in range(FRESH_FRAME_RETRY_BUDGET):
                self._verify_identity()
                try:
                    packet = self._provider.next_frame()
                except NoFreshCaptureFrameError:
                    if attempt + 1 >= FRESH_FRAME_RETRY_BUDGET:
                        raise
                    time.sleep(FRESH_FRAME_RETRY_WAIT_S)
                    continue
                self._verify_identity()
                break
            if packet is None:
                raise NoFreshCaptureFrameError(
                    "capture retry budget ended without a fresh frame"
                )
            frame = bgra_view_from_packet(
                packet,
                maximum_frame_pixels=8_847_360,
                validator=self._capture_validator,
            )
            combat_record = self._combat_detector.detect(
                dict(packet.manifest),
                frame,
                observation_id=f"combat-f4a:{self._counter}:{uuid4()}",
            )
            observed_s = time.monotonic()
            combat_timing = combat_record["timing"]
            captured_s = float(combat_timing["monotonic_timestamp_s"])
            frame_age_ms = float(combat_timing["frame_age_ms"])
            combat_timing["observed_monotonic_s"] = observed_s
            combat_timing["age_at_observation_ms"] = max(
                frame_age_ms,
                (observed_s - captured_s) * 1000.0,
            )
            if combat_timing["age_at_observation_ms"] > combat_timing["freshness_limit_ms"]:
                raise RuntimeError("combat frame became stale during detection")
            self._combat_validator.validate(combat_record)
            validate_valid_observation_semantics(combat_record)
            observed = decode_combat_observation(
                combat_record,
                validator=self._combat_validator,
            )
            crc_bearing = decode_crc_target_bearing(
                combat_record,
                observed,
                validator=self._combat_validator,
            )
            selected_bearing = crc_bearing
            if (
                observed.target is not None
                and crc_bearing.tracking_state == "VISIBLE"
                and int(combat_record["protocol"]["version"]) < 6
            ):
                # The addon's CRC-bound exact-name/selected-alpha nameplate
                # scan is the gate. Legacy packets exposed only a coarse
                # bucket, so pixel geometry could refine it. Protocol v6
                # carries the selected semantic frame's exact CRC-bound X/Y
                # and deliberately bypasses this fallible colour refinement.
                try:
                    bearing_record = self._bearing_detector.detect(
                        dict(packet.manifest),
                        frame,
                        combat_record,
                        observation_id=(
                            f"combat-f4a:{self._counter}:{uuid4()}:selected-bearing"
                        ),
                        indicator_color_override=(
                            self._selected_target_indicator_color_override
                        ),
                    )
                    refined_bearing = decode_target_bearing_observation(
                        bearing_record,
                        validator=self._bearing_validator,
                    )
                    # CRC visibility remains the exact selected-target gate.
                    # Once that gate is open, use the continuous selection-ring
                    # geometry even when the addon's coarse LEFT/CENTER/RIGHT
                    # bucket lags at a boundary. Falling back to +/-0.35 on
                    # those frames injected a false steering impulse precisely
                    # as the target crossed the center line.
                    if bearing_refinement_is_compatible(
                        crc_bearing,
                        refined_bearing,
                    ):
                        selected_bearing = refined_bearing
                except SelectedTargetBearingError:
                    selected_bearing = crc_bearing
            if not selected_bearing.is_bound_to(observed):
                raise RuntimeError("combat and bearing observations are not cross-bound")
            self._last_pose = None
            self._last_heading_rad = None
            self._last_tether_observation_id = observed.observation_id
            current_target_identity = (
                None
                if observed.target is None
                else observed.target.identity_crc16
            )
            preserve_recent_tether = (
                self._last_tether_intent is not None
                and current_target_identity
                == self._last_tether_target_identity_crc16
                and self._last_tether_observed_monotonic_s is not None
                and 0.0
                <= observed.observed_monotonic_s
                - self._last_tether_observed_monotonic_s
                <= 1.20
            )
            if not preserve_recent_tether:
                self._last_tether_intent = None
                self._last_tether_target_identity_crc16 = None
                self._last_tether_observed_monotonic_s = None
            try:
                coordinate_manifest = dict(packet.manifest)
                coordinate_manifest["authorization_sha256"] = (
                    self._coordinate_identity.authorization_sha256
                )
                coordinate_record = self._coordinate_detector.detect(
                    coordinate_manifest,
                    frame,
                    observation_id=f"combat-pose:{self._counter}:{uuid4()}",
                )
                position = coordinate_record.get("position")
                if (
                    coordinate_record.get("tracking_state") == "VALID"
                    and coordinate_record.get("map_position_available") is True
                    and isinstance(position, dict)
                    and position.get("continent_index") == 2
                    and position.get("zone_index") in {25, 26}
                ):
                    transform = tbc243_zone_transform(
                        2, int(position["zone_index"])
                    )
                    world_x, world_y = transform.world_from_normalized(
                        float(position["x"]), float(position["y"])
                    )
                    self._last_pose = NavPoint(
                        world_x, world_y, self._start_world_z_hint
                    )
                    if position.get("facing_rad") is not None:
                        self._last_heading_rad = float(position["facing_rad"])
                    else:
                        minimap = self._minimap_detector.detect(
                            coordinate_manifest,
                            frame,
                            observation_id=(
                                f"combat-heading:{self._counter}:{uuid4()}"
                            ),
                        )
                        marker = minimap.get("player_marker")
                        if (
                            minimap.get("tracking_state") == "FOUND"
                            and isinstance(marker, dict)
                            and marker.get("orientation_deg_screen") is not None
                            and marker.get("detection_model") == "neutral_mdx"
                        ):
                            self._last_heading_rad = world_heading_from_marker(
                                MarkerCandidate(
                                    center_x_px=float(marker["center_x_px"]),
                                    center_y_px=float(marker["center_y_px"]),
                                    orientation_deg_screen=float(
                                        marker["orientation_deg_screen"]
                                    ),
                                    pixel_count=int(marker["pixel_count"]),
                                    confidence=float(marker["confidence"]),
                                    detection_model=str(marker["detection_model"]),
                                ),
                                self._minimap_profile,
                            )
            except Exception:
                # Combat observation remains useful, but approach movement is
                # fail-closed by the required tether controller below.
                self._last_pose = None
                self._last_heading_rad = None
            if (
                self._tether_coordinator is not None
                and observed.target is not None
                and selected_bearing.tracking_state == "VISIBLE"
                and selected_bearing.offset_x_normalized is not None
                and self._last_pose is not None
                and self._last_heading_rad is not None
            ):
                known_ranges = tuple(
                    action.in_range
                    for action in (observed.attack, observed.sinister_strike)
                    if action.in_range is not None
                )
                in_melee = (
                    True if any(known_ranges)
                    else False if known_ranges
                    else None
                )
                self._last_tether_intent = self._tether_coordinator.update(
                    target_identity_crc16=observed.target.identity_crc16,
                    player=self._last_pose,
                    player_heading_rad=self._last_heading_rad,
                    target_bearing_error_x_normalized=(
                        selected_bearing.offset_x_normalized
                    ),
                    client_in_melee=in_melee,
                    observed_monotonic_s=observed.observed_monotonic_s,
                )
                self._last_tether_target_identity_crc16 = (
                    observed.target.identity_crc16
                )
                self._last_tether_observed_monotonic_s = (
                    observed.observed_monotonic_s
                )
            self._last_observation = observed
            self._last_bearing = selected_bearing
            if self._movement_lab_state_file is not None:
                movement_record = MovementLabSnapshot(
                        observed_monotonic_s=selected_bearing.observed_monotonic_s,
                        tracking_state=selected_bearing.tracking_state,
                        target_identity_crc16=selected_bearing.target_identity_crc16,
                        target_error_x_normalized=selected_bearing.offset_x_normalized,
                        target_screen_y_normalized=(
                            selected_bearing.center_y_normalized
                        ),
                        player_world_x=(
                            None if self._last_pose is None else self._last_pose.x
                        ),
                        player_world_y=(
                            None if self._last_pose is None else self._last_pose.y
                        ),
                        player_world_z=(
                            None if self._last_pose is None else self._last_pose.z
                        ),
                        waypoint_error_rad=(
                            None
                            if self._last_tether_intent is None
                            else self._last_tether_intent.guidance_error_rad
                        ),
                        controller_state=(
                            "ALIGNED"
                            if selected_bearing.tracking_state == "VISIBLE"
                            and selected_bearing.direction == "CENTER"
                            else "TRACK"
                            if selected_bearing.tracking_state == "VISIBLE"
                            else selected_bearing.tracking_state
                        ),
                        navmesh_polygons_world=(
                            ()
                            if self._last_tether_intent is None
                            else self._last_tether_intent.navmesh_polygons_world
                        ),
                        tether_state=(
                            "UNAVAILABLE"
                            if self._last_tether_intent is None
                            else self._last_tether_intent.state
                        ),
                        tether_guidance_error_rad=(
                            None
                            if self._last_tether_intent is None
                            else self._last_tether_intent.guidance_error_rad
                        ),
                        tether_projected_target_world=(
                            None
                            if self._last_tether_intent is None
                            else (
                                self._last_tether_intent.projected_target.x,
                                self._last_tether_intent.projected_target.y,
                            )
                        ),
                        tether_centerline_world=(
                            ()
                            if self._last_tether_intent is None
                            else self._last_tether_intent.corridor_centerline_world
                        ),
                        visible_attackable_candidate_count=(
                            max(
                                observed.visible_attackable_candidate_count,
                                int(
                                    observed.target is not None
                                    and observed.target.attackable_npc
                                    and selected_bearing.tracking_state == "VISIBLE"
                                ),
                            )
                        ),
                    ).to_record()
                if observed.target is not None:
                    movement_record["selected_target_range_awareness"] = (
                        selected_target_melee_range_awareness(
                            target_identity_crc16=observed.target.identity_crc16,
                            observed_monotonic_s=observed.observed_monotonic_s,
                            expires_monotonic_s=observed.expires_monotonic_s,
                            ability_witnesses={
                                "rogue.auto_attack": observed.attack.in_range,
                                "rogue.sinister_strike": (
                                    observed.sinister_strike.in_range
                                ),
                                "rogue.eviscerate": observed.eviscerate.in_range,
                            },
                        )
                    )
                _atomic_write(
                    self._movement_lab_state_file,
                    _exact_json_bytes(movement_record),
                )
            return observed
        finally:
            if frame is not None:
                del frame
            if packet is not None and packet.pixels is not None:
                packet.pixels.release()

    def bearing_for(self, observation):
        if self._last_observation != observation or self._last_bearing is None:
            raise RuntimeError("bearing request does not match the latest combat frame")
        return self._last_bearing

    @property
    def latest_world_pose(self) -> NavPoint | None:
        return self._last_pose

    @property
    def latest_world_heading_rad(self) -> float | None:
        return self._last_heading_rad

    def tether_for(self, observation, bearing):
        if (
            self._last_observation != observation
            or self._last_tether_observation_id != observation.observation_id
            or bearing != self._last_bearing
        ):
            raise RuntimeError("tether request does not match latest combat frame")
        return self._last_tether_intent


def _invoke_revalidation(
    *,
    session_authorization: Path,
    combat_authorization: Path,
) -> Path:
    completed = subprocess.run(
        [
            "pwsh", "-NoProfile", "-NonInteractive", "-File", str(OPERATOR),
            "-Action", "IssueCombatRealmRevalidation",
            "-RepositoryRoot", str(ROOT),
            "-AuthorizationFile", str(session_authorization),
            "-CombatAuthorizationFile", str(combat_authorization),
            "-AcknowledgeControlledCombat",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15.0,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "combat realm revalidation failed closed: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    prefix = "LAB_COMBAT_REALM_REVALIDATION="
    for line in completed.stdout.splitlines():
        if line.startswith(prefix):
            return Path(line[len(prefix):])
    raise RuntimeError("combat realm revalidation path was not returned")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one bounded, NPC-only, controlled LAB Rogue encounter."
    )
    parser.add_argument("--session-authorization-file", type=Path, required=True)
    parser.add_argument(
        "--session-receipt",
        type=Path,
        default=OPERATOR_RUNTIME / "lab-client-launch-receipt.json",
    )
    parser.add_argument("--acknowledge-controlled-combat", action="store_true")
    parser.add_argument(
        "--facing-probe-only",
        action="store_true",
        help="Acquire one hostile NPC and execute at most one visually justified mouse turn; never attack.",
    )
    parser.add_argument(
        "--facing-transfer-probe-only",
        choices=("NEGATIVE", "POSITIVE"),
        help=(
            "Measure one signed, bounded RMB mouse-X impulse between neutral "
            "selected-target observations; never translate, strafe, or attack."
        ),
    )
    parser.add_argument(
        "--observe-facing-only",
        action="store_true",
        help="Read one combat and selected-target-bearing frame without sending any game input.",
    )
    parser.add_argument(
        "--target-name",
        help=(
            "Optional exact NPC name to probe once through the allowlisted "
            "/targetexact transport before combat acquisition."
        ),
    )
    parser.add_argument(
        "--initial-search-direction",
        choices=("LEFT", "RIGHT"),
        default="RIGHT",
        help="Initial offscreen sweep chosen by the hunting engine's last-seen spatial memory.",
    )
    parser.add_argument(
        "--camera-pitch-probe-only",
        choices=("UP", "DOWN"),
        help="Execute one bounded, selected-target-bound camera pitch calibration drag.",
    )
    parser.add_argument(
        "--recover-selected-corpse-only",
        action="store_true",
        help=(
            "Require the currently selected exact hostile NPC to be dead, then "
            "perform only CRC-bound loot recovery."
        ),
    )
    parser.add_argument(
        "--allow-friendly-dummy-facing",
        action="store_true",
        help="Allow the exact Undercity Practice Dummy only for a no-attack facing probe.",
    )
    parser.add_argument(
        "--movement-lab-state-file",
        type=Path,
        default=MOVEMENT_LAB_STATE,
        help="Publish read-only facing telemetry for the optional external Movement Lab overlay.",
    )
    parser.add_argument("--nav-root", type=Path, default=DEFAULT_NAV_ROOT)
    parser.add_argument("--navmesh-worker", type=Path, default=DEFAULT_NAV_WORKER)
    parser.add_argument("--start-world-z-hint", type=float, default=100.0)
    parser.add_argument(
        "--navigation-handoff-result",
        type=Path,
        help=(
            "Exact preceding navigation result whose fresh, physically "
            "traversed breadcrumbs may authorize a bounded risky-aggro retreat."
        ),
    )
    parser.add_argument(
        "--operator-control-file",
        type=Path,
        help="Exact local Start/Pause/Stop command file owned by the visible Predator UI.",
    )
    return parser


def _risky_aggro(observation) -> bool:
    target = observation.target
    return bool(
        observation.in_combat
        and target is not None
        and not target.dead
        and not target.is_player
        and target.attackable_npc
        and (target.level is None or target.level > observation.player_level + 1)
    )


def _retreat_corridor_from_handoff(path: Path, *, perception):
    record = json.loads(path.read_text(encoding="utf-8"))
    pose = perception.latest_world_pose
    if (
        record.get("record_type") != "navmesh_roaming_result"
        or record.get("status") != "COMBAT_HANDOFF_REQUIRED"
        or pose is None
    ):
        raise RuntimeError("navigation handoff cannot authorize safe retreat")
    final_world = record.get("final_world")
    if (
        not isinstance(final_world, list)
        or len(final_world) != 2
    ):
        raise RuntimeError("navigation handoff final pose is invalid")
    # The strict geometric attachment check belongs to the breadcrumb
    # consumer.  It accepts the original handoff endpoint or a fresh live pose
    # part-way along the same bounded trail after a fail-closed interruption.
    return corridor_from_retreat_context(
        record.get("safe_retreat_context"),
        current=pose,
        expected_map_name=str(record.get("map")),
    )


def _run_risky_aggro_retreat(
    *, motion_gateway, perception, initial_observation, corridor, encounter_id: str,
) -> dict[str, object]:
    def pose() -> tuple[float, float, float | None]:
        latest = perception.latest_world_pose
        if latest is None:
            raise RuntimeError("safe retreat lost fresh client-visible world pose")
        return latest.x, latest.y, perception.latest_world_heading_rad

    controller = BreadcrumbCombatRetreatController(
        corridor=corridor,
        pose_source=pose,
    )
    motion_gateway.replace_controller(controller)
    # Parsing and validating the navigation handoff can outlive the strict
    # continuous-input frame age. Refresh from the same client-visible stream
    # immediately before the first retreat pulse; never replay the handoff
    # snapshot as a motion frame.
    observation = perception.next_observation()
    started_s = observation.observed_monotonic_s
    deadline_s = safe_retreat_deadline_seconds(corridor)
    records: list[dict[str, object]] = []
    target_identity = (
        None
        if initial_observation.target is None
        else initial_observation.target.identity_crc16
    )
    for _ in range(1_024):
        bearing = perception.bearing_for(observation)
        records.append(motion_gateway.update(observation, bearing))
        if controller.terminal_state == "ESCAPED":
            motion_gateway.release()
            return {
                "record_type": "controlled_combat_result",
                "schema_version": "0.1",
                "encounter_id": encounter_id,
                "status": "ESCAPED_RISKY_AGGRO",
                "target_identity_crc16": target_identity,
                "actions_executed": 0,
                "decisions": [],
                "executions": [],
                "motion_records": records,
                "retreat_source": corridor.source,
                "retreat_stop_world": [corridor.stop.x, corridor.stop.y],
                "manual_takeover_available": True,
                "execution_authority": False,
            }
        if controller.terminal_state == "CORRIDOR_EXHAUSTED_IN_COMBAT":
            raise RuntimeError("verified retreat corridor ended before combat cleared")
        if observation.observed_monotonic_s - started_s > deadline_s:
            raise RuntimeError("safe retreat deadline expired")
        time.sleep(0.05)
        observation = perception.next_observation()
    raise RuntimeError("safe retreat frame budget exhausted")


def _run_facing_probe(
    *, gateway, perception, policy, probe_id: str,
    allow_friendly_calibration_target: bool = False,
) -> dict[str, object]:
    decisions: list[dict[str, object]] = []
    executions: list[dict[str, object]] = []
    def decision_record(decision) -> dict[str, object]:
        return decision.to_record(
            created_at=datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            )
        )

    observed = perception.next_observation()
    selected_bearing = perception.bearing_for(observed)
    if observed.target is None:
        if (
            selected_bearing is None
            or selected_bearing.tracking_state != "VISIBLE"
        ):
            scan = policy.decide_acquisition_scan(
                observed,
                decision_id=f"decision:{probe_id}:scan",
            )
            decisions.append(decision_record(scan))
            executions.append(gateway.execute(scan, observed))
            return {
                "record_type": "bounded_mouse_facing_probe",
                "schema_version": "0.1",
                "probe_id": probe_id,
                "status": "ONE_ACQUISITION_SCAN_EXECUTED",
                "before": {
                    "observation_id": observed.observation_id,
                    "target_identity_crc16": None,
                    "tracking_state": selected_bearing.tracking_state,
                    "direction": selected_bearing.direction,
                    "offset_x_normalized": selected_bearing.offset_x_normalized,
                },
                "after": None,
                "decisions": decisions,
                "executions": executions,
                "manual_takeover_available": True,
                "execution_authority": False,
            }
        if selected_bearing.direction in {"LEFT", "RIGHT", "CENTER"}:
            acquire = CombatDecision(
                decision_id=f"decision:{probe_id}:visible-acquire",
                observation=observed,
                action_id="combat.acquire_visible_hostile",
                priority_tier="TARGET_CONTROL",
                reason_code="visible_attackable_candidate_screen_bound",
                explanation=(
                    "Select the evaluated red/yellow nameplate at its fresh screen point."
                ),
                requested_control="TARGET_VISIBLE_HOSTILE",
                preconditions=(
                    "target=null",
                    "visible_candidate=true",
                    "acquisition_screen_point=fresh",
                ),
                confidence=observed.confidence,
                bearing=selected_bearing,
            )
        else:
            raise RuntimeError("facing probe could not produce exact target acquisition")
        if acquire.requested_control != "TARGET_VISIBLE_HOSTILE":
            raise RuntimeError("facing probe did not preserve visible target acquisition")
        decisions.append(decision_record(acquire))
        executions.append(gateway.execute(acquire, observed))
        for _ in range(TARGET_CHANGE_OBSERVATION_BUDGET):
            time.sleep(0.1)
            observed = perception.next_observation()
            selected_bearing = perception.bearing_for(observed)
            if (
                observed.target is not None
                and selected_bearing.tracking_state == "VISIBLE"
                and selected_bearing.direction in {"LEFT", "RIGHT", "CENTER"}
            ):
                break
    if observed.target is None:
        scan = policy.decide_acquisition_scan(
            observed,
            decision_id=f"decision:{probe_id}:scan",
        )
        decisions.append(decision_record(scan))
        executions.append(gateway.execute(scan, observed))
        return {
            "record_type": "bounded_mouse_facing_probe",
            "schema_version": "0.1",
            "probe_id": probe_id,
            "status": "ONE_ACQUISITION_SCAN_EXECUTED",
            "before": {
                "observation_id": observed.observation_id,
                "target_identity_crc16": None,
                "tracking_state": selected_bearing.tracking_state,
                "direction": selected_bearing.direction,
                "offset_x_normalized": selected_bearing.offset_x_normalized,
            },
            "after": None,
            "decisions": decisions,
            "executions": executions,
            "manual_takeover_available": True,
            "execution_authority": False,
        }
    if (
        observed.target.is_player
        or observed.target.dead
        or (not observed.target.hostile and not allow_friendly_calibration_target)
    ):
        raise RuntimeError("facing probe refuses non-hostile, dead, or player targets")
    before = {
        "observation_id": observed.observation_id,
        "target_identity_crc16": observed.target.identity_crc16,
        "tracking_state": selected_bearing.tracking_state,
        "direction": selected_bearing.direction,
        "offset_x_normalized": selected_bearing.offset_x_normalized,
    }
    if selected_bearing.tracking_state in {"LOST", "AMBIGUOUS"}:
        search = policy.decide(
            observed,
            decision_id=f"decision:{probe_id}:selected-target-search",
            bearing=selected_bearing,
        )
        if search.requested_control not in {"TURN_LEFT", "TURN_RIGHT"}:
            raise RuntimeError(
                "facing probe did not preserve the selected-target search: "
                f"action={search.action_id}, reason={search.reason_code}, "
                f"bearing={selected_bearing.tracking_state}/{selected_bearing.direction}"
            )
        decisions.append(decision_record(search))
        executions.append(gateway.execute(search, observed))
        time.sleep(0.2)
        after_observation = perception.next_observation()
        after_bearing = perception.bearing_for(after_observation)
        after_target_crc = (
            None
            if after_observation.target is None
            else after_observation.target.identity_crc16
        )
        return {
            "record_type": "bounded_mouse_facing_probe",
            "schema_version": "0.1",
            "probe_id": probe_id,
            "status": "ONE_SELECTED_TARGET_SEARCH_EXECUTED",
            "before": before,
            "after": {
                "observation_id": after_observation.observation_id,
                "target_identity_crc16": after_target_crc,
                "tracking_state": after_bearing.tracking_state,
                "direction": after_bearing.direction,
                "offset_x_normalized": after_bearing.offset_x_normalized,
            },
            "decisions": decisions,
            "executions": executions,
            "manual_takeover_available": True,
            "execution_authority": False,
        }
    if (
        selected_bearing.tracking_state != "VISIBLE"
        or selected_bearing.direction not in {"LEFT", "RIGHT"}
    ):
        return {
            "record_type": "bounded_mouse_facing_probe",
            "schema_version": "0.1",
            "probe_id": probe_id,
            "status": "NO_TURN_REQUIRED_OR_VISUALLY_JUSTIFIED",
            "before": before,
            "after": None,
            "decisions": decisions,
            "executions": executions,
            "manual_takeover_available": True,
            "execution_authority": False,
        }
    if allow_friendly_calibration_target:
        turn = policy.decide_facing_only(
            observed,
            decision_id=f"decision:{probe_id}:turn",
            bearing=selected_bearing,
        )
    else:
        turn = policy.decide(
            observed,
            decision_id=f"decision:{probe_id}:turn",
            bearing=selected_bearing,
        )
    if turn.requested_control not in {"TURN_LEFT", "TURN_RIGHT"}:
        raise RuntimeError(
            "facing probe policy did not preserve facing priority: "
            f"action={turn.action_id}, reason={turn.reason_code}, "
            f"bearing={selected_bearing.tracking_state}/{selected_bearing.direction}"
        )
    decisions.append(decision_record(turn))
    executions.append(gateway.execute(turn, observed))
    time.sleep(0.2)
    after_observation = perception.next_observation()
    after_bearing = perception.bearing_for(after_observation)
    after_target_crc = (
        None
        if after_observation.target is None
        else after_observation.target.identity_crc16
    )
    return {
        "record_type": "bounded_mouse_facing_probe",
        "schema_version": "0.1",
        "probe_id": probe_id,
        "status": "ONE_MOUSE_TURN_EXECUTED",
        "before": before,
        "after": {
            "observation_id": after_observation.observation_id,
            "target_identity_crc16": after_target_crc,
            "tracking_state": after_bearing.tracking_state,
            "direction": after_bearing.direction,
            "offset_x_normalized": after_bearing.offset_x_normalized,
        },
        "decisions": decisions,
        "executions": executions,
        "manual_takeover_available": True,
        "execution_authority": False,
    }


def _run_camera_pitch_probe(*, motion_gateway, perception, probe_id: str, direction: str):
    records = []
    for _ in range(10):
        observed = perception.next_observation()
        bearing = perception.bearing_for(observed)
        records.append(motion_gateway.update(observed, bearing))
    motion_gateway.release()
    return {
        "record_type": "bounded_camera_pitch_probe",
        "schema_version": "0.1",
        "probe_id": probe_id,
        "status": "ONE_CAMERA_PITCH_PROBE_EXECUTED",
        "direction": direction,
        "target_identity_crc16": records[-1]["target_identity_crc16"],
        "motion_records": records,
        "decisions": [],
        "executions": [],
        "actions_executed": 0,
        "manual_takeover_available": True,
        "execution_authority": False,
    }


def _observe_facing_only(*, perception, probe_id: str) -> dict[str, object]:
    observed = perception.next_observation()
    bearing = perception.bearing_for(observed)
    target = observed.target
    return {
        "record_type": "read_only_facing_observation",
        "schema_version": "0.1",
        "probe_id": probe_id,
        "status": "READ_ONLY_OBSERVATION_COMPLETE",
        "observation_id": observed.observation_id,
        "target": None
        if target is None
        else {
            "identity_crc16": target.identity_crc16,
            "hostile": target.hostile,
            "reaction": target.reaction,
            "is_player": target.is_player,
            "dead": target.dead,
            "level": target.level,
            "attackable_npc": target.attackable_npc,
        },
        "bearing": {
            "tracking_state": bearing.tracking_state,
            "direction": bearing.direction,
            "offset_x_normalized": bearing.offset_x_normalized,
            "confidence": bearing.confidence,
        },
        "actions_executed": 0,
        "manual_takeover_available": True,
        "execution_authority": False,
    }


def _run_continuous_facing_probe(
    *,
    motion_gateway,
    perception,
    probe_id: str,
    allow_friendly_calibration_target: bool,
) -> dict[str, object]:
    """Acquire a stable magnetic lock without any discrete turn action."""

    records: list[dict[str, object]] = []
    target_identity = None
    aligned_frames = 0
    started_s = time.monotonic()
    next_tick_s = started_s
    observation_times_s: list[float] = []
    terminal_hold_state: str | None = None
    for _ in range(CONTINUOUS_FACING_MAX_FRAMES):
        delay_s = next_tick_s - time.monotonic()
        if delay_s > 0.0:
            time.sleep(delay_s)
        # Advance against an absolute cadence.  If perception is slower than
        # 20 Hz we do not add another fixed sleep and make the lag worse.
        next_tick_s += CONTINUOUS_CONTROL_PERIOD_S
        observed = perception.next_observation()
        observation_times_s.append(observed.observed_monotonic_s)
        target = observed.target
        bearing = perception.bearing_for(observed)
        if (
            not observed.player_alive
            or target is None
            or target.dead
            or target.is_player
            or (
                not target.attackable_npc
                and not allow_friendly_calibration_target
            )
            or not bearing.is_bound_to(observed)
        ):
            motion_gateway.release()
            raise RuntimeError(
                "continuous facing probe lost its exact safe NPC target"
            )
        if target_identity is None:
            target_identity = target.identity_crc16
        elif target.identity_crc16 != target_identity:
            motion_gateway.release()
            raise RuntimeError(
                "continuous facing probe target continuity changed"
            )
        record = motion_gateway.update(observed, bearing)
        records.append(record)
        if record["state"] in {"HOLD_WORLD_REPOSITION", "HOLD_LOST_TARGET"}:
            # A facing calibration cannot solve an occluded target or an
            # exhausted visual sweep.  Release immediately instead of holding
            # RMB for the remainder of the 100-frame evidence budget.
            terminal_hold_state = str(record["state"])
            break
        if record["aligned"] and record["state"] == "LOCK":
            aligned_frames += 1
            if aligned_frames >= CONTINUOUS_FACING_LOCK_FRAMES:
                motion_gateway.release()
                elapsed_s = max(0.0, time.monotonic() - started_s)
                intervals_ms = [
                    (current - previous) * 1000.0
                    for previous, current in zip(
                        observation_times_s, observation_times_s[1:]
                    )
                ]
                return {
                    "record_type": "continuous_facing_probe",
                    "schema_version": "0.1",
                    "probe_id": probe_id,
                    "status": "CONTINUOUS_FACING_LOCK_VERIFIED",
                    "target_identity_crc16": target_identity,
                    "frames_observed": len(records),
                    "consecutive_aligned_frames": aligned_frames,
                    "motion_records": records,
                    "elapsed_s": elapsed_s,
                    "effective_observation_hz": (
                        len(records) / elapsed_s if elapsed_s > 0.0 else None
                    ),
                    "maximum_observation_gap_ms": (
                        max(intervals_ms) if intervals_ms else None
                    ),
                    "discrete_turn_actions": 0,
                    "manual_takeover_available": True,
                    "execution_authority": False,
                }
        else:
            aligned_frames = 0
    motion_gateway.release()
    elapsed_s = max(0.0, time.monotonic() - started_s)
    intervals_ms = [
        (current - previous) * 1000.0
        for previous, current in zip(observation_times_s, observation_times_s[1:])
    ]
    detail = (
        "continuous facing probe handed an occluded target to world navigation"
        if terminal_hold_state == "HOLD_WORLD_REPOSITION"
        else "continuous facing probe exhausted its bounded visual sweep"
        if terminal_hold_state == "HOLD_LOST_TARGET"
        else "continuous facing probe did not acquire six stable aligned frames"
    )
    return {
        "record_type": "continuous_facing_probe",
        "schema_version": "0.1",
        "probe_id": probe_id,
        "status": "CONTINUOUS_FACING_LOCK_NOT_ACQUIRED",
        "target_identity_crc16": target_identity,
        "frames_observed": len(records),
        "consecutive_aligned_frames": aligned_frames,
        "motion_records": records,
        "elapsed_s": elapsed_s,
        "effective_observation_hz": (
            len(records) / elapsed_s if elapsed_s > 0.0 else None
        ),
        "maximum_observation_gap_ms": max(intervals_ms) if intervals_ms else None,
        "discrete_turn_actions": 0,
        "detail": detail,
        "manual_takeover_available": True,
        "execution_authority": False,
    }


def _run_facing_transfer_probe(
    *,
    motion_gateway,
    perception,
    probe_id: str,
    signed_delta_x: int,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    post_impulse_visible = 0
    impulse_seen = False
    for _ in range(45):
        observed = perception.next_observation()
        bearing = perception.bearing_for(observed)
        record = motion_gateway.update(observed, bearing)
        records.append(record)
        if record["state"] == "CALIBRATION_IMPULSE":
            impulse_seen = True
        elif impulse_seen and record["state"] == "CALIBRATION_OBSERVE":
            post_impulse_visible += 1
            if post_impulse_visible >= 12:
                break
    motion_gateway.release()

    impulse_indexes = [
        index
        for index, record in enumerate(records)
        if record["state"] == "CALIBRATION_IMPULSE"
    ]
    if len(impulse_indexes) != 8 or impulse_indexes != list(
        range(impulse_indexes[0], impulse_indexes[0] + 8)
    ):
        raise RuntimeError("facing transfer probe did not emit one bounded impulse burst")
    impulse_index = impulse_indexes[0]
    impulse_end_index = impulse_indexes[-1]
    before_values = [
        float(record["bearing_offset_x_normalized"])
        for record in records[:impulse_index]
        if record["bearing_offset_x_normalized"] is not None
    ][-5:]
    after_values = [
        float(record["bearing_offset_x_normalized"])
        for record in records[impulse_end_index + 1:]
        if record["bearing_offset_x_normalized"] is not None
    ][-5:]
    if len(before_values) != 5 or len(after_values) != 5:
        raise RuntimeError("facing transfer probe lacks stable visible samples")
    before = sum(before_values) / len(before_values)
    after = sum(after_values) / len(after_values)
    observed_change = after - before
    return {
        "record_type": "facing_transfer_probe",
        "schema_version": "0.1",
        "probe_id": probe_id,
        "status": "FACING_TRANSFER_MEASURED",
        "signed_delta_x": signed_delta_x,
        "mean_offset_before": before,
        "mean_offset_after": after,
        "observed_offset_change": observed_change,
        "observed_transfer_sign": (
            "POSITIVE" if observed_change > 0 else "NEGATIVE" if observed_change < 0 else "ZERO"
        ),
        "motion_records": records,
        "discrete_turn_actions": 0,
        "actions_executed": 0,
        "manual_takeover_available": True,
        "execution_authority": False,
    }


def run(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.acknowledge_controlled_combat is not True:
        raise SystemExit("--acknowledge-controlled-combat is required")
    if args.observe_facing_only and (
        args.facing_probe_only or args.facing_transfer_probe_only or args.camera_pitch_probe_only or args.target_name or args.allow_friendly_dummy_facing
    ):
        raise SystemExit("read-only facing observation cannot target or execute a facing probe")
    if args.allow_friendly_dummy_facing and (
        not (args.facing_probe_only or args.facing_transfer_probe_only)
        or args.target_name != "Undercity Practice Dummy"
    ):
        raise SystemExit(
            "friendly dummy facing is restricted to the exact no-attack calibration probe"
        )
    if not args.session_authorization_file.is_file() or not args.session_receipt.is_file():
        raise SystemExit("active session authorization and receipt are required")

    run_uuid = uuid4()
    encounter_id = f"encounter:f4a:{run_uuid}"
    combat_auth_path = RUNTIME_ROOT / f"combat-authorization-{run_uuid}.json"
    arm_path = RUNTIME_ROOT / f"combat-arm-{run_uuid}.json"
    result_path = RUNTIME_ROOT / "results" / f"controlled-combat-{run_uuid}.json"
    sink = None
    perception = None
    unregister_takeover = None
    gateway = None
    motion_gateway = None
    target_command_gateway = None
    tether_coordinator = None
    try:
        combat_raw = issue_combat_execution_authorization_snapshot(
            COMBAT_TEMPLATE.read_bytes(),
            schema_path=AUTH_SCHEMA,
            now_utc=datetime.now(timezone.utc),
            evidence_ref=f"gate:{encounter_id}",
            acknowledge_controlled_combat=True,
        )
        _atomic_write(combat_auth_path, combat_raw)
        revalidation_path = _invoke_revalidation(
            session_authorization=args.session_authorization_file,
            combat_authorization=combat_auth_path,
        )
        session_auth_raw = args.session_authorization_file.read_bytes()
        receipt_raw = args.session_receipt.read_bytes()
        revalidation_raw = revalidation_path.read_bytes()
        now_utc = datetime.now(timezone.utc)
        now_monotonic_ms = monotonic_ns() / 1_000_000.0
        arm_raw = issue_combat_runtime_arm_snapshot(
            authorization_raw=combat_raw,
            authorization_schema_path=AUTH_SCHEMA,
            session_authorization_raw=session_auth_raw,
            session_receipt_raw=receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            realm_revalidation_raw=revalidation_raw,
            realm_revalidation_schema_path=REALM_SCHEMA,
            arm_schema_path=ARM_SCHEMA,
            now_utc=now_utc,
            now_monotonic_ms=now_monotonic_ms,
            clock_id="clock:windows:monotonic",
            acknowledge_controlled_combat=True,
        )
        _atomic_write(arm_path, arm_raw)
        arm = load_combat_runtime_arm(
            arm_raw,
            arm_schema_path=ARM_SCHEMA,
            authorization_raw=combat_raw,
            authorization_schema_path=AUTH_SCHEMA,
            session_authorization_raw=session_auth_raw,
            session_receipt_raw=receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            realm_revalidation_raw=revalidation_raw,
            realm_revalidation_schema_path=REALM_SCHEMA,
            now_utc=datetime.now(timezone.utc),
            now_monotonic_ms=monotonic_ns() / 1_000_000.0,
        )
        clock = SystemMonotonicClock(arm.clock_id)
        authority = AuthorityBinding(
            actor_id=arm.actor_id,
            actor_instance_id=arm.actor_instance_id,
            actor_role="lab_clone",
            decision_context="lab_clone",
            target_profile="tbc_243_lab",
            target_instance_id=arm.actor_instance_id,
            authorization_id=COMBAT_EXECUTION_AUTHORIZATION_ID,
            authorization_sha256=arm.authorization_sha256,
        )
        target = WindowsInputTargetBinding(
            authority_binding=authority,
            pid=arm.pid,
            hwnd=int(arm.hwnd, 16),
            process_creation_time_100ns=int(arm.process_creation_filetime_utc),
            executable_path=arm.executable_path,
            executable_sha256=arm.executable_sha256,
            window_class_exact=arm.window_class,
            window_title_exact=arm.window_title,
        )
        keyboard_backend = CtypesWin32KeyboardBackend()
        if keyboard_backend.focus_bound_target(target) != 1:
            raise RuntimeError("bound WoW target could not be focused")
        time.sleep(0.1)
        keyboard_sink = WindowsSendInputSink(
            target=target,
            backend=keyboard_backend,
            clock=clock,
        )
        mouse_turn_sink = None
        try:
            mouse_turn_sink = WindowsMouseTurnSink(
                target=target,
                backend=CtypesWin32KeyboardBackend(),
                clock=clock,
            )
            sink = WindowsCombatInputSink(
                keyboard_sink=keyboard_sink,
                mouse_turn_sink=mouse_turn_sink,
            )
        except Exception:
            if mouse_turn_sink is not None:
                mouse_turn_sink.close()
            keyboard_sink.close()
            raise
        gateway = CombatActionGateway(arm=arm, sink=sink, clock=clock)
        tether_coordinator = AsyncTargetTetherCoordinator(
            ClientAssetNavmeshQuery(
                worker=args.navmesh_worker,
                nav_root=args.nav_root,
            )
        )
        perception = LiveCombatPerceptionSource(
            arm=arm,
            authorization_file=combat_auth_path,
            session_authorization_file=args.session_authorization_file,
            session_receipt=args.session_receipt,
            session_id=f"session:f4a:{run_uuid}",
            tether_coordinator=tether_coordinator,
            start_world_z_hint=args.start_world_z_hint,
            movement_lab_state_file=args.movement_lab_state_file,
            selected_target_indicator_color_override=(
                "red" if args.allow_friendly_dummy_facing else None
            ),
        )
        motion_controller = (
            CameraPitchProbeController(
                signed_delta_y=(-16 if args.camera_pitch_probe_only == "UP" else 16)
            )
            if args.camera_pitch_probe_only
            else
            FacingTransferProbeController(
                signed_delta_x=(
                    -16 if args.facing_transfer_probe_only == "NEGATIVE" else 16
                )
            )
            if args.facing_transfer_probe_only
            else HumanlikeCombatMotionController(
                translation_enabled=not args.facing_probe_only,
                require_tether_for_approach=True,
                allow_non_attackable_npc=args.allow_friendly_dummy_facing,
                initial_search_direction=args.initial_search_direction,
            )
        )
        motion_gateway = CombatMotionGateway(
            controller=motion_controller,
            tether_source=perception.tether_for,
            session=WindowsContinuousMotionSession(
                target=target,
                backend=CtypesWin32KeyboardBackend(),
                clock=clock,
                expires_at_monotonic_ms=arm.expires_at_monotonic_ms,
            ),
        )
        perception.open()
        takeover = PauseHotkeySource()
        def cancel_for_manual_takeover() -> bool:
            # Release the held-state owner first.  Each cancellation is
            # independent so one failure cannot prevent the other release.
            try:
                motion_gateway.cancel_for_manual_takeover()
            finally:
                gateway.cancel_for_manual_takeover()
            return True

        unregister_takeover = takeover.arm(cancel_for_manual_takeover)
        target_probe = None
        if args.target_name:
            # A valid combat-HUD observation is also the in-world precondition.
            # Never type the allowlisted command merely because the executable
            # window is valid: the same HWND also owns login/character screens.
            preflight = perception.next_observation()
            if not preflight.player_alive:
                raise RuntimeError("exact target probe requires a living in-world actor")
            target_command_gateway = WindowsExactTargetCommandGateway(
                arm=arm,
                target=target,
                backend=CtypesWin32KeyboardBackend(),
                clock=clock,
            )
            target_probe = target_command_gateway.execute(args.target_name)
            time.sleep(0.2)
        if args.recover_selected_corpse_only:
            selected = perception.next_observation()
            if (
                selected.target is None
                or not selected.target.dead
                or selected.target.is_player
                or not selected.target.hostile
                or selected.in_combat
            ):
                raise RuntimeError(
                    "selected-corpse recovery requires one exact dead hostile NPC out of combat"
                )
        policy = RogueLevelOneCombatPolicy(
            initial_search_direction=args.initial_search_direction
        )
        if args.observe_facing_only:
            result = _observe_facing_only(
                perception=perception,
                probe_id=f"observe-facing:{run_uuid}",
            )
        elif args.facing_transfer_probe_only:
            result = _run_facing_transfer_probe(
                motion_gateway=motion_gateway,
                perception=perception,
                probe_id=f"facing-transfer:{run_uuid}",
                signed_delta_x=(
                    -16 if args.facing_transfer_probe_only == "NEGATIVE" else 16
                ),
            )
        elif args.facing_probe_only:
            result = _run_continuous_facing_probe(
                motion_gateway=motion_gateway,
                perception=perception,
                probe_id=f"facing:{run_uuid}",
                allow_friendly_calibration_target=args.allow_friendly_dummy_facing,
            )
        elif args.camera_pitch_probe_only:
            result = _run_camera_pitch_probe(
                motion_gateway=motion_gateway,
                perception=perception,
                probe_id=f"camera-pitch:{run_uuid}",
                direction=args.camera_pitch_probe_only,
            )
        else:
            handoff_observation = (
                None
                if args.navigation_handoff_result is None
                else perception.next_observation()
            )
            if handoff_observation is not None and _risky_aggro(handoff_observation):
                corridor = _retreat_corridor_from_handoff(
                    args.navigation_handoff_result,
                    perception=perception,
                )
                result = _run_risky_aggro_retreat(
                    motion_gateway=motion_gateway,
                    perception=perception,
                    initial_observation=handoff_observation,
                    corridor=corridor,
                    encounter_id=encounter_id,
                )
            else:
                run_control = (
                    None
                    if args.operator_control_file is None
                    else FileOperatorCombatControl(args.operator_control_file.resolve())
                )
                result = ControlledCombatEncounter(
                    gateway=gateway,
                    observations=perception,
                    policy=policy,
                    clock=clock,
                    wait_ms=lambda milliseconds: time.sleep(milliseconds / 1_000.0),
                    preserve_selected_target=(
                        args.target_name is not None or args.recover_selected_corpse_only
                    ),
                    recover_after_kill=True,
                    advance_past_initial_dead_target=(
                        args.target_name is None and not args.recover_selected_corpse_only
                    ),
                    motion=motion_gateway,
                    run_control=run_control,
                ).run(encounter_id=encounter_id)
        if target_probe is not None:
            result["precombat_target_probe"] = target_probe.to_record()
        _atomic_write(result_path, _exact_json_bytes(result))
        print(json.dumps({"result_path": str(result_path), **result}, sort_keys=True))
        successful_statuses = {
            "TARGET_DEFEATED",
            "ONE_MOUSE_TURN_EXECUTED",
            "CONTINUOUS_FACING_LOCK_VERIFIED",
            "FACING_TRANSFER_MEASURED",
            "ONE_ACQUISITION_SCAN_EXECUTED",
            "ONE_SELECTED_TARGET_SEARCH_EXECUTED",
            "NO_TURN_REQUIRED_OR_VISUALLY_JUSTIFIED",
            "READ_ONLY_OBSERVATION_COMPLETE",
            "ONE_CAMERA_PITCH_PROBE_EXECUTED",
            "ESCAPED_RISKY_AGGRO",
        }
        return 0 if result["status"] in successful_statuses else 3
    except Exception as error:
        failure = (
            error.to_record()
            if isinstance(error, ControlledCombatEncounterFailure)
            else {
                "record_type": "controlled_combat_failure",
                "schema_version": "0.1",
                "encounter_id": encounter_id,
                "status": "STOPPED_FAIL_CLOSED",
                "target_identity_crc16": None,
                "error_type": type(error).__name__,
                "detail": str(error),
                "actions_executed": 0,
                "decisions": [],
                "executions": [],
                "manual_takeover_available": True,
                "execution_authority": False,
            }
        )
        _atomic_write(result_path, _exact_json_bytes(failure))
        print(json.dumps({"result_path": str(result_path), **failure}, sort_keys=True))
        return 1
    finally:
        if target_command_gateway is not None:
            try:
                target_command_gateway.close()
            except Exception:
                pass
        if unregister_takeover is not None:
            try:
                unregister_takeover()
            except Exception:
                pass
        if perception is not None:
            try:
                perception.close()
            except Exception:
                pass
        elif tether_coordinator is not None:
            try:
                tether_coordinator.close()
            except Exception:
                pass
        if gateway is not None:
            try:
                gateway.close()
            except Exception:
                pass
        if motion_gateway is not None:
            try:
                motion_gateway.close()
            except Exception:
                pass
        if sink is not None:
            try:
                sink.close()
            except Exception:
                pass
        arm_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(run())
