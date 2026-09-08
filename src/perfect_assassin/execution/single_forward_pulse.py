from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import hypot, isfinite, sqrt
from typing import Callable, Mapping, Protocol

from perfect_assassin.adapter.coordinate_hud import (
    CoordinateHudProtocolError,
    validate_valid_observation_semantics,
)
from perfect_assassin.contract_validation import ContractValidationError, ContractValidator
from perfect_assassin.execution.contracts import ExecutionPoseState, ExecutionResult
from perfect_assassin.execution.gateway import ExecutionGateway
from perfect_assassin.execution.movement_runtime_arm import (
    F3A_EXECUTION_LEASE_POLICY,
    F3A_POSE_COORDINATE_SPACE,
    MAX_MOVEMENT_HOLD_MS,
    MovementRuntimeArm,
)
from perfect_assassin.execution.ports import InMemoryRuntimeArm, InputSink, MonotonicClock


COORDINATOR_SCHEMA_VERSION = "0.1"
POSITION_RADIUS_95 = sqrt(2.0) / (2.0 * 65_535.0)
MAX_COORDINATOR_DURATION_MS = 5_000.0
MAX_POST_OBSERVATION_ATTEMPTS = 64
F3A_HUD_PROFILE_ID = "coordinate_hud_tbc243_v1"
F3A_HUD_PROFILE_VERSION = "0.2.0"
F3A_HUD_PROFILE_SHA256 = (
    "C05E2FF78B5857088559EE4C96AA8889C718FDE9A07D2E2748EBB2534FF8958E"
)
F3A_HUD_CALIBRATION_STATE = "synthetic_verified"


class ObservationSource(Protocol):
    def next_observation(self) -> Mapping[str, object] | None: ...


class ManualTakeoverSource(Protocol):
    def arm(self, callback: Callable[[], bool]) -> Callable[[], None]: ...


class SingleForwardPulseError(ValueError):
    """The bounded single-pulse coordinator was configured unsafely."""


def validate_single_forward_pulse_result_semantics(
    record: Mapping[str, object],
) -> None:
    """Reject cross-field result claims that JSON Schema cannot express."""

    if record.get("record_type") != "single_forward_pulse_result" or record.get(
        "schema_version"
    ) != COORDINATOR_SCHEMA_VERSION:
        raise SingleForwardPulseError("single-pulse result version is invalid")
    timing = record.get("timing")
    cleanup = record.get("cleanup")
    if not isinstance(timing, Mapping) or not isinstance(cleanup, Mapping):
        raise SingleForwardPulseError("single-pulse timing or cleanup is missing")
    try:
        started = float(timing["started_at_monotonic_ms"])
        completed = float(timing["completed_at_monotonic_ms"])
        deadline = float(timing["deadline_monotonic_ms"])
    except (KeyError, TypeError, ValueError) as error:
        raise SingleForwardPulseError("single-pulse timing is invalid") from error
    if not all(isfinite(value) and value >= 0 for value in (started, completed, deadline)):
        raise SingleForwardPulseError("single-pulse timing must be finite")
    if completed < started or deadline != started + MAX_COORDINATOR_DURATION_MS:
        raise SingleForwardPulseError("single-pulse timing window is inconsistent")
    if (
        cleanup.get("arm_disarmed") is not True
        or not isinstance(cleanup.get("gateway_closed"), bool)
        or cleanup.get("manual_takeover_disarmed") is not True
        or not isinstance(cleanup.get("release_faulted"), bool)
    ):
        raise SingleForwardPulseError("single-pulse cleanup is incomplete")

    status = record.get("status")
    pre = record.get("pre_observation")
    post = record.get("post_observation")
    execution = record.get("execution_result")
    delta = record.get("delta")
    measured_status = status in {"PROVEN_DISPLACEMENT", "NO_PROVEN_DISPLACEMENT"}
    if measured_status:
        if not all(isinstance(value, Mapping) for value in (pre, post, execution, delta)):
            raise SingleForwardPulseError("measured result requires complete evidence")
        assert isinstance(pre, Mapping)
        assert isinstance(post, Mapping)
        assert isinstance(execution, Mapping)
        assert isinstance(delta, Mapping)
        if execution.get("status") != "EXECUTED" or execution.get("reason_code") != "EXECUTED":
            raise SingleForwardPulseError("measured result requires executed primitive")
        if cleanup.get("gateway_closed") is not True or cleanup.get("release_faulted") is not False:
            raise SingleForwardPulseError("measured result requires clean final release")
        if completed > deadline:
            raise SingleForwardPulseError("measured result exceeded coordinator deadline")
        if (
            pre.get("session_id") != post.get("session_id")
            or pre.get("continent_index") != post.get("continent_index")
            or pre.get("zone_index") != post.get("zone_index")
            or pre.get("frame_id") == post.get("frame_id")
            or pre.get("observation_id") == post.get("observation_id")
        ):
            raise SingleForwardPulseError("measured observations do not share one fresh source")
        sequence_delta = (int(post["sequence"]) - int(pre["sequence"])) & 0xFF
        if not 1 <= sequence_delta <= 127:
            raise SingleForwardPulseError("measured post sequence is not newer")
        if float(post["captured_at_monotonic_ms"]) <= float(
            execution["completed_at_monotonic_ms"]
        ):
            raise SingleForwardPulseError("measured post frame predates execution completion")
        dx = float(post["x"]) - float(pre["x"])
        dy = float(post["y"]) - float(pre["y"])
        distance = hypot(dx, dy)
        combined = float(pre["position_radius_95"]) + float(post["position_radius_95"])
        lower = max(0.0, distance - combined)
        for name, expected in (
            ("dx", dx),
            ("dy", dy),
            ("distance", distance),
            ("combined_position_radius_95", combined),
            ("proven_lower_bound", lower),
        ):
            actual = float(delta[name])
            if not isfinite(actual) or abs(actual - expected) > 1e-12:
                raise SingleForwardPulseError(f"single-pulse delta {name} is inconsistent")
        if (status == "PROVEN_DISPLACEMENT") != (lower > 0.0):
            raise SingleForwardPulseError("single-pulse displacement claim contradicts uncertainty")
    elif status == "EXECUTION_REJECTED" or status == "CANCELLED":
        if not isinstance(execution, Mapping) or post is not None or delta is not None:
            raise SingleForwardPulseError("execution rejection evidence is inconsistent")
        expected_status = "CANCELLED" if status == "CANCELLED" else None
        if expected_status is not None and execution.get("status") != expected_status:
            raise SingleForwardPulseError("cancelled coordinator result contradicts execution")
        if execution.get("status") == "EXECUTED":
            raise SingleForwardPulseError("execution rejection cannot contain success")
    elif status == "OBSERVATION_REJECTED":
        if delta is not None:
            raise SingleForwardPulseError("observation rejection cannot publish displacement")
    elif status == "FAILED":
        if delta is not None:
            raise SingleForwardPulseError("failed coordinator cannot publish displacement")
    else:
        raise SingleForwardPulseError("single-pulse status is unsupported")


@dataclass(frozen=True, slots=True)
class _ObservationSnapshot:
    record: dict[str, object]
    digest: str
    sequence: int
    x: float
    y: float
    continent_index: int
    zone_index: int
    captured_at_ms: float
    observed_at_ms: float
    expires_at_ms: float

    def summary(self) -> dict[str, object]:
        return {
            "observation_id": self.record["observation_id"],
            "frame_id": self.record["frame_id"],
            "session_id": self.record["session_id"],
            "sequence": self.sequence,
            "x": self.x,
            "y": self.y,
            "continent_index": self.continent_index,
            "zone_index": self.zone_index,
            "captured_at_monotonic_ms": self.captured_at_ms,
            "observed_at_monotonic_ms": self.observed_at_ms,
            "expires_at_monotonic_ms": self.expires_at_ms,
            "confidence": float(self.record["confidence"]),
            "position_radius_95": POSITION_RADIUS_95,
            "observation_sha256": self.digest,
        }


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise SingleForwardPulseError("record is not finite canonical JSON") from error
    if not 1 <= len(raw) <= 2 * 1024 * 1024:
        raise SingleForwardPulseError("record exceeds the bounded snapshot size")
    return raw


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


class SingleForwardPulseCoordinator:
    """Execute and measure exactly one LAB-only 100/150ms forward pulse.

    This coordinator consumes only the client-visible coordinate HUD. It does
    not use server truth, WorldMap transforms, navigation meshes, or invented
    yaw. A successful movement claim requires a distinct post-execution frame
    whose displacement exceeds the combined quantization uncertainty.
    """

    def __init__(
        self,
        *,
        arm: MovementRuntimeArm,
        clock: MonotonicClock,
        sink: InputSink,
        observations: ObservationSource,
        observation_validator: ContractValidator,
        result_validator: ContractValidator,
        manual_takeover: ManualTakeoverSource | None = None,
        sleep_ms: Callable[[float], None] | None = None,
    ) -> None:
        if not isinstance(arm, MovementRuntimeArm):
            raise SingleForwardPulseError("arm must be a validated movement arm")
        if arm.lease_policy != F3A_EXECUTION_LEASE_POLICY:
            raise SingleForwardPulseError("arm does not carry the exact F3a policy")
        if not callable(getattr(observations, "next_observation", None)):
            raise SingleForwardPulseError("observation source is invalid")
        self._arm = arm
        self._clock = clock
        self._sink = sink
        self._observations = observations
        self._observation_validator = observation_validator
        self._result_validator = result_validator
        self._manual_takeover = manual_takeover
        self._sleep_ms = sleep_ms or (lambda _milliseconds: None)

    def run(self, *, run_id: str, owner_id: str) -> dict[str, object]:
        started = self._now()
        deadline = started + MAX_COORDINATOR_DURATION_MS
        arm_provider = InMemoryRuntimeArm(self._arm.runtime_snapshot())
        lease = self._arm.compile_execution_lease(
            lease_id=f"lease:{run_id}",
            owner_id=owner_id,
            now_monotonic_ms=started,
        )
        gateway = ExecutionGateway(
            authorization=self._arm.execution_authorization(),
            lease=lease,
            runtime_arm=arm_provider,
            clock=self._clock,
            sink=self._sink,
        )
        pre: _ObservationSnapshot | None = None
        post: _ObservationSnapshot | None = None
        execution: ExecutionResult | None = None
        delta: dict[str, float] | None = None
        status = "FAILED"
        reason = "INTERNAL_FAILURE"
        gateway_closed = False
        takeover_disarmed = self._manual_takeover is None
        unregister_takeover: Callable[[], None] | None = None
        try:
            if self._manual_takeover is not None:
                unregister_takeover = self._manual_takeover.arm(
                    gateway.cancel_for_manual_takeover
                )
                if not callable(unregister_takeover):
                    raise SingleForwardPulseError("MANUAL_TAKEOVER_SOURCE_INVALID")
            candidate = self._observations.next_observation()
            pre = self._snapshot_observation(candidate, now_ms=self._now())
            self._require_arm_binding(pre)
            pose = self._pose_from(pre)

            primitive_now = self._now()
            primitive = self._arm.compile_forward_primitive(
                lease=lease,
                primitive_id=f"primitive:{run_id}",
                now_monotonic_ms=primitive_now,
                hold_duration_ms=MAX_MOVEMENT_HOLD_MS,
            )
            execution = gateway.execute(primitive, pose)
            if execution.status != "EXECUTED":
                status = "CANCELLED" if execution.status == "CANCELLED" else "EXECUTION_REJECTED"
                reason = execution.reason_code
            else:
                post, post_reason = self._wait_for_post(pre, execution, deadline)
                if post is None:
                    status = "OBSERVATION_REJECTED"
                    reason = post_reason
                else:
                    dx = post.x - pre.x
                    dy = post.y - pre.y
                    distance = hypot(dx, dy)
                    combined = POSITION_RADIUS_95 * 2.0
                    lower = max(0.0, distance - combined)
                    delta = {
                        "dx": dx,
                        "dy": dy,
                        "distance": distance,
                        "combined_position_radius_95": combined,
                        "proven_lower_bound": lower,
                    }
                    if lower > 0.0:
                        status = "PROVEN_DISPLACEMENT"
                        reason = "DISPLACEMENT_EXCEEDS_UNCERTAINTY"
                    else:
                        status = "NO_PROVEN_DISPLACEMENT"
                        reason = "DISPLACEMENT_WITHIN_UNCERTAINTY"
        except (SingleForwardPulseError, CoordinateHudProtocolError, ContractValidationError) as error:
            status = "OBSERVATION_REJECTED"
            reason = self._bounded_error_reason(error)
        except Exception:
            status = "FAILED"
            reason = "INTERNAL_FAILURE"
        finally:
            if unregister_takeover is not None:
                try:
                    unregister_takeover()
                    takeover_disarmed = True
                except Exception:
                    takeover_disarmed = False
            arm_provider.disarm()
            gateway_closed = gateway.close()

        if not takeover_disarmed:
            status = "FAILED"
            reason = "MANUAL_TAKEOVER_CLEANUP_FAILED"
            delta = None

        completed = self._now()
        record = {
            "record_type": "single_forward_pulse_result",
            "schema_version": COORDINATOR_SCHEMA_VERSION,
            "run_id": run_id,
            "binding": self._arm.binding.to_record(),
            "movement_arm": {
                "arm_nonce": self._arm.arm_nonce,
                "arm_sha256": self._arm.record_sha256,
                "session_receipt_nonce": self._arm.session_receipt_nonce,
                "session_receipt_sha256": self._arm.session_receipt_sha256,
                "realm_revalidation_nonce": self._arm.realm_revalidation_nonce,
                "realm_revalidation_sha256": self._arm.realm_revalidation_sha256,
            },
            "status": status,
            "reason": reason,
            "pre_observation": pre.summary() if pre is not None else None,
            "post_observation": post.summary() if post is not None else None,
            "execution_result": self._execution_summary(execution),
            "delta": delta,
            "timing": {
                "clock_id": self._arm.clock_id,
                "started_at_monotonic_ms": started,
                "completed_at_monotonic_ms": completed,
                "deadline_monotonic_ms": deadline,
            },
            "cleanup": {
                "arm_disarmed": arm_provider.snapshot().active is False,
                "gateway_closed": gateway_closed,
                "manual_takeover_disarmed": takeover_disarmed,
                "release_faulted": gateway.release_faulted,
            },
            "scope": "lab_evaluation_only",
            "execution_authority": False,
        }
        validate_single_forward_pulse_result_semantics(record)
        self._result_validator.validate(record)
        return record

    def _wait_for_post(
        self,
        pre: _ObservationSnapshot,
        execution: ExecutionResult,
        deadline: float,
    ) -> tuple[_ObservationSnapshot | None, str]:
        for _ in range(MAX_POST_OBSERVATION_ATTEMPTS):
            now = self._now()
            if now > deadline:
                return None, "POST_OBSERVATION_DEADLINE"
            candidate = self._observations.next_observation()
            if candidate is None:
                self._sleep_ms(10.0)
                continue
            post = self._snapshot_observation(candidate, now_ms=self._now())
            self._require_arm_binding(post)
            if post.record["session_id"] != pre.record["session_id"]:
                return None, "POST_SOURCE_CHANGED"
            if (
                post.continent_index != pre.continent_index
                or post.zone_index != pre.zone_index
            ):
                return None, "MAP_CONTEXT_CHANGED"
            if post.record["frame_id"] == pre.record["frame_id"] or post.record["observation_id"] == pre.record["observation_id"]:
                self._sleep_ms(10.0)
                continue
            sequence_delta = (post.sequence - pre.sequence) & 0xFF
            if not 1 <= sequence_delta <= 127:
                return None, "POST_SEQUENCE_NOT_NEWER"
            if post.captured_at_ms <= execution.completed_at_monotonic_ms:
                self._sleep_ms(10.0)
                continue
            return post, "POST_OBSERVATION_VERIFIED"
        return None, "POST_OBSERVATION_LIMIT"

    def _snapshot_observation(
        self,
        candidate: Mapping[str, object] | None,
        *,
        now_ms: float,
    ) -> _ObservationSnapshot:
        if candidate is None or not isinstance(candidate, Mapping):
            raise SingleForwardPulseError("OBSERVATION_MISSING")
        raw = _canonical_bytes(candidate)
        record = json.loads(raw)
        self._observation_validator.validate(record)
        packet = validate_valid_observation_semantics(record)
        provenance = record.get("provenance")
        if not isinstance(provenance, dict) or (
            provenance.get("capture_origin") != "window_capture"
            or provenance.get("scope") != "lab_evaluation_only"
            or provenance.get("profile_id") != F3A_HUD_PROFILE_ID
            or provenance.get("profile_version") != F3A_HUD_PROFILE_VERSION
            or provenance.get("profile_sha256") != F3A_HUD_PROFILE_SHA256
            or provenance.get("profile_calibration_state")
            != F3A_HUD_CALIBRATION_STATE
        ):
            raise SingleForwardPulseError("OBSERVATION_NOT_CONTROLLED_LIVE_LAB")
        timing = record["timing"]
        captured = float(timing["monotonic_timestamp_s"]) * 1000.0
        observed = float(timing["observed_monotonic_s"]) * 1000.0
        expires = float(timing["expires_monotonic_s"]) * 1000.0
        if now_ms > expires or observed > now_ms + 1.0:
            raise SingleForwardPulseError("OBSERVATION_NOT_FRESH_NOW")
        if float(record["confidence"]) < F3A_EXECUTION_LEASE_POLICY.min_pose_confidence:
            raise SingleForwardPulseError("OBSERVATION_CONFIDENCE_TOO_LOW")
        assert packet.x is not None and packet.y is not None
        return _ObservationSnapshot(
            record=record,
            digest=_sha256(raw),
            sequence=packet.sequence,
            x=packet.x,
            y=packet.y,
            continent_index=packet.continent_index,
            zone_index=packet.zone_index,
            captured_at_ms=captured,
            observed_at_ms=observed,
            expires_at_ms=expires,
        )

    def _require_arm_binding(self, observation: _ObservationSnapshot) -> None:
        record = observation.record
        actor = record.get("actor_binding")
        binding = self._arm.binding
        if not isinstance(actor, dict) or (
            actor.get("actor_id") != binding.actor_id
            or actor.get("instance_id") != binding.actor_instance_id
            or actor.get("actor_role") != binding.actor_role
            or actor.get("decision_context") != binding.decision_context
            or record.get("decision_context") != binding.decision_context
            or record.get("target_profile") != binding.target_profile
            or record.get("authorization_sha256") != binding.authorization_sha256
        ):
            raise SingleForwardPulseError("OBSERVATION_AUTHORITY_BINDING_MISMATCH")

    def _pose_from(self, observation: _ObservationSnapshot) -> ExecutionPoseState:
        binding = self._arm.binding
        return ExecutionPoseState(
            pose_id=f"pose:{observation.digest[:32]}",
            actor_id=binding.actor_id,
            actor_instance_id=binding.actor_instance_id,
            actor_role=binding.actor_role,
            decision_context=binding.decision_context,
            target_profile=binding.target_profile,
            target_instance_id=binding.target_instance_id,
            authorization_id=binding.authorization_id,
            authorization_sha256=binding.authorization_sha256,
            state="VALID",
            source_scope="lab_evaluation_only",
            source_id="coordinate_hud:v2",
            capability="self_map_position",
            source_origins=("visible_addon_hud", "window_capture"),
            evidence_refs=(
                f"hud_observation_sha256:{observation.digest}",
                f"hud_frame_sha256:{_sha256(str(observation.record['frame_id']).encode('utf-8'))}",
            ),
            confidence=float(observation.record["confidence"]),
            freshness_status="FRESH",
            available_pose_components=("POSITION_2D",),
            position_coordinate_space=F3A_POSE_COORDINATE_SPACE,
            position_radius_95=POSITION_RADIUS_95,
            yaw_error_95_deg=None,
            clock_id=self._arm.clock_id,
            observed_at_monotonic_ms=observation.observed_at_ms,
            expires_at_monotonic_ms=observation.expires_at_ms,
        )

    @staticmethod
    def _execution_summary(result: ExecutionResult | None) -> dict[str, object] | None:
        if result is None:
            return None
        record = result.to_record()
        return {
            "result_id": result.result_id,
            "primitive_id": result.primitive_id,
            "status": result.status,
            "reason_code": result.reason_code,
            "completed_at_monotonic_ms": result.completed_at_monotonic_ms,
            "result_sha256": _sha256(_canonical_bytes(record)),
        }

    def _now(self) -> float:
        value = self._clock.now_ms()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            raise SingleForwardPulseError("CLOCK_INVALID")
        return float(value)

    @staticmethod
    def _bounded_error_reason(error: Exception) -> str:
        text = str(error).upper()
        known = (
            "OBSERVATION_MISSING",
            "OBSERVATION_NOT_CONTROLLED_LIVE_LAB",
            "OBSERVATION_NOT_FRESH_NOW",
            "OBSERVATION_CONFIDENCE_TOO_LOW",
            "OBSERVATION_AUTHORITY_BINDING_MISMATCH",
            "CLOCK_INVALID",
        )
        for reason in known:
            if reason in text:
                return reason
        return "OBSERVATION_CONTRACT_INVALID"
