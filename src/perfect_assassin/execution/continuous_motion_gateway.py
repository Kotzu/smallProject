"""Fail-closed gateway for the long-lived navigation actuator.

The normal fixed-UI session is enough to read the client.  It is not enough
to hold movement keys.  This small gateway keeps that distinction visible at
the call site and makes a future continuous-motion runtime arm an explicit
dependency of navigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
from threading import RLock
from typing import Any

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator
from perfect_assassin.execution.continuous_motion_authorization import (
    load_continuous_motion_authorization_profile,
)
from perfect_assassin.execution.continuous_motion import ContinuousMotionFrame
from perfect_assassin.execution.contracts import AuthorityBinding
from perfect_assassin.execution.ports import CooperativeCancellation, MonotonicClock
from perfect_assassin.execution.windows_continuous_motion import (
    CONTINUOUS_LEASE_TIMEOUT_MS,
    WindowsContinuousMotionBackend,
    WindowsContinuousMotionSession,
)
from perfect_assassin.execution.windows_send_input import WindowsInputTargetBinding


CONTINUOUS_NAVIGATION_AUTHORIZATION_ID = (
    "execution:tbc243-lab:movement-f4a-continuous-navmesh"
)
CONTINUOUS_NAVIGATION_ALLOWED_CONTROLS = frozenset(
    {"MOVE_FORWARD", "MOVE_BACKWARD", "STRAFE_LEFT", "STRAFE_RIGHT"}
)


class ContinuousMotionAuthorityError(ValueError):
    """Raised when the navigation actuator has no exact continuous arm."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _read_object(raw: bytes, name: str) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 2 * 1024 * 1024:
        raise ContinuousMotionAuthorityError(f"{name} must be bounded bytes")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ContinuousMotionAuthorityError(f"{name} is not strict JSON") from error
    if type(value) is not dict:
        raise ContinuousMotionAuthorityError(f"{name} root must be an object")
    return value


def load_continuous_motion_authority(
    raw: bytes,
    *,
    authorization_raw: bytes,
    session_receipt_raw: bytes,
    realm_revalidation_raw: bytes | None,
    target: WindowsInputTargetBinding,
    clock: MonotonicClock,
    schema_path: Path | None = None,
    authorization_schema_path: Path | None = None,
    prior_authorization_raw: bytes | None = None,
) -> ContinuousMotionAuthority:
    """Load a separately issued F4a arm and bind it to this exact client.

    The loader intentionally requires a *continuous* authorization profile.
    A fixed-UI file, the old F3a single pulse, or a hand-written arm cannot be
    upgraded here.  The trusted issuer still has to produce the arm; this
    function only checks the byte bindings needed by the actuator.
    """

    record = _read_object(raw, "continuous motion runtime arm")
    if schema_path is not None:
        try:
            ContractValidator(schema_path).validate(record)
        except ContractValidationError as error:
            raise ContinuousMotionAuthorityError(
                "continuous motion runtime arm failed its versioned contract"
            ) from error
    authorization = _read_object(authorization_raw, "continuous motion authorization")
    receipt = _read_object(session_receipt_raw, "session receipt")
    if realm_revalidation_raw is None:
        raise ContinuousMotionAuthorityError(
            "continuous motion runtime arm must bind a fresh realm revalidation"
        )
    revalidation = _read_object(realm_revalidation_raw, "realm revalidation")
    if authorization_schema_path is not None:
        try:
            load_continuous_motion_authorization_profile(
                authorization_raw,
                schema_path=authorization_schema_path,
                now_utc=datetime.now(timezone.utc),
            )
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ContinuousMotionAuthorityError(
                "continuous motion authorization failed its active profile checks"
            ) from error
    if (
        record.get("record_type") != "continuous_motion_runtime_arm"
        or record.get("schema_version") != "0.1"
        or record.get("authorization_id") != CONTINUOUS_NAVIGATION_AUTHORIZATION_ID
        or record.get("scope") != "lab_movement_continuous_navmesh"
        or record.get("active") is not True
        or record.get("execution_authority") is not True
    ):
        raise ContinuousMotionAuthorityError("runtime arm is not the F4a continuous profile")
    if (
        authorization.get("record_type") != "execution_target_authorization"
        or authorization.get("schema_version") != "2.0"
        or authorization.get("authorization_id") != CONTINUOUS_NAVIGATION_AUTHORIZATION_ID
        or authorization.get("status") != "approved_bounded"
        or authorization.get("environment_scope") != "emulator_local"
        or authorization.get("runtime_arm_required") is not True
        or authorization.get("permitted_modes") != ["MOVEMENT_ONLY"]
    ):
        raise ContinuousMotionAuthorityError(
            "continuous authorization is missing or is still pending evidence"
        )
    expected_capabilities = {
        "SCREEN_CAPTURE_READ_ONLY",
        "VISIBLE_COORDINATE_HUD_READ_ONLY",
        "MOVEMENT_EXECUTION",
    }
    if set(authorization.get("permitted_capabilities", ())) != expected_capabilities:
        raise ContinuousMotionAuthorityError(
            "continuous authorization capability set is not exact"
        )
    policy = authorization.get("movement_policy")
    if type(policy) is not dict:
        raise ContinuousMotionAuthorityError("continuous authorization has no movement policy")
    if (
        set(policy.get("allowed_controls", ())) != CONTINUOUS_NAVIGATION_ALLOWED_CONTROLS
        or policy.get("max_hold_duration_ms") != 450
        or policy.get("max_execution_envelope_ms") != 500
        or policy.get("max_primitives") != 4096
        or policy.get("manual_takeover_required") is not True
        or policy.get("release_all_required") is not True
        or policy.get("combat_authorized") is not False
        or policy.get("economy_authorized") is not False
    ):
        raise ContinuousMotionAuthorityError(
            "continuous authorization policy exceeds the reviewed F4a bounds"
        )
    if record.get("authorization_sha256") != _sha256(authorization_raw):
        raise ContinuousMotionAuthorityError("runtime arm does not bind authorization bytes")
    if record.get("session_receipt_sha256") != _sha256(session_receipt_raw):
        raise ContinuousMotionAuthorityError("runtime arm does not bind the session receipt")
    if record.get("realm_revalidation_sha256") != _sha256(realm_revalidation_raw):
        raise ContinuousMotionAuthorityError("runtime arm does not bind realm revalidation")
    if receipt.get("execution_authority") is not False:
        raise ContinuousMotionAuthorityError("session receipt must remain non-authority evidence")
    if (
        revalidation.get("record_type") != "local_realm_revalidation_receipt"
        or revalidation.get("execution_authority") is not False
        or revalidation.get("authorization_id") != CONTINUOUS_NAVIGATION_AUTHORIZATION_ID
        or revalidation.get("authorization_sha256") != _sha256(authorization_raw)
        or revalidation.get("session_receipt_nonce") != receipt.get("receipt_nonce")
        or revalidation.get("session_receipt_sha256") != _sha256(session_receipt_raw)
        or revalidation.get("target_profile") != record.get("target_profile")
        or revalidation.get("actor_id") != record.get("actor_binding", {}).get("actor_id")
        or revalidation.get("actor_instance_id")
        != record.get("actor_binding", {}).get("instance_id")
        or revalidation.get("pid") != record.get("pid")
        or revalidation.get("hwnd") != record.get("hwnd")
        or revalidation.get("process_creation_filetime_utc")
        != record.get("process_creation_filetime_utc")
    ):
        raise ContinuousMotionAuthorityError(
            "realm revalidation does not bind the continuous authorization and receipt"
        )

    actor = authorization.get("actor_binding")
    if type(actor) is not dict or record.get("actor_binding") != actor:
        raise ContinuousMotionAuthorityError("runtime arm actor binding diverges")
    try:
        expected_target_instance = (
            f"client:windows:{int(record['pid'])}:{record['process_creation_filetime_utc']}"
        )
        target_instance = str(record["target_instance_id"])
        binding = AuthorityBinding(
            actor_id=str(actor["actor_id"]),
            actor_instance_id=str(actor["instance_id"]),
            actor_role=str(actor["actor_role"]),
            decision_context=str(actor["decision_context"]),
            target_profile=str(record["target_profile"]),
            target_instance_id=target_instance,
            authorization_id=CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
            authorization_sha256=_sha256(authorization_raw),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ContinuousMotionAuthorityError("runtime arm binding is malformed") from error
    renewal_parent = authorization.get("approval", {}).get(
        "renews_authorization_sha256"
    )
    temporal_rollover = (
        prior_authorization_raw is not None
        and renewal_parent == _sha256(prior_authorization_raw)
        and authorization.get("approval", {}).get("renewal_scope") == "temporal_only"
    )
    binding_identity = (
        binding.actor_id,
        binding.actor_instance_id,
        binding.actor_role,
        binding.decision_context,
        binding.target_profile,
        binding.target_instance_id,
        binding.authorization_id,
    )
    target_binding = target.authority_binding
    target_identity = (
        target_binding.actor_id,
        target_binding.actor_instance_id,
        target_binding.actor_role,
        target_binding.decision_context,
        target_binding.target_profile,
        target_binding.target_instance_id,
        target_binding.authorization_id,
    )
    if (
        target_instance != expected_target_instance
        or binding_identity != target_identity
        or (binding != target_binding and not temporal_rollover)
    ):
        raise ContinuousMotionAuthorityError(
            "runtime arm does not bind the exact Windows client target"
        )
    identity_pairs = (
        (record.get("pid"), target.pid),
        (record.get("hwnd"), f"0x{target.hwnd:X}"),
        (record.get("process_creation_filetime_utc"), str(target.process_creation_time_100ns)),
        (record.get("executable_path"), target.executable_path),
        (record.get("executable_sha256"), target.executable_sha256),
        (record.get("window_class"), target.window_class_exact),
        (record.get("window_title"), target.window_title_exact),
    )
    if any(actual != expected for actual, expected in identity_pairs):
        raise ContinuousMotionAuthorityError("runtime arm target identity is not exact")
    if record.get("target_profile") != "tbc_243_lab":
        raise ContinuousMotionAuthorityError("runtime arm target profile is not the LAB")
    if record.get("clock_id") != clock.clock_id:
        raise ContinuousMotionAuthorityError("runtime arm clock does not match the actuator")
    try:
        issued = float(record["issued_at_monotonic_ms"])
        expires = float(record["expires_at_monotonic_ms"])
    except (KeyError, TypeError, ValueError) as error:
        raise ContinuousMotionAuthorityError("runtime arm monotonic window is malformed") from error
    authority = ContinuousMotionAuthority(
        binding=binding,
        authorization_id=CONTINUOUS_NAVIGATION_AUTHORIZATION_ID,
        authorization_sha256=_sha256(authorization_raw),
        clock_id=clock.clock_id,
        issued_at_monotonic_ms=issued,
        expires_at_monotonic_ms=expires,
        allowed_controls=frozenset(policy["allowed_controls"]),
        lease_timeout_ms=CONTINUOUS_LEASE_TIMEOUT_MS,
        renewal_parent_sha256=renewal_parent,
    )
    now_ms = clock.now_ms()
    if now_ms < authority.issued_at_monotonic_ms or now_ms >= authority.expires_at_monotonic_ms:
        raise ContinuousMotionAuthorityError("runtime arm is expired or not yet valid")
    return authority


@dataclass(frozen=True, slots=True)
class ContinuousMotionAuthority:
    """The already-validated, short-lived authority consumed by the gateway.

    This is deliberately an in-memory value.  A JSON arm must be validated by
    its issuer/loader before it is turned into this object; the gateway never
    treats a fixed-UI receipt as an arm.
    """

    binding: AuthorityBinding
    authorization_id: str
    authorization_sha256: str
    clock_id: str
    issued_at_monotonic_ms: float
    expires_at_monotonic_ms: float
    allowed_controls: frozenset[str]
    lease_timeout_ms: int = CONTINUOUS_LEASE_TIMEOUT_MS
    active: bool = True
    renewal_parent_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.authorization_id != CONTINUOUS_NAVIGATION_AUTHORIZATION_ID:
            raise ContinuousMotionAuthorityError(
                "continuous navigation authority id is not the reviewed profile"
            )
        if (
            type(self.authorization_sha256) is not str
            or len(self.authorization_sha256) != 64
            or any(character not in "0123456789ABCDEF" for character in self.authorization_sha256)
        ):
            raise ContinuousMotionAuthorityError(
                "continuous navigation authority hash is invalid"
            )
        if type(self.clock_id) is not str or not self.clock_id:
            raise ContinuousMotionAuthorityError("continuous navigation clock is invalid")
        if (
            not isfinite(self.issued_at_monotonic_ms)
            or not isfinite(self.expires_at_monotonic_ms)
            or self.issued_at_monotonic_ms < 0
            or self.expires_at_monotonic_ms <= self.issued_at_monotonic_ms
        ):
            raise ContinuousMotionAuthorityError(
                "continuous navigation authority lifetime is invalid"
            )
        if (
            not self.allowed_controls
            or not self.allowed_controls.issubset(CONTINUOUS_NAVIGATION_ALLOWED_CONTROLS)
        ):
            raise ContinuousMotionAuthorityError(
                "continuous navigation authority controls exceed the reviewed profile"
            )
        if type(self.lease_timeout_ms) is not int or not 120 <= self.lease_timeout_ms <= 500:
            raise ContinuousMotionAuthorityError(
                "continuous navigation lease timeout is invalid"
            )
        if self.active is not True:
            raise ContinuousMotionAuthorityError(
                "continuous navigation authority must be active at construction"
            )
        if self.renewal_parent_sha256 is not None and (
            len(self.renewal_parent_sha256) != 64
            or any(character not in "0123456789ABCDEF" for character in self.renewal_parent_sha256)
        ):
            raise ContinuousMotionAuthorityError(
                "continuous navigation renewal parent hash is invalid"
            )


class ContinuousMotionExecutionGateway:
    """Own one continuous session only after an exact runtime arm is present."""

    def __init__(
        self,
        *,
        authority: ContinuousMotionAuthority | None,
        target: WindowsInputTargetBinding,
        backend: WindowsContinuousMotionBackend,
        clock: MonotonicClock,
    ) -> None:
        if not isinstance(authority, ContinuousMotionAuthority):
            raise ContinuousMotionAuthorityError(
                "continuous navigation requires a dedicated runtime arm; fixed UI is not enough"
            )
        if authority.binding != target.authority_binding:
            raise ContinuousMotionAuthorityError(
                "continuous navigation authority does not bind the exact client target"
            )
        if authority.clock_id != clock.clock_id:
            raise ContinuousMotionAuthorityError(
                "continuous navigation authority clock does not match the actuator clock"
            )
        now_ms = clock.now_ms()
        if (
            not isfinite(now_ms)
            or now_ms < authority.issued_at_monotonic_ms
            or now_ms >= authority.expires_at_monotonic_ms
        ):
            raise ContinuousMotionAuthorityError(
                "continuous navigation runtime arm is expired or not yet valid"
            )
        self._authority = authority
        self._clock = clock
        self._lock = RLock()
        self._revoked = False
        self._session = WindowsContinuousMotionSession(
            target=target,
            backend=backend,
            clock=clock,
            expires_at_monotonic_ms=authority.expires_at_monotonic_ms,
            lease_timeout_ms=authority.lease_timeout_ms,
        )

    @property
    def held_controls(self) -> tuple[str, ...]:
        return self._session.held_controls

    @property
    def mouse_look_held(self) -> bool:
        return self._session.mouse_look_held

    def apply_frame(
        self,
        frame: ContinuousMotionFrame,
        cancellation: CooperativeCancellation,
    ):
        if not isinstance(frame, ContinuousMotionFrame):
            raise ContinuousMotionAuthorityError("continuous frame type is invalid")
        controls = {
            control
            for control in (frame.movement, frame.strafe)
            if control is not None
        }
        with self._lock:
            now_ms = self._clock.now_ms()
            if self._revoked or not self._authority.active:
                self._session.release_all()
                raise ContinuousMotionAuthorityError(
                    "continuous navigation runtime arm was revoked"
                )
            if now_ms >= self._authority.expires_at_monotonic_ms:
                self._session.release_all()
                raise ContinuousMotionAuthorityError(
                    "continuous navigation runtime arm expired"
                )
            if not controls.issubset(self._authority.allowed_controls):
                self._session.release_all()
                raise ContinuousMotionAuthorityError(
                    "continuous frame asks for a control outside the runtime arm"
                )
            return self._session.apply_frame(frame, cancellation)

    def renew_authority(self, authority: ContinuousMotionAuthority) -> bool:
        """Adopt a newer exact arm without interrupting one continuous hold."""

        if not isinstance(authority, ContinuousMotionAuthority):
            raise ContinuousMotionAuthorityError(
                "renewed continuous navigation authority type is invalid"
            )
        with self._lock:
            stable_binding = (
                authority.binding.actor_id == self._authority.binding.actor_id
                and authority.binding.actor_instance_id == self._authority.binding.actor_instance_id
                and authority.binding.actor_role == self._authority.binding.actor_role
                and authority.binding.decision_context == self._authority.binding.decision_context
                and authority.binding.target_profile == self._authority.binding.target_profile
                and authority.binding.target_instance_id == self._authority.binding.target_instance_id
                and authority.binding.authorization_id == self._authority.binding.authorization_id
                and authority.authorization_id == self._authority.authorization_id
                and (
                    authority.authorization_sha256 == self._authority.authorization_sha256
                    or authority.renewal_parent_sha256
                    == self._authority.authorization_sha256
                )
                and authority.clock_id == self._authority.clock_id
                and authority.allowed_controls == self._authority.allowed_controls
                and authority.lease_timeout_ms == self._authority.lease_timeout_ms
                and authority.active is True
            )
            if not stable_binding:
                raise ContinuousMotionAuthorityError(
                    "renewed continuous navigation authority changes the reviewed binding"
                )
            now_ms = self._clock.now_ms()
            if (
                now_ms < authority.issued_at_monotonic_ms
                or now_ms >= authority.expires_at_monotonic_ms
            ):
                raise ContinuousMotionAuthorityError(
                    "renewed continuous navigation runtime arm is expired or not yet valid"
                )
            renewed = self._session.renew_authority_expiry(
                authority.expires_at_monotonic_ms
            )
            if renewed:
                self._authority = authority
            return renewed

    def release_all(self) -> None:
        self._session.release_all()

    def revoke(self) -> None:
        with self._lock:
            self._revoked = True
            self._session.release_all()

    def close(self) -> None:
        self._session.close()
