from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re
from typing import ClassVar


CONTRACT_VERSION = "1.0"
MOVEMENT_MODE = "MOVEMENT_ONLY"
MOVEMENT_EXECUTION_CAPABILITY = "MOVEMENT_EXECUTION"
POSITION_2D_COMPONENT = "POSITION_2D"
YAW_COMPONENT = "YAW"
ALLOWED_POSE_COMPONENTS = frozenset({POSITION_2D_COMPONENT, YAW_COMPONENT})

MAX_LEASE_DURATION_MS = 60_000
MAX_HOLD_DURATION_MS = 1_000
MIN_EXECUTION_SLACK_MS = 5
MAX_EXECUTION_SLACK_MS = 250
MIN_EXECUTION_ENVELOPE_MS = 1 + MIN_EXECUTION_SLACK_MS
MAX_EXECUTION_ENVELOPE_MS = MAX_HOLD_DURATION_MS + MAX_EXECUTION_SLACK_MS
MAX_PRIMITIVE_LIFETIME_MS = 2_000
MAX_QUEUE_DEPTH = 8
MAX_PRIMITIVES_PER_LEASE = 4_096
MAX_SEQUENCE = 2**63 - 1
ABSOLUTE_MAX_POSITION_RADIUS_95 = 100.0
ABSOLUTE_MAX_YAW_ERROR_95_DEG = 90.0
MAX_POSE_POSITION_RADIUS_95 = 1_000_000.0
MAX_POSE_EVIDENCE_REFS = 64
RESULT_LIFETIME_MS = 30_000
ERROR_TYPE_COOPERATIVE_CANCELLATION = "COOPERATIVE_CANCELLATION"
ERROR_TYPE_SINK_APPLY_FAILURE = "SINK_APPLY_FAILURE"
ERROR_TYPE_SINK_RELEASE_FAILURE = "SINK_RELEASE_FAILURE"

ALLOWED_CONTROLS = frozenset(
    {
        "MOVE_FORWARD",
        "MOVE_BACKWARD",
        "STRAFE_LEFT",
        "STRAFE_RIGHT",
        "TURN_LEFT",
        "TURN_RIGHT",
        "JUMP",
    }
)
ALLOWED_POSE_ORIGINS = frozenset(
    {
        "client_visible_api",
        "addon_observed",
        "window_capture",
        "minimap_vision",
        "scene_vision",
        "optical_flow",
        "dead_reckoning",
        "manual_anchor",
        "fused_client_observations",
        "visible_addon_hud",
        "client_asset_calibration",
        "coordinate_hud_world_map_transform",
    }
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256 = re.compile(r"^[A-Fa-f0-9]{64}$")


def _require_identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} is not a bounded identifier")


def _require_sha256(name: str, value: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a SHA-256 digest")


def _require_monotonic_window(
    *,
    name: str,
    issued_at_monotonic_ms: float,
    expires_at_monotonic_ms: float,
    maximum_ms: int,
) -> None:
    if (
        isinstance(issued_at_monotonic_ms, bool)
        or isinstance(expires_at_monotonic_ms, bool)
        or not isinstance(issued_at_monotonic_ms, (int, float))
        or not isinstance(expires_at_monotonic_ms, (int, float))
        or not isfinite(issued_at_monotonic_ms)
        or not isfinite(expires_at_monotonic_ms)
    ):
        raise ValueError(f"{name} monotonic timestamps must be finite")
    if issued_at_monotonic_ms < 0 or expires_at_monotonic_ms <= 0:
        raise ValueError(f"{name} monotonic timestamps must be non-negative")
    duration = expires_at_monotonic_ms - issued_at_monotonic_ms
    if duration <= 0 or duration > maximum_ms:
        raise ValueError(f"{name} lifetime must be in (0, {maximum_ms}] ms")


def _require_bounded_int(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")


def _require_finite_range(
    name: str, value: float, minimum: float, maximum: float
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{name} must be finite and in [{minimum}, {maximum}]")


def _require_pose_components(
    name: str,
    value: tuple[str, ...],
    *,
    allow_empty: bool,
) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(component, str) for component in value
    ):
        raise ValueError(f"{name} must be an immutable string tuple")
    if (not allow_empty and not value) or len(set(value)) != len(value):
        raise ValueError(f"{name} must be unique and satisfy its cardinality")
    unknown = set(value) - ALLOWED_POSE_COMPONENTS
    if unknown:
        raise ValueError(f"{name} contains unsupported components: {sorted(unknown)}")


@dataclass(frozen=True, slots=True)
class AuthorityBinding:
    """Opaque exact identity pins; authorization_sha256 seals target evidence."""

    actor_id: str
    actor_instance_id: str
    actor_role: str
    decision_context: str
    target_profile: str
    target_instance_id: str
    authorization_id: str
    authorization_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "actor_id",
            "actor_instance_id",
            "target_profile",
            "target_instance_id",
            "authorization_id",
        ):
            _require_identifier(name, getattr(self, name))
        expected_context = {
            "champion_journey": "champion",
            "lab_clone": "lab_clone",
        }.get(self.actor_role)
        if expected_context is None or self.decision_context != expected_context:
            raise ValueError("actor_role and decision_context do not form a valid pair")
        _require_sha256("authorization_sha256", self.authorization_sha256)
        object.__setattr__(
            self, "authorization_sha256", self.authorization_sha256.upper()
        )

    def to_record(self) -> dict[str, str]:
        return {
            "actor_id": self.actor_id,
            "actor_instance_id": self.actor_instance_id,
            "actor_role": self.actor_role,
            "decision_context": self.decision_context,
            "target_profile": self.target_profile,
            "target_instance_id": self.target_instance_id,
            "authorization_id": self.authorization_id,
            "authorization_sha256": self.authorization_sha256.upper(),
        }


@dataclass(frozen=True, slots=True)
class ExecutionLeasePolicy:
    """Immutable authority ceiling for one versioned execution-lease shape.

    A lease may be stricter than this policy, but it may never broaden any
    control, temporal, queue, pose, coordinate-space, or uncertainty bound.
    The object is carried independently by the authorization and runtime arm
    so a caller cannot manufacture authority merely by constructing a lease.
    """

    mode: str
    capability: str
    allowed_controls: tuple[str, ...]
    max_primitives: int
    max_hold_duration_ms: int
    max_execution_envelope_ms: int
    max_queue_depth: int
    min_pose_confidence: float
    required_pose_components: tuple[str, ...]
    position_coordinate_space: str | None
    max_position_radius_95: float | None
    max_yaw_error_95_deg: float | None
    schema_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CONTRACT_VERSION:
            raise ValueError(
                f"Execution lease policy schema_version must be {CONTRACT_VERSION}"
            )
        if self.mode != MOVEMENT_MODE:
            raise ValueError(f"Unsupported execution mode: {self.mode}")
        if self.capability != MOVEMENT_EXECUTION_CAPABILITY:
            raise ValueError(
                f"Unsupported execution capability: {self.capability}"
            )
        if (
            not isinstance(self.allowed_controls, tuple)
            or not 1 <= len(self.allowed_controls) <= len(ALLOWED_CONTROLS)
            or not all(
                isinstance(control, str) for control in self.allowed_controls
            )
            or len(set(self.allowed_controls)) != len(self.allowed_controls)
            or not set(self.allowed_controls) <= ALLOWED_CONTROLS
        ):
            raise ValueError(
                "allowed_controls must be an immutable supported subset"
            )
        _require_bounded_int(
            "max_primitives",
            self.max_primitives,
            1,
            MAX_PRIMITIVES_PER_LEASE,
        )
        _require_bounded_int(
            "max_hold_duration_ms",
            self.max_hold_duration_ms,
            1,
            MAX_HOLD_DURATION_MS,
        )
        _require_bounded_int(
            "max_execution_envelope_ms",
            self.max_execution_envelope_ms,
            MIN_EXECUTION_ENVELOPE_MS,
            MAX_EXECUTION_ENVELOPE_MS,
        )
        _require_bounded_int(
            "max_queue_depth", self.max_queue_depth, 1, MAX_QUEUE_DEPTH
        )
        _require_finite_range(
            "min_pose_confidence", self.min_pose_confidence, 0.0, 1.0
        )
        _require_pose_components(
            "required_pose_components",
            self.required_pose_components,
            allow_empty=True,
        )
        if POSITION_2D_COMPONENT in self.required_pose_components:
            _require_identifier(
                "position_coordinate_space", self.position_coordinate_space
            )
            _require_finite_range(
                "max_position_radius_95",
                self.max_position_radius_95,
                0.0,
                ABSOLUTE_MAX_POSITION_RADIUS_95,
            )
            if self.max_position_radius_95 <= 0:
                raise ValueError(
                    "max_position_radius_95 must be greater than zero"
                )
        elif (
            self.position_coordinate_space is not None
            or self.max_position_radius_95 is not None
        ):
            raise ValueError(
                "Position policy fields require the POSITION_2D component"
            )
        if YAW_COMPONENT in self.required_pose_components:
            _require_finite_range(
                "max_yaw_error_95_deg",
                self.max_yaw_error_95_deg,
                0.0,
                ABSOLUTE_MAX_YAW_ERROR_95_DEG,
            )
            if self.max_yaw_error_95_deg <= 0:
                raise ValueError(
                    "max_yaw_error_95_deg must be greater than zero"
                )
        elif self.max_yaw_error_95_deg is not None:
            raise ValueError("Yaw policy fields require the YAW component")

    def is_effective_subset_of(self, authority: "ExecutionLeasePolicy") -> bool:
        """Return whether this policy is equal to or stricter than authority."""

        if not isinstance(authority, ExecutionLeasePolicy):
            return False
        if (
            self.schema_version != authority.schema_version
            or self.mode != authority.mode
            or self.capability != authority.capability
            or not set(self.allowed_controls) <= set(authority.allowed_controls)
            or self.max_primitives > authority.max_primitives
            or self.max_hold_duration_ms > authority.max_hold_duration_ms
            or self.max_execution_envelope_ms
            > authority.max_execution_envelope_ms
            or self.max_queue_depth > authority.max_queue_depth
            or self.min_pose_confidence < authority.min_pose_confidence
        ):
            return False
        own_components = set(self.required_pose_components)
        authority_components = set(authority.required_pose_components)
        if not own_components >= authority_components:
            return False
        if POSITION_2D_COMPONENT in authority_components and (
            self.position_coordinate_space != authority.position_coordinate_space
            or self.max_position_radius_95 is None
            or authority.max_position_radius_95 is None
            or self.max_position_radius_95 > authority.max_position_radius_95
        ):
            return False
        if YAW_COMPONENT in authority_components and (
            self.max_yaw_error_95_deg is None
            or authority.max_yaw_error_95_deg is None
            or self.max_yaw_error_95_deg > authority.max_yaw_error_95_deg
        ):
            return False
        return True

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "capability": self.capability,
            "allowed_controls": list(self.allowed_controls),
            "max_primitives": self.max_primitives,
            "max_hold_duration_ms": self.max_hold_duration_ms,
            "max_execution_envelope_ms": self.max_execution_envelope_ms,
            "max_queue_depth": self.max_queue_depth,
            "min_pose_confidence": self.min_pose_confidence,
            "required_pose_components": list(self.required_pose_components),
            "position_coordinate_space": self.position_coordinate_space,
            "max_position_radius_95": self.max_position_radius_95,
            "max_yaw_error_95_deg": self.max_yaw_error_95_deg,
        }


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    """Already-verified authorization input to the pure gateway policy gate."""

    binding: AuthorityBinding
    clock_id: str
    issued_at_monotonic_ms: float
    expires_at_monotonic_ms: float
    permitted_modes: frozenset[str]
    permitted_capabilities: frozenset[str]
    lease_policy: ExecutionLeasePolicy
    active: bool = True
    runtime_arm_required: bool = True

    def __post_init__(self) -> None:
        _require_identifier("clock_id", self.clock_id)
        _require_monotonic_window(
            name="authorization",
            issued_at_monotonic_ms=self.issued_at_monotonic_ms,
            expires_at_monotonic_ms=self.expires_at_monotonic_ms,
            maximum_ms=MAX_LEASE_DURATION_MS,
        )
        if not isinstance(self.active, bool):
            raise ValueError("active must be boolean")
        if self.runtime_arm_required is not True:
            raise ValueError("Execution authorization must require a runtime arm")
        if not isinstance(self.permitted_modes, frozenset) or not all(
            isinstance(value, str) for value in self.permitted_modes
        ):
            raise ValueError("permitted_modes must be an immutable string set")
        if not isinstance(self.permitted_capabilities, frozenset) or not all(
            isinstance(value, str) for value in self.permitted_capabilities
        ):
            raise ValueError(
                "permitted_capabilities must be an immutable string set"
            )
        if not isinstance(self.lease_policy, ExecutionLeasePolicy):
            raise ValueError("authorization lease_policy must be versioned")


@dataclass(frozen=True, slots=True)
class RuntimeArmSnapshot:
    """Current arm state supplied by a revocable, in-memory provider."""

    binding: AuthorityBinding
    arm_nonce: str
    clock_id: str
    issued_at_monotonic_ms: float
    expires_at_monotonic_ms: float
    allowed_modes: frozenset[str]
    allowed_capabilities: frozenset[str]
    lease_policy: ExecutionLeasePolicy
    active: bool

    def __post_init__(self) -> None:
        _require_identifier("arm_nonce", self.arm_nonce)
        _require_identifier("clock_id", self.clock_id)
        _require_monotonic_window(
            name="runtime arm",
            issued_at_monotonic_ms=self.issued_at_monotonic_ms,
            expires_at_monotonic_ms=self.expires_at_monotonic_ms,
            maximum_ms=MAX_LEASE_DURATION_MS,
        )
        if not isinstance(self.active, bool):
            raise ValueError("active must be boolean")
        if not isinstance(self.allowed_modes, frozenset) or not all(
            isinstance(value, str) for value in self.allowed_modes
        ):
            raise ValueError("allowed_modes must be an immutable string set")
        if not isinstance(self.allowed_capabilities, frozenset) or not all(
            isinstance(value, str) for value in self.allowed_capabilities
        ):
            raise ValueError("allowed_capabilities must be an immutable string set")
        if not isinstance(self.lease_policy, ExecutionLeasePolicy):
            raise ValueError("runtime-arm lease_policy must be versioned")


@dataclass(frozen=True, slots=True)
class ExecutionLease:
    record_type: ClassVar[str] = "execution_lease"
    schema_version: ClassVar[str] = CONTRACT_VERSION

    lease_id: str
    binding: AuthorityBinding
    owner_id: str
    runtime_arm_nonce: str
    mode: str
    capability: str
    clock_id: str
    issued_at_monotonic_ms: float
    expires_at_monotonic_ms: float
    first_sequence: int
    max_hold_duration_ms: int
    max_execution_envelope_ms: int
    max_queue_depth: int
    min_pose_confidence: float
    required_pose_components: tuple[str, ...]
    position_coordinate_space: str | None
    max_position_radius_95: float | None
    max_yaw_error_95_deg: float | None
    allowed_controls: tuple[str, ...] = tuple(sorted(ALLOWED_CONTROLS))
    max_primitives: int = MAX_PRIMITIVES_PER_LEASE

    def __post_init__(self) -> None:
        for name in ("lease_id", "owner_id", "runtime_arm_nonce", "clock_id"):
            _require_identifier(name, getattr(self, name))
        if self.mode != MOVEMENT_MODE:
            raise ValueError(f"Unsupported execution mode: {self.mode}")
        if self.capability != MOVEMENT_EXECUTION_CAPABILITY:
            raise ValueError(f"Unsupported execution capability: {self.capability}")
        _require_monotonic_window(
            name="execution lease",
            issued_at_monotonic_ms=self.issued_at_monotonic_ms,
            expires_at_monotonic_ms=self.expires_at_monotonic_ms,
            maximum_ms=MAX_LEASE_DURATION_MS,
        )
        _require_bounded_int("first_sequence", self.first_sequence, 1, MAX_SEQUENCE)
        _require_bounded_int(
            "max_hold_duration_ms",
            self.max_hold_duration_ms,
            1,
            MAX_HOLD_DURATION_MS,
        )
        _require_bounded_int(
            "max_execution_envelope_ms",
            self.max_execution_envelope_ms,
            MIN_EXECUTION_ENVELOPE_MS,
            MAX_EXECUTION_ENVELOPE_MS,
        )
        _require_bounded_int(
            "max_queue_depth", self.max_queue_depth, 1, MAX_QUEUE_DEPTH
        )
        if (
            not isinstance(self.allowed_controls, tuple)
            or not 1 <= len(self.allowed_controls) <= len(ALLOWED_CONTROLS)
            or not all(isinstance(control, str) for control in self.allowed_controls)
            or len(set(self.allowed_controls)) != len(self.allowed_controls)
            or not set(self.allowed_controls) <= ALLOWED_CONTROLS
        ):
            raise ValueError("allowed_controls must be an immutable supported subset")
        _require_bounded_int(
            "max_primitives",
            self.max_primitives,
            1,
            MAX_PRIMITIVES_PER_LEASE,
        )
        _require_finite_range("min_pose_confidence", self.min_pose_confidence, 0.0, 1.0)
        if self.min_pose_confidence <= 0:
            raise ValueError("min_pose_confidence must be greater than zero")
        _require_pose_components(
            "required_pose_components",
            self.required_pose_components,
            allow_empty=False,
        )
        if POSITION_2D_COMPONENT in self.required_pose_components:
            _require_identifier(
                "position_coordinate_space", self.position_coordinate_space
            )
            _require_finite_range(
                "max_position_radius_95",
                self.max_position_radius_95,
                0.0,
                ABSOLUTE_MAX_POSITION_RADIUS_95,
            )
            if self.max_position_radius_95 <= 0:
                raise ValueError("max_position_radius_95 must be greater than zero")
        elif (
            self.position_coordinate_space is not None
            or self.max_position_radius_95 is not None
        ):
            raise ValueError(
                "Position lease fields require the POSITION_2D component"
            )
        if YAW_COMPONENT in self.required_pose_components:
            _require_finite_range(
                "max_yaw_error_95_deg",
                self.max_yaw_error_95_deg,
                0.0,
                ABSOLUTE_MAX_YAW_ERROR_95_DEG,
            )
            if self.max_yaw_error_95_deg <= 0:
                raise ValueError("max_yaw_error_95_deg must be greater than zero")
        elif self.max_yaw_error_95_deg is not None:
            raise ValueError("Yaw lease fields require the YAW component")

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "lease_id": self.lease_id,
            "binding": self.binding.to_record(),
            "owner_id": self.owner_id,
            "runtime_arm_nonce": self.runtime_arm_nonce,
            "mode": self.mode,
            "capability": self.capability,
            "clock_id": self.clock_id,
            "issued_at_monotonic_ms": self.issued_at_monotonic_ms,
            "expires_at_monotonic_ms": self.expires_at_monotonic_ms,
            "first_sequence": self.first_sequence,
            "max_hold_duration_ms": self.max_hold_duration_ms,
            "max_execution_envelope_ms": self.max_execution_envelope_ms,
            "max_queue_depth": self.max_queue_depth,
            "allowed_controls": list(self.allowed_controls),
            "max_primitives": self.max_primitives,
            "min_pose_confidence": self.min_pose_confidence,
            "required_pose_components": list(self.required_pose_components),
            "position_coordinate_space": self.position_coordinate_space,
            "max_position_radius_95": self.max_position_radius_95,
            "max_yaw_error_95_deg": self.max_yaw_error_95_deg,
            "execution_authority": True,
        }
        validate_execution_record_semantics(record)
        return record

    def execution_policy(self) -> ExecutionLeasePolicy:
        """Project the complete immutable policy enforced by this lease."""

        return ExecutionLeasePolicy(
            mode=self.mode,
            capability=self.capability,
            allowed_controls=self.allowed_controls,
            max_primitives=self.max_primitives,
            max_hold_duration_ms=self.max_hold_duration_ms,
            max_execution_envelope_ms=self.max_execution_envelope_ms,
            max_queue_depth=self.max_queue_depth,
            min_pose_confidence=self.min_pose_confidence,
            required_pose_components=self.required_pose_components,
            position_coordinate_space=self.position_coordinate_space,
            max_position_radius_95=self.max_position_radius_95,
            max_yaw_error_95_deg=self.max_yaw_error_95_deg,
        )


@dataclass(frozen=True, slots=True)
class MovementPrimitive:
    record_type: ClassVar[str] = "movement_primitive"
    schema_version: ClassVar[str] = CONTRACT_VERSION

    primitive_id: str
    lease_id: str
    binding: AuthorityBinding
    owner_id: str
    runtime_arm_nonce: str
    mode: str
    capability: str
    sequence: int
    controls: tuple[str, ...]
    hold_duration_ms: int
    max_execution_envelope_ms: int
    clock_id: str
    issued_at_monotonic_ms: float
    expires_at_monotonic_ms: float

    def __post_init__(self) -> None:
        for name in (
            "primitive_id",
            "lease_id",
            "owner_id",
            "runtime_arm_nonce",
            "clock_id",
        ):
            _require_identifier(name, getattr(self, name))
        if self.mode != MOVEMENT_MODE:
            raise ValueError(f"Unsupported execution mode: {self.mode}")
        if self.capability != MOVEMENT_EXECUTION_CAPABILITY:
            raise ValueError(f"Unsupported execution capability: {self.capability}")
        _require_bounded_int("sequence", self.sequence, 1, MAX_SEQUENCE)
        if not isinstance(self.controls, tuple):
            raise ValueError("controls must be an immutable tuple")
        if not all(isinstance(control, str) for control in self.controls):
            raise ValueError("controls must contain only strings")
        if not 1 <= len(self.controls) <= 3:
            raise ValueError("controls must contain between one and three controls")
        if len(set(self.controls)) != len(self.controls):
            raise ValueError("controls must be unique")
        unknown = set(self.controls) - ALLOWED_CONTROLS
        if unknown:
            raise ValueError(f"Unsupported controls: {sorted(unknown)}")
        contradictory_pairs = (
            {"MOVE_FORWARD", "MOVE_BACKWARD"},
            {"STRAFE_LEFT", "STRAFE_RIGHT"},
            {"TURN_LEFT", "TURN_RIGHT"},
        )
        if any(pair <= set(self.controls) for pair in contradictory_pairs):
            raise ValueError("controls contain a contradictory pair")
        _require_bounded_int(
            "hold_duration_ms",
            self.hold_duration_ms,
            1,
            MAX_HOLD_DURATION_MS,
        )
        _require_bounded_int(
            "max_execution_envelope_ms",
            self.max_execution_envelope_ms,
            MIN_EXECUTION_ENVELOPE_MS,
            MAX_EXECUTION_ENVELOPE_MS,
        )
        execution_slack = self.max_execution_envelope_ms - self.hold_duration_ms
        if execution_slack < MIN_EXECUTION_SLACK_MS:
            raise ValueError("Execution envelope has insufficient release slack")
        if execution_slack > MAX_EXECUTION_SLACK_MS:
            raise ValueError("Execution envelope slack exceeds the absolute bound")
        _require_monotonic_window(
            name="movement primitive",
            issued_at_monotonic_ms=self.issued_at_monotonic_ms,
            expires_at_monotonic_ms=self.expires_at_monotonic_ms,
            maximum_ms=MAX_PRIMITIVE_LIFETIME_MS,
        )
        if (
            self.issued_at_monotonic_ms + self.max_execution_envelope_ms
            > self.expires_at_monotonic_ms
        ):
            raise ValueError("Movement primitive execution envelope outlives its record")

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "primitive_id": self.primitive_id,
            "lease_id": self.lease_id,
            "binding": self.binding.to_record(),
            "owner_id": self.owner_id,
            "runtime_arm_nonce": self.runtime_arm_nonce,
            "mode": self.mode,
            "capability": self.capability,
            "sequence": self.sequence,
            "controls": list(self.controls),
            "hold_duration_ms": self.hold_duration_ms,
            "max_execution_envelope_ms": self.max_execution_envelope_ms,
            "clock_id": self.clock_id,
            "issued_at_monotonic_ms": self.issued_at_monotonic_ms,
            "expires_at_monotonic_ms": self.expires_at_monotonic_ms,
            "execution_authority": False,
        }
        validate_execution_record_semantics(record)
        return record


@dataclass(frozen=True, slots=True)
class ExecutionPoseState:
    record_type: ClassVar[str] = "execution_pose_state"
    schema_version: ClassVar[str] = CONTRACT_VERSION

    pose_id: str
    actor_id: str
    actor_instance_id: str
    actor_role: str
    decision_context: str
    target_profile: str
    target_instance_id: str
    authorization_id: str
    authorization_sha256: str
    state: str
    source_scope: str
    source_id: str
    capability: str
    source_origins: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    confidence: float
    freshness_status: str
    available_pose_components: tuple[str, ...]
    position_coordinate_space: str | None
    position_radius_95: float | None
    yaw_error_95_deg: float | None
    clock_id: str
    observed_at_monotonic_ms: float
    expires_at_monotonic_ms: float

    def __post_init__(self) -> None:
        for name in (
            "pose_id",
            "actor_id",
            "actor_instance_id",
            "source_id",
            "capability",
            "target_profile",
            "target_instance_id",
            "authorization_id",
            "clock_id",
        ):
            _require_identifier(name, getattr(self, name))
        if self.state not in {"VALID", "DEGRADED", "LOST"}:
            raise ValueError(f"Unsupported pose execution state: {self.state}")
        expected_context = {
            "champion_journey": "champion",
            "lab_clone": "lab_clone",
        }.get(self.actor_role)
        if expected_context is None or self.decision_context != expected_context:
            raise ValueError("pose actor_role and decision_context do not match")
        _require_sha256("authorization_sha256", self.authorization_sha256)
        object.__setattr__(
            self, "authorization_sha256", self.authorization_sha256.upper()
        )
        expected_scope = (
            "lab_evaluation_only"
            if self.decision_context == "lab_clone"
            else "champion_eligible"
        )
        if self.source_scope != expected_scope:
            raise ValueError("pose source scope cannot cross decision contexts")
        if not isinstance(self.source_origins, tuple):
            raise ValueError("source_origins must be an immutable tuple")
        if not all(isinstance(origin, str) for origin in self.source_origins):
            raise ValueError("source_origins must contain only strings")
        if not self.source_origins or len(set(self.source_origins)) != len(
            self.source_origins
        ):
            raise ValueError("source_origins must be non-empty and unique")
        if not set(self.source_origins) <= ALLOWED_POSE_ORIGINS:
            raise ValueError("Execution pose contains a non-client fact origin")
        if not isinstance(self.evidence_refs, tuple):
            raise ValueError("evidence_refs must be an immutable tuple")
        if not all(isinstance(item, str) for item in self.evidence_refs):
            raise ValueError("evidence_refs must contain only strings")
        if not self.evidence_refs or len(set(self.evidence_refs)) != len(
            self.evidence_refs
        ):
            raise ValueError("evidence_refs must be non-empty and unique")
        if len(self.evidence_refs) > MAX_POSE_EVIDENCE_REFS:
            raise ValueError(
                f"evidence_refs cannot exceed {MAX_POSE_EVIDENCE_REFS} entries"
            )
        for evidence_ref in self.evidence_refs:
            _require_identifier("evidence_ref", evidence_ref)
        _require_finite_range("confidence", self.confidence, 0.0, 1.0)
        _require_pose_components(
            "available_pose_components",
            self.available_pose_components,
            allow_empty=True,
        )
        if POSITION_2D_COMPONENT in self.available_pose_components:
            _require_identifier(
                "position_coordinate_space", self.position_coordinate_space
            )
            _require_finite_range(
                "position_radius_95",
                self.position_radius_95,
                0.0,
                MAX_POSE_POSITION_RADIUS_95,
            )
        elif (
            self.position_coordinate_space is not None
            or self.position_radius_95 is not None
        ):
            raise ValueError(
                "Position pose fields require the POSITION_2D component"
            )
        if YAW_COMPONENT in self.available_pose_components:
            _require_finite_range(
                "yaw_error_95_deg", self.yaw_error_95_deg, 0.0, 180.0
            )
        elif self.yaw_error_95_deg is not None:
            raise ValueError("Yaw pose fields require the YAW component")
        if self.freshness_status not in {"FRESH", "STALE", "EXPIRED"}:
            raise ValueError("Unsupported freshness_status")
        _require_monotonic_window(
            name="execution pose",
            issued_at_monotonic_ms=self.observed_at_monotonic_ms,
            expires_at_monotonic_ms=self.expires_at_monotonic_ms,
            maximum_ms=MAX_PRIMITIVE_LIFETIME_MS,
        )

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "pose_id": self.pose_id,
            "actor_id": self.actor_id,
            "actor_instance_id": self.actor_instance_id,
            "actor_role": self.actor_role,
            "decision_context": self.decision_context,
            "target_profile": self.target_profile,
            "target_instance_id": self.target_instance_id,
            "authorization_id": self.authorization_id,
            "authorization_sha256": self.authorization_sha256.upper(),
            "state": self.state,
            "source_scope": self.source_scope,
            "source_id": self.source_id,
            "capability": self.capability,
            "source_origins": list(self.source_origins),
            "evidence_refs": list(self.evidence_refs),
            "confidence": self.confidence,
            "freshness_status": self.freshness_status,
            "available_pose_components": list(self.available_pose_components),
            "position_coordinate_space": self.position_coordinate_space,
            "position_radius_95": self.position_radius_95,
            "yaw_error_95_deg": self.yaw_error_95_deg,
            "clock_id": self.clock_id,
            "observed_at_monotonic_ms": self.observed_at_monotonic_ms,
            "expires_at_monotonic_ms": self.expires_at_monotonic_ms,
            "execution_authority": False,
        }
        validate_execution_record_semantics(record)
        return record


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    record_type: ClassVar[str] = "execution_result"
    schema_version: ClassVar[str] = CONTRACT_VERSION

    result_id: str
    primitive_id: str
    lease_id: str
    binding: AuthorityBinding
    owner_id: str
    sequence: int
    status: str
    reason_code: str
    clock_id: str
    completed_at_monotonic_ms: float
    expires_at_monotonic_ms: float
    sink_release_attempted: bool
    sink_release_succeeded: bool
    error_type: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "result_id",
            "primitive_id",
            "lease_id",
            "owner_id",
            "clock_id",
        ):
            _require_identifier(name, getattr(self, name))
        _require_bounded_int("sequence", self.sequence, 1, MAX_SEQUENCE)
        if self.status not in {"EXECUTED", "REJECTED", "FAILED", "CANCELLED"}:
            raise ValueError(f"Unsupported execution result status: {self.status}")
        _require_identifier("reason_code", self.reason_code)
        _require_monotonic_window(
            name="execution result",
            issued_at_monotonic_ms=self.completed_at_monotonic_ms,
            expires_at_monotonic_ms=self.expires_at_monotonic_ms,
            maximum_ms=RESULT_LIFETIME_MS,
        )
        if self.error_type is not None:
            _require_identifier("error_type", self.error_type)
        if self.sink_release_attempted is not True:
            raise ValueError("sink_release_attempted must be true")
        if not isinstance(self.sink_release_succeeded, bool):
            raise ValueError("sink_release_succeeded must be boolean")
        allowed_reasons = _RESULT_REASONS_BY_STATUS.get(self.status, frozenset())
        if self.reason_code not in allowed_reasons:
            raise ValueError("Execution result status and reason_code contradict")
        if self.error_type is not None and self.error_type not in _ALLOWED_ERROR_TYPES:
            raise ValueError("Execution result contains an unsupported error_type")
        if self.status == "EXECUTED" and (
            not self.sink_release_succeeded or self.error_type is not None
        ):
            raise ValueError("Executed result must have a clean release")
        if not self.sink_release_succeeded and (
            self.status != "FAILED"
            or self.reason_code != "RELEASE_ALL_EXCEPTION"
            or self.error_type != ERROR_TYPE_SINK_RELEASE_FAILURE
        ):
            raise ValueError("Failed release must be an explicit failed result")
        if self.reason_code == "SINK_EXCEPTION" and (
            self.error_type != ERROR_TYPE_SINK_APPLY_FAILURE
        ):
            raise ValueError("Sink exception result requires the normalized apply error")
        if self.error_type == ERROR_TYPE_SINK_RELEASE_FAILURE and (
            self.reason_code != "RELEASE_ALL_EXCEPTION"
        ):
            raise ValueError("Release error type requires a release failure result")
        if self.error_type == ERROR_TYPE_SINK_APPLY_FAILURE and (
            self.reason_code != "SINK_EXCEPTION"
        ):
            raise ValueError("Apply error type requires a sink exception result")
        if self.error_type == ERROR_TYPE_COOPERATIVE_CANCELLATION and (
            self.reason_code
            not in {"MANUAL_TAKEOVER", "GATEWAY_CLOSED", "RUNTIME_ARM_INACTIVE"}
        ):
            raise ValueError("Cancellation error type requires a cancellation reason")
        if self.reason_code == "RELEASE_ALL_EXCEPTION" and (
            self.sink_release_succeeded is not False
            or self.error_type != ERROR_TYPE_SINK_RELEASE_FAILURE
        ):
            raise ValueError("Release failure result contradicts release outcome")

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "primitive_id": self.primitive_id,
            "lease_id": self.lease_id,
            "binding": self.binding.to_record(),
            "owner_id": self.owner_id,
            "sequence": self.sequence,
            "status": self.status,
            "reason_code": self.reason_code,
            "clock_id": self.clock_id,
            "completed_at_monotonic_ms": self.completed_at_monotonic_ms,
            "expires_at_monotonic_ms": self.expires_at_monotonic_ms,
            "sink_release_attempted": self.sink_release_attempted,
            "sink_release_succeeded": self.sink_release_succeeded,
            "execution_authority": False,
        }
        if self.error_type is not None:
            record["error_type"] = self.error_type
        validate_execution_record_semantics(record)
        return record


_RESULT_REASONS_BY_STATUS = {
    "EXECUTED": frozenset({"EXECUTED"}),
    "CANCELLED": frozenset({"MANUAL_TAKEOVER", "GATEWAY_CLOSED"}),
    "FAILED": frozenset(
        {
            "CLOCK_INVALID",
            "INTERNAL_EMPTY_QUEUE",
            "RELEASE_ALL_EXCEPTION",
            "RUNTIME_ARM_PROVIDER_EXCEPTION",
            "SINK_EXCEPTION",
            "TEMPORAL_OVERRUN",
        }
    ),
    "REJECTED": frozenset(
        {
            "AUTHORIZATION_EXPIRED",
            "AUTHORIZATION_INACTIVE",
            "AUTHORIZATION_NOT_YET_VALID",
            "CAPABILITY_DENIED",
            "CLOCK_INVALID",
            "CLOCK_MISMATCH",
            "CONTROL_DENIED",
            "DURATION_DENIED",
            "GATEWAY_FAULTED",
            "LEASE_BINDING_MISMATCH",
            "LEASE_EXPIRED",
            "LEASE_NOT_YET_VALID",
            "LEASE_POLICY_DENIED",
            "MODE_DENIED",
            "OWNER_MISMATCH",
            "POSE_BINDING_MISMATCH",
            "POSE_COMPONENTS_MISSING",
            "POSE_CONFIDENCE_BELOW_MINIMUM",
            "POSE_COORDINATE_SPACE_MISMATCH",
            "POSE_EXPIRED",
            "POSE_NOT_VALID",
            "POSE_SCOPE_MISMATCH",
            "POSE_UNCERTAINTY_EXCEEDED",
            "PRIMITIVE_BINDING_MISMATCH",
            "PRIMITIVE_BUDGET_EXHAUSTED",
            "PRIMITIVE_EXPIRED",
            "PRIMITIVE_LEASE_MISMATCH",
            "PRIMITIVE_NOT_YET_VALID",
            "PRIMITIVE_OUTLIVES_LEASE",
            "PRIMITIVE_REPLAY",
            "QUEUE_FULL",
            "RUNTIME_ARM_EXPIRED",
            "RUNTIME_ARM_INACTIVE",
            "RUNTIME_ARM_MISMATCH",
            "RUNTIME_ARM_POLICY_MISMATCH",
            "SEQUENCE_GAP",
            "SEQUENCE_REPLAY",
            "SINK_SAFETY_CONTRACT_DENIED",
            "TEMPORAL_BUDGET_INSUFFICIENT",
        }
    ),
}
_ALLOWED_ERROR_TYPES = frozenset(
    {
        ERROR_TYPE_COOPERATIVE_CANCELLATION,
        ERROR_TYPE_SINK_APPLY_FAILURE,
        ERROR_TYPE_SINK_RELEASE_FAILURE,
    }
)


def _semantic_number(record: dict[str, object], name: str) -> float:
    value = record.get(name)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _semantic_int(
    record: dict[str, object], name: str, minimum: int, maximum: int
) -> int:
    value = record.get(name)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _semantic_bounded_number(
    record: dict[str, object], name: str, minimum: float, maximum: float
) -> float:
    value = _semantic_number(record, name)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return value


def _semantic_pose_components(
    record: dict[str, object],
    name: str,
    *,
    allow_empty: bool,
) -> frozenset[str]:
    value = record.get(name)
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or not all(isinstance(component, str) for component in value)
        or len(set(value)) != len(value)
        or not set(value) <= ALLOWED_POSE_COMPONENTS
    ):
        raise ValueError(f"{name} must be a bounded unique pose-component array")
    return frozenset(value)


def _semantic_optional_bounded_number(
    record: dict[str, object],
    name: str,
    minimum: float,
    maximum: float,
) -> float | None:
    if name not in record:
        raise ValueError(f"{name} is required and must be explicit")
    if record.get(name) is None:
        return None
    return _semantic_bounded_number(record, name, minimum, maximum)


def _semantic_optional_identifier(
    record: dict[str, object], name: str
) -> str | None:
    if name not in record:
        raise ValueError(f"{name} is required and must be explicit")
    value = record.get(name)
    if value is None:
        return None
    _require_identifier(name, value)
    return value


def _semantic_window(
    record: dict[str, object],
    start_name: str,
    end_name: str,
    maximum_ms: float,
) -> tuple[float, float]:
    start = _semantic_number(record, start_name)
    end = _semantic_number(record, end_name)
    if start < 0 or end <= start or end - start > maximum_ms:
        raise ValueError(f"{start_name}/{end_name} form an invalid lifetime")
    return start, end


def validate_execution_record_semantics(record: dict[str, object]) -> None:
    """Mandatory cross-field validation complementing the JSON schema.

    JSON Schema validates raw shape. This function rejects relationships that
    Draft 2020-12 cannot compare, and must run before a raw record is trusted.
    Every local ``to_record`` path invokes it automatically.
    """

    if not isinstance(record, dict):
        raise ValueError("Execution record must be an object")
    if record.get("schema_version") != CONTRACT_VERSION:
        raise ValueError(
            f"Execution record schema_version must be {CONTRACT_VERSION}"
        )
    record_type = record.get("record_type")
    if record_type == "execution_lease":
        _semantic_window(
            record,
            "issued_at_monotonic_ms",
            "expires_at_monotonic_ms",
            MAX_LEASE_DURATION_MS,
        )
        _semantic_int(record, "first_sequence", 1, MAX_SEQUENCE)
        _semantic_int(
            record, "max_hold_duration_ms", 1, MAX_HOLD_DURATION_MS
        )
        _semantic_int(
            record,
            "max_execution_envelope_ms",
            MIN_EXECUTION_ENVELOPE_MS,
            MAX_EXECUTION_ENVELOPE_MS,
        )
        controls = record.get("allowed_controls")
        if (
            not isinstance(controls, list)
            or not 1 <= len(controls) <= len(ALLOWED_CONTROLS)
            or not all(isinstance(control, str) for control in controls)
            or len(set(controls)) != len(controls)
            or not set(controls) <= ALLOWED_CONTROLS
        ):
            raise ValueError("allowed_controls must be a bounded supported subset")
        _semantic_int(
            record,
            "max_primitives",
            1,
            MAX_PRIMITIVES_PER_LEASE,
        )
        _semantic_bounded_number(record, "min_pose_confidence", 0.0, 1.0)
        required_components = _semantic_pose_components(
            record,
            "required_pose_components",
            allow_empty=False,
        )
        position_coordinate_space = _semantic_optional_identifier(
            record, "position_coordinate_space"
        )
        max_position_radius = _semantic_optional_bounded_number(
            record,
            "max_position_radius_95",
            0.0,
            ABSOLUTE_MAX_POSITION_RADIUS_95,
        )
        max_yaw_error = _semantic_optional_bounded_number(
            record,
            "max_yaw_error_95_deg",
            0.0,
            ABSOLUTE_MAX_YAW_ERROR_95_DEG,
        )
        if POSITION_2D_COMPONENT in required_components:
            if position_coordinate_space is None or max_position_radius is None:
                raise ValueError(
                    "POSITION_2D lease requires coordinate space and uncertainty"
                )
            if max_position_radius <= 0:
                raise ValueError(
                    "max_position_radius_95 must be greater than zero"
                )
        elif position_coordinate_space is not None or max_position_radius is not None:
            raise ValueError(
                "Position lease fields require the POSITION_2D component"
            )
        if YAW_COMPONENT in required_components:
            if max_yaw_error is None or max_yaw_error <= 0:
                raise ValueError(
                    "YAW lease requires a positive uncertainty threshold"
                )
        elif max_yaw_error is not None:
            raise ValueError("Yaw lease fields require the YAW component")
        return
    if record_type == "movement_primitive":
        issued, expires = _semantic_window(
            record,
            "issued_at_monotonic_ms",
            "expires_at_monotonic_ms",
            MAX_PRIMITIVE_LIFETIME_MS,
        )
        _semantic_int(record, "sequence", 1, MAX_SEQUENCE)
        hold_duration = _semantic_int(
            record, "hold_duration_ms", 1, MAX_HOLD_DURATION_MS
        )
        envelope = _semantic_int(
            record,
            "max_execution_envelope_ms",
            MIN_EXECUTION_ENVELOPE_MS,
            MAX_EXECUTION_ENVELOPE_MS,
        )
        execution_slack = envelope - hold_duration
        if execution_slack < MIN_EXECUTION_SLACK_MS:
            raise ValueError("Execution envelope has insufficient release slack")
        if execution_slack > MAX_EXECUTION_SLACK_MS:
            raise ValueError("Execution envelope slack exceeds the absolute bound")
        if issued + envelope > expires:
            raise ValueError("Movement primitive execution envelope outlives its record")
        controls = record.get("controls")
        if not isinstance(controls, list) or not all(
            isinstance(control, str) for control in controls
        ):
            raise ValueError("controls must be a string array")
        control_set = set(controls)
        for pair in (
            {"MOVE_FORWARD", "MOVE_BACKWARD"},
            {"STRAFE_LEFT", "STRAFE_RIGHT"},
            {"TURN_LEFT", "TURN_RIGHT"},
        ):
            if pair <= control_set:
                raise ValueError("Movement primitive controls are contradictory")
        return
    if record_type == "execution_pose_state":
        _semantic_window(
            record,
            "observed_at_monotonic_ms",
            "expires_at_monotonic_ms",
            MAX_PRIMITIVE_LIFETIME_MS,
        )
        _semantic_bounded_number(record, "confidence", 0.0, 1.0)
        available_components = _semantic_pose_components(
            record,
            "available_pose_components",
            allow_empty=True,
        )
        position_coordinate_space = _semantic_optional_identifier(
            record, "position_coordinate_space"
        )
        position_radius = _semantic_optional_bounded_number(
            record,
            "position_radius_95",
            0.0,
            MAX_POSE_POSITION_RADIUS_95,
        )
        yaw_error = _semantic_optional_bounded_number(
            record, "yaw_error_95_deg", 0.0, 180.0
        )
        if POSITION_2D_COMPONENT in available_components:
            if position_coordinate_space is None or position_radius is None:
                raise ValueError(
                    "Available POSITION_2D requires coordinate space and uncertainty"
                )
        elif position_coordinate_space is not None or position_radius is not None:
            raise ValueError(
                "Position pose fields require the POSITION_2D component"
            )
        if YAW_COMPONENT in available_components:
            if yaw_error is None:
                raise ValueError("Available YAW requires uncertainty")
        elif yaw_error is not None:
            raise ValueError("Yaw pose fields require the YAW component")
        evidence_refs = record.get("evidence_refs")
        if (
            not isinstance(evidence_refs, list)
            or not evidence_refs
            or len(evidence_refs) > MAX_POSE_EVIDENCE_REFS
            or not all(isinstance(item, str) for item in evidence_refs)
            or len(set(evidence_refs)) != len(evidence_refs)
        ):
            raise ValueError("evidence_refs must be a bounded unique string array")
        return
    if record_type == "execution_result":
        _semantic_window(
            record,
            "completed_at_monotonic_ms",
            "expires_at_monotonic_ms",
            RESULT_LIFETIME_MS,
        )
        _semantic_int(record, "sequence", 1, MAX_SEQUENCE)
        status = record.get("status")
        reason = record.get("reason_code")
        if not isinstance(status, str) or reason not in _RESULT_REASONS_BY_STATUS.get(
            status, frozenset()
        ):
            raise ValueError("Execution result status and reason_code contradict")
        release_attempted = record.get("sink_release_attempted")
        release_succeeded = record.get("sink_release_succeeded")
        if release_attempted is not True or not isinstance(release_succeeded, bool):
            raise ValueError("Execution result has an invalid release outcome")
        error_type = record.get("error_type")
        if error_type is not None and error_type not in _ALLOWED_ERROR_TYPES:
            raise ValueError("Execution result contains an unsupported error_type")
        if status == "EXECUTED" and (
            release_succeeded is not True or error_type is not None
        ):
            raise ValueError("Executed result must have a clean release")
        if release_succeeded is False and (
            status != "FAILED"
            or reason != "RELEASE_ALL_EXCEPTION"
            or error_type is None
        ):
            raise ValueError("Failed release must be an explicit failed result")
        if reason == "RELEASE_ALL_EXCEPTION" and (
            release_succeeded is not False
            or error_type != ERROR_TYPE_SINK_RELEASE_FAILURE
        ):
            raise ValueError("Release failure result contradicts release outcome")
        if reason == "SINK_EXCEPTION" and error_type != ERROR_TYPE_SINK_APPLY_FAILURE:
            raise ValueError("Sink exception result requires the normalized apply error")
        if error_type == ERROR_TYPE_SINK_RELEASE_FAILURE and reason != "RELEASE_ALL_EXCEPTION":
            raise ValueError("Release error type requires a release failure result")
        if error_type == ERROR_TYPE_SINK_APPLY_FAILURE and reason != "SINK_EXCEPTION":
            raise ValueError("Apply error type requires a sink exception result")
        if error_type == ERROR_TYPE_COOPERATIVE_CANCELLATION and reason not in {
            "MANUAL_TAKEOVER",
            "GATEWAY_CLOSED",
            "RUNTIME_ARM_INACTIVE",
        }:
            raise ValueError("Cancellation error type requires a cancellation reason")
        return
    raise ValueError(f"Unsupported execution record type: {record_type!r}")
