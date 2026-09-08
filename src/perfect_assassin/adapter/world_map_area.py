from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import hmac
import json
from math import isfinite
from pathlib import Path
import re
import struct
from typing import Any, Mapping

from perfect_assassin.adapter.coordinate_hud import validate_valid_observation_semantics
from perfect_assassin.contract_validation import ContractValidator


_WDBC_HEADER = struct.Struct("<4s4I")
_WORLD_MAP_AREA_ROW = struct.Struct("<IIIIffffi")
_RECORD_FINGERPRINT_ROW = struct.Struct("<IIIffffiI")
_WDBC_MAGIC = b"WDBC"
_EXPECTED_FIELD_COUNT = 9
_EXPECTED_RECORD_SIZE = 36
_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
_PROFILE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "world-map-area-profile.schema.json"
)
_COORDINATE_HUD_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "contracts" / "coordinate-hud.schema.json"
)
_CHAMPION_PROFILE_PINS: dict[str, object] = {
    "profile": "world_map_area_tbc243_8606",
    "profile_version": "0.2.0",
    "target_profile": "tbc_243_lab",
    "client_build": "2.4.3.8606",
    "build_signature": (
        "wow-tbc-2.4.3.8606-enGB:sha256:"
        "406DA0C1C22D6E9121FD3BC17740A0D013660A03748CFE2A235768B8C574D3E6"
    ),
    "asset_name": "WorldMapArea.dbc",
    "asset_relative_path": "dbc/WorldMapArea.dbc",
    "asset_sha256": (
        "918BF402A83BAA78B0D35F0978BC760683291EE8CF48D7CE8C90E3814AA1BC7B"
    ),
    "record_fingerprint_sha256": (
        "82CB76957FC8BB0A6DB94AC1F179BE5EA3B96033AEA02ED3B597D030D9A66215"
    ),
    "map_bindings": [
        {
            "continent_index": 2,
            "zone_index": 25,
            "internal_name": "Tirisfal",
            "map_id": 0,
            "area_id": 85,
        }
    ],
    "coordinate_space": "wow_world_map_2d",
    "provenance_origin": "client_asset_calibration",
    "asset_location_policy": "external_user_extracted",
    "execution_authority": False,
}


class WorldMapAreaError(ValueError):
    """Raised when a client WorldMapArea asset cannot be trusted or resolved."""


@dataclass(frozen=True)
class ClientAssetCalibrationProvenance:
    """Pinned identity and trust scope of a WorldMapArea calibration source."""

    client_build: str
    build_signature: str
    asset_name: str
    asset_sha256: str
    origin: str
    scope: str
    profile: str | None = None
    profile_version: str | None = None
    target_profile: str | None = None
    execution_authority: bool = False

    def as_dict(self) -> dict[str, str | bool | None]:
        return {
            "origin": self.origin,
            "scope": self.scope,
            "client_build": self.client_build,
            "build_signature": self.build_signature,
            "asset_name": self.asset_name,
            "asset_sha256": self.asset_sha256,
            "profile": self.profile,
            "profile_version": self.profile_version,
            "target_profile": self.target_profile,
            "execution_authority": self.execution_authority,
        }


@dataclass(frozen=True)
class WorldMapAreaRecord:
    """One TBC WorldMapArea row, retaining patch-specific IDs in the adapter."""

    record_id: int
    map_id: int
    area_id: int
    internal_name: str
    loc_left: float
    loc_right: float
    loc_top: float
    loc_bottom: float
    virtual_map_id: int


@dataclass(frozen=True)
class WorldMapAreaBinding:
    """Versioned client UI map indices bound to one exact DBC record."""

    continent_index: int
    zone_index: int
    internal_name: str
    map_id: int
    area_id: int


@dataclass(frozen=True)
class WorldMapTransformUncertainty:
    """Conservative axis-aligned bounds for the 2D calibration result.

    Quantization is derived from the normalized input step. Source calibration
    uncertainty is deliberately optional: until it is measured for a build, the
    total uncertainty remains unknown rather than silently treating it as zero.
    """

    normalized_quantization_step: float
    quantization_radius_world_x: float
    quantization_radius_world_y: float
    source_radius_world_x: float | None
    source_radius_world_y: float | None
    total_radius_world_x: float | None
    total_radius_world_y: float | None
    source_uncertainty_state: str


@dataclass(frozen=True)
class WorldMapActorBindingAssuranceSource:
    """Truthful assurance attached to the configured actor route binding."""

    state: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class WorldMapActorBindingSource:
    """Immutable PA actor identity propagated from the source observation."""

    schema_version: str
    instance_id: str
    actor_role: str
    actor_id: str
    decision_context: str
    memory_namespace: str
    expected_character_name: str
    credential_alias: str
    binding_assurance: WorldMapActorBindingAssuranceSource


@dataclass(frozen=True)
class WorldMapPositionSource:
    """Immutable identity of the versioned position fact being transformed."""

    schema_version: str
    observation_id: str
    frame_id: str
    session_id: str
    target_profile: str
    authorization_sha256: str
    actor_binding: WorldMapActorBindingSource
    decision_context: str
    client_build: str
    build_signature: str
    coordinate_space: str
    continent_index: int
    zone_index: int
    captured_at: str
    observed_monotonic_s: float
    expires_monotonic_s: float
    confidence: float
    origin: str
    capture_origin: str
    capability: str
    scope: str
    profile_id: str
    profile_version: str
    profile_sha256: str
    profile_calibration_state: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class WorldMapCoordinateProvenance:
    """Composite provenance; calibration eligibility never upgrades a fact."""

    origin: str
    scope: str
    calibration: ClientAssetCalibrationProvenance
    position: WorldMapPositionSource
    evidence_refs: tuple[str, ...]
    execution_authority: bool = False


@dataclass(frozen=True)
class WorldMapCoordinate2D:
    """A client-asset-derived 2D coordinate; height is intentionally absent."""

    world_x: float
    world_y: float
    coordinate_space: str
    area: WorldMapAreaRecord
    uncertainty: WorldMapTransformUncertainty
    confidence: float
    provenance: WorldMapCoordinateProvenance


class WorldMapAreaTable:
    """Strict, hash-pinned reader for the TBC `WorldMapArea.dbc` client asset.

    The table converts the normalized current-zone map coordinates exposed by
    the client into WoW's 2D world-map axes. It is not a pose oracle: it neither
    reads server state nor invents terrain height.
    """

    __slots__ = ("_records", "_provenance", "_coordinate_space", "_map_bindings")

    def __init__(
        self,
        records: tuple[WorldMapAreaRecord, ...],
        provenance: ClientAssetCalibrationProvenance,
        *,
        coordinate_space: str = "wow_world_map_2d",
        map_bindings: tuple[WorldMapAreaBinding, ...] = (),
    ) -> None:
        if not records:
            raise WorldMapAreaError("WorldMapArea table contains no records")
        if provenance.execution_authority:
            raise WorldMapAreaError("WorldMapArea calibration cannot grant execution authority")
        if provenance.scope == "champion_eligible" and (
            provenance.origin != _CHAMPION_PROFILE_PINS["provenance_origin"]
            or provenance.profile != _CHAMPION_PROFILE_PINS["profile"]
            or provenance.profile_version != _CHAMPION_PROFILE_PINS["profile_version"]
            or provenance.target_profile != _CHAMPION_PROFILE_PINS["target_profile"]
            or provenance.client_build != _CHAMPION_PROFILE_PINS["client_build"]
            or provenance.build_signature != _CHAMPION_PROFILE_PINS["build_signature"]
            or provenance.asset_name != _CHAMPION_PROFILE_PINS["asset_name"]
            or provenance.asset_sha256.upper()
            != _CHAMPION_PROFILE_PINS["asset_sha256"]
            or self._record_fingerprint(records)
            != _CHAMPION_PROFILE_PINS["record_fingerprint_sha256"]
        ):
            raise WorldMapAreaError(
                "champion_eligible WorldMapArea provenance does not match the pinned profile"
            )
        if provenance.scope not in {
            "champion_eligible",
            "lab_evaluation_only",
            "fixture_only",
        }:
            raise WorldMapAreaError(f"Unsupported WorldMapArea scope: {provenance.scope}")
        if not isinstance(coordinate_space, str) or not coordinate_space:
            raise WorldMapAreaError("coordinate_space must be a non-empty string")
        validated_bindings = self._validated_bindings(records, map_bindings)
        if provenance.scope == "champion_eligible":
            expected_bindings = tuple(
                WorldMapAreaBinding(**binding)
                for binding in _CHAMPION_PROFILE_PINS["map_bindings"]
            )
            if validated_bindings != expected_bindings:
                raise WorldMapAreaError(
                    "champion_eligible map bindings do not match the pinned profile"
                )
        object.__setattr__(self, "_records", records)
        object.__setattr__(self, "_provenance", provenance)
        object.__setattr__(self, "_coordinate_space", coordinate_space)
        object.__setattr__(self, "_map_bindings", validated_bindings)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("WorldMapAreaTable is immutable")

    @property
    def records(self) -> tuple[WorldMapAreaRecord, ...]:
        return self._records

    @property
    def provenance(self) -> ClientAssetCalibrationProvenance:
        return self._provenance

    @property
    def map_bindings(self) -> tuple[WorldMapAreaBinding, ...]:
        return self._map_bindings

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        expected_sha256: str,
        client_build: str,
        build_signature: str,
        map_bindings: tuple[WorldMapAreaBinding, ...] = (),
    ) -> WorldMapAreaTable:
        """Load a directly supplied asset for LAB evaluation, never Champion use."""

        source = Path(path)
        try:
            payload = source.read_bytes()
        except OSError as error:
            raise WorldMapAreaError(f"Cannot read WorldMapArea asset: {source}") from error
        records, actual_sha256 = cls._verified_records(
            payload,
            expected_sha256=expected_sha256,
            client_build=client_build,
            build_signature=build_signature,
            asset_name=source.name,
        )
        return cls(
            records,
            ClientAssetCalibrationProvenance(
                client_build=client_build,
                build_signature=build_signature,
                asset_name=source.name,
                asset_sha256=actual_sha256,
                origin="client_asset_calibration",
                scope="lab_evaluation_only",
            ),
            map_bindings=map_bindings,
        )

    @classmethod
    def from_bytes(
        cls,
        payload: bytes,
        *,
        expected_sha256: str,
        client_build: str,
        build_signature: str,
        asset_name: str = "WorldMapArea.dbc",
        map_bindings: tuple[WorldMapAreaBinding, ...] = (),
    ) -> WorldMapAreaTable:
        """Load deterministic fixture bytes with fixture-only provenance.

        A caller-computed hash proves byte stability, not that the bytes came
        from an authorized client build, so this entry point can never produce
        Champion-eligible calibration.
        """

        records, actual_sha256 = cls._verified_records(
            payload,
            expected_sha256=expected_sha256,
            client_build=client_build,
            build_signature=build_signature,
            asset_name=asset_name,
        )
        return cls(
            records,
            ClientAssetCalibrationProvenance(
                client_build=client_build,
                build_signature=build_signature,
                asset_name=asset_name,
                asset_sha256=actual_sha256,
                origin="synthetic_fixture",
                scope="fixture_only",
            ),
            map_bindings=map_bindings,
        )

    @classmethod
    def from_profile(
        cls,
        profile_path: str | Path,
        *,
        asset_root: str | Path,
    ) -> WorldMapAreaTable:
        """Load the one contract-validated, build-pinned Champion asset profile."""

        source_profile = Path(profile_path)
        try:
            profile = json.loads(source_profile.read_text(encoding="utf-8"))
            ContractValidator(_PROFILE_SCHEMA_PATH).validate(profile)
        except (OSError, UnicodeError, ValueError) as error:
            raise WorldMapAreaError(
                f"WorldMapArea profile failed contract validation: {source_profile}"
            ) from error
        if profile != _CHAMPION_PROFILE_PINS:
            raise WorldMapAreaError(
                "WorldMapArea profile does not match the code-pinned Champion profile"
            )

        asset_path = cls._resolve_profile_asset(
            asset_root,
            profile["asset_relative_path"],
            profile["asset_name"],
        )
        try:
            payload = asset_path.read_bytes()
        except OSError as error:
            raise WorldMapAreaError(
                f"Cannot read profile-bound WorldMapArea asset: {asset_path}"
            ) from error
        records, actual_sha256 = cls._verified_records(
            payload,
            expected_sha256=profile["asset_sha256"],
            client_build=profile["client_build"],
            build_signature=profile["build_signature"],
            asset_name=profile["asset_name"],
        )
        provenance = ClientAssetCalibrationProvenance(
            client_build=profile["client_build"],
            build_signature=profile["build_signature"],
            asset_name=profile["asset_name"],
            asset_sha256=actual_sha256,
            origin=profile["provenance_origin"],
            scope="champion_eligible",
            profile=profile["profile"],
            profile_version=profile["profile_version"],
            target_profile=profile["target_profile"],
        )
        map_bindings = tuple(
            WorldMapAreaBinding(**binding) for binding in profile["map_bindings"]
        )
        return cls(
            records,
            provenance,
            coordinate_space=profile["coordinate_space"],
            map_bindings=map_bindings,
        )

    @classmethod
    def _verified_records(
        cls,
        payload: bytes,
        *,
        expected_sha256: str,
        client_build: str,
        build_signature: str,
        asset_name: str,
    ) -> tuple[tuple[WorldMapAreaRecord, ...], str]:
        normalized_sha256 = cls._validate_identity(
            expected_sha256,
            client_build,
            build_signature,
            asset_name,
        )
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(actual_sha256, normalized_sha256):
            raise WorldMapAreaError(
                "WorldMapArea SHA-256 mismatch: the client asset is not the pinned build asset"
            )
        return cls._parse(payload), actual_sha256

    @staticmethod
    def _resolve_profile_asset(
        asset_root: str | Path,
        asset_relative_path: str,
        asset_name: str,
    ) -> Path:
        if not isinstance(asset_relative_path, str) or not asset_relative_path:
            raise WorldMapAreaError("asset_relative_path must be a non-empty string")
        relative = Path(asset_relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise WorldMapAreaError("asset_relative_path must stay below asset_root")
        if relative.name != asset_name:
            raise WorldMapAreaError("asset_relative_path does not match asset_name")
        try:
            root = Path(asset_root).resolve(strict=True)
            if not root.is_dir():
                raise WorldMapAreaError("asset_root must resolve to a directory")
            candidate = (root / relative).resolve(strict=True)
        except OSError as error:
            raise WorldMapAreaError("WorldMapArea asset root or path does not exist") from error
        if not candidate.is_relative_to(root):
            raise WorldMapAreaError("WorldMapArea asset resolves outside asset_root")
        if not candidate.is_file():
            raise WorldMapAreaError("WorldMapArea profile asset must be a regular file")
        return candidate

    @staticmethod
    def _validate_identity(
        expected_sha256: str,
        client_build: str,
        build_signature: str,
        asset_name: str,
    ) -> str:
        if not isinstance(expected_sha256, str) or not _SHA256_PATTERN.fullmatch(
            expected_sha256
        ):
            raise WorldMapAreaError("expected_sha256 must be exactly 64 hexadecimal characters")
        for label, value in (
            ("client_build", client_build),
            ("build_signature", build_signature),
            ("asset_name", asset_name),
        ):
            if not isinstance(value, str) or not value.strip():
                raise WorldMapAreaError(f"{label} must be a non-empty string")
        return expected_sha256.lower()

    @staticmethod
    def _record_fingerprint(records: tuple[WorldMapAreaRecord, ...]) -> str:
        digest = hashlib.sha256()
        for record in records:
            encoded_name = record.internal_name.encode("utf-8")
            digest.update(
                _RECORD_FINGERPRINT_ROW.pack(
                    record.record_id,
                    record.map_id,
                    record.area_id,
                    record.loc_left,
                    record.loc_right,
                    record.loc_top,
                    record.loc_bottom,
                    record.virtual_map_id,
                    len(encoded_name),
                )
            )
            digest.update(encoded_name)
        return digest.hexdigest().upper()

    @staticmethod
    def _validated_bindings(
        records: tuple[WorldMapAreaRecord, ...],
        bindings: tuple[WorldMapAreaBinding, ...],
    ) -> tuple[WorldMapAreaBinding, ...]:
        if not isinstance(bindings, tuple):
            raise WorldMapAreaError("map_bindings must be an immutable tuple")
        seen_contexts: set[tuple[int, int]] = set()
        for binding in bindings:
            if not isinstance(binding, WorldMapAreaBinding):
                raise WorldMapAreaError(
                    "map_bindings must contain WorldMapAreaBinding values"
                )
            if any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 0 <= value <= 255
                for value in (binding.continent_index, binding.zone_index)
            ):
                raise WorldMapAreaError(
                    "map binding continent and zone indices must be uint8 values"
                )
            context = (binding.continent_index, binding.zone_index)
            if context in seen_contexts:
                raise WorldMapAreaError("map_bindings contain a duplicate client context")
            seen_contexts.add(context)
            matches = tuple(
                record
                for record in records
                if record.internal_name == binding.internal_name
                and record.map_id == binding.map_id
                and record.area_id == binding.area_id
            )
            if len(matches) != 1:
                raise WorldMapAreaError(
                    "map binding must resolve exactly one WorldMapArea record"
                )
        return bindings

    @staticmethod
    def _parse(payload: bytes) -> tuple[WorldMapAreaRecord, ...]:
        if len(payload) < _WDBC_HEADER.size:
            raise WorldMapAreaError("WorldMapArea asset is shorter than the WDBC header")
        magic, record_count, field_count, record_size, string_block_size = (
            _WDBC_HEADER.unpack_from(payload)
        )
        if magic != _WDBC_MAGIC:
            raise WorldMapAreaError("WorldMapArea asset has invalid WDBC magic")
        if field_count != _EXPECTED_FIELD_COUNT:
            raise WorldMapAreaError(
                f"WorldMapArea field count must be {_EXPECTED_FIELD_COUNT}, got {field_count}"
            )
        if record_size != _EXPECTED_RECORD_SIZE:
            raise WorldMapAreaError(
                f"WorldMapArea record size must be {_EXPECTED_RECORD_SIZE}, got {record_size}"
            )
        if record_count == 0:
            raise WorldMapAreaError("WorldMapArea table contains no records")
        if string_block_size == 0:
            raise WorldMapAreaError("WorldMapArea string block is empty")

        records_end = _WDBC_HEADER.size + (record_count * record_size)
        expected_size = records_end + string_block_size
        if len(payload) != expected_size:
            raise WorldMapAreaError(
                "WorldMapArea byte length does not match its WDBC header "
                f"(expected {expected_size}, got {len(payload)})"
            )
        string_block = payload[records_end:]
        if string_block[0] != 0:
            raise WorldMapAreaError("WorldMapArea string block must begin with a NUL byte")

        records: list[WorldMapAreaRecord] = []
        record_ids: set[int] = set()
        for index in range(record_count):
            offset = _WDBC_HEADER.size + (index * record_size)
            (
                record_id,
                map_id,
                area_id,
                name_offset,
                loc_left,
                loc_right,
                loc_top,
                loc_bottom,
                virtual_map_id,
            ) = _WORLD_MAP_AREA_ROW.unpack_from(payload, offset)
            if record_id in record_ids:
                raise WorldMapAreaError(f"WorldMapArea contains duplicate record ID {record_id}")
            record_ids.add(record_id)
            internal_name = WorldMapAreaTable._read_string(
                string_block,
                name_offset,
                record_index=index,
            )
            bounds = (loc_left, loc_right, loc_top, loc_bottom)
            if not all(isfinite(value) for value in bounds):
                raise WorldMapAreaError(
                    f"WorldMapArea record {record_id} contains non-finite bounds"
                )
            if loc_left == loc_right or loc_top == loc_bottom:
                raise WorldMapAreaError(
                    f"WorldMapArea record {record_id} contains degenerate bounds"
                )
            records.append(
                WorldMapAreaRecord(
                    record_id=record_id,
                    map_id=map_id,
                    area_id=area_id,
                    internal_name=internal_name,
                    loc_left=loc_left,
                    loc_right=loc_right,
                    loc_top=loc_top,
                    loc_bottom=loc_bottom,
                    virtual_map_id=virtual_map_id,
                )
            )
        return tuple(records)

    @staticmethod
    def _read_string(
        string_block: bytes,
        offset: int,
        *,
        record_index: int,
    ) -> str:
        if offset >= len(string_block):
            raise WorldMapAreaError(
                f"WorldMapArea record {record_index} has an out-of-bounds string offset"
            )
        terminator = string_block.find(b"\0", offset)
        if terminator < 0:
            raise WorldMapAreaError(
                f"WorldMapArea record {record_index} has an unterminated string"
            )
        raw_name = string_block[offset:terminator]
        if not raw_name:
            raise WorldMapAreaError(
                f"WorldMapArea record {record_index} has an empty internal name"
            )
        try:
            return raw_name.decode("utf-8")
        except UnicodeDecodeError as error:
            raise WorldMapAreaError(
                f"WorldMapArea record {record_index} has an invalid UTF-8 internal name"
            ) from error

    def resolve(
        self,
        *,
        internal_name: str | None = None,
        map_id: int | None = None,
        area_id: int | None = None,
    ) -> WorldMapAreaRecord:
        """Resolve an exact selector intersection, rejecting zero or many rows."""

        if internal_name is None and map_id is None and area_id is None:
            raise WorldMapAreaError("At least one WorldMapArea selector is required")
        if internal_name is not None and (
            not isinstance(internal_name, str) or not internal_name
        ):
            raise WorldMapAreaError("internal_name must be a non-empty exact string")
        if map_id is not None and (
            not isinstance(map_id, int) or isinstance(map_id, bool) or map_id < 0
        ):
            raise WorldMapAreaError("map_id must be a non-negative integer")
        if area_id is not None and (
            not isinstance(area_id, int) or isinstance(area_id, bool) or area_id < 0
        ):
            raise WorldMapAreaError("area_id must be a non-negative integer")

        matches = tuple(
            record
            for record in self._records
            if (internal_name is None or record.internal_name == internal_name)
            and (map_id is None or record.map_id == map_id)
            and (area_id is None or record.area_id == area_id)
        )
        selector = (
            f"internal_name={internal_name!r}, map_id={map_id!r}, area_id={area_id!r}"
        )
        if not matches:
            raise WorldMapAreaError(f"No WorldMapArea record matches {selector}")
        if len(matches) != 1:
            raise WorldMapAreaError(
                f"Ambiguous WorldMapArea selector {selector}: {len(matches)} records match"
            )
        return matches[0]

    def resolve_client_map_context(
        self,
        *,
        continent_index: int,
        zone_index: int,
    ) -> WorldMapAreaBinding:
        """Resolve one profile-bound client UI context, never a caller selector."""

        matches = tuple(
            binding
            for binding in self._map_bindings
            if binding.continent_index == continent_index
            and binding.zone_index == zone_index
        )
        if not matches:
            raise WorldMapAreaError(
                "HUD map context is not present in the versioned WorldMapArea bindings"
            )
        if len(matches) != 1:
            raise WorldMapAreaError("HUD map context binding is ambiguous")
        return matches[0]

    def transform(
        self,
        position_observation: Mapping[str, Any],
        *,
        evaluated_monotonic_s: float,
    ) -> WorldMapCoordinate2D:
        """Transform one contract-valid, fresh coordinate HUD position fact.

        TBC/CMaNGOS swaps the normalized map axes before applying the DBC bounds:
        world x uses the client's normalized y and top/bottom bounds; world y
        uses normalized x and left/right bounds. Asset eligibility and position
        trust remain separate; the output receives the most restrictive scope.
        """

        position_source, client_x, client_y = self._validated_position_source(
            position_observation,
            evaluated_monotonic_s=evaluated_monotonic_s,
        )
        binding = self.resolve_client_map_context(
            continent_index=position_source.continent_index,
            zone_index=position_source.zone_index,
        )
        record = self.resolve(
            internal_name=binding.internal_name,
            map_id=binding.map_id,
            area_id=binding.area_id,
        )

        world_x_span = record.loc_bottom - record.loc_top
        world_y_span = record.loc_right - record.loc_left
        world_x = record.loc_top + (client_y * world_x_span)
        world_y = record.loc_left + (client_x * world_y_span)
        normalized_quantization_step = 1.0 / 65535.0
        quantization_x = abs(world_x_span) * normalized_quantization_step / 2.0
        quantization_y = abs(world_y_span) * normalized_quantization_step / 2.0

        scope = self._derived_scope(self.provenance.scope, position_source.scope)
        evidence_refs = list(position_source.evidence_refs)
        asset_ref = (
            f"asset:{self.provenance.asset_name}:sha256:"
            f"{self.provenance.asset_sha256.upper()}"
        )
        if asset_ref not in evidence_refs:
            evidence_refs.append(asset_ref)
        if self.provenance.profile is not None:
            profile_ref = (
                f"profile:{self.provenance.profile}:"
                f"version:{self.provenance.profile_version}"
            )
            if profile_ref not in evidence_refs:
                evidence_refs.append(profile_ref)

        return WorldMapCoordinate2D(
            world_x=world_x,
            world_y=world_y,
            coordinate_space=f"{self._coordinate_space}:map:{record.map_id}",
            area=record,
            uncertainty=WorldMapTransformUncertainty(
                normalized_quantization_step=float(normalized_quantization_step),
                quantization_radius_world_x=quantization_x,
                quantization_radius_world_y=quantization_y,
                source_radius_world_x=None,
                source_radius_world_y=None,
                total_radius_world_x=None,
                total_radius_world_y=None,
                source_uncertainty_state="uncharacterized",
            ),
            confidence=position_source.confidence,
            provenance=WorldMapCoordinateProvenance(
                origin="coordinate_hud_world_map_transform",
                scope=scope,
                calibration=self.provenance,
                position=position_source,
                evidence_refs=tuple(evidence_refs),
            ),
        )

    def _validated_position_source(
        self,
        observation: Mapping[str, Any],
        *,
        evaluated_monotonic_s: float,
    ) -> tuple[WorldMapPositionSource, float, float]:
        if not isinstance(observation, Mapping):
            raise WorldMapAreaError(
                "position input must be a versioned coordinate HUD observation"
            )
        try:
            observation = copy.deepcopy(dict(observation))
            ContractValidator(_COORDINATE_HUD_SCHEMA_PATH).validate(observation)
            decoded_packet = validate_valid_observation_semantics(observation)
        except (OSError, TypeError, ValueError) as error:
            raise WorldMapAreaError(
                "position input failed the coordinate HUD observation contract"
            ) from error
        if observation["tracking_state"] != "VALID":
            raise WorldMapAreaError("position observation must have VALID tracking")
        if observation["execution_authority"] is not False:
            raise WorldMapAreaError("position observation cannot grant execution authority")

        position = observation["position"]
        if position is None or position["coordinate_space"] != "normalized_current_zone_map":
            raise WorldMapAreaError(
                "position observation must use normalized_current_zone_map"
            )
        client_x = self._normalized_coordinate(decoded_packet.x, "position.x")
        client_y = self._normalized_coordinate(decoded_packet.y, "position.y")

        if (
            not isinstance(evaluated_monotonic_s, (int, float))
            or isinstance(evaluated_monotonic_s, bool)
            or not isfinite(evaluated_monotonic_s)
            or evaluated_monotonic_s < 0
        ):
            raise WorldMapAreaError("evaluated_monotonic_s must be finite and non-negative")
        timing = observation["timing"]
        captured_monotonic_s = float(timing["monotonic_timestamp_s"])
        observed_monotonic_s = float(timing["observed_monotonic_s"])
        expires_monotonic_s = float(timing["expires_monotonic_s"])
        if captured_monotonic_s > observed_monotonic_s:
            raise WorldMapAreaError("position observation precedes its capture")
        if observed_monotonic_s > expires_monotonic_s:
            raise WorldMapAreaError("position observation has an invalid freshness interval")
        if evaluated_monotonic_s < observed_monotonic_s:
            raise WorldMapAreaError("position observation cannot be evaluated before observation")
        if evaluated_monotonic_s > expires_monotonic_s:
            raise WorldMapAreaError("position observation is expired")

        if observation["client_build"] != self.provenance.client_build:
            raise WorldMapAreaError(
                "position client_build does not match WorldMapArea calibration"
            )
        if observation["build_signature"] != self.provenance.build_signature:
            raise WorldMapAreaError(
                "position build_signature does not match WorldMapArea calibration"
            )
        if (
            self.provenance.target_profile is not None
            and observation["target_profile"] != self.provenance.target_profile
        ):
            raise WorldMapAreaError(
                "position target_profile does not match WorldMapArea calibration"
            )

        source_provenance = observation["provenance"]
        actor_binding = observation["actor_binding"]
        binding_assurance = actor_binding["binding_assurance"]
        source = WorldMapPositionSource(
            schema_version=observation["schema_version"],
            observation_id=observation["observation_id"],
            frame_id=observation["frame_id"],
            session_id=observation["session_id"],
            target_profile=observation["target_profile"],
            authorization_sha256=observation["authorization_sha256"],
            actor_binding=WorldMapActorBindingSource(
                schema_version=actor_binding["schema_version"],
                instance_id=actor_binding["instance_id"],
                actor_role=actor_binding["actor_role"],
                actor_id=actor_binding["actor_id"],
                decision_context=actor_binding["decision_context"],
                memory_namespace=actor_binding["memory_namespace"],
                expected_character_name=actor_binding["expected_character_name"],
                credential_alias=actor_binding["credential_alias"],
                binding_assurance=WorldMapActorBindingAssuranceSource(
                    state=binding_assurance["state"],
                    evidence_refs=tuple(binding_assurance["evidence_refs"]),
                ),
            ),
            decision_context=observation["decision_context"],
            client_build=observation["client_build"],
            build_signature=observation["build_signature"],
            coordinate_space=position["coordinate_space"],
            continent_index=decoded_packet.continent_index,
            zone_index=decoded_packet.zone_index,
            captured_at=timing["captured_at"],
            observed_monotonic_s=observed_monotonic_s,
            expires_monotonic_s=expires_monotonic_s,
            confidence=float(observation["confidence"]),
            origin=source_provenance["origin"],
            capture_origin=source_provenance["capture_origin"],
            capability=source_provenance["capability"],
            scope=source_provenance["scope"],
            profile_id=source_provenance["profile_id"],
            profile_version=source_provenance["profile_version"],
            profile_sha256=source_provenance["profile_sha256"],
            profile_calibration_state=source_provenance[
                "profile_calibration_state"
            ],
            evidence_refs=tuple(source_provenance["evidence_refs"]),
        )
        return source, client_x, client_y

    @staticmethod
    def _derived_scope(calibration_scope: str, position_scope: str) -> str:
        """Combine fact and asset restrictions without granting promotion."""

        if calibration_scope == "fixture_only" or position_scope == "synthetic_fixture":
            return "fixture_only"
        if (
            calibration_scope == "lab_evaluation_only"
            or position_scope == "lab_evaluation_only"
        ):
            return "lab_evaluation_only"
        if (
            calibration_scope == "champion_eligible"
            and position_scope == "unpromoted_evaluation_only"
        ):
            return "unpromoted_evaluation_only"
        raise WorldMapAreaError(
            "position and calibration scopes cannot form a trusted world-map fact"
        )

    @staticmethod
    def _normalized_coordinate(value: float, label: str) -> float:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(value)
            or not 0 <= value <= 1
        ):
            raise WorldMapAreaError(f"{label} must be finite and in the range [0, 1]")
        return float(value)
