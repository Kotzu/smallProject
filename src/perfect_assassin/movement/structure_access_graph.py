from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from math import atan2, ceil, floor, hypot, isfinite, pi, sqrt, tau
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.local_environment_awareness import (
    EnvironmentBoundary,
    LocalEnvironmentAwareness,
    VerifiedEnvironmentEgress,
)
from perfect_assassin.movement.standalone_world_pack import (
    VerifiedStandaloneWorldPack,
)


class StructureAccessGraphError(ValueError):
    """Raised when structure-access evidence is malformed or misbound."""


@dataclass(frozen=True, slots=True)
class StructureAccessObservation:
    awareness: LocalEnvironmentAwareness
    nav_awareness: LocalStaticAwareness
    probe_worker_sha256: str

    def __post_init__(self) -> None:
        if (
            self.awareness.physical_surfaces
            != self.nav_awareness.physical_surfaces
        ):
            raise StructureAccessGraphError(
                "local and native awareness surfaces are inconsistent"
            )
        if (
            len(self.probe_worker_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.probe_worker_sha256)
        ):
            raise StructureAccessGraphError("probe worker hash is invalid")


@dataclass(frozen=True, slots=True)
class StructureAccessGraphIdentity:
    graph_id: str
    world_pack_id: str
    world_pack_content_sha256: str
    catalog_id: str
    target_profile: str
    client_version: str
    client_build: str
    nav_profile_id: str
    map_id: int
    map_name: str
    structure_index_id: str
    structure_index_sha256: str
    map_artifact_sha256: str


@dataclass(frozen=True, slots=True)
class _SegmentEvidence:
    left: NavPoint
    right: NavPoint
    distance_yards: float
    structure_ids: tuple[str, ...]
    floor_bucket: int
    observation_hash: str
    collision_corroborated: bool


def _canonical_bytes(record: Mapping[str, Any]) -> bytes:
    return json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(record)).hexdigest()


def _point(value: NavPoint) -> list[float]:
    return [value.x, value.y, value.z]


def _distance_3d(left: NavPoint, right: NavPoint) -> float:
    return sqrt(
        (left.x - right.x) ** 2
        + (left.y - right.y) ** 2
        + (left.z - right.z) ** 2
    )


def _midpoint(left: NavPoint, right: NavPoint) -> NavPoint:
    return NavPoint(
        (left.x + right.x) / 2.0,
        (left.y + right.y) / 2.0,
        (left.z + right.z) / 2.0,
    )


def _quantize(value: float, quantum: float) -> int:
    scaled = value / quantum
    return int(floor(scaled + 0.5) if scaled >= 0 else ceil(scaled - 0.5))


def _point_key(point: NavPoint, quantum: float = 0.05) -> tuple[int, int, int]:
    return tuple(_quantize(value, quantum) for value in (point.x, point.y, point.z))


def _segment_key(
    left: NavPoint,
    right: NavPoint,
    quantum: float = 0.05,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    endpoints = sorted((_point_key(left, quantum), _point_key(right, quantum)))
    return endpoints[0], endpoints[1]


def _angular_distance(left: float, right: float) -> float:
    return abs((left - right + pi) % tau - pi)


def _collision_corroborates_boundary(
    *,
    origin: NavPoint,
    boundary: EnvironmentBoundary,
    probes: Sequence[RadialClearanceProbe],
    probe_radius_yards: float,
) -> bool:
    if not probes:
        return False
    nearest = min(
        probes,
        key=lambda probe: _angular_distance(
            boundary.bearing_rad, probe.bearing_rad,
        ),
    )
    angular_limit = pi / len(probes) + 0.03
    if (
        _angular_distance(boundary.bearing_rad, nearest.bearing_rad)
        > angular_limit
        or nearest.clearance_yards >= probe_radius_yards * 0.95
    ):
        return False
    midpoint_distance = origin.distance_2d(boundary.midpoint)
    tolerance = max(1.25, boundary.length_yards * 0.50)
    return abs(nearest.clearance_yards - midpoint_distance) <= tolerance


def _direction(left: NavPoint, right: NavPoint) -> tuple[float, float, float]:
    length = _distance_3d(left, right)
    return (
        (right.x - left.x) / length,
        (right.y - left.y) / length,
        (right.z - left.z) / length,
    )


def _turn_angle(
    previous: NavPoint,
    joint: NavPoint,
    candidate: NavPoint,
) -> float:
    incoming = _direction(previous, joint)
    outgoing = _direction(joint, candidate)
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(incoming, outgoing))))
    # atan2 avoids importing acos and remains stable close to a straight line.
    cross_x = incoming[1] * outgoing[2] - incoming[2] * outgoing[1]
    cross_y = incoming[2] * outgoing[0] - incoming[0] * outgoing[2]
    cross_z = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
    return atan2(sqrt(cross_x ** 2 + cross_y ** 2 + cross_z ** 2), dot)


def _chain_segments(
    segments: Sequence[_SegmentEvidence],
    *,
    maximum_turn_rad: float = 5.0 * pi / 9.0,
) -> list[tuple[list[NavPoint], list[_SegmentEvidence]]]:
    # Recast boundaries follow a voxelized staircase: a geometrically continuous
    # wall commonly alternates nearly 90-degree micro-edges.  Keep those edges
    # in one connected polyline while still refusing a reversal/U-turn.
    if not 0 < maximum_turn_rad < pi:
        raise StructureAccessGraphError("boundary chain angle is invalid")
    by_endpoint: dict[tuple[int, int, int], set[int]] = {}
    for index, item in enumerate(segments):
        for endpoint in (item.left, item.right):
            by_endpoint.setdefault(_point_key(endpoint), set()).add(index)
    unused = set(range(len(segments)))
    results: list[tuple[list[NavPoint], list[_SegmentEvidence]]] = []

    def extend(
        points: list[NavPoint],
        used: list[_SegmentEvidence],
        *,
        at_front: bool,
    ) -> None:
        while True:
            joint = points[0] if at_front else points[-1]
            previous = points[1] if at_front else points[-2]
            candidates = []
            for candidate_index in by_endpoint.get(_point_key(joint), set()):
                if candidate_index not in unused:
                    continue
                item = segments[candidate_index]
                if _point_key(item.left) == _point_key(joint):
                    other = item.right
                elif _point_key(item.right) == _point_key(joint):
                    other = item.left
                else:
                    continue
                angle = _turn_angle(other, joint, previous) if at_front else _turn_angle(previous, joint, other)
                if angle <= maximum_turn_rad:
                    candidates.append((angle, _point_key(other), candidate_index, other))
            if not candidates:
                return
            _, _, candidate_index, other = min(candidates)
            unused.remove(candidate_index)
            if at_front:
                points.insert(0, other)
                used.insert(0, segments[candidate_index])
            else:
                points.append(other)
                used.append(segments[candidate_index])

    while unused:
        seed = min(unused, key=lambda index: _segment_key(
            segments[index].left, segments[index].right,
        ))
        unused.remove(seed)
        item = segments[seed]
        left, right = item.left, item.right
        if _point_key(right) < _point_key(left):
            left, right = right, left
        points = [left, right]
        used = [item]
        extend(points, used, at_front=False)
        extend(points, used, at_front=True)
        results.append((points, used))
    return results


def _split_boundary_chain(
    points: Sequence[NavPoint],
    evidence: Sequence[_SegmentEvidence],
    *,
    maximum_points: int = 129,
) -> list[tuple[list[NavPoint], list[_SegmentEvidence]]]:
    """Split a long connected chain losslessly at shared endpoints.

    A single local observation is bounded to 128 wall segments, but several
    observations can connect into a much longer world contour.  The graph
    contract bounds one polyline, not the physical contour.  Overlapping the
    endpoint between chunks preserves every segment, its length and evidence
    without simplifying geometry or introducing a location-specific cut.
    """

    if not 2 <= maximum_points <= 129:
        raise StructureAccessGraphError("boundary chain point bound is invalid")
    if len(points) < 2 or len(evidence) != len(points) - 1:
        raise StructureAccessGraphError("boundary chain evidence is inconsistent")
    maximum_segments = maximum_points - 1
    chunks: list[tuple[list[NavPoint], list[_SegmentEvidence]]] = []
    first_segment = 0
    while first_segment < len(evidence):
        last_segment = min(
            first_segment + maximum_segments,
            len(evidence),
        )
        chunks.append((
            list(points[first_segment:last_segment + 1]),
            list(evidence[first_segment:last_segment]),
        ))
        first_segment = last_segment
    return chunks


def _connected_egress_components(
    portals: Sequence[tuple[VerifiedEnvironmentEgress, tuple[str, ...], str]],
    *,
    endpoint_tolerance_yards: float = 0.15,
) -> list[list[tuple[VerifiedEnvironmentEgress, tuple[str, ...], str]]]:
    remaining = set(range(len(portals)))
    components = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        component_indices = [seed]
        cursor = 0
        while cursor < len(component_indices):
            current = portals[component_indices[cursor]][0]
            cursor += 1
            connected = []
            for candidate_index in sorted(remaining):
                candidate = portals[candidate_index][0]
                if min(
                    _distance_3d(left, right)
                    for left in (current.left, current.right)
                    for right in (candidate.left, candidate.right)
                ) <= endpoint_tolerance_yards:
                    connected.append(candidate_index)
            for candidate_index in connected:
                remaining.remove(candidate_index)
                component_indices.append(candidate_index)
        components.append([portals[index] for index in component_indices])
    return components


def structure_access_graph_identity(
    pack: VerifiedStandaloneWorldPack,
    *,
    structure_index_record: Mapping[str, Any],
) -> StructureAccessGraphIdentity:
    manifest = pack.manifest
    catalog = pack.catalog
    pairs = (
        ("pack_id", manifest["pack_id"]),
        ("catalog_id", catalog.catalog_id),
        ("source_pack_content_sha256", manifest["content_sha256"]),
        ("client_version", catalog.client_version),
        ("client_build", catalog.client_build),
    )
    for field, expected in pairs:
        if structure_index_record.get(field) != expected:
            raise StructureAccessGraphError(
                f"structure index {field} does not match the WorldPack"
            )
    map_id = int(structure_index_record["map_id"])
    map_name = str(structure_index_record["map_name"])
    declared = catalog.map_by_id(map_id)
    if declared.internal_name != map_name:
        raise StructureAccessGraphError("structure index map is inconsistent")
    index_sha256 = _canonical_sha256(structure_index_record)
    return StructureAccessGraphIdentity(
        graph_id=f"{manifest['pack_id']}:{map_name}:structure-access-v1",
        world_pack_id=str(manifest["pack_id"]),
        world_pack_content_sha256=str(manifest["content_sha256"]),
        catalog_id=catalog.catalog_id,
        target_profile=catalog.target_profile,
        client_version=catalog.client_version,
        client_build=catalog.client_build,
        nav_profile_id=catalog.nav_profile_id,
        map_id=map_id,
        map_name=map_name,
        structure_index_id=str(structure_index_record["index_id"]),
        structure_index_sha256=index_sha256,
        map_artifact_sha256=str(structure_index_record["map_artifact_sha256"]),
    )


def build_structure_access_graph_record(
    pack: VerifiedStandaloneWorldPack,
    *,
    structure_index_record: Mapping[str, Any],
    observations: Iterable[StructureAccessObservation],
) -> dict[str, Any]:
    identity = structure_access_graph_identity(
        pack, structure_index_record=structure_index_record,
    )
    values = tuple(observations)
    if not values or len(values) > 4096:
        raise StructureAccessGraphError("structure access observation count is invalid")
    worker_hashes = {item.probe_worker_sha256 for item in values}
    if len(worker_hashes) != 1:
        raise StructureAccessGraphError(
            "structure access observations use different probe workers"
        )
    probe_worker_sha256 = next(iter(worker_hashes))
    observation_records = []
    boundary_segments: dict[
        tuple[tuple[str, ...], int], dict[
            tuple[tuple[int, int, int], tuple[int, int, int]], _SegmentEvidence
        ],
    ] = {}
    egress_portals: dict[
        tuple[tuple[str, ...], int], dict[
            tuple[tuple[int, int, int], tuple[int, int, int]],
            tuple[VerifiedEnvironmentEgress, tuple[str, ...], str],
        ],
    ] = {}
    for item in values:
        awareness = item.awareness
        if awareness.map_name != identity.map_name:
            raise StructureAccessGraphError("awareness map does not match graph map")
        raw_record = awareness.to_record()
        observation_hash = _canonical_sha256(raw_record)
        structure_ids = tuple(sorted(
            structure.structure_id
            for structure in awareness.containing_structures
        ))
        observation_records.append({
            "observation_sha256": observation_hash,
            "observed_monotonic_s": awareness.observed_monotonic_s,
            "position": _point(awareness.position),
            "environment_state": awareness.environment_state,
            "topology_complete": awareness.topology_complete,
            "containing_structure_ids": list(structure_ids),
            "boundary_count": len(awareness.boundaries),
            "verified_egress_count": len(awareness.verified_egresses),
        })
        for boundary in awareness.boundaries:
            boundary_floor_bucket = _quantize(boundary.midpoint.z, 0.5)
            target_boundaries = boundary_segments.setdefault(
                # Boundary polylines are connected in full 3D.  Grouping their
                # micro-edges by a Z bucket first would split a sloped wall or
                # stairwell into artificial half-yard fragments.
                (structure_ids, 0), {},
            )
            key = _segment_key(boundary.left, boundary.right)
            evidence = _SegmentEvidence(
                left=boundary.left,
                right=boundary.right,
                distance_yards=boundary.distance_yards,
                structure_ids=structure_ids,
                floor_bucket=boundary_floor_bucket,
                observation_hash=observation_hash,
                collision_corroborated=_collision_corroborates_boundary(
                    origin=awareness.position,
                    boundary=boundary,
                    probes=item.nav_awareness.radial_probes,
                    probe_radius_yards=item.nav_awareness.probe_radius_yards,
                ),
            )
            existing = target_boundaries.get(key)
            if existing is None or (
                evidence.collision_corroborated,
                -evidence.distance_yards,
                evidence.observation_hash,
            ) > (
                existing.collision_corroborated,
                -existing.distance_yards,
                existing.observation_hash,
            ):
                target_boundaries[key] = evidence
        for egress in awareness.verified_egresses:
            egress_floor_bucket = _quantize(egress.midpoint.z, 0.5)
            target_egresses = egress_portals.setdefault(
                (structure_ids, egress_floor_bucket), {},
            )
            key = _segment_key(egress.left, egress.right)
            evidence = egress, structure_ids, observation_hash
            existing = target_egresses.get(key)
            if existing is None or (
                egress.route_distance_yards,
                -egress.width_yards,
                observation_hash,
            ) < (
                existing[0].route_distance_yards,
                -existing[0].width_yards,
                existing[2],
            ):
                target_egresses[key] = evidence

    chains = []
    for (structure_ids, _), indexed in sorted(boundary_segments.items()):
        connected = _chain_segments(tuple(indexed.values()))
        bounded = (
            chunk
            for points, evidence in connected
            for chunk in _split_boundary_chain(points, evidence)
        )
        for points, evidence in bounded:
            floor_bucket = _quantize(
                sum(point.z for point in points) / len(points), 0.5,
            )
            segment_lengths = [
                _distance_3d(left, right)
                for left, right in zip(points, points[1:])
            ]
            total_length = sum(segment_lengths)
            corroborated_length = sum(
                length for length, item in zip(segment_lengths, evidence)
                if item.collision_corroborated
            )
            corroboration_fraction = (
                corroborated_length / total_length if total_length else 0.0
            )
            digest_input = {
                "structures": structure_ids,
                "floor_bucket": floor_bucket,
                "points": [_point_key(point) for point in points],
            }
            chains.append({
                "chain_id": "boundary:" + _canonical_sha256(digest_input)[:24],
                "structure_ids": list(structure_ids),
                "floor_z_yards": floor_bucket * 0.5,
                "polyline": [_point(point) for point in points],
                "length_yards": total_length,
                "minimum_observed_distance_yards": min(
                    item.distance_yards for item in evidence
                ),
                "barrier_semantics": (
                    "BVH_COLLISION_CORROBORATED_STATIC_BARRIER"
                    if corroboration_fraction >= 0.5
                    else "NAVMESH_BOUNDARY_CHAIN_ONLY"
                ),
                "collision_corroboration_fraction": corroboration_fraction,
                "physical_object_class": "UNKNOWN_NOT_INFERRED",
                "source_observation_sha256": sorted({
                    item.observation_hash for item in evidence
                }),
                "execution_authority": False,
            })

    openings = []
    for (structure_ids, floor_bucket), indexed in sorted(egress_portals.items()):
        components = _connected_egress_components(tuple(indexed.values()))
        for component in components:
            unique = sorted(
                component,
                key=lambda value: _segment_key(value[0].left, value[0].right),
            )
            total_width = sum(item[0].width_yards for item in unique)
            midpoint = NavPoint(
                sum(_midpoint(item[0].left, item[0].right).x * item[0].width_yards for item in unique) / total_width,
                sum(_midpoint(item[0].left, item[0].right).y * item[0].width_yards for item in unique) / total_width,
                sum(_midpoint(item[0].left, item[0].right).z * item[0].width_yards for item in unique) / total_width,
            )
            segments = [{
                "left": _point(item[0].left),
                "right": _point(item[0].right),
                "width_yards": item[0].width_yards,
            } for item in unique]
            digest_input = {
                "structures": structure_ids,
                "floor_bucket": floor_bucket,
                "segments": [
                    _segment_key(item[0].left, item[0].right) for item in unique
                ],
            }
            openings.append({
                "opening_id": "access:" + _canonical_sha256(digest_input)[:24],
                "structure_ids": list(structure_ids),
                "floor_z_yards": floor_bucket * 0.5,
                "midpoint": _point(midpoint),
                "segments": segments,
                "connected_width_yards": total_width,
                "minimum_observed_route_distance_yards": min(
                    item[0].route_distance_yards for item in unique
                ),
                "from_surfaces": sorted(set().union(*(
                    item[0].from_surfaces for item in unique
                ))),
                "to_surfaces": sorted(set().union(*(
                    item[0].to_surfaces for item in unique
                ))),
                "opening_kind": "COVERED_TO_OPEN_ROUTE_VERIFIED",
                "physical_door_semantics": "UNKNOWN_NOT_INFERRED",
                "dynamic_state": "UNKNOWN_NOT_OBSERVED",
                "source_observation_sha256": sorted({
                    item[2] for item in unique
                }),
                "execution_authority": False,
            })

    observations_sorted = sorted(
        observation_records,
        key=lambda item: (item["observation_sha256"], item["observed_monotonic_s"]),
    )
    record: dict[str, Any] = {
        "record_type": "structure_access_graph",
        "schema_version": "1.0",
        **{
            field: getattr(identity, field)
            for field in StructureAccessGraphIdentity.__dataclass_fields__
        },
        "coverage_semantics": "LOCAL_IMMUTABLE_GEOMETRY_PROBE_AGGREGATE",
        "probe_contract_id": "detour-bvh-local-structure-access-v1",
        "probe_worker_sha256": probe_worker_sha256,
        "coverage_state": (
            "COMPLETE_FOR_OBSERVED_COMPONENTS"
            if all(item.awareness.topology_complete for item in values)
            else "PARTIAL_OBSERVED_COMPONENTS"
        ),
        "observations": observations_sorted,
        "boundary_chains": sorted(chains, key=lambda item: item["chain_id"]),
        "access_openings": sorted(openings, key=lambda item: item["opening_id"]),
        "dynamic_entity_knowledge": "NONE",
        "execution_authority": False,
    }
    record["content_sha256"] = _canonical_sha256(record)
    return record


def verify_structure_access_graph_binding(
    record: Mapping[str, Any],
    *,
    pack: VerifiedStandaloneWorldPack,
    structure_index_record: Mapping[str, Any],
    expected_probe_worker_sha256: str | None = None,
) -> None:
    identity = structure_access_graph_identity(
        pack, structure_index_record=structure_index_record,
    )
    for field in StructureAccessGraphIdentity.__dataclass_fields__:
        actual = record.get(field)
        expected = getattr(identity, field)
        if actual != expected:
            raise StructureAccessGraphError(
                f"structure access graph {field} does not match its WorldPack"
            )
    content_sha256 = record.get("content_sha256")
    if not isinstance(content_sha256, str):
        raise StructureAccessGraphError("structure access graph hash is missing")
    unsigned = dict(record)
    del unsigned["content_sha256"]
    if not hmac.compare_digest(_canonical_sha256(unsigned), content_sha256):
        raise StructureAccessGraphError("structure access graph content hash mismatch")
    if expected_probe_worker_sha256 is not None and not hmac.compare_digest(
        str(record.get("probe_worker_sha256", "")),
        expected_probe_worker_sha256,
    ):
        raise StructureAccessGraphError(
            "structure access graph probe worker does not match runtime"
        )


class StructureAccessSpatialGraph:
    def __init__(self, record: Mapping[str, Any]) -> None:
        self.record = record

    def nearest_openings(
        self,
        *,
        x: float,
        y: float,
        z: float | None = None,
        structure_id: str | None = None,
        maximum_distance_yards: float = 1_000.0,
        limit: int = 8,
    ) -> tuple[Mapping[str, Any], ...]:
        if (
            not isfinite(x) or not isfinite(y)
            or (z is not None and not isfinite(z))
            or not isfinite(maximum_distance_yards)
            or maximum_distance_yards <= 0
            or maximum_distance_yards > 1_000
            or not 1 <= limit <= 64
        ):
            raise StructureAccessGraphError("access opening query is invalid")
        matches = []
        for item in self.record["access_openings"]:
            if structure_id is not None and structure_id not in item["structure_ids"]:
                continue
            midpoint = item["midpoint"]
            distance = hypot(float(midpoint[0]) - x, float(midpoint[1]) - y)
            if z is not None:
                distance = hypot(distance, float(midpoint[2]) - z)
            if distance <= maximum_distance_yards:
                matches.append((distance, item["opening_id"], item))
        return tuple(item for _, _, item in sorted(matches)[:limit])


def load_structure_access_graph(
    path: Path,
    *,
    schema_path: Path,
    pack: VerifiedStandaloneWorldPack,
    structure_index_record: Mapping[str, Any],
    expected_probe_worker_sha256: str | None = None,
) -> StructureAccessSpatialGraph:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StructureAccessGraphError(
            f"cannot read structure access graph: {error}"
        ) from error
    if not isinstance(record, dict):
        raise StructureAccessGraphError("structure access graph is not one object")
    ContractValidator(schema_path).validate(record)
    verify_structure_access_graph_binding(
        record,
        pack=pack,
        structure_index_record=structure_index_record,
        expected_probe_worker_sha256=expected_probe_worker_sha256,
    )
    return StructureAccessSpatialGraph(record)
