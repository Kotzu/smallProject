from __future__ import annotations

from dataclasses import replace
import json
from math import tau
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    LocalTopologicalEgressPortal,
    LocalWallSegment,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.local_environment_awareness import (
    build_local_environment_awareness,
)
from perfect_assassin.movement.structure_access_graph import (
    StructureAccessGraphError,
    StructureAccessObservation,
    StructureAccessSpatialGraph,
    _split_boundary_chain,
    build_structure_access_graph_record,
    load_structure_access_graph,
    verify_structure_access_graph_binding,
)
from perfect_assassin.movement.world_structure_index import (
    AxisAlignedBounds,
    Vector3,
    WorldStructure,
    WorldStructureSpatialIndex,
)


ROOT = Path(__file__).parents[1]


class _Catalog:
    catalog_id = "wow.test.catalog-v1"
    target_profile = "test_lab"
    client_version = "2.5.5"
    client_build = "2.5.5.12345"
    nav_profile_id = "test-nav-v1"

    @staticmethod
    def map_by_id(map_id: int) -> SimpleNamespace:
        if map_id != 33:
            raise KeyError(map_id)
        return SimpleNamespace(internal_name="Fixture")


def _pack() -> SimpleNamespace:
    return SimpleNamespace(
        manifest={
            "pack_id": "wow.test.pack-v1",
            "content_sha256": "a" * 64,
        },
        catalog=_Catalog(),
    )


def _index() -> dict[str, object]:
    return {
        "record_type": "world_structure_index",
        "schema_version": "1.0",
        "index_id": "wow.test.pack-v1:Fixture:structures-v1",
        "pack_id": "wow.test.pack-v1",
        "catalog_id": "wow.test.catalog-v1",
        "source_pack_content_sha256": "a" * 64,
        "client_version": "2.5.5",
        "client_build": "2.5.5.12345",
        "map_id": 33,
        "map_name": "Fixture",
        "map_artifact_sha256": "b" * 64,
        "structures": [],
        "execution_authority": False,
    }


def _structures() -> WorldStructureSpatialIndex:
    return WorldStructureSpatialIndex((WorldStructure(
        structure_id="33:wmo:7",
        kind="WMO",
        instance_id=7,
        asset_path="world/wmo/fixture/house.wmo",
        asset_tokens=("world", "wmo", "fixture", "house"),
        bounds=AxisAlignedBounds(
            Vector3(-30.0, -30.0, 0.0), Vector3(30.0, 30.0, 20.0),
        ),
        center=Vector3(0.0, 0.0, 10.0),
        horizontal_radius_yards=42.5,
        collision_role="ENCLOSURE_OR_LARGE_STRUCTURE",
        nav_coverage="FULL",
    ),), cell_size_yards=64.0)


def _observation() -> StructureAccessObservation:
    walls = (
        LocalWallSegment(NavPoint(4.0, -0.25, 5.0), NavPoint(4.0, 0.0, 5.0), 4.0),
        LocalWallSegment(NavPoint(4.0, 0.0, 5.0), NavPoint(4.0, 0.25, 5.0), 4.0),
    )
    portals = (
        LocalTopologicalEgressPortal(
            NavPoint(10.0, -2.0, 5.0), NavPoint(10.0, 0.0, 5.0),
            2.0, 10.0, 12.0, False, True,
            frozenset({"wmo"}), frozenset({"ground"}),
        ),
        LocalTopologicalEgressPortal(
            NavPoint(10.0, 0.0, 5.0), NavPoint(10.0, 2.0, 5.0),
            2.0, 10.0, 12.5, False, True,
            frozenset({"wmo"}), frozenset({"ground"}),
        ),
        LocalTopologicalEgressPortal(
            NavPoint(20.0, -1.0, 5.0), NavPoint(20.0, 1.0, 5.0),
            2.0, 20.0, 22.0, False, True,
            frozenset({"wmo"}), frozenset({"ground"}),
        ),
    )
    probes = tuple(
        RadialClearanceProbe(
            index * tau / 16,
            4.0 if index == 0 else 12.0,
            index != 0,
        )
        for index in range(16)
    )
    native = LocalStaticAwareness(
        physical_surfaces=frozenset({"wmo"}),
        probe_radius_yards=12.0,
        overhead_clear=False,
        radial_probes=probes,
        component_polygon_count=100,
        wall_segments=walls,
        egress_portals=portals,
    )
    local = build_local_environment_awareness(
        map_name="Fixture",
        observed_monotonic_s=10.0,
        position=NavPoint(0.0, 0.0, 5.0),
        nav_awareness=native,
        structures=_structures(),
    )
    return StructureAccessObservation(local, native, "c" * 64)


class StructureAccessGraphTests(unittest.TestCase):
    def test_long_boundary_contour_is_split_losslessly_at_shared_endpoints(self) -> None:
        points = tuple(
            NavPoint(float(index), 0.0, 5.0) for index in range(300)
        )
        evidence = tuple(range(299))

        chunks = _split_boundary_chain(points, evidence)  # type: ignore[arg-type]

        self.assertEqual(tuple(len(item[0]) for item in chunks), (129, 129, 44))
        self.assertTrue(all(len(item[0]) <= 129 for item in chunks))
        self.assertEqual(
            tuple(value for _, values in chunks for value in values),
            evidence,
        )
        self.assertEqual(chunks[0][0][-1], chunks[1][0][0])
        self.assertEqual(chunks[1][0][-1], chunks[2][0][0])

    def test_adjacent_detour_edges_become_openings_and_boundary_chains(self) -> None:
        record = build_structure_access_graph_record(
            _pack(),
            structure_index_record=_index(),
            observations=(_observation(),),
        )
        ContractValidator(
            ROOT / "contracts" / "structure-access-graph.schema.json"
        ).validate(record)

        self.assertEqual(len(record["access_openings"]), 2)
        widths = sorted(item["connected_width_yards"] for item in record["access_openings"])
        self.assertEqual(widths, [2.0, 4.0])
        self.assertEqual(len(record["boundary_chains"]), 1)
        chain = record["boundary_chains"][0]
        self.assertEqual(len(chain["polyline"]), 3)
        self.assertEqual(
            chain["barrier_semantics"],
            "BVH_COLLISION_CORROBORATED_STATIC_BARRIER",
        )
        self.assertEqual(chain["physical_object_class"], "UNKNOWN_NOT_INFERRED")
        self.assertFalse(record["execution_authority"])

    def test_graph_is_deterministic_and_deduplicates_repeated_probe(self) -> None:
        observation = _observation()
        first = build_structure_access_graph_record(
            _pack(), structure_index_record=_index(), observations=(observation,),
        )
        repeated = build_structure_access_graph_record(
            _pack(),
            structure_index_record=_index(),
            observations=(observation, observation),
        )
        self.assertEqual(first["access_openings"], repeated["access_openings"])
        self.assertEqual(first["boundary_chains"], repeated["boundary_chains"])

    def test_same_portal_is_grouped_by_geometry_floor_not_probe_height(self) -> None:
        first = _observation()
        second = StructureAccessObservation(
            awareness=replace(
                first.awareness,
                position=NavPoint(0.0, 0.0, 15.0),
                observed_monotonic_s=11.0,
            ),
            nav_awareness=first.nav_awareness,
            probe_worker_sha256=first.probe_worker_sha256,
        )
        record = build_structure_access_graph_record(
            _pack(),
            structure_index_record=_index(),
            observations=(first, second),
        )
        self.assertEqual(len(record["access_openings"]), 2)
        self.assertEqual(
            {item["floor_z_yards"] for item in record["access_openings"]},
            {5.0},
        )

    def test_nearest_opening_is_structure_and_floor_aware(self) -> None:
        record = build_structure_access_graph_record(
            _pack(), structure_index_record=_index(), observations=(_observation(),),
        )
        graph = StructureAccessSpatialGraph(record)
        nearest = graph.nearest_openings(
            x=0.0, y=0.0, z=5.0, structure_id="33:wmo:7", limit=1,
        )
        self.assertEqual(len(nearest), 1)
        self.assertAlmostEqual(nearest[0]["midpoint"][0], 10.0)
        self.assertEqual(
            graph.nearest_openings(
                x=0.0, y=0.0, structure_id="missing", limit=1,
            ),
            (),
        )

    def test_loader_rejects_tampering_or_other_build(self) -> None:
        record = build_structure_access_graph_record(
            _pack(), structure_index_record=_index(), observations=(_observation(),),
        )
        verify_structure_access_graph_binding(
            record, pack=_pack(), structure_index_record=_index(),
            expected_probe_worker_sha256="c" * 64,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "access.json"
            altered = json.loads(json.dumps(record))
            altered["access_openings"][0]["connected_width_yards"] = 999.0
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaisesRegex(StructureAccessGraphError, "hash mismatch"):
                load_structure_access_graph(
                    path,
                    schema_path=ROOT / "contracts" / "structure-access-graph.schema.json",
                    pack=_pack(),
                    structure_index_record=_index(),
                    expected_probe_worker_sha256="c" * 64,
                )

            wrong_index = {**_index(), "client_build": "2.4.3.8606"}
            with self.assertRaisesRegex(StructureAccessGraphError, "client_build"):
                verify_structure_access_graph_binding(
                    record, pack=_pack(), structure_index_record=wrong_index,
                )
            with self.assertRaisesRegex(StructureAccessGraphError, "probe worker"):
                verify_structure_access_graph_binding(
                    record,
                    pack=_pack(),
                    structure_index_record=_index(),
                    expected_probe_worker_sha256="d" * 64,
                )


if __name__ == "__main__":
    unittest.main()
