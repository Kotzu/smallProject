from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from math import isclose, isfinite
import re
import struct
from typing import Any, ClassVar, Mapping, Sequence


CONTRACT_VERSION = "1.0"
PGEOM_FORMAT_VERSION = 1
PNAV_FORMAT_VERSION = 1
DEBUG_SNAPSHOT_FORMAT_VERSION = 1
PINNED_RECAST_COMMIT = "9f4ce64458dfae86e1239c525ddc219c4e9e06f1"
HASH_WIRE_FORMAT = "pa-nav-wire-v1"

MAX_EVIDENCE_REFS = 64
MAX_BINDING_EVIDENCE_REFS = 4
MAX_SOURCE_ASSET_REFS = 256
MAX_GEOMETRY_TILES = 4_096
MAX_VERTICES_PER_GEOMETRY_TILE = 262_144
MAX_TRIANGLES_PER_GEOMETRY_TILE = 524_288
MAX_NAVIGATION_TILES = 4_096
MAX_NAVIGATION_TILE_BYTES = 16 * 1024 * 1024
MAX_NAVIGATION_TOTAL_BYTES = 512 * 1024 * 1024
MAX_DEBUG_TILE_HASHES = 1_024
MAX_DEBUG_ROUTE_POINTS = 4_096
MAX_DEBUG_POLYGONS = 16_384
MAX_DEBUG_POLYGON_VERTICES = 12
MAX_DEBUG_FLAGS = 16
MAX_NAVIGATION_RECORD_BYTES = 64 * 1024 * 1024
MAX_NAVIGATION_JSON_NODES = 2_000_000
MAX_NAVIGATION_STRING_BYTES = 16 * 1024 * 1024
MAX_NAVIGATION_NESTING_DEPTH = 32
MAX_GEOMETRY_TOTAL_VERTICES = 1_000_000
MAX_GEOMETRY_TOTAL_TRIANGLES = 2_000_000
MAX_GEOMETRY_TOTAL_SOURCE_ASSET_REFS = 262_144
MAX_DEBUG_TOTAL_POLYGON_VERTICES = 131_072
MAX_SAFE_CANONICAL_INTEGER = (1 << 53) - 1
MAX_NAVIGATION_NUMBER_LEXEME_BYTES = 128

# Pinned Detour v7 native tile ABI (Recast commit above, Windows little-endian).
DETOUR_NAVMESH_MAGIC = 0x444E4156
DETOUR_NAVMESH_VERSION = 7
DETOUR_TILE_HEADER_BYTES = 100
DETOUR_VERTEX_BYTES = 12
DETOUR_POLYGON_BYTES = 32
DETOUR_LINK_BYTES = 12
DETOUR_DETAIL_MESH_BYTES = 12
DETOUR_DETAIL_VERTEX_BYTES = 12
DETOUR_DETAIL_TRIANGLE_BYTES = 4
DETOUR_BV_NODE_BYTES = 16
DETOUR_OFFMESH_CONNECTION_BYTES = 36
MAX_VERTICES_PER_NAVIGATION_TILE = (
    min(
        0xFFFE,
        (
            MAX_NAVIGATION_TILE_BYTES
            - DETOUR_TILE_HEADER_BYTES
            - DETOUR_POLYGON_BYTES
        )
        // DETOUR_VERTEX_BYTES,
    )
)
MAX_POLYGONS_PER_NAVIGATION_TILE = (
    MAX_NAVIGATION_TILE_BYTES - DETOUR_TILE_HEADER_BYTES - 3 * DETOUR_VERTEX_BYTES
) // DETOUR_POLYGON_BYTES

ORACLE_ORIGINS = frozenset(
    {"lab_oracle", "server_ground_truth", "server_mmap"}
)
DECISION_SCOPES = frozenset(
    {
        "unpromoted_evaluation_only",
        "lab_evaluation_only",
        "synthetic_fixture",
    }
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256 = re.compile(r"^[A-Fa-f0-9]{64}$")
_GIT_COMMIT = re.compile(r"^[A-Fa-f0-9]{40}$")
_CONTENT_ADDRESSED_REF = re.compile(r"^sha256:[a-f0-9]{64}$")
_UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:"
    r"[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)


class NavigationContractError(ValueError):
    """Raised when a navigation value cannot enter a versioned contract."""


def _require_identifier(name: str, value: Any) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise NavigationContractError(f"{name} is not a bounded identifier")
    return value


def _require_text(name: str, value: Any, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise NavigationContractError(
            f"{name} must contain between 1 and {maximum} characters"
        )
    if any(ord(character) < 0x20 for character in value):
        raise NavigationContractError(f"{name} cannot contain control characters")
    return value


def _require_sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise NavigationContractError(f"{name} must be a SHA-256 digest")
    return value.lower()


def _require_git_commit(name: str, value: Any) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise NavigationContractError(f"{name} must be a full 40-character commit")
    return value.lower()


def _require_bounded_int(
    name: str, value: Any, *, minimum: int, maximum: int
) -> int:
    if type(value) is int:
        result = value
    elif type(value) is float and isfinite(value) and value.is_integer():
        result = int(value)
    else:
        raise NavigationContractError(f"{name} must be an integer")
    if not -MAX_SAFE_CANONICAL_INTEGER <= result <= MAX_SAFE_CANONICAL_INTEGER:
        raise NavigationContractError(
            f"{name} must fit the exact IEEE-754 integer range"
        )
    if not minimum <= result <= maximum:
        raise NavigationContractError(
            f"{name} must be in [{minimum}, {maximum}]"
        )
    return result


def _require_finite(
    name: str,
    value: Any,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise NavigationContractError(f"{name} must be a finite number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise NavigationContractError(f"{name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise NavigationContractError(f"{name} must be <= {maximum}")
    return result


def _parse_utc_timestamp(name: str, value: Any) -> datetime:
    if not isinstance(value, str) or _UTC_TIMESTAMP.fullmatch(value) is None:
        raise NavigationContractError(f"{name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise NavigationContractError(f"{name} is not a valid timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise NavigationContractError(f"{name} must use UTC")
    return parsed


def _require_tuple(
    name: str,
    value: Any,
    *,
    minimum: int,
    maximum: int,
) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        raise NavigationContractError(f"{name} must be an immutable tuple")
    if not minimum <= len(value) <= maximum:
        raise NavigationContractError(
            f"{name} must contain between {minimum} and {maximum} items"
        )
    return value


def _utf8_character_size(character: str) -> int:
    codepoint = ord(character)
    if 0xD800 <= codepoint <= 0xDFFF:
        raise NavigationContractError("navigation JSON must not contain surrogates")
    if codepoint <= 0x7F:
        return 1
    if codepoint <= 0x7FF:
        return 2
    if codepoint <= 0xFFFF:
        return 3
    return 4


def _preflight_builtin_tree(value: Any, *, root_must_be_object: bool = True) -> None:
    """Bound an already-parsed tree before copying, hashing, or typed decoding.

    Only exact JSON builtin types are accepted.  Custom Mapping/Sequence objects
    are intentionally rejected so validation cannot execute attacker-controlled
    iteration methods.  The walk is iterative, cycle-aware, and globally bounded.
    """

    if root_must_be_object and type(value) is not dict:
        raise NavigationContractError("navigation record root must be an object")
    stack: list[tuple[Any, int, bool]] = [(value, 0, False)]
    active_containers: set[int] = set()
    node_count = 0
    string_bytes = 0
    while stack:
        current, depth, exiting = stack.pop()
        if exiting:
            active_containers.remove(id(current))
            continue
        node_count += 1
        if node_count > MAX_NAVIGATION_JSON_NODES:
            raise NavigationContractError("navigation record exceeds the global node budget")
        if depth > MAX_NAVIGATION_NESTING_DEPTH:
            raise NavigationContractError("navigation record exceeds the nesting budget")
        if current is None or type(current) is bool:
            continue
        if type(current) is int:
            if not -MAX_SAFE_CANONICAL_INTEGER <= current <= MAX_SAFE_CANONICAL_INTEGER:
                raise NavigationContractError(
                    "canonical integers must fit exact IEEE-754 binary64 range"
                )
            continue
        if type(current) is float:
            if not isfinite(current):
                raise NavigationContractError("canonical floats must be finite binary64")
            continue
        if type(current) is str:
            for character in current:
                string_bytes += _utf8_character_size(character)
                if string_bytes > MAX_NAVIGATION_STRING_BYTES:
                    raise NavigationContractError(
                        "navigation record exceeds the global string-byte budget"
                    )
            continue
        if type(current) not in {dict, list}:
            raise NavigationContractError("navigation record contains a non-JSON builtin")
        identity = id(current)
        if identity in active_containers:
            raise NavigationContractError("navigation record contains a cycle")
        active_containers.add(identity)
        stack.append((current, depth, True))
        if type(current) is dict:
            for key, item in current.items():
                if type(key) is not str:
                    raise NavigationContractError("navigation object keys must be strings")
                stack.append((key, depth + 1, False))
                stack.append((item, depth + 1, False))
        else:
            for item in current:
                stack.append((item, depth + 1, False))


def _wire_length(length: int) -> bytes:
    if not 0 <= length <= 0xFFFFFFFF:
        raise NavigationContractError("canonical wire collection is too large")
    return struct.pack(">I", length)


def canonical_wire_bytes(value: Mapping[str, Any]) -> bytes:
    """Encode the PA navigation canonical wire format v1.

    The preimage is language-neutral and typed: maps are ordered by UTF-8 key
    bytes, every JSON number is normalized to finite IEEE-754 binary64 (integers
    must be exactly representable), negative zero becomes positive zero, and
    every variable-length value has a big-endian u32 length.  Thus `1` and `1.0`
    have one cross-language preimage without relying on a JSON float printer.
    The fixed prefix versions the hash domain.
    """

    _preflight_builtin_tree(value)
    output = bytearray(b"PA-NAV-WIRE\x00\x01")

    def encode(current: Any) -> None:
        if current is None:
            output.extend(b"N")
        elif type(current) is bool:
            output.extend(b"T" if current else b"F")
        elif type(current) in {int, float}:
            normalized = 0.0 if current == 0 else float(current)
            output.extend(b"D")
            output.extend(struct.pack(">d", normalized))
        elif type(current) is str:
            encoded = current.encode("utf-8", errors="strict")
            output.extend(b"S")
            output.extend(_wire_length(len(encoded)))
            output.extend(encoded)
        elif type(current) is list:
            output.extend(b"A")
            output.extend(_wire_length(len(current)))
            for item in current:
                encode(item)
        elif type(current) is dict:
            output.extend(b"M")
            output.extend(_wire_length(len(current)))
            ordered = sorted(
                current.items(), key=lambda pair: pair[0].encode("utf-8", errors="strict")
            )
            for key, item in ordered:
                encode(key)
                encode(item)
        else:  # guarded by the preflight; retained as a local invariant
            raise NavigationContractError("unsupported canonical wire value")

    encode(value)
    return bytes(output)


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Compatibility alias for the v1 canonical wire preimage.

    PA-024C originally exposed this name before the cross-language wire format
    was frozen.  New consumers should call :func:`canonical_wire_bytes`.
    """

    return canonical_wire_bytes(value)


def canonical_record_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_wire_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class Vector3:
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        for name in ("x", "y", "z"):
            object.__setattr__(
                self, name, _require_finite(name, getattr(self, name))
            )

    def to_record(self) -> dict[str, float]:
        return {"x": float(self.x), "y": float(self.y), "z": float(self.z)}


@dataclass(frozen=True, slots=True)
class Bounds3:
    minimum: Vector3
    maximum: Vector3

    def __post_init__(self) -> None:
        if not isinstance(self.minimum, Vector3) or not isinstance(
            self.maximum, Vector3
        ):
            raise NavigationContractError("bounds require Vector3 endpoints")
        if not (
            self.minimum.x < self.maximum.x
            and self.minimum.y < self.maximum.y
            and self.minimum.z < self.maximum.z
        ):
            raise NavigationContractError(
                "bounds minimum must be strictly below maximum on every axis"
            )

    def contains(self, point: Vector3, *, tolerance: float = 1e-6) -> bool:
        return (
            self.minimum.x - tolerance <= point.x <= self.maximum.x + tolerance
            and self.minimum.y - tolerance <= point.y <= self.maximum.y + tolerance
            and self.minimum.z - tolerance <= point.z <= self.maximum.z + tolerance
        )

    def contains_bounds(self, other: "Bounds3") -> bool:
        return self.contains(other.minimum) and self.contains(other.maximum)

    def to_record(self) -> dict[str, dict[str, float]]:
        return {
            "minimum": self.minimum.to_record(),
            "maximum": self.maximum.to_record(),
        }


_DIRECTION_VECTORS = {
    "east": (1, 0, 0),
    "west": (-1, 0, 0),
    "north": (0, 1, 0),
    "south": (0, -1, 0),
    "up": (0, 0, 1),
    "down": (0, 0, -1),
}


def _determinant3(columns: Sequence[Sequence[float]]) -> float:
    first, second, third = columns
    return (
        first[0] * (second[1] * third[2] - second[2] * third[1])
        - second[0] * (first[1] * third[2] - first[2] * third[1])
        + third[0] * (first[1] * second[2] - first[2] * second[1])
    )


@dataclass(frozen=True, slots=True)
class CoordinateSystem:
    space_id: str
    units: str
    handedness: str
    axis_x: str
    axis_y: str
    axis_z: str
    triangle_winding: str
    world_to_nav_row_major: tuple[float, ...]

    def __post_init__(self) -> None:
        _require_identifier("space_id", self.space_id)
        if self.units not in {"world_units", "meters"}:
            raise NavigationContractError("unsupported coordinate units")
        if self.handedness not in {"right_handed", "left_handed"}:
            raise NavigationContractError("unsupported handedness")
        directions = (self.axis_x, self.axis_y, self.axis_z)
        if any(direction not in _DIRECTION_VECTORS for direction in directions):
            raise NavigationContractError("unsupported axis direction")
        dimensions = (
            {"east", "west"},
            {"north", "south"},
            {"up", "down"},
        )
        if any(
            sum(direction in dimension for direction in directions) != 1
            for dimension in dimensions
        ):
            raise NavigationContractError(
                "axes must map one east/west, one north/south and one up/down direction"
            )
        determinant = _determinant3(
            tuple(_DIRECTION_VECTORS[direction] for direction in directions)
        )
        expected_handedness = "right_handed" if determinant > 0 else "left_handed"
        if self.handedness != expected_handedness:
            raise NavigationContractError("declared handedness contradicts axis directions")
        if self.triangle_winding not in {"clockwise", "counter_clockwise"}:
            raise NavigationContractError("unsupported triangle winding")
        _require_tuple(
            "world_to_nav_row_major",
            self.world_to_nav_row_major,
            minimum=16,
            maximum=16,
        )
        matrix = tuple(
            _require_finite("world_to_nav_row_major", value)
            for value in self.world_to_nav_row_major
        )
        object.__setattr__(self, "world_to_nav_row_major", matrix)
        if not (
            isclose(matrix[12], 0.0, abs_tol=1e-9)
            and isclose(matrix[13], 0.0, abs_tol=1e-9)
            and isclose(matrix[14], 0.0, abs_tol=1e-9)
            and isclose(matrix[15], 1.0, abs_tol=1e-9)
        ):
            raise NavigationContractError("world_to_nav_row_major must be affine")
        linear_rows = (
            (matrix[0], matrix[1], matrix[2]),
            (matrix[4], matrix[5], matrix[6]),
            (matrix[8], matrix[9], matrix[10]),
        )
        for axis_name, row, direction_name in zip(
            ("x", "y", "z"), linear_rows, directions
        ):
            declared_direction = _DIRECTION_VECTORS[direction_name]
            scale = sum(
                component * direction
                for component, direction in zip(row, declared_direction)
            )
            if scale <= 0.0 or any(
                not isclose(
                    component,
                    scale * direction,
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                )
                for component, direction in zip(row, declared_direction)
            ):
                raise NavigationContractError(
                    f"transform row {axis_name} contradicts its declared axis direction"
                )
        linear_columns = (
            (matrix[0], matrix[4], matrix[8]),
            (matrix[1], matrix[5], matrix[9]),
            (matrix[2], matrix[6], matrix[10]),
        )
        matrix_determinant = _determinant3(linear_columns)
        if isclose(matrix_determinant, 0.0, abs_tol=1e-12):
            raise NavigationContractError("world_to_nav_row_major must be invertible")
        if (matrix_determinant > 0) != (determinant > 0):
            raise NavigationContractError(
                "transform determinant contradicts declared axis handedness"
            )
        expected_winding = (
            "clockwise" if matrix_determinant > 0 else "counter_clockwise"
        )
        if self.triangle_winding != expected_winding:
            raise NavigationContractError(
                "triangle winding contradicts transform determinant"
            )

    def to_record(self) -> dict[str, object]:
        return {
            "space_id": self.space_id,
            "units": self.units,
            "handedness": self.handedness,
            "axes": {"x": self.axis_x, "y": self.axis_y, "z": self.axis_z},
            "triangle_winding": self.triangle_winding,
            "world_to_nav_row_major": [
                float(value) for value in self.world_to_nav_row_major
            ],
        }


@dataclass(frozen=True, slots=True)
class ArtifactScope:
    """V1 artifact state: immutable candidate data with no promotion authority.

    Promotion needs an external trust anchor and a future contract version.  A
    manifest cannot promote itself by changing three strings and recomputing its
    own hash.
    """

    asset_trust: str
    promotion_state: str
    decision_scope: str

    def __post_init__(self) -> None:
        if self.asset_trust != "candidate_untrusted":
            raise NavigationContractError("v1 artifacts are candidate_untrusted only")
        if self.promotion_state != "unpromoted":
            raise NavigationContractError("v1 artifacts cannot self-promote")
        if self.decision_scope not in DECISION_SCOPES:
            raise NavigationContractError("unsupported decision_scope")

    def to_record(self) -> dict[str, str]:
        return {
            "asset_trust": self.asset_trust,
            "promotion_state": self.promotion_state,
            "decision_scope": self.decision_scope,
        }


@dataclass(frozen=True, slots=True)
class NavigationActorBinding:
    """Configured actor identity copied intact into query/debug facts only."""

    schema_version: ClassVar[str] = "1.0"

    instance_id: str
    actor_role: str
    actor_id: str
    decision_context: str
    memory_namespace: str
    expected_character_name: str
    credential_alias: str
    binding_assurance_state: str
    binding_assurance_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "instance_id",
            "actor_id",
            "memory_namespace",
            "credential_alias",
        ):
            _require_identifier(name, getattr(self, name))
        _require_text("expected_character_name", self.expected_character_name, maximum=64)
        expected_context = {
            "champion_journey": "champion",
            "lab_clone": "lab_clone",
        }.get(self.actor_role)
        if expected_context is None or self.decision_context != expected_context:
            raise NavigationContractError(
                "actor_role and decision_context do not form a valid pair"
            )
        expected_prefix = (
            "memory:champion:"
            if self.actor_role == "champion_journey"
            else "memory:lab:"
        )
        if not self.memory_namespace.startswith(expected_prefix):
            raise NavigationContractError("memory_namespace does not match actor_role")
        if self.binding_assurance_state != "configured_expected_only":
            raise NavigationContractError(
                "navigation binding assurance must remain configured-only"
            )
        _require_tuple(
            "binding_assurance_evidence_refs",
            self.binding_assurance_evidence_refs,
            minimum=1,
            maximum=MAX_BINDING_EVIDENCE_REFS,
        )
        if len(set(self.binding_assurance_evidence_refs)) != len(
            self.binding_assurance_evidence_refs
        ):
            raise NavigationContractError(
                "binding assurance evidence refs must be unique"
            )
        for evidence_ref in self.binding_assurance_evidence_refs:
            _require_identifier("binding assurance evidence_ref", evidence_ref)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "instance_id": self.instance_id,
            "actor_role": self.actor_role,
            "actor_id": self.actor_id,
            "decision_context": self.decision_context,
            "memory_namespace": self.memory_namespace,
            "expected_character_name": self.expected_character_name,
            "credential_alias": self.credential_alias,
            "binding_assurance": {
                "state": self.binding_assurance_state,
                "evidence_refs": list(self.binding_assurance_evidence_refs),
            },
        }


@dataclass(frozen=True, slots=True)
class NavigationProvenance:
    source_id: str
    origin: str
    scope: str
    capability: str
    evidence_refs: tuple[str, ...]
    observed_at: str
    confidence: float

    def __post_init__(self) -> None:
        _require_identifier("source_id", self.source_id)
        if self.origin not in {
            "client_asset_derived",
            "navigation_runtime",
            "replay_fixture",
            *ORACLE_ORIGINS,
        }:
            raise NavigationContractError("unsupported provenance origin")
        if self.scope not in DECISION_SCOPES:
            raise NavigationContractError("unsupported provenance scope")
        if self.origin in ORACLE_ORIGINS and self.scope != "lab_evaluation_only":
            raise NavigationContractError("oracle provenance is LAB evaluation only")
        _require_identifier("capability", self.capability)
        _require_tuple(
            "evidence_refs",
            self.evidence_refs,
            minimum=1,
            maximum=MAX_EVIDENCE_REFS,
        )
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise NavigationContractError("evidence_refs must be unique")
        for evidence_ref in self.evidence_refs:
            _require_identifier("evidence_ref", evidence_ref)
        _parse_utc_timestamp("observed_at", self.observed_at)
        object.__setattr__(
            self,
            "confidence",
            _require_finite(
                "confidence", self.confidence, minimum=0.0, maximum=1.0
            ),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "origin": self.origin,
            "scope": self.scope,
            "capability": self.capability,
            "evidence_refs": list(self.evidence_refs),
            "observed_at": self.observed_at,
            "confidence": float(self.confidence),
        }


def _validate_identity_fields(
    *,
    target_profile: str,
    client_build: str,
    build_signature: str,
    map_ref: str,
    map_signature: str,
    ordered_asset_manifest_sha256: str,
) -> None:
    _require_identifier("target_profile", target_profile)
    _require_text("client_build", client_build, maximum=64)
    _require_text("build_signature", build_signature)
    _require_identifier("map_ref", map_ref)
    _require_text("map_signature", map_signature)
    _require_sha256(
        "ordered_asset_manifest_sha256", ordered_asset_manifest_sha256
    )


def _validate_creation_time(created_at: str, provenance: NavigationProvenance) -> None:
    created = _parse_utc_timestamp("created_at", created_at)
    observed = _parse_utc_timestamp("provenance.observed_at", provenance.observed_at)
    if created < observed:
        raise NavigationContractError("created_at cannot precede observed_at")


def _validate_artifact_provenance(
    *, artifact_scope: ArtifactScope, provenance: NavigationProvenance
) -> None:
    if provenance.origin in ORACLE_ORIGINS:
        raise NavigationContractError(
            "server and LAB oracle data cannot enter pgeom or pnav artifacts"
        )
    if provenance.scope != artifact_scope.decision_scope:
        raise NavigationContractError(
            "artifact decision_scope must match provenance scope"
        )


@dataclass(frozen=True, slots=True)
class GeometryTriangle:
    indices: tuple[int, int, int]
    area: str
    material_ref: str
    source_ref: str

    def __post_init__(self) -> None:
        _require_tuple("indices", self.indices, minimum=3, maximum=3)
        normalized_indices = tuple(
            _require_bounded_int(
                "triangle index", index, minimum=0, maximum=2**31 - 1
            )
            for index in self.indices
        )
        object.__setattr__(self, "indices", normalized_indices)
        if len(set(self.indices)) != 3:
            raise NavigationContractError("triangle indices must be distinct")
        if self.area not in {
            "ground",
            "road",
            "water",
            "steep",
            "blocked",
            "unknown",
        }:
            raise NavigationContractError("unsupported triangle area")
        _require_identifier("material_ref", self.material_ref)
        _require_identifier("source_ref", self.source_ref)

    def to_record(self) -> dict[str, object]:
        return {
            "indices": list(self.indices),
            "area": self.area,
            "material_ref": self.material_ref,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class GeometryTile:
    tile_id: str
    grid_x: int
    grid_y: int
    layer: int
    bounds: Bounds3
    vertices: tuple[Vector3, ...]
    triangles: tuple[GeometryTriangle, ...]
    source_asset_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier("tile_id", self.tile_id)
        object.__setattr__(self, "grid_x", _require_bounded_int(
            "grid_x", self.grid_x, minimum=-(2**20), maximum=2**20
        ))
        object.__setattr__(self, "grid_y", _require_bounded_int(
            "grid_y", self.grid_y, minimum=-(2**20), maximum=2**20
        ))
        object.__setattr__(self, "layer", _require_bounded_int(
            "layer", self.layer, minimum=0, maximum=255
        ))
        if not isinstance(self.bounds, Bounds3):
            raise NavigationContractError("geometry tile requires bounds")
        _require_tuple(
            "vertices",
            self.vertices,
            minimum=3,
            maximum=MAX_VERTICES_PER_GEOMETRY_TILE,
        )
        for vertex in self.vertices:
            if not isinstance(vertex, Vector3) or not self.bounds.contains(vertex):
                raise NavigationContractError("geometry vertex lies outside tile bounds")
        _require_tuple(
            "triangles",
            self.triangles,
            minimum=1,
            maximum=MAX_TRIANGLES_PER_GEOMETRY_TILE,
        )
        for triangle in self.triangles:
            if not isinstance(triangle, GeometryTriangle):
                raise NavigationContractError("triangles require GeometryTriangle values")
            if max(triangle.indices) >= len(self.vertices):
                raise NavigationContractError("triangle index exceeds vertex count")
        _require_tuple(
            "source_asset_refs",
            self.source_asset_refs,
            minimum=1,
            maximum=MAX_SOURCE_ASSET_REFS,
        )
        if len(set(self.source_asset_refs)) != len(self.source_asset_refs):
            raise NavigationContractError("source_asset_refs must be unique")
        for source_asset_ref in self.source_asset_refs:
            _require_identifier("source_asset_ref", source_asset_ref)

    def unsigned_record(self) -> dict[str, object]:
        return {
            "hash_wire_format": HASH_WIRE_FORMAT,
            "tile_id": self.tile_id,
            "grid_x": self.grid_x,
            "grid_y": self.grid_y,
            "layer": self.layer,
            "bounds": self.bounds.to_record(),
            "vertices": [vertex.to_record() for vertex in self.vertices],
            "triangles": [triangle.to_record() for triangle in self.triangles],
            "source_asset_refs": list(self.source_asset_refs),
        }

    @property
    def tile_sha256(self) -> str:
        return canonical_record_sha256(self.unsigned_record())

    def to_record(self) -> dict[str, object]:
        record = self.unsigned_record()
        record["tile_sha256"] = self.tile_sha256
        return record


@dataclass(frozen=True, slots=True)
class NavigationGeometry:
    record_type: ClassVar[str] = "navigation_geometry"
    schema_version: ClassVar[str] = CONTRACT_VERSION
    format: ClassVar[str] = "pgeom"
    format_version: ClassVar[int] = PGEOM_FORMAT_VERSION

    geometry_id: str
    target_profile: str
    client_build: str
    build_signature: str
    map_ref: str
    map_signature: str
    ordered_asset_manifest_sha256: str
    geometry_profile_id: str
    geometry_profile_hash: str
    coordinate_system: CoordinateSystem
    bounds: Bounds3
    tiles: tuple[GeometryTile, ...]
    artifact_scope: ArtifactScope
    provenance: NavigationProvenance
    created_at: str

    def __post_init__(self) -> None:
        _require_identifier("geometry_id", self.geometry_id)
        _validate_identity_fields(
            target_profile=self.target_profile,
            client_build=self.client_build,
            build_signature=self.build_signature,
            map_ref=self.map_ref,
            map_signature=self.map_signature,
            ordered_asset_manifest_sha256=self.ordered_asset_manifest_sha256,
        )
        _require_identifier("geometry_profile_id", self.geometry_profile_id)
        _require_sha256("geometry_profile_hash", self.geometry_profile_hash)
        if not isinstance(self.coordinate_system, CoordinateSystem):
            raise NavigationContractError("geometry requires a coordinate system")
        if not isinstance(self.bounds, Bounds3):
            raise NavigationContractError("geometry requires bounds")
        _require_tuple(
            "tiles", self.tiles, minimum=1, maximum=MAX_GEOMETRY_TILES
        )
        tile_ids: set[str] = set()
        tile_coordinates: set[tuple[int, int, int]] = set()
        total_vertices = 0
        total_triangles = 0
        total_source_asset_refs = 0
        for tile in self.tiles:
            if not isinstance(tile, GeometryTile):
                raise NavigationContractError("geometry tiles require GeometryTile values")
            coordinates = (tile.grid_x, tile.grid_y, tile.layer)
            if tile.tile_id in tile_ids or coordinates in tile_coordinates:
                raise NavigationContractError("geometry tiles must have unique identities")
            if not self.bounds.contains_bounds(tile.bounds):
                raise NavigationContractError("geometry tile lies outside artifact bounds")
            tile_ids.add(tile.tile_id)
            tile_coordinates.add(coordinates)
            total_vertices += len(tile.vertices)
            total_triangles += len(tile.triangles)
            total_source_asset_refs += len(tile.source_asset_refs)
        if total_vertices > MAX_GEOMETRY_TOTAL_VERTICES:
            raise NavigationContractError("geometry exceeds the global vertex budget")
        if total_triangles > MAX_GEOMETRY_TOTAL_TRIANGLES:
            raise NavigationContractError("geometry exceeds the global triangle budget")
        if total_source_asset_refs > MAX_GEOMETRY_TOTAL_SOURCE_ASSET_REFS:
            raise NavigationContractError(
                "geometry exceeds the global source-asset reference budget"
            )
        if not isinstance(self.artifact_scope, ArtifactScope):
            raise NavigationContractError("geometry requires artifact_scope")
        if not isinstance(self.provenance, NavigationProvenance):
            raise NavigationContractError("geometry requires provenance")
        if self.provenance.origin != "client_asset_derived":
            raise NavigationContractError("pgeom accepts client-asset geometry only")
        _validate_artifact_provenance(
            artifact_scope=self.artifact_scope, provenance=self.provenance
        )
        _validate_creation_time(self.created_at, self.provenance)

    def unsigned_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "format": self.format,
            "format_version": self.format_version,
            "hash_wire_format": HASH_WIRE_FORMAT,
            "geometry_id": self.geometry_id,
            "target_profile": self.target_profile,
            "client_build": self.client_build,
            "build_signature": self.build_signature,
            "map_ref": self.map_ref,
            "map_signature": self.map_signature,
            "ordered_asset_manifest_sha256": self.ordered_asset_manifest_sha256.lower(),
            "geometry_profile_id": self.geometry_profile_id,
            "geometry_profile_hash": self.geometry_profile_hash.lower(),
            "coordinate_system": self.coordinate_system.to_record(),
            "bounds": self.bounds.to_record(),
            "tile_count": len(self.tiles),
            "tiles": [tile.to_record() for tile in self.tiles],
            "artifact_scope": self.artifact_scope.to_record(),
            "provenance": self.provenance.to_record(),
            "execution_authority": False,
            "created_at": self.created_at,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_record_sha256(self.unsigned_record())

    def to_record(self) -> dict[str, object]:
        record = self.unsigned_record()
        record["content_sha256"] = self.content_sha256
        return record


@dataclass(frozen=True, slots=True)
class NavigationMeshTile:
    tile_id: str
    grid_x: int
    grid_y: int
    layer: int
    bounds: Bounds3
    vertex_count: int
    polygon_count: int
    binary_artifact_ref: str
    data_size_bytes: int
    tile_sha256: str

    def __post_init__(self) -> None:
        _require_identifier("tile_id", self.tile_id)
        object.__setattr__(self, "grid_x", _require_bounded_int(
            "grid_x", self.grid_x, minimum=-(2**20), maximum=2**20
        ))
        object.__setattr__(self, "grid_y", _require_bounded_int(
            "grid_y", self.grid_y, minimum=-(2**20), maximum=2**20
        ))
        object.__setattr__(self, "layer", _require_bounded_int(
            "layer", self.layer, minimum=0, maximum=255
        ))
        if not isinstance(self.bounds, Bounds3):
            raise NavigationContractError("navigation tile requires bounds")
        object.__setattr__(self, "vertex_count", _require_bounded_int(
            "vertex_count", self.vertex_count, minimum=3,
            maximum=MAX_VERTICES_PER_NAVIGATION_TILE,
        ))
        object.__setattr__(self, "polygon_count", _require_bounded_int(
            "polygon_count", self.polygon_count, minimum=1,
            maximum=MAX_POLYGONS_PER_NAVIGATION_TILE,
        ))
        if (
            not isinstance(self.binary_artifact_ref, str)
            or _CONTENT_ADDRESSED_REF.fullmatch(self.binary_artifact_ref) is None
        ):
            raise NavigationContractError(
                "binary_artifact_ref must be an opaque sha256 content reference"
            )
        object.__setattr__(self, "data_size_bytes", _require_bounded_int(
            "data_size_bytes", self.data_size_bytes, minimum=1,
            maximum=MAX_NAVIGATION_TILE_BYTES,
        ))
        _require_sha256("tile_sha256", self.tile_sha256)
        if self.binary_artifact_ref != f"sha256:{self.tile_sha256.lower()}":
            raise NavigationContractError(
                "binary_artifact_ref digest must equal tile_sha256"
            )
        minimum_payload_bytes = (
            DETOUR_TILE_HEADER_BYTES
            + self.vertex_count * DETOUR_VERTEX_BYTES
            + self.polygon_count * DETOUR_POLYGON_BYTES
        )
        if self.data_size_bytes < minimum_payload_bytes:
            raise NavigationContractError(
                "navigation tile counts exceed the declared payload size"
            )

    @classmethod
    def from_fixture_payload(
        cls,
        *,
        tile_id: str,
        grid_x: int,
        grid_y: int,
        layer: int,
        bounds: Bounds3,
        vertex_count: int,
        polygon_count: int,
        binary_artifact_ref: str | None = None,
        payload: bytes,
    ) -> "NavigationMeshTile":
        if type(payload) is not bytes or not payload:
            raise NavigationContractError("fixture payload must be non-empty bytes")
        if len(payload) > MAX_NAVIGATION_TILE_BYTES:
            raise NavigationContractError("fixture payload exceeds the tile byte budget")
        payload_sha256 = hashlib.sha256(payload).hexdigest()
        content_ref = binary_artifact_ref or f"sha256:{payload_sha256}"
        result = cls(
            tile_id=tile_id,
            grid_x=grid_x,
            grid_y=grid_y,
            layer=layer,
            bounds=bounds,
            vertex_count=vertex_count,
            polygon_count=polygon_count,
            binary_artifact_ref=content_ref,
            data_size_bytes=len(payload),
            tile_sha256=payload_sha256,
        )
        verify_navigation_tile_payload(result, payload)
        return result

    def to_record(self) -> dict[str, object]:
        return {
            "tile_id": self.tile_id,
            "grid_x": self.grid_x,
            "grid_y": self.grid_y,
            "layer": self.layer,
            "bounds": self.bounds.to_record(),
            "vertex_count": self.vertex_count,
            "polygon_count": self.polygon_count,
            "binary_artifact_ref": self.binary_artifact_ref,
            "data_size_bytes": self.data_size_bytes,
            "tile_sha256": self.tile_sha256.lower(),
        }


def verify_navigation_tile_payload(
    tile: NavigationMeshTile | Mapping[str, Any], payload: bytes
) -> None:
    """Verify exact bytes and the pinned Detour v7 header against the manifest."""

    if type(payload) is not bytes:
        raise NavigationContractError("navigation tile payload must be bytes")
    if isinstance(tile, NavigationMeshTile):
        decoded_tile = tile
    elif type(tile) is dict:
        _preflight_builtin_tree(tile)
        decoded_tile = _decode_navigation_tile(tile)
        if decoded_tile.to_record() != tile:
            raise NavigationContractError("navigation tile manifest is not canonical")
    else:
        raise NavigationContractError("tile must be a manifest tile")
    expected_size = decoded_tile.data_size_bytes
    expected_sha256 = decoded_tile.tile_sha256
    if len(payload) != expected_size:
        raise NavigationContractError("navigation tile payload size mismatch")
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(expected_sha256.lower(), actual_sha256):
        raise NavigationContractError("navigation tile payload hash mismatch")
    if len(payload) < DETOUR_TILE_HEADER_BYTES:
        raise NavigationContractError("navigation tile payload has no Detour header")
    header = struct.unpack_from("<15i10f", payload, 0)
    if header[0] != DETOUR_NAVMESH_MAGIC or header[1] != DETOUR_NAVMESH_VERSION:
        raise NavigationContractError("navigation tile payload is not pinned Detour v7")
    if any(not isfinite(value) for value in header[15:25]):
        raise NavigationContractError(
            "navigation tile payload header contains a non-finite float"
        )
    if any(value < 0.0 for value in header[15:18]) or header[24] <= 0.0:
        raise NavigationContractError(
            "navigation tile payload walkability or quantization is invalid"
        )
    if (header[2], header[3], header[4]) != (
        decoded_tile.grid_x,
        decoded_tile.grid_y,
        decoded_tile.layer,
    ):
        raise NavigationContractError(
            "navigation tile payload coordinates do not match the manifest"
        )
    if header[6] != decoded_tile.polygon_count or header[7] != decoded_tile.vertex_count:
        raise NavigationContractError(
            "navigation tile payload counts do not match the manifest"
        )
    section_counts = header[6:15]
    if any(count < 0 for count in section_counts):
        raise NavigationContractError(
            "navigation tile payload contains a negative section count"
        )
    (
        polygon_count,
        vertex_count,
        max_link_count,
        detail_mesh_count,
        detail_vertex_count,
        detail_triangle_count,
        bv_node_count,
        offmesh_connection_count,
        offmesh_base,
    ) = section_counts
    if max_link_count <= 0:
        raise NavigationContractError(
            "navigation tile payload maxLinkCount must be positive"
        )
    if (
        offmesh_base <= 0
        or detail_mesh_count != offmesh_base
        or offmesh_base + offmesh_connection_count != polygon_count
        or bv_node_count not in {0, detail_mesh_count * 2}
    ):
        raise NavigationContractError(
            "navigation tile payload section counts are inconsistent"
        )
    expected_serialized_size = (
        DETOUR_TILE_HEADER_BYTES
        + vertex_count * DETOUR_VERTEX_BYTES
        + polygon_count * DETOUR_POLYGON_BYTES
        + max_link_count * DETOUR_LINK_BYTES
        + detail_mesh_count * DETOUR_DETAIL_MESH_BYTES
        + detail_vertex_count * DETOUR_DETAIL_VERTEX_BYTES
        + detail_triangle_count * DETOUR_DETAIL_TRIANGLE_BYTES
        + bv_node_count * DETOUR_BV_NODE_BYTES
        + offmesh_connection_count * DETOUR_OFFMESH_CONNECTION_BYTES
    )
    if expected_serialized_size != len(payload):
        raise NavigationContractError(
            "navigation tile payload size contradicts its Detour header"
        )
    header_bounds_values = (*header[18:21], *header[21:24])
    manifest_bounds_values = (
        decoded_tile.bounds.minimum.x,
        decoded_tile.bounds.minimum.y,
        decoded_tile.bounds.minimum.z,
        decoded_tile.bounds.maximum.x,
        decoded_tile.bounds.maximum.y,
        decoded_tile.bounds.maximum.z,
    )
    if any(
        not isfinite(actual)
        or not isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-5)
        for actual, expected in zip(header_bounds_values, manifest_bounds_values)
    ):
        raise NavigationContractError(
            "navigation tile payload bounds do not match the manifest"
        )

    # Parse and validate every section emitted by pinned dtCreateNavMeshData.
    # This verifier is the mandatory trust boundary before native addTile: a
    # correct header and byte count are not sufficient when internal indices can
    # otherwise drive unchecked native pointer arithmetic.
    cursor = DETOUR_TILE_HEADER_BYTES
    vertex_offset = cursor
    cursor += vertex_count * DETOUR_VERTEX_BYTES
    polygon_offset = cursor
    cursor += polygon_count * DETOUR_POLYGON_BYTES
    link_offset = cursor
    cursor += max_link_count * DETOUR_LINK_BYTES
    detail_mesh_offset = cursor
    cursor += detail_mesh_count * DETOUR_DETAIL_MESH_BYTES
    detail_vertex_offset = cursor
    cursor += detail_vertex_count * DETOUR_DETAIL_VERTEX_BYTES
    detail_triangle_offset = cursor
    cursor += detail_triangle_count * DETOUR_DETAIL_TRIANGLE_BYTES
    bv_node_offset = cursor
    cursor += bv_node_count * DETOUR_BV_NODE_BYTES
    offmesh_connection_offset = cursor
    cursor += offmesh_connection_count * DETOUR_OFFMESH_CONNECTION_BYTES
    if cursor != len(payload):
        raise NavigationContractError(
            "navigation tile payload section offsets do not cover the payload"
        )

    ground_vertex_count = vertex_count - offmesh_connection_count * 2
    if ground_vertex_count < 3:
        raise NavigationContractError(
            "navigation tile payload has too few ground vertices"
        )
    header_minimum = header[18:21]
    header_maximum = header[21:24]
    for vertex_index in range(vertex_count):
        vertex = struct.unpack_from(
            "<3f", payload, vertex_offset + vertex_index * DETOUR_VERTEX_BYTES
        )
        if any(not isfinite(component) for component in vertex):
            raise NavigationContractError(
                "navigation tile payload contains a non-finite vertex"
            )
        if vertex_index < ground_vertex_count and any(
            component < minimum - 1e-5 or component > maximum + 1e-5
            for component, minimum, maximum in zip(
                vertex, header_minimum, header_maximum
            )
        ):
            raise NavigationContractError(
                "navigation tile payload ground vertex lies outside header bounds"
            )

    def ground_vertex(index: int) -> tuple[float, float, float]:
        return struct.unpack_from(
            "<3f", payload, vertex_offset + index * DETOUR_VERTEX_BYTES
        )

    # Recast vertices originate on a quantized grid.  Converting a large world
    # coordinate back to float32 can make three exactly collinear grid points
    # differ by a tiny signed area.  Scale the turn tolerance to five percent of
    # a grid cell squared: far below a real one-cell concavity, but above that
    # representational noise.
    projected_area_tolerance = max(1e-5, (1.0 / header[24]) ** 2 * 0.05)

    def require_convex_ground_polygon(indices: Sequence[int]) -> None:
        turn_sign = 0
        for index in range(len(indices)):
            previous = ground_vertex(indices[index - 1])
            current = ground_vertex(indices[index])
            following = ground_vertex(indices[(index + 1) % len(indices)])
            cross = (
                (current[0] - previous[0]) * (following[2] - current[2])
                - (current[2] - previous[2]) * (following[0] - current[0])
            )
            if isclose(cross, 0.0, abs_tol=projected_area_tolerance):
                continue
            current_sign = 1 if cross > 0.0 else -1
            if turn_sign and current_sign != turn_sign:
                raise NavigationContractError(
                    "navigation tile payload ground polygon is concave"
                )
            turn_sign = current_sign
        if not turn_sign:
            raise NavigationContractError(
                "navigation tile payload ground polygon has zero projected area"
            )

    ground_polygon_vertex_counts: list[int] = []
    ground_edge_count = 0
    portal_count = 0
    for polygon_index in range(polygon_count):
        unpacked_polygon = struct.unpack_from(
            "<I6H6HHBB",
            payload,
            polygon_offset + polygon_index * DETOUR_POLYGON_BYTES,
        )
        first_link = unpacked_polygon[0]
        vertex_indices = unpacked_polygon[1:7]
        neighbours = unpacked_polygon[7:13]
        polygon_vertex_count = unpacked_polygon[14]
        polygon_type = unpacked_polygon[15] >> 6
        if first_link != 0:
            raise NavigationContractError(
                "navigation tile payload contains a pre-linked polygon"
            )
        expected_type = 0 if polygon_index < offmesh_base else 1
        expected_vertex_count = None if expected_type == 0 else 2
        if polygon_type != expected_type or (
            expected_vertex_count is not None
            and polygon_vertex_count != expected_vertex_count
        ):
            raise NavigationContractError(
                "navigation tile payload polygon type or vertex count is invalid"
            )
        if expected_type == 0 and not 3 <= polygon_vertex_count <= 6:
            raise NavigationContractError(
                "navigation tile payload ground polygon vertex count is invalid"
            )
        active_vertices = vertex_indices[:polygon_vertex_count]
        if len(set(active_vertices)) != polygon_vertex_count:
            raise NavigationContractError(
                "navigation tile payload polygon repeats a vertex index"
            )
        if any(index >= vertex_count for index in active_vertices):
            raise NavigationContractError(
                "navigation tile payload polygon vertex index is out of range"
            )
        if expected_type == 0:
            if any(index >= ground_vertex_count for index in active_vertices):
                raise NavigationContractError(
                    "navigation tile payload ground polygon references an off-mesh vertex"
                )
            require_convex_ground_polygon(active_vertices)
            ground_polygon_vertex_counts.append(polygon_vertex_count)
            ground_edge_count += polygon_vertex_count
        else:
            offmesh_index = polygon_index - offmesh_base
            expected_indices = (
                ground_vertex_count + offmesh_index * 2,
                ground_vertex_count + offmesh_index * 2 + 1,
            )
            if tuple(active_vertices) != expected_indices:
                raise NavigationContractError(
                    "navigation tile payload off-mesh polygon vertex indices are invalid"
                )
        if any(vertex_indices[index] != 0 for index in range(polygon_vertex_count, 6)):
            raise NavigationContractError(
                "navigation tile payload polygon has non-zero unused vertex slots"
            )
        if any(neighbours[index] != 0 for index in range(polygon_vertex_count, 6)):
            raise NavigationContractError(
                "navigation tile payload polygon has non-zero unused neighbour slots"
            )
        for neighbour in neighbours[:polygon_vertex_count]:
            if expected_type == 1 and neighbour != 0:
                raise NavigationContractError(
                    "navigation tile payload off-mesh polygon has baked neighbours"
                )
            if neighbour == 0:
                continue
            if neighbour & 0x8000:
                if neighbour not in {0x8000, 0x8002, 0x8004, 0x8006}:
                    raise NavigationContractError(
                        "navigation tile payload external neighbour is invalid"
                    )
                portal_count += 1
            else:
                if not 1 <= neighbour <= offmesh_base or neighbour == polygon_index + 1:
                    raise NavigationContractError(
                        "navigation tile payload internal neighbour is out of range"
                    )

    if any(payload[link_offset:detail_mesh_offset]):
        raise NavigationContractError(
            "navigation tile payload link scratch space must be zero before addTile"
        )

    next_detail_vertex = 0
    next_detail_triangle = 0
    for detail_index in range(detail_mesh_count):
        detail_record_offset = (
            detail_mesh_offset + detail_index * DETOUR_DETAIL_MESH_BYTES
        )
        detail_vertex_base, detail_triangle_base, extra_vertex_count, triangle_count = (
            struct.unpack_from("<IIBB", payload, detail_record_offset)
        )
        if payload[detail_record_offset + 10 : detail_record_offset + 12] != b"\x00\x00":
            raise NavigationContractError(
                "navigation tile payload detail mesh padding must be zero"
            )
        if (
            detail_vertex_base != next_detail_vertex
            or detail_triangle_base != next_detail_triangle
            or detail_vertex_base + extra_vertex_count > detail_vertex_count
            or detail_triangle_base + triangle_count > detail_triangle_count
        ):
            raise NavigationContractError(
                "navigation tile payload detail mesh ranges are invalid"
            )
        polygon_vertex_count = ground_polygon_vertex_counts[detail_index]
        if triangle_count < polygon_vertex_count - 2:
            raise NavigationContractError(
                "navigation tile payload detail mesh under-triangulates its polygon"
            )
        local_vertex_count = polygon_vertex_count + extra_vertex_count
        for triangle_index in range(
            detail_triangle_base, detail_triangle_base + triangle_count
        ):
            detail_triangle = struct.unpack_from(
                "<4B",
                payload,
                detail_triangle_offset
                + triangle_index * DETOUR_DETAIL_TRIANGLE_BYTES,
            )
            if (
                len(set(detail_triangle[:3])) != 3
                or any(index >= local_vertex_count for index in detail_triangle[:3])
                or detail_triangle[3] & 0xC0
            ):
                raise NavigationContractError(
                    "navigation tile payload detail triangle is invalid"
                )
        next_detail_vertex += extra_vertex_count
        next_detail_triangle += triangle_count
    if (
        next_detail_vertex != detail_vertex_count
        or next_detail_triangle != detail_triangle_count
    ):
        raise NavigationContractError(
            "navigation tile payload detail ranges do not cover their sections"
        )

    for vertex_index in range(detail_vertex_count):
        detail_vertex = struct.unpack_from(
            "<3f",
            payload,
            detail_vertex_offset + vertex_index * DETOUR_DETAIL_VERTEX_BYTES,
        )
        if any(not isfinite(component) for component in detail_vertex) or any(
            component < minimum - 1e-5 or component > maximum + 1e-5
            for component, minimum, maximum in zip(
                detail_vertex, header_minimum, header_maximum
            )
        ):
            raise NavigationContractError(
                "navigation tile payload detail vertex is invalid"
            )

    for node_index in range(bv_node_count):
        node = struct.unpack_from(
            "<6Hi", payload, bv_node_offset + node_index * DETOUR_BV_NODE_BYTES
        )
        if any(node[axis] > node[axis + 3] for axis in range(3)):
            raise NavigationContractError(
                "navigation tile payload BV node bounds are inverted"
            )
        node_value = node[6]
        if node_value >= 0:
            if node_value >= offmesh_base:
                raise NavigationContractError(
                    "navigation tile payload BV leaf polygon index is out of range"
                )
        else:
            escape_count = -node_value
            if escape_count < 1 or node_index + escape_count > bv_node_count:
                raise NavigationContractError(
                    "navigation tile payload BV escape range is invalid"
                )

    offmesh_link_endpoints = 0
    for connection_index in range(offmesh_connection_count):
        connection = struct.unpack_from(
            "<6ffHBBI",
            payload,
            offmesh_connection_offset
            + connection_index * DETOUR_OFFMESH_CONNECTION_BYTES,
        )
        positions = connection[:6]
        radius = connection[6]
        polygon_index = connection[7]
        connection_flags = connection[8]
        side = connection[9]
        if any(not isfinite(value) for value in positions) or not isfinite(radius):
            raise NavigationContractError(
                "navigation tile payload off-mesh connection is non-finite"
            )
        if radius < 0.0 or connection_flags not in {0, 1} or side not in {
            0, 1, 2, 3, 4, 5, 6, 7, 0xFF
        }:
            raise NavigationContractError(
                "navigation tile payload off-mesh connection metadata is invalid"
            )
        if polygon_index != offmesh_base + connection_index:
            raise NavigationContractError(
                "navigation tile payload off-mesh polygon index is out of range"
            )
        endpoint_vertex_offset = (
            vertex_offset
            + (ground_vertex_count + connection_index * 2) * DETOUR_VERTEX_BYTES
        )
        endpoint_positions = struct.unpack_from("<6f", payload, endpoint_vertex_offset)
        if any(
            not isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-5)
            for actual, expected in zip(endpoint_positions, positions)
        ):
            raise NavigationContractError(
                "navigation tile payload off-mesh endpoints contradict vertices"
            )
        offmesh_link_endpoints += 1 + (1 if side == 0xFF else 0)

    expected_max_link_count = (
        ground_edge_count + portal_count * 2 + offmesh_link_endpoints * 2
    )
    if max_link_count != expected_max_link_count:
        raise NavigationContractError(
            "navigation tile payload maxLinkCount contradicts its topology"
        )


@dataclass(frozen=True, slots=True)
class NavigationMesh:
    record_type: ClassVar[str] = "navigation_mesh"
    schema_version: ClassVar[str] = CONTRACT_VERSION
    format: ClassVar[str] = "pnav"
    format_version: ClassVar[int] = PNAV_FORMAT_VERSION

    mesh_id: str
    geometry_content_sha256: str
    target_profile: str
    client_build: str
    build_signature: str
    map_ref: str
    map_signature: str
    ordered_asset_manifest_sha256: str
    recast_pin: str
    agent_profile_id: str
    agent_profile_hash: str
    coordinate_system: CoordinateSystem
    bounds: Bounds3
    tiles: tuple[NavigationMeshTile, ...]
    artifact_scope: ArtifactScope
    provenance: NavigationProvenance
    created_at: str

    def __post_init__(self) -> None:
        _require_identifier("mesh_id", self.mesh_id)
        _require_sha256("geometry_content_sha256", self.geometry_content_sha256)
        _validate_identity_fields(
            target_profile=self.target_profile,
            client_build=self.client_build,
            build_signature=self.build_signature,
            map_ref=self.map_ref,
            map_signature=self.map_signature,
            ordered_asset_manifest_sha256=self.ordered_asset_manifest_sha256,
        )
        recast_pin = _require_git_commit("recast_pin", self.recast_pin)
        if recast_pin != PINNED_RECAST_COMMIT:
            raise NavigationContractError("navigation mesh uses an unpinned Recast build")
        _require_identifier("agent_profile_id", self.agent_profile_id)
        _require_sha256("agent_profile_hash", self.agent_profile_hash)
        if not isinstance(self.coordinate_system, CoordinateSystem):
            raise NavigationContractError("navigation mesh requires a coordinate system")
        if not isinstance(self.bounds, Bounds3):
            raise NavigationContractError("navigation mesh requires bounds")
        _require_tuple(
            "tiles", self.tiles, minimum=1, maximum=MAX_NAVIGATION_TILES
        )
        total_payload_bytes = 0
        tile_ids: set[str] = set()
        tile_coordinates: set[tuple[int, int, int]] = set()
        for tile in self.tiles:
            if not isinstance(tile, NavigationMeshTile):
                raise NavigationContractError(
                    "navigation mesh tiles require NavigationMeshTile values"
                )
            coordinates = (tile.grid_x, tile.grid_y, tile.layer)
            if (
                tile.tile_id in tile_ids
                or coordinates in tile_coordinates
            ):
                raise NavigationContractError(
                    "navigation mesh tiles must have unique identities"
                )
            if not self.bounds.contains_bounds(tile.bounds):
                raise NavigationContractError("navigation tile lies outside mesh bounds")
            total_payload_bytes += tile.data_size_bytes
            tile_ids.add(tile.tile_id)
            tile_coordinates.add(coordinates)
        if total_payload_bytes > MAX_NAVIGATION_TOTAL_BYTES:
            raise NavigationContractError("navigation mesh payload is too large")
        if not isinstance(self.artifact_scope, ArtifactScope):
            raise NavigationContractError("navigation mesh requires artifact_scope")
        if not isinstance(self.provenance, NavigationProvenance):
            raise NavigationContractError("navigation mesh requires provenance")
        if self.provenance.origin != "client_asset_derived":
            raise NavigationContractError("pnav accepts client-asset-derived builds only")
        _validate_artifact_provenance(
            artifact_scope=self.artifact_scope, provenance=self.provenance
        )
        _validate_creation_time(self.created_at, self.provenance)

    def unsigned_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "format": self.format,
            "format_version": self.format_version,
            "hash_wire_format": HASH_WIRE_FORMAT,
            "mesh_id": self.mesh_id,
            "geometry_content_sha256": self.geometry_content_sha256.lower(),
            "target_profile": self.target_profile,
            "client_build": self.client_build,
            "build_signature": self.build_signature,
            "map_ref": self.map_ref,
            "map_signature": self.map_signature,
            "ordered_asset_manifest_sha256": self.ordered_asset_manifest_sha256.lower(),
            "recast_pin": self.recast_pin.lower(),
            "agent_profile_id": self.agent_profile_id,
            "agent_profile_hash": self.agent_profile_hash.lower(),
            "coordinate_system": self.coordinate_system.to_record(),
            "bounds": self.bounds.to_record(),
            "tile_count": len(self.tiles),
            "total_payload_bytes": sum(
                tile.data_size_bytes for tile in self.tiles
            ),
            "tiles": [tile.to_record() for tile in self.tiles],
            "artifact_scope": self.artifact_scope.to_record(),
            "provenance": self.provenance.to_record(),
            "execution_authority": False,
            "created_at": self.created_at,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_record_sha256(self.unsigned_record())

    def to_record(self) -> dict[str, object]:
        record = self.unsigned_record()
        record["content_sha256"] = self.content_sha256
        return record


@dataclass(frozen=True, slots=True)
class DebugTileHash:
    tile_id: str
    tile_sha256: str
    bounds: Bounds3

    def __post_init__(self) -> None:
        _require_identifier("tile_id", self.tile_id)
        _require_sha256("tile_sha256", self.tile_sha256)
        if not isinstance(self.bounds, Bounds3):
            raise NavigationContractError("debug tile evidence requires bounds")

    def to_record(self) -> dict[str, object]:
        return {
            "tile_id": self.tile_id,
            "tile_sha256": self.tile_sha256.lower(),
            "bounds": self.bounds.to_record(),
        }


@dataclass(frozen=True, slots=True)
class DebugPolygon:
    polygon_ref: str
    source_tile_id: str
    source_polygon_index: int
    vertices: tuple[Vector3, ...]
    area: str
    flags: tuple[str, ...]
    traversal_cost: float
    blocked: bool

    def __post_init__(self) -> None:
        _require_identifier("polygon_ref", self.polygon_ref)
        _require_identifier("source_tile_id", self.source_tile_id)
        object.__setattr__(self, "source_polygon_index", _require_bounded_int(
            "source_polygon_index", self.source_polygon_index, minimum=0,
            maximum=MAX_POLYGONS_PER_NAVIGATION_TILE - 1,
        ))
        _require_tuple(
            "vertices",
            self.vertices,
            minimum=3,
            maximum=MAX_DEBUG_POLYGON_VERTICES,
        )
        if any(not isinstance(vertex, Vector3) for vertex in self.vertices):
            raise NavigationContractError("debug polygon vertices require Vector3 values")
        _require_identifier("area", self.area)
        _require_tuple("flags", self.flags, minimum=0, maximum=MAX_DEBUG_FLAGS)
        if len(set(self.flags)) != len(self.flags):
            raise NavigationContractError("debug polygon flags must be unique")
        for flag in self.flags:
            _require_identifier("debug polygon flag", flag)
        object.__setattr__(
            self,
            "traversal_cost",
            _require_finite(
                "traversal_cost", self.traversal_cost, minimum=0.0, maximum=1e12
            ),
        )
        if not isinstance(self.blocked, bool):
            raise NavigationContractError("blocked must be boolean")

    def to_record(self) -> dict[str, object]:
        return {
            "polygon_ref": self.polygon_ref,
            "source_tile_id": self.source_tile_id,
            "source_polygon_index": self.source_polygon_index,
            "vertices": [vertex.to_record() for vertex in self.vertices],
            "area": self.area,
            "flags": list(self.flags),
            "traversal_cost": float(self.traversal_cost),
            "blocked": self.blocked,
        }


def _point_in_any_bounds(point: Vector3, bounds: Sequence[Bounds3]) -> bool:
    return any(item.contains(point) for item in bounds)


def _segment_interval_in_bounds(
    start: Vector3, end: Vector3, bounds: Bounds3
) -> tuple[float, float] | None:
    lower = 0.0
    upper = 1.0
    for origin, destination, minimum, maximum in (
        (start.x, end.x, bounds.minimum.x, bounds.maximum.x),
        (start.y, end.y, bounds.minimum.y, bounds.maximum.y),
        (start.z, end.z, bounds.minimum.z, bounds.maximum.z),
    ):
        delta = destination - origin
        if isclose(delta, 0.0, abs_tol=1e-12):
            if origin < minimum - 1e-6 or origin > maximum + 1e-6:
                return None
            continue
        first = (minimum - origin) / delta
        second = (maximum - origin) / delta
        entry, exit_ = sorted((first, second))
        lower = max(lower, entry)
        upper = min(upper, exit_)
        if lower > upper + 1e-9:
            return None
    if upper < -1e-9 or lower > 1.0 + 1e-9:
        return None
    return max(0.0, lower), min(1.0, upper)


def _segment_is_covered_by_bounds(
    start: Vector3, end: Vector3, bounds: Sequence[Bounds3]
) -> bool:
    intervals = [
        interval
        for item in bounds
        if (interval := _segment_interval_in_bounds(start, end, item)) is not None
    ]
    if not intervals:
        return False
    intervals.sort()
    covered_until = 0.0
    for lower, upper in intervals:
        if lower > covered_until + 1e-8:
            return False
        covered_until = max(covered_until, upper)
        if covered_until >= 1.0 - 1e-8:
            return True
    return False


@dataclass(frozen=True, slots=True)
class NavigationDebugSnapshot:
    record_type: ClassVar[str] = "navigation_debug_snapshot"
    schema_version: ClassVar[str] = CONTRACT_VERSION
    format: ClassVar[str] = "navigation-debug-snapshot"
    format_version: ClassVar[int] = DEBUG_SNAPSHOT_FORMAT_VERSION

    snapshot_id: str
    mode: str
    binding: NavigationActorBinding
    authorization_sha256: str
    target_profile: str
    client_build: str
    build_signature: str
    map_ref: str
    map_signature: str
    ordered_asset_manifest_sha256: str
    navigation_mesh_content_sha256: str
    navigation_mesh_artifact_scope: ArtifactScope
    recast_pin: str
    agent_profile_hash: str
    coordinate_system: CoordinateSystem
    bounds: Bounds3
    tile_hashes: tuple[DebugTileHash, ...]
    player_position: Vector3 | None
    target_position: Vector3 | None
    uncertainty_radius: float | None
    route_points: tuple[Vector3, ...]
    mesh_polygons: tuple[DebugPolygon, ...]
    provenance: NavigationProvenance
    created_at: str

    def __post_init__(self) -> None:
        _require_identifier("snapshot_id", self.snapshot_id)
        if self.mode not in {"OFF", "ROUTE", "MESH"}:
            raise NavigationContractError("unsupported debug mode")
        if not isinstance(self.binding, NavigationActorBinding):
            raise NavigationContractError("debug snapshot requires an actor binding")
        _require_sha256("authorization_sha256", self.authorization_sha256)
        _validate_identity_fields(
            target_profile=self.target_profile,
            client_build=self.client_build,
            build_signature=self.build_signature,
            map_ref=self.map_ref,
            map_signature=self.map_signature,
            ordered_asset_manifest_sha256=self.ordered_asset_manifest_sha256,
        )
        _require_sha256(
            "navigation_mesh_content_sha256", self.navigation_mesh_content_sha256
        )
        if not isinstance(self.navigation_mesh_artifact_scope, ArtifactScope):
            raise NavigationContractError(
                "debug snapshot requires navigation_mesh_artifact_scope"
            )
        recast_pin = _require_git_commit("recast_pin", self.recast_pin)
        if recast_pin != PINNED_RECAST_COMMIT:
            raise NavigationContractError("debug snapshot uses an unpinned Recast build")
        _require_sha256("agent_profile_hash", self.agent_profile_hash)
        if not isinstance(self.coordinate_system, CoordinateSystem):
            raise NavigationContractError("debug snapshot requires a coordinate system")
        if not isinstance(self.bounds, Bounds3):
            raise NavigationContractError("debug snapshot requires bounds")
        _require_tuple(
            "tile_hashes",
            self.tile_hashes,
            minimum=0,
            maximum=MAX_DEBUG_TILE_HASHES,
        )
        tile_ids: set[str] = set()
        tile_evidence: dict[str, DebugTileHash] = {}
        for tile_hash in self.tile_hashes:
            if not isinstance(tile_hash, DebugTileHash):
                raise NavigationContractError("tile_hashes require DebugTileHash values")
            if tile_hash.tile_id in tile_ids:
                raise NavigationContractError("debug tile hashes must be unique")
            if not self.bounds.contains_bounds(tile_hash.bounds):
                raise NavigationContractError(
                    "debug tile evidence lies outside snapshot bounds"
                )
            tile_ids.add(tile_hash.tile_id)
            tile_evidence[tile_hash.tile_id] = tile_hash
        evidence_bounds = tuple(item.bounds for item in self.tile_hashes)
        for name, position in (
            ("player_position", self.player_position),
            ("target_position", self.target_position),
        ):
            if position is not None and (
                not isinstance(position, Vector3) or not self.bounds.contains(position)
            ):
                raise NavigationContractError(f"{name} lies outside debug bounds")
            if position is not None and not _point_in_any_bounds(
                position, evidence_bounds
            ):
                raise NavigationContractError(
                    f"{name} has no referenced tile evidence"
                )
        if self.uncertainty_radius is not None:
            object.__setattr__(
                self,
                "uncertainty_radius",
                _require_finite(
                    "uncertainty_radius",
                    self.uncertainty_radius,
                    minimum=0.0,
                    maximum=1e9,
                ),
            )
            if self.player_position is None:
                raise NavigationContractError(
                    "uncertainty_radius requires player_position"
                )
        _require_tuple(
            "route_points",
            self.route_points,
            minimum=0,
            maximum=MAX_DEBUG_ROUTE_POINTS,
        )
        if len(self.route_points) == 1:
            raise NavigationContractError("debug route must be empty or contain a path")
        for point in self.route_points:
            if not isinstance(point, Vector3) or not self.bounds.contains(point):
                raise NavigationContractError("debug route point lies outside bounds")
            if not _point_in_any_bounds(point, evidence_bounds):
                raise NavigationContractError(
                    "debug route point has no referenced tile evidence"
                )
        for start, end in zip(self.route_points, self.route_points[1:]):
            if not _segment_is_covered_by_bounds(start, end, evidence_bounds):
                raise NavigationContractError(
                    "debug route segment leaves referenced tile evidence"
                )
        _require_tuple(
            "mesh_polygons",
            self.mesh_polygons,
            minimum=0,
            maximum=MAX_DEBUG_POLYGONS,
        )
        polygon_refs: set[str] = set()
        source_polygon_keys: set[tuple[str, int]] = set()
        total_polygon_vertices = 0
        for polygon in self.mesh_polygons:
            if not isinstance(polygon, DebugPolygon):
                raise NavigationContractError(
                    "mesh_polygons require DebugPolygon values"
                )
            if polygon.polygon_ref in polygon_refs:
                raise NavigationContractError("debug polygon refs must be unique")
            source_polygon_key = (
                polygon.source_tile_id,
                polygon.source_polygon_index,
            )
            if source_polygon_key in source_polygon_keys:
                raise NavigationContractError(
                    "debug source tile/polygon indices must be unique"
                )
            if any(not self.bounds.contains(vertex) for vertex in polygon.vertices):
                raise NavigationContractError("debug polygon lies outside bounds")
            source_tile = tile_evidence.get(polygon.source_tile_id)
            if source_tile is None:
                raise NavigationContractError(
                    "debug polygon has no referenced source tile evidence"
                )
            if any(
                not source_tile.bounds.contains(vertex)
                for vertex in polygon.vertices
            ):
                raise NavigationContractError(
                    "debug polygon leaves its referenced source tile bounds"
                )
            polygon_refs.add(polygon.polygon_ref)
            source_polygon_keys.add(source_polygon_key)
            total_polygon_vertices += len(polygon.vertices)
        if total_polygon_vertices > MAX_DEBUG_TOTAL_POLYGON_VERTICES:
            raise NavigationContractError(
                "debug snapshot exceeds the global polygon-vertex budget"
            )
        if self.mode == "OFF":
            if any(
                (
                    self.tile_hashes,
                    self.route_points,
                    self.mesh_polygons,
                    self.player_position is not None,
                    self.target_position is not None,
                    self.uncertainty_radius is not None,
                )
            ):
                raise NavigationContractError("OFF snapshots cannot contain render data")
        elif self.mode == "ROUTE":
            if (
                len(self.route_points) < 2
                or self.mesh_polygons
                or not self.tile_hashes
                or self.player_position is None
            ):
                raise NavigationContractError(
                    "ROUTE snapshots require pose, tile hashes and route only"
                )
        elif not self.tile_hashes or not self.mesh_polygons:
            raise NavigationContractError(
                "MESH snapshots require tile hashes and mesh polygons"
            )
        if not isinstance(self.provenance, NavigationProvenance):
            raise NavigationContractError("debug snapshot requires provenance")
        if self.provenance.origin not in {"navigation_runtime", *ORACLE_ORIGINS}:
            raise NavigationContractError("unsupported debug snapshot provenance")
        expected_scope = (
            "unpromoted_evaluation_only"
            if self.binding.decision_context == "champion"
            else "lab_evaluation_only"
        )
        if self.provenance.scope != expected_scope:
            raise NavigationContractError(
                "configured-only debug binding cannot claim promoted decision scope"
            )
        if (
            self.binding.decision_context == "champion"
            and self.navigation_mesh_artifact_scope.decision_scope
            != "unpromoted_evaluation_only"
        ):
            raise NavigationContractError(
                "Champion debug cannot bind a LAB or synthetic navigation mesh"
            )
        if self.provenance.origin in ORACLE_ORIGINS and (
            self.binding.decision_context != "lab_clone"
            or self.navigation_mesh_artifact_scope.decision_scope
            != "lab_evaluation_only"
        ):
            raise NavigationContractError(
                "server and LAB oracle snapshots are LAB evaluation only"
            )
        _validate_creation_time(self.created_at, self.provenance)

    def unsigned_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "format": self.format,
            "format_version": self.format_version,
            "hash_wire_format": HASH_WIRE_FORMAT,
            "snapshot_id": self.snapshot_id,
            "mode": self.mode,
            "view_kind": "top_down",
            "purpose": "debug_visualization_only",
            "target_profile": self.target_profile,
            "actor_binding": self.binding.to_record(),
            "authorization_sha256": self.authorization_sha256.upper(),
            "client_build": self.client_build,
            "build_signature": self.build_signature,
            "map_ref": self.map_ref,
            "map_signature": self.map_signature,
            "ordered_asset_manifest_sha256": self.ordered_asset_manifest_sha256.lower(),
            "navigation_mesh_content_sha256": self.navigation_mesh_content_sha256.lower(),
            "navigation_mesh_artifact_scope": (
                self.navigation_mesh_artifact_scope.to_record()
            ),
            "recast_pin": self.recast_pin.lower(),
            "agent_profile_hash": self.agent_profile_hash.lower(),
            "coordinate_system": self.coordinate_system.to_record(),
            "bounds": self.bounds.to_record(),
            "tile_hashes": [tile_hash.to_record() for tile_hash in self.tile_hashes],
            "player_position": (
                None if self.player_position is None else self.player_position.to_record()
            ),
            "target_position": (
                None if self.target_position is None else self.target_position.to_record()
            ),
            "uncertainty_radius": (
                None
                if self.uncertainty_radius is None
                else float(self.uncertainty_radius)
            ),
            "route_points": [point.to_record() for point in self.route_points],
            "mesh_polygons": [polygon.to_record() for polygon in self.mesh_polygons],
            "provenance": self.provenance.to_record(),
            "render_only": True,
            "decision_input": False,
            "execution_authority": False,
            "created_at": self.created_at,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_record_sha256(self.unsigned_record())

    def to_record(self) -> dict[str, object]:
        record = self.unsigned_record()
        record["content_sha256"] = self.content_sha256
        return record


def _require_exact_keys(name: str, value: Any, expected: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise NavigationContractError(f"{name} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise NavigationContractError(
            f"{name} fields mismatch; missing={missing}, extra={extra}"
        )
    return value


def _require_raw_array(
    name: str, value: Any, *, minimum: int, maximum: int
) -> list[Any]:
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise NavigationContractError(
            f"{name} must be an array with between {minimum} and {maximum} items"
        )
    return value


def _require_raw_string(name: str, value: Any) -> str:
    if type(value) is not str:
        raise NavigationContractError(f"{name} must be a string")
    return value


def _require_raw_float(name: str, value: Any) -> float:
    if type(value) is int:
        if not -MAX_SAFE_CANONICAL_INTEGER <= value <= MAX_SAFE_CANONICAL_INTEGER:
            raise NavigationContractError(
                f"{name} integer must fit the exact IEEE-754 range"
            )
        return float(value)
    if type(value) is not float or not isfinite(value):
        raise NavigationContractError(f"{name} must be a finite binary64 number")
    return float(value)


def _decode_vector(value: Any, name: str) -> Vector3:
    record = _require_exact_keys(name, value, {"x", "y", "z"})
    return Vector3(
        _require_raw_float(f"{name}.x", record["x"]),
        _require_raw_float(f"{name}.y", record["y"]),
        _require_raw_float(f"{name}.z", record["z"]),
    )


def _decode_bounds(value: Any, name: str) -> Bounds3:
    record = _require_exact_keys(name, value, {"minimum", "maximum"})
    return Bounds3(
        _decode_vector(record["minimum"], f"{name}.minimum"),
        _decode_vector(record["maximum"], f"{name}.maximum"),
    )


def _decode_coordinate_system(value: Any) -> CoordinateSystem:
    record = _require_exact_keys(
        "coordinate_system",
        value,
        {
            "space_id",
            "units",
            "handedness",
            "axes",
            "triangle_winding",
            "world_to_nav_row_major",
        },
    )
    axes = _require_exact_keys("coordinate_system.axes", record["axes"], {"x", "y", "z"})
    matrix = _require_raw_array(
        "coordinate_system.world_to_nav_row_major",
        record["world_to_nav_row_major"],
        minimum=16,
        maximum=16,
    )
    return CoordinateSystem(
        space_id=_require_raw_string("coordinate_system.space_id", record["space_id"]),
        units=_require_raw_string("coordinate_system.units", record["units"]),
        handedness=_require_raw_string(
            "coordinate_system.handedness", record["handedness"]
        ),
        axis_x=_require_raw_string("coordinate_system.axes.x", axes["x"]),
        axis_y=_require_raw_string("coordinate_system.axes.y", axes["y"]),
        axis_z=_require_raw_string("coordinate_system.axes.z", axes["z"]),
        triangle_winding=_require_raw_string(
            "coordinate_system.triangle_winding", record["triangle_winding"]
        ),
        world_to_nav_row_major=tuple(
            _require_raw_float("coordinate_system matrix value", item) for item in matrix
        ),
    )


def _decode_artifact_scope(value: Any) -> ArtifactScope:
    record = _require_exact_keys(
        "artifact_scope", value, {"asset_trust", "promotion_state", "decision_scope"}
    )
    return ArtifactScope(
        asset_trust=_require_raw_string("asset_trust", record["asset_trust"]),
        promotion_state=_require_raw_string(
            "promotion_state", record["promotion_state"]
        ),
        decision_scope=_require_raw_string("decision_scope", record["decision_scope"]),
    )


def _decode_provenance(value: Any) -> NavigationProvenance:
    record = _require_exact_keys(
        "provenance",
        value,
        {
            "source_id",
            "origin",
            "scope",
            "capability",
            "evidence_refs",
            "observed_at",
            "confidence",
        },
    )
    refs = _require_raw_array(
        "provenance.evidence_refs",
        record["evidence_refs"],
        minimum=1,
        maximum=MAX_EVIDENCE_REFS,
    )
    return NavigationProvenance(
        source_id=_require_raw_string("provenance.source_id", record["source_id"]),
        origin=_require_raw_string("provenance.origin", record["origin"]),
        scope=_require_raw_string("provenance.scope", record["scope"]),
        capability=_require_raw_string("provenance.capability", record["capability"]),
        evidence_refs=tuple(
            _require_raw_string("provenance.evidence_ref", item) for item in refs
        ),
        observed_at=_require_raw_string("provenance.observed_at", record["observed_at"]),
        confidence=_require_raw_float("provenance.confidence", record["confidence"]),
    )


def _decode_actor_binding(value: Any) -> NavigationActorBinding:
    record = _require_exact_keys(
        "actor_binding",
        value,
        {
            "schema_version",
            "instance_id",
            "actor_role",
            "actor_id",
            "decision_context",
            "memory_namespace",
            "expected_character_name",
            "credential_alias",
            "binding_assurance",
        },
    )
    if record["schema_version"] != "1.0":
        raise NavigationContractError("actor_binding schema_version must be 1.0")
    assurance = _require_exact_keys(
        "actor_binding.binding_assurance",
        record["binding_assurance"],
        {"state", "evidence_refs"},
    )
    refs = _require_raw_array(
        "actor_binding.binding_assurance.evidence_refs",
        assurance["evidence_refs"],
        minimum=1,
        maximum=MAX_BINDING_EVIDENCE_REFS,
    )
    return NavigationActorBinding(
        instance_id=_require_raw_string("actor_binding.instance_id", record["instance_id"]),
        actor_role=_require_raw_string("actor_binding.actor_role", record["actor_role"]),
        actor_id=_require_raw_string("actor_binding.actor_id", record["actor_id"]),
        decision_context=_require_raw_string(
            "actor_binding.decision_context", record["decision_context"]
        ),
        memory_namespace=_require_raw_string(
            "actor_binding.memory_namespace", record["memory_namespace"]
        ),
        expected_character_name=_require_raw_string(
            "actor_binding.expected_character_name", record["expected_character_name"]
        ),
        credential_alias=_require_raw_string(
            "actor_binding.credential_alias", record["credential_alias"]
        ),
        binding_assurance_state=_require_raw_string(
            "actor_binding.binding_assurance.state", assurance["state"]
        ),
        binding_assurance_evidence_refs=tuple(
            _require_raw_string("binding assurance evidence_ref", item) for item in refs
        ),
    )


def _decode_geometry_triangle(value: Any) -> GeometryTriangle:
    record = _require_exact_keys(
        "geometry triangle", value, {"indices", "area", "material_ref", "source_ref"}
    )
    indices = _require_raw_array(
        "geometry triangle indices", record["indices"], minimum=3, maximum=3
    )
    return GeometryTriangle(
        indices=tuple(
            _require_bounded_int("triangle index", item, minimum=0, maximum=2**31 - 1)
            for item in indices
        ),
        area=_require_raw_string("geometry triangle area", record["area"]),
        material_ref=_require_raw_string(
            "geometry triangle material_ref", record["material_ref"]
        ),
        source_ref=_require_raw_string(
            "geometry triangle source_ref", record["source_ref"]
        ),
    )


def _decode_geometry_tile(value: Any) -> GeometryTile:
    record = _require_exact_keys(
        "geometry tile",
        value,
        {
            "hash_wire_format",
            "tile_id",
            "grid_x",
            "grid_y",
            "layer",
            "bounds",
            "vertices",
            "triangles",
            "source_asset_refs",
            "tile_sha256",
        },
    )
    if record["hash_wire_format"] != HASH_WIRE_FORMAT:
        raise NavigationContractError("geometry tile hash_wire_format mismatch")
    unsigned = {key: item for key, item in record.items() if key != "tile_sha256"}
    expected_hash = _require_sha256("geometry tile_sha256", record["tile_sha256"])
    if record["tile_sha256"] != expected_hash:
        raise NavigationContractError("geometry tile_sha256 must be lowercase canonical")
    if not hmac.compare_digest(expected_hash, canonical_record_sha256(unsigned)):
        raise NavigationContractError("geometry tile hash mismatch")
    vertices = _require_raw_array(
        "geometry tile vertices",
        record["vertices"],
        minimum=3,
        maximum=MAX_VERTICES_PER_GEOMETRY_TILE,
    )
    triangles = _require_raw_array(
        "geometry tile triangles",
        record["triangles"],
        minimum=1,
        maximum=MAX_TRIANGLES_PER_GEOMETRY_TILE,
    )
    refs = _require_raw_array(
        "geometry tile source_asset_refs",
        record["source_asset_refs"],
        minimum=1,
        maximum=MAX_SOURCE_ASSET_REFS,
    )
    return GeometryTile(
        tile_id=_require_raw_string("geometry tile_id", record["tile_id"]),
        grid_x=_require_bounded_int(
            "geometry grid_x", record["grid_x"], minimum=-(2**20), maximum=2**20
        ),
        grid_y=_require_bounded_int(
            "geometry grid_y", record["grid_y"], minimum=-(2**20), maximum=2**20
        ),
        layer=_require_bounded_int(
            "geometry layer", record["layer"], minimum=0, maximum=255
        ),
        bounds=_decode_bounds(record["bounds"], "geometry tile bounds"),
        vertices=tuple(
            _decode_vector(item, "geometry vertex") for item in vertices
        ),
        triangles=tuple(_decode_geometry_triangle(item) for item in triangles),
        source_asset_refs=tuple(
            _require_raw_string("source_asset_ref", item) for item in refs
        ),
    )


_GEOMETRY_KEYS = {
    "record_type",
    "schema_version",
    "format",
    "format_version",
    "hash_wire_format",
    "geometry_id",
    "target_profile",
    "client_build",
    "build_signature",
    "map_ref",
    "map_signature",
    "ordered_asset_manifest_sha256",
    "geometry_profile_id",
    "geometry_profile_hash",
    "coordinate_system",
    "bounds",
    "tile_count",
    "tiles",
    "artifact_scope",
    "provenance",
    "execution_authority",
    "created_at",
    "content_sha256",
}


def _decode_geometry(value: dict[str, Any]) -> NavigationGeometry:
    record = _require_exact_keys("navigation geometry", value, _GEOMETRY_KEYS)
    format_version = _require_bounded_int(
        "navigation geometry format_version",
        record["format_version"],
        minimum=PGEOM_FORMAT_VERSION,
        maximum=PGEOM_FORMAT_VERSION,
    )
    if (
        record["record_type"] != "navigation_geometry"
        or record["schema_version"] != CONTRACT_VERSION
        or record["format"] != "pgeom"
        or format_version != PGEOM_FORMAT_VERSION
        or record["hash_wire_format"] != HASH_WIRE_FORMAT
        or record["execution_authority"] is not False
    ):
        raise NavigationContractError("navigation geometry fixed fields are invalid")
    tiles = _require_raw_array(
        "navigation geometry tiles", record["tiles"], minimum=1, maximum=MAX_GEOMETRY_TILES
    )
    tile_count = _require_bounded_int(
        "geometry tile_count", record["tile_count"],
        minimum=1, maximum=MAX_GEOMETRY_TILES,
    )
    if tile_count != len(tiles):
        raise NavigationContractError("geometry tile_count does not match tiles")
    expected_hash = _require_sha256("content_sha256", record["content_sha256"])
    if record["content_sha256"] != expected_hash:
        raise NavigationContractError("content_sha256 must be lowercase canonical")
    unsigned = {key: item for key, item in record.items() if key != "content_sha256"}
    if not hmac.compare_digest(expected_hash, canonical_record_sha256(unsigned)):
        # Decode tiles as well so nested integrity failures remain explicit.
        for item in tiles:
            _decode_geometry_tile(item)
        raise NavigationContractError("navigation content hash mismatch")
    result = NavigationGeometry(
        geometry_id=_require_raw_string("geometry_id", record["geometry_id"]),
        target_profile=_require_raw_string("target_profile", record["target_profile"]),
        client_build=_require_raw_string("client_build", record["client_build"]),
        build_signature=_require_raw_string("build_signature", record["build_signature"]),
        map_ref=_require_raw_string("map_ref", record["map_ref"]),
        map_signature=_require_raw_string("map_signature", record["map_signature"]),
        ordered_asset_manifest_sha256=_require_raw_string(
            "ordered_asset_manifest_sha256", record["ordered_asset_manifest_sha256"]
        ),
        geometry_profile_id=_require_raw_string(
            "geometry_profile_id", record["geometry_profile_id"]
        ),
        geometry_profile_hash=_require_raw_string(
            "geometry_profile_hash", record["geometry_profile_hash"]
        ),
        coordinate_system=_decode_coordinate_system(record["coordinate_system"]),
        bounds=_decode_bounds(record["bounds"], "geometry bounds"),
        tiles=tuple(_decode_geometry_tile(item) for item in tiles),
        artifact_scope=_decode_artifact_scope(record["artifact_scope"]),
        provenance=_decode_provenance(record["provenance"]),
        created_at=_require_raw_string("created_at", record["created_at"]),
    )
    if result.to_record() != record:
        raise NavigationContractError("navigation geometry is not canonical")
    return result


def _decode_navigation_tile(value: Any) -> NavigationMeshTile:
    record = _require_exact_keys(
        "navigation tile",
        value,
        {
            "tile_id",
            "grid_x",
            "grid_y",
            "layer",
            "bounds",
            "vertex_count",
            "polygon_count",
            "binary_artifact_ref",
            "data_size_bytes",
            "tile_sha256",
        },
    )
    return NavigationMeshTile(
        tile_id=_require_raw_string("navigation tile_id", record["tile_id"]),
        grid_x=_require_bounded_int(
            "navigation grid_x", record["grid_x"], minimum=-(2**20), maximum=2**20
        ),
        grid_y=_require_bounded_int(
            "navigation grid_y", record["grid_y"], minimum=-(2**20), maximum=2**20
        ),
        layer=_require_bounded_int(
            "navigation layer", record["layer"], minimum=0, maximum=255
        ),
        bounds=_decode_bounds(record["bounds"], "navigation tile bounds"),
        vertex_count=_require_bounded_int(
            "vertex_count",
            record["vertex_count"],
            minimum=3,
            maximum=MAX_VERTICES_PER_NAVIGATION_TILE,
        ),
        polygon_count=_require_bounded_int(
            "polygon_count",
            record["polygon_count"],
            minimum=1,
            maximum=MAX_POLYGONS_PER_NAVIGATION_TILE,
        ),
        binary_artifact_ref=_require_raw_string(
            "binary_artifact_ref", record["binary_artifact_ref"]
        ),
        data_size_bytes=_require_bounded_int(
            "data_size_bytes",
            record["data_size_bytes"],
            minimum=1,
            maximum=MAX_NAVIGATION_TILE_BYTES,
        ),
        tile_sha256=_require_raw_string("tile_sha256", record["tile_sha256"]),
    )


_MESH_KEYS = {
    "record_type",
    "schema_version",
    "format",
    "format_version",
    "hash_wire_format",
    "mesh_id",
    "geometry_content_sha256",
    "target_profile",
    "client_build",
    "build_signature",
    "map_ref",
    "map_signature",
    "ordered_asset_manifest_sha256",
    "recast_pin",
    "agent_profile_id",
    "agent_profile_hash",
    "coordinate_system",
    "bounds",
    "tile_count",
    "total_payload_bytes",
    "tiles",
    "artifact_scope",
    "provenance",
    "execution_authority",
    "created_at",
    "content_sha256",
}


def _decode_mesh(value: dict[str, Any]) -> NavigationMesh:
    record = _require_exact_keys("navigation mesh", value, _MESH_KEYS)
    format_version = _require_bounded_int(
        "navigation mesh format_version",
        record["format_version"],
        minimum=PNAV_FORMAT_VERSION,
        maximum=PNAV_FORMAT_VERSION,
    )
    if (
        record["record_type"] != "navigation_mesh"
        or record["schema_version"] != CONTRACT_VERSION
        or record["format"] != "pnav"
        or format_version != PNAV_FORMAT_VERSION
        or record["hash_wire_format"] != HASH_WIRE_FORMAT
        or record["execution_authority"] is not False
    ):
        raise NavigationContractError("navigation mesh fixed fields are invalid")
    tiles = _require_raw_array(
        "navigation mesh tiles", record["tiles"], minimum=1, maximum=MAX_NAVIGATION_TILES
    )
    tile_count = _require_bounded_int(
        "navigation tile_count", record["tile_count"],
        minimum=1, maximum=MAX_NAVIGATION_TILES,
    )
    if tile_count != len(tiles):
        raise NavigationContractError("navigation tile_count does not match tiles")
    decoded_tiles = tuple(_decode_navigation_tile(item) for item in tiles)
    total_payload = sum(tile.data_size_bytes for tile in decoded_tiles)
    declared_total_payload = _require_bounded_int(
        "total_payload_bytes", record["total_payload_bytes"],
        minimum=1, maximum=MAX_NAVIGATION_TOTAL_BYTES,
    )
    if declared_total_payload != total_payload:
        raise NavigationContractError("total_payload_bytes does not match navigation tiles")
    expected_hash = _require_sha256("content_sha256", record["content_sha256"])
    if record["content_sha256"] != expected_hash:
        raise NavigationContractError("content_sha256 must be lowercase canonical")
    unsigned = {key: item for key, item in record.items() if key != "content_sha256"}
    if not hmac.compare_digest(expected_hash, canonical_record_sha256(unsigned)):
        raise NavigationContractError("navigation content hash mismatch")
    result = NavigationMesh(
        mesh_id=_require_raw_string("mesh_id", record["mesh_id"]),
        geometry_content_sha256=_require_raw_string(
            "geometry_content_sha256", record["geometry_content_sha256"]
        ),
        target_profile=_require_raw_string("target_profile", record["target_profile"]),
        client_build=_require_raw_string("client_build", record["client_build"]),
        build_signature=_require_raw_string("build_signature", record["build_signature"]),
        map_ref=_require_raw_string("map_ref", record["map_ref"]),
        map_signature=_require_raw_string("map_signature", record["map_signature"]),
        ordered_asset_manifest_sha256=_require_raw_string(
            "ordered_asset_manifest_sha256", record["ordered_asset_manifest_sha256"]
        ),
        recast_pin=_require_raw_string("recast_pin", record["recast_pin"]),
        agent_profile_id=_require_raw_string(
            "agent_profile_id", record["agent_profile_id"]
        ),
        agent_profile_hash=_require_raw_string(
            "agent_profile_hash", record["agent_profile_hash"]
        ),
        coordinate_system=_decode_coordinate_system(record["coordinate_system"]),
        bounds=_decode_bounds(record["bounds"], "navigation mesh bounds"),
        tiles=decoded_tiles,
        artifact_scope=_decode_artifact_scope(record["artifact_scope"]),
        provenance=_decode_provenance(record["provenance"]),
        created_at=_require_raw_string("created_at", record["created_at"]),
    )
    if result.to_record() != record:
        raise NavigationContractError("navigation mesh is not canonical")
    return result


def _decode_debug_tile_hash(value: Any) -> DebugTileHash:
    record = _require_exact_keys(
        "debug tile hash", value, {"tile_id", "tile_sha256", "bounds"}
    )
    return DebugTileHash(
        _require_raw_string("debug tile_id", record["tile_id"]),
        _require_raw_string("debug tile_sha256", record["tile_sha256"]),
        _decode_bounds(record["bounds"], "debug tile bounds"),
    )


def _decode_debug_polygon(value: Any) -> DebugPolygon:
    record = _require_exact_keys(
        "debug polygon",
        value,
        {
            "polygon_ref",
            "source_tile_id",
            "source_polygon_index",
            "vertices",
            "area",
            "flags",
            "traversal_cost",
            "blocked",
        },
    )
    vertices = _require_raw_array(
        "debug polygon vertices",
        record["vertices"],
        minimum=3,
        maximum=MAX_DEBUG_POLYGON_VERTICES,
    )
    flags = _require_raw_array(
        "debug polygon flags", record["flags"], minimum=0, maximum=MAX_DEBUG_FLAGS
    )
    if type(record["blocked"]) is not bool:
        raise NavigationContractError("debug polygon blocked must be boolean")
    return DebugPolygon(
        polygon_ref=_require_raw_string("polygon_ref", record["polygon_ref"]),
        source_tile_id=_require_raw_string(
            "source_tile_id", record["source_tile_id"]
        ),
        source_polygon_index=_require_bounded_int(
            "source_polygon_index",
            record["source_polygon_index"],
            minimum=0,
            maximum=MAX_POLYGONS_PER_NAVIGATION_TILE - 1,
        ),
        vertices=tuple(_decode_vector(item, "debug polygon vertex") for item in vertices),
        area=_require_raw_string("debug polygon area", record["area"]),
        flags=tuple(_require_raw_string("debug polygon flag", item) for item in flags),
        traversal_cost=_require_raw_float("traversal_cost", record["traversal_cost"]),
        blocked=record["blocked"],
    )


_DEBUG_KEYS = {
    "record_type",
    "schema_version",
    "format",
    "format_version",
    "hash_wire_format",
    "snapshot_id",
    "mode",
    "view_kind",
    "purpose",
    "target_profile",
    "actor_binding",
    "authorization_sha256",
    "client_build",
    "build_signature",
    "map_ref",
    "map_signature",
    "ordered_asset_manifest_sha256",
    "navigation_mesh_content_sha256",
    "navigation_mesh_artifact_scope",
    "recast_pin",
    "agent_profile_hash",
    "coordinate_system",
    "bounds",
    "tile_hashes",
    "player_position",
    "target_position",
    "uncertainty_radius",
    "route_points",
    "mesh_polygons",
    "provenance",
    "render_only",
    "decision_input",
    "execution_authority",
    "created_at",
    "content_sha256",
}


def _decode_debug(value: dict[str, Any]) -> NavigationDebugSnapshot:
    record = _require_exact_keys("navigation debug snapshot", value, _DEBUG_KEYS)
    format_version = _require_bounded_int(
        "navigation debug format_version",
        record["format_version"],
        minimum=DEBUG_SNAPSHOT_FORMAT_VERSION,
        maximum=DEBUG_SNAPSHOT_FORMAT_VERSION,
    )
    if (
        record["record_type"] != "navigation_debug_snapshot"
        or record["schema_version"] != CONTRACT_VERSION
        or record["format"] != "navigation-debug-snapshot"
        or format_version != DEBUG_SNAPSHOT_FORMAT_VERSION
        or record["hash_wire_format"] != HASH_WIRE_FORMAT
        or record["view_kind"] != "top_down"
        or record["purpose"] != "debug_visualization_only"
        or record["render_only"] is not True
        or record["decision_input"] is not False
        or record["execution_authority"] is not False
    ):
        raise NavigationContractError("navigation debug fixed fields are invalid")
    tile_hashes = _require_raw_array(
        "debug tile_hashes",
        record["tile_hashes"],
        minimum=0,
        maximum=MAX_DEBUG_TILE_HASHES,
    )
    route_points = _require_raw_array(
        "debug route_points",
        record["route_points"],
        minimum=0,
        maximum=MAX_DEBUG_ROUTE_POINTS,
    )
    polygons = _require_raw_array(
        "debug mesh_polygons",
        record["mesh_polygons"],
        minimum=0,
        maximum=MAX_DEBUG_POLYGONS,
    )
    expected_hash = _require_sha256("content_sha256", record["content_sha256"])
    if record["content_sha256"] != expected_hash:
        raise NavigationContractError("content_sha256 must be lowercase canonical")
    unsigned = {key: item for key, item in record.items() if key != "content_sha256"}
    if not hmac.compare_digest(expected_hash, canonical_record_sha256(unsigned)):
        raise NavigationContractError("navigation content hash mismatch")
    player = (
        None
        if record["player_position"] is None
        else _decode_vector(record["player_position"], "player_position")
    )
    target = (
        None
        if record["target_position"] is None
        else _decode_vector(record["target_position"], "target_position")
    )
    uncertainty = record["uncertainty_radius"]
    if uncertainty is not None:
        uncertainty = _require_raw_float("uncertainty_radius", uncertainty)
    result = NavigationDebugSnapshot(
        snapshot_id=_require_raw_string("snapshot_id", record["snapshot_id"]),
        mode=_require_raw_string("mode", record["mode"]),
        binding=_decode_actor_binding(record["actor_binding"]),
        authorization_sha256=_require_raw_string(
            "authorization_sha256", record["authorization_sha256"]
        ),
        target_profile=_require_raw_string("target_profile", record["target_profile"]),
        client_build=_require_raw_string("client_build", record["client_build"]),
        build_signature=_require_raw_string("build_signature", record["build_signature"]),
        map_ref=_require_raw_string("map_ref", record["map_ref"]),
        map_signature=_require_raw_string("map_signature", record["map_signature"]),
        ordered_asset_manifest_sha256=_require_raw_string(
            "ordered_asset_manifest_sha256", record["ordered_asset_manifest_sha256"]
        ),
        navigation_mesh_content_sha256=_require_raw_string(
            "navigation_mesh_content_sha256", record["navigation_mesh_content_sha256"]
        ),
        navigation_mesh_artifact_scope=_decode_artifact_scope(
            record["navigation_mesh_artifact_scope"]
        ),
        recast_pin=_require_raw_string("recast_pin", record["recast_pin"]),
        agent_profile_hash=_require_raw_string(
            "agent_profile_hash", record["agent_profile_hash"]
        ),
        coordinate_system=_decode_coordinate_system(record["coordinate_system"]),
        bounds=_decode_bounds(record["bounds"], "debug bounds"),
        tile_hashes=tuple(_decode_debug_tile_hash(item) for item in tile_hashes),
        player_position=player,
        target_position=target,
        uncertainty_radius=uncertainty,
        route_points=tuple(_decode_vector(item, "route point") for item in route_points),
        mesh_polygons=tuple(_decode_debug_polygon(item) for item in polygons),
        provenance=_decode_provenance(record["provenance"]),
        created_at=_require_raw_string("created_at", record["created_at"]),
    )
    if result.to_record() != record:
        raise NavigationContractError("navigation debug snapshot is not canonical")
    return result


NavigationRecord = NavigationGeometry | NavigationMesh | NavigationDebugSnapshot


def validate_navigation_record_semantics(value: Mapping[str, Any]) -> NavigationRecord:
    """Validate an already-parsed raw record without copying it first."""

    _preflight_builtin_tree(value)
    assert type(value) is dict
    record_type = value.get("record_type")
    if record_type == "navigation_geometry":
        return _decode_geometry(value)
    if record_type == "navigation_mesh":
        return _decode_mesh(value)
    if record_type == "navigation_debug_snapshot":
        return _decode_debug(value)
    raise NavigationContractError("unsupported navigation record type")


_JSON_NUMBER = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:[.][0-9]+)?(?:[eE][+-]?[0-9]+)?"
)
_JSON_WHITESPACE = frozenset(" \t\r\n")
_JSON_ESCAPES = frozenset('"\\/bfnrt')


def _bounded_utf8_size(text: str) -> int:
    total = 0
    for character in text:
        total += _utf8_character_size(character)
        if total > MAX_NAVIGATION_RECORD_BYTES:
            raise NavigationContractError("navigation JSON exceeds the byte budget")
    return total


class _JsonNodePreflight:
    """Grammar-aware JSON scan with an exact node count before json.loads."""

    __slots__ = ("text", "length", "index", "nodes", "string_bytes")

    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.index = 0
        self.nodes = 0
        self.string_bytes = 0

    def _skip_whitespace(self) -> None:
        while (
            self.index < self.length
            and self.text[self.index] in _JSON_WHITESPACE
        ):
            self.index += 1

    def _count_node(self, depth: int) -> None:
        if depth > MAX_NAVIGATION_NESTING_DEPTH:
            raise NavigationContractError("navigation JSON exceeds the nesting budget")
        self.nodes += 1
        if self.nodes > MAX_NAVIGATION_JSON_NODES:
            raise NavigationContractError(
                "navigation JSON exceeds the exact global node budget"
            )

    def _scan_string(self) -> None:
        if self.index >= self.length or self.text[self.index] != '"':
            raise NavigationContractError("navigation JSON object key must be a string")
        self.index += 1
        while self.index < self.length:
            character = self.text[self.index]
            if character == '"':
                self.index += 1
                return
            if ord(character) < 0x20:
                raise NavigationContractError(
                    "navigation JSON string contains a control character"
                )
            self.string_bytes += _utf8_character_size(character)
            if self.string_bytes > MAX_NAVIGATION_STRING_BYTES:
                raise NavigationContractError(
                    "navigation JSON exceeds the global string-byte budget"
                )
            if character != "\\":
                self.index += 1
                continue
            self.index += 1
            if self.index >= self.length:
                raise NavigationContractError("navigation JSON string escape is incomplete")
            escape = self.text[self.index]
            self.string_bytes += 1
            if escape == "u":
                if self.index + 4 >= self.length or any(
                    item not in "0123456789abcdefABCDEF"
                    for item in self.text[self.index + 1 : self.index + 5]
                ):
                    raise NavigationContractError(
                        "navigation JSON unicode escape is invalid"
                    )
                self.string_bytes += 4
                self.index += 5
            elif escape in _JSON_ESCAPES:
                self.index += 1
            else:
                raise NavigationContractError("navigation JSON string escape is invalid")
            if self.string_bytes > MAX_NAVIGATION_STRING_BYTES:
                raise NavigationContractError(
                    "navigation JSON exceeds the global string-byte budget"
                )
        raise NavigationContractError("navigation JSON string is incomplete")

    def _scan_value(self, depth: int) -> None:
        self._skip_whitespace()
        self._count_node(depth)
        if self.index >= self.length:
            raise NavigationContractError("navigation JSON value is incomplete")
        character = self.text[self.index]
        if character == "{":
            self.index += 1
            self._skip_whitespace()
            if self.index < self.length and self.text[self.index] == "}":
                self.index += 1
                return
            while True:
                self._count_node(depth + 1)
                self._scan_string()
                self._skip_whitespace()
                if self.index >= self.length or self.text[self.index] != ":":
                    raise NavigationContractError(
                        "navigation JSON object key is missing a colon"
                    )
                self.index += 1
                self._scan_value(depth + 1)
                self._skip_whitespace()
                if self.index < self.length and self.text[self.index] == "}":
                    self.index += 1
                    return
                if self.index >= self.length or self.text[self.index] != ",":
                    raise NavigationContractError(
                        "navigation JSON object is missing a comma"
                    )
                self.index += 1
                self._skip_whitespace()
        elif character == "[":
            self.index += 1
            self._skip_whitespace()
            if self.index < self.length and self.text[self.index] == "]":
                self.index += 1
                return
            while True:
                self._scan_value(depth + 1)
                self._skip_whitespace()
                if self.index < self.length and self.text[self.index] == "]":
                    self.index += 1
                    return
                if self.index >= self.length or self.text[self.index] != ",":
                    raise NavigationContractError(
                        "navigation JSON array is missing a comma"
                    )
                self.index += 1
        elif character == '"':
            self._scan_string()
        elif self.text.startswith("true", self.index):
            self.index += 4
        elif self.text.startswith("false", self.index):
            self.index += 5
        elif self.text.startswith("null", self.index):
            self.index += 4
        elif any(
            self.text.startswith(token, self.index)
            for token in ("NaN", "Infinity", "-Infinity")
        ):
            raise NavigationContractError("navigation JSON contains a non-finite number")
        else:
            match = _JSON_NUMBER.match(self.text, self.index)
            if match is None:
                raise NavigationContractError("navigation JSON contains an invalid value")
            if match.end() - self.index > MAX_NAVIGATION_NUMBER_LEXEME_BYTES:
                raise NavigationContractError(
                    "navigation JSON number exceeds the lexeme budget"
                )
            self.index = match.end()

    def run(self) -> None:
        self._skip_whitespace()
        self._scan_value(0)
        self._skip_whitespace()
        if self.index != self.length:
            raise NavigationContractError("navigation JSON has trailing content")


def _preflight_json_text(text: str, *, utf8_size: int) -> str:
    if not text or utf8_size > MAX_NAVIGATION_RECORD_BYTES:
        raise NavigationContractError("navigation JSON exceeds the byte budget")
    if text.startswith("\ufeff"):
        raise NavigationContractError("navigation JSON must not contain a BOM")
    _JsonNodePreflight(text).run()
    return text


def _preflight_json_bytes(raw: bytes) -> str:
    if not raw or len(raw) > MAX_NAVIGATION_RECORD_BYTES:
        raise NavigationContractError("navigation JSON exceeds the byte budget")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise NavigationContractError("navigation JSON must not contain a BOM")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise NavigationContractError("navigation JSON must be UTF-8") from error
    return _preflight_json_text(text, utf8_size=len(raw))


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NavigationContractError(f"navigation JSON repeats object key: {key}")
        result[key] = value
    return result


def _parse_bounded_json_int(value: str) -> int:
    if len(value) > MAX_NAVIGATION_NUMBER_LEXEME_BYTES:
        raise NavigationContractError("navigation JSON integer exceeds the lexeme budget")
    result = int(value, 10)
    if not -MAX_SAFE_CANONICAL_INTEGER <= result <= MAX_SAFE_CANONICAL_INTEGER:
        raise NavigationContractError(
            "navigation JSON integer exceeds the exact IEEE-754 range"
        )
    return result


def _parse_bounded_json_float(value: str) -> float:
    if len(value) > MAX_NAVIGATION_NUMBER_LEXEME_BYTES:
        raise NavigationContractError("navigation JSON number exceeds the lexeme budget")
    result = float(value)
    if not isfinite(result):
        raise NavigationContractError("navigation JSON number must be finite binary64")
    return result


def decode_navigation_record(raw: bytes | bytearray | memoryview | str) -> NavigationRecord:
    """Bounded UTF-8 JSON decoder followed by the semantic raw validator."""

    if type(raw) is str:
        text = _preflight_json_text(raw, utf8_size=_bounded_utf8_size(raw))
    elif type(raw) is bytes:
        text = _preflight_json_bytes(raw)
    elif type(raw) is bytearray:
        if len(raw) > MAX_NAVIGATION_RECORD_BYTES:
            raise NavigationContractError("navigation JSON exceeds the byte budget")
        text = _preflight_json_bytes(bytes(raw))
    elif type(raw) is memoryview:
        try:
            raw_size = raw.nbytes
        except ValueError as error:
            raise NavigationContractError(
                "navigation JSON memory view is unavailable"
            ) from error
        if raw_size > MAX_NAVIGATION_RECORD_BYTES:
            raise NavigationContractError("navigation JSON exceeds the byte budget")
        try:
            raw_bytes = raw.tobytes()
        except (TypeError, ValueError) as error:
            raise NavigationContractError(
                "navigation JSON memory view cannot be read"
            ) from error
        text = _preflight_json_bytes(raw_bytes)
    else:
        raise NavigationContractError("navigation JSON input must be bytes or text")
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_int=_parse_bounded_json_int,
            parse_float=_parse_bounded_json_float,
            parse_constant=lambda value: (_ for _ in ()).throw(
                NavigationContractError(f"non-finite JSON constant: {value}")
            ),
        )
    except NavigationContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise NavigationContractError("navigation JSON cannot be decoded") from error
    return validate_navigation_record_semantics(parsed)


def verify_navigation_record_integrity(value: Mapping[str, Any]) -> None:
    """Verify schema semantics and all canonical manifest hashes without I/O."""

    validate_navigation_record_semantics(value)


def _coerce_geometry(value: NavigationGeometry | Mapping[str, Any]) -> NavigationGeometry:
    if isinstance(value, NavigationGeometry):
        return value
    decoded = validate_navigation_record_semantics(value)
    if not isinstance(decoded, NavigationGeometry):
        raise NavigationContractError("expected a pgeom record")
    return decoded


def _coerce_mesh(value: NavigationMesh | Mapping[str, Any]) -> NavigationMesh:
    if isinstance(value, NavigationMesh):
        return value
    decoded = validate_navigation_record_semantics(value)
    if not isinstance(decoded, NavigationMesh):
        raise NavigationContractError("expected a pnav record")
    return decoded


def _coerce_debug(
    value: NavigationDebugSnapshot | Mapping[str, Any],
) -> NavigationDebugSnapshot:
    if isinstance(value, NavigationDebugSnapshot):
        return value
    decoded = validate_navigation_record_semantics(value)
    if not isinstance(decoded, NavigationDebugSnapshot):
        raise NavigationContractError("expected a navigation debug snapshot")
    return decoded


def verify_geometry_mesh_binding(
    geometry_value: NavigationGeometry | Mapping[str, Any],
    mesh_value: NavigationMesh | Mapping[str, Any],
) -> None:
    """Require one pnav manifest to be an exact derivative of one pgeom."""

    geometry = _coerce_geometry(geometry_value)
    mesh = _coerce_mesh(mesh_value)
    if not hmac.compare_digest(mesh.geometry_content_sha256, geometry.content_sha256):
        raise NavigationContractError("pnav geometry_content_sha256 is not the pgeom hash")
    identity_fields = (
        "target_profile",
        "client_build",
        "build_signature",
        "map_ref",
        "map_signature",
        "ordered_asset_manifest_sha256",
    )
    if any(getattr(mesh, field) != getattr(geometry, field) for field in identity_fields):
        raise NavigationContractError("pgeom and pnav identity fields do not match")
    if mesh.coordinate_system.to_record() != geometry.coordinate_system.to_record():
        raise NavigationContractError("pgeom and pnav coordinate systems do not match")
    if mesh.bounds != geometry.bounds:
        raise NavigationContractError("pgeom and pnav bounds do not match")
    if mesh.artifact_scope != geometry.artifact_scope:
        raise NavigationContractError("pgeom and pnav artifact scopes do not match")
    geometry_tiles = {
        (tile.grid_x, tile.grid_y, tile.layer): tile for tile in geometry.tiles
    }
    mesh_coordinates = {
        (tile.grid_x, tile.grid_y, tile.layer) for tile in mesh.tiles
    }
    if mesh_coordinates != set(geometry_tiles):
        raise NavigationContractError(
            "pgeom and pnav require a full-tile coordinate bijection in v1"
        )
    for tile in mesh.tiles:
        source = geometry_tiles.get((tile.grid_x, tile.grid_y, tile.layer))
        if source is None or source.bounds != tile.bounds:
            raise NavigationContractError("pnav tile has no exact pgeom source tile")


def verify_mesh_debug_binding(
    mesh_value: NavigationMesh | Mapping[str, Any],
    debug_value: NavigationDebugSnapshot | Mapping[str, Any],
) -> None:
    """Require a render-only snapshot to name the exact pnav it displays."""

    mesh = _coerce_mesh(mesh_value)
    debug = _coerce_debug(debug_value)
    if not hmac.compare_digest(debug.navigation_mesh_content_sha256, mesh.content_sha256):
        raise NavigationContractError("debug snapshot does not name the exact pnav hash")
    identity_fields = (
        "target_profile",
        "client_build",
        "build_signature",
        "map_ref",
        "map_signature",
        "ordered_asset_manifest_sha256",
        "recast_pin",
        "agent_profile_hash",
    )
    if any(getattr(debug, field) != getattr(mesh, field) for field in identity_fields):
        raise NavigationContractError("pnav and debug identity fields do not match")
    if debug.coordinate_system.to_record() != mesh.coordinate_system.to_record():
        raise NavigationContractError("pnav and debug coordinate systems do not match")
    if debug.bounds != mesh.bounds:
        raise NavigationContractError("pnav and debug bounds do not match")
    if debug.navigation_mesh_artifact_scope != mesh.artifact_scope:
        raise NavigationContractError("pnav and debug artifact scopes do not match")
    if (
        debug.binding.decision_context == "champion"
        and mesh.artifact_scope.decision_scope != "unpromoted_evaluation_only"
    ):
        raise NavigationContractError(
            "Champion debug cannot bind a LAB or synthetic navigation mesh"
        )
    mesh_tiles = {tile.tile_id: tile for tile in mesh.tiles}
    for reference in debug.tile_hashes:
        expected = mesh_tiles.get(reference.tile_id)
        if (
            expected is None
            or not hmac.compare_digest(
                expected.tile_sha256.lower(), reference.tile_sha256.lower()
            )
            or expected.bounds != reference.bounds
        ):
            raise NavigationContractError("debug tile hash is not bound to the exact pnav tile")
    for polygon in debug.mesh_polygons:
        source_tile = mesh_tiles.get(polygon.source_tile_id)
        if (
            source_tile is None
            or polygon.source_polygon_index >= source_tile.polygon_count
        ):
            raise NavigationContractError(
                "debug polygon index is not evidenced by the referenced pnav payload"
            )


def verify_navigation_artifact_chain(
    geometry_value: NavigationGeometry | Mapping[str, Any],
    mesh_value: NavigationMesh | Mapping[str, Any],
    debug_value: NavigationDebugSnapshot | Mapping[str, Any],
) -> None:
    verify_geometry_mesh_binding(geometry_value, mesh_value)
    verify_mesh_debug_binding(mesh_value, debug_value)


__all__ = [
    "ArtifactScope",
    "Bounds3",
    "CoordinateSystem",
    "DebugPolygon",
    "DebugTileHash",
    "GeometryTile",
    "GeometryTriangle",
    "NavigationActorBinding",
    "NavigationContractError",
    "NavigationDebugSnapshot",
    "NavigationGeometry",
    "NavigationMesh",
    "NavigationMeshTile",
    "NavigationProvenance",
    "NavigationRecord",
    "ORACLE_ORIGINS",
    "PINNED_RECAST_COMMIT",
    "HASH_WIRE_FORMAT",
    "Vector3",
    "canonical_json_bytes",
    "canonical_wire_bytes",
    "canonical_record_sha256",
    "decode_navigation_record",
    "validate_navigation_record_semantics",
    "verify_geometry_mesh_binding",
    "verify_mesh_debug_binding",
    "verify_navigation_artifact_chain",
    "verify_navigation_record_integrity",
    "verify_navigation_tile_payload",
]
