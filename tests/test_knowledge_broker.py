from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator, ContractValidationError
from perfect_assassin.knowledge.broker import (
    KnowledgeBrokerCatalog,
    KnowledgeBrokerError,
    KnowledgeEntry,
    KnowledgePosition,
    KnowledgeSource,
    load_knowledge_broker_catalog,
)
from perfect_assassin.knowledge.route_teacher import (
    RouteTeacherImportConfig,
    RouteTeacherImportError,
    import_zygor_lua,
    next_advisory_route_steps,
)
from perfect_assassin.knowledge.npc_data import (
    NpcDataImportConfig,
    NpcDataImportError,
    import_zygor_npc_data,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "knowledge-broker-catalog.schema.json"


def _source(*, provider: str = "wowhead", origin: str = "external_cached") -> KnowledgeSource:
    return KnowledgeSource(
        provider=provider,
        origin=origin,
        uri="https://www.wowhead.com/tbc",
        provider_version="tbc-2.4.3",
        retrieved_at="2026-08-31T18:00:00Z",
        content_mode="metadata_only",
    )


def _entry(
    *, kind: str = "class_trainer", source: KnowledgeSource | None = None,
    position: KnowledgePosition | None = None, entry_id: str = "trainer.rogue",
    map_scope: str = "worldpack",
) -> KnowledgeEntry:
    return KnowledgeEntry(
        entry_id=entry_id,
        kind=kind,
        name="Rogue Trainer (source candidate)",
        map_id=0,
        map_name="Azeroth",
        level_min=1,
        level_max=70,
        source=source or _source(),
        confidence=0.92,
        evidence_refs=("wowhead:tbc:trainer.rogue",),
        position=position,
        summary="Static source metadata; confirm against the client before movement.",
        tags=("class", "rogue"),
        map_scope=map_scope,
    )


def _catalog_record() -> dict[str, object]:
    return KnowledgeBrokerCatalog(
        catalog_id="fixture.knowledge.tbc243",
        target_profile="tbc243_lab",
        product="wow",
        expansion="the_burning_crusade",
        client_version="2.4.3",
        client_build="2.4.3.8606",
        entries=(_entry(),),
    ).to_record()


class KnowledgeBrokerTests(unittest.TestCase):
    def test_static_sources_round_trip_and_query_by_exact_map(self) -> None:
        location = KnowledgePosition(
            x=1634.5, y=54.0, z=38.2, coordinate_frame="source_world_3d"
        )
        catalog = KnowledgeBrokerCatalog(
            catalog_id="fixture.knowledge.tbc243",
            target_profile="tbc243_lab",
            product="wow",
            expansion="the_burning_crusade",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            entries=(
                _entry(position=location),
                _entry(
                    kind="route_step",
                    source=_source(provider="route_teacher", origin="route_guidance"),
                    entry_id="leveling.step.001",
                ),
            ),
        )
        restored = KnowledgeBrokerCatalog.from_record(catalog.to_record())

        self.assertEqual(restored, catalog)
        self.assertEqual(len(restored.by_kind("class_trainer", map_id=0)), 1)
        self.assertEqual(len(restored.by_map(map_id=0, map_name="Azeroth")), 2)
        self.assertFalse(restored.entry("trainer.rogue").execution_authority)

    def test_nearby_static_candidates_are_exact_map_scoped_and_advisory(self) -> None:
        near = _entry(
            position=KnowledgePosition(
                x=0.30, y=0.40, coordinate_frame="normalized_map_2d"
            ),
            entry_id="trainer.near",
            map_scope="zone_area",
        )
        far = _entry(
            position=KnowledgePosition(
                x=0.90, y=0.90, coordinate_frame="normalized_map_2d"
            ),
            entry_id="trainer.far",
            map_scope="zone_area",
        )
        other_scope = KnowledgeEntry(
            entry_id="trainer.worldpack",
            kind="class_trainer",
            name="Worldpack candidate",
            map_id=0,
            map_name="Azeroth",
            level_min=1,
            level_max=70,
            source=_source(),
            confidence=0.99,
            evidence_refs=("wowhead:tbc:trainer.worldpack",),
            position=KnowledgePosition(
                x=0.30, y=0.40, coordinate_frame="normalized_map_2d"
            ),
            map_scope="worldpack",
        )
        catalog = KnowledgeBrokerCatalog(
            catalog_id="fixture.knowledge.nearby",
            target_profile="tbc243_lab",
            product="wow",
            expansion="the_burning_crusade",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            entries=(near, far, other_scope),
        )
        result = catalog.nearby_static_candidates(
            map_id=0,
            map_name="Azeroth",
            normalized_x=0.30,
            normalized_y=0.40,
            radius=0.02,
            kinds=frozenset({"class_trainer"}),
        )
        self.assertEqual(result, (near,))
        self.assertFalse(result[0].execution_authority)
        with self.assertRaises(KnowledgeBrokerError):
            catalog.nearby_static_candidates(
                map_id=0, map_name="Azeroth", normalized_x=1.2, normalized_y=0.4,
            )

    def test_schema_and_loader_validate_provenance_and_read_only_contract(self) -> None:
        record = _catalog_record()
        ContractValidator(SCHEMA).validate(record)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(load_knowledge_broker_catalog(path).catalog_id, "fixture.knowledge.tbc243")

        invalid = copy.deepcopy(record)
        invalid["entries"][0]["execution_authority"] = True
        with self.assertRaises(ContractValidationError):
            ContractValidator(SCHEMA).validate(invalid)

    def test_forbidden_or_live_position_semantics_are_rejected(self) -> None:
        with self.assertRaises(KnowledgeBrokerError):
            KnowledgeSource(
                provider="wowhead", origin="server_ground_truth", uri="db://spawn",
                provider_version="fixture", retrieved_at="2026-08-31T18:00:00Z",
                content_mode="metadata_only",
            )
        with self.assertRaises(KnowledgeBrokerError):
            KnowledgePosition(
                x=1, y=2, coordinate_frame="client_world_3d",
                position_semantics="LIVE_EXACT",
            )

    def test_route_teacher_is_distinct_from_external_cached_wowhead(self) -> None:
        with self.assertRaises(KnowledgeBrokerError):
            _source(provider="route_teacher", origin="external_cached")
        advisory = _entry(kind="class_trainer", source=_source(
            provider="route_teacher", origin="route_guidance"
        ))
        self.assertEqual(advisory.source.origin, "route_guidance")
        self.assertFalse(advisory.execution_authority)

    def test_imports_current_zygor_step_blocks_without_evaluating_lua(self) -> None:
        text = '''
ZygorGuidesViewer:RegisterGuide("Leveling\\\\Horde\\\\Undead",{},[[
step
talk Undertaker Mordo##1568
accept Rude Awakening##363 |goto Tirisfal Glades/0 30.22,71.65
step
kill 8 Mindless Zombie##1501 |q 364/1 |goto Tirisfal Glades 32.60,63.40
step
talk Shadow Priest Sarvis##1569
turnin The Mindless Ones##364 |goto Tirisfal Glades 30.84,66.20
step
Train Abilities |trainer Zelma Rockslide##459 |goto Tirisfal Glades 30.91,66.34
|only if Rogue
step
Train Cooking |trainer Cook##999 |goto Tirisfal Glades 31.00,66.00
]])
'''
        config = RouteTeacherImportConfig(
            catalog_id="fixture.zygor.tbc243",
            target_profile="tbc243_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            provider_version="8.1.37070",
            retrieved_at="2026-08-31T19:00:00Z",
            source_uri="local://Zygor.zip!/guide.lua",
            default_map_id=0,
            default_map_name="Azeroth",
            zone_map_bindings={"Tirisfal Glades": (0, "Azeroth")},
        )

        catalog = import_zygor_lua(text, config=config)
        self.assertEqual(len(catalog.entries), 5)
        self.assertEqual(catalog.entries[0].position.position_semantics, "STATIC_SOURCE_CANDIDATE")
        self.assertAlmostEqual(catalog.entries[0].position.x, 0.3022)
        self.assertIn("accept", catalog.entries[0].tags)
        self.assertIn("combat", catalog.entries[1].tags)
        self.assertEqual(catalog.entries[2].step_order, 3)
        self.assertEqual(catalog.entries[3].kind, "class_trainer")
        self.assertEqual(catalog.entries[4].kind, "profession_trainer")

    def test_import_requires_explicit_binding_for_unknown_route_zone(self) -> None:
        config = RouteTeacherImportConfig(
            catalog_id="fixture.zygor.tbc243",
            target_profile="tbc243_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            provider_version="8.1.37070",
            retrieved_at="2026-08-31T19:00:00Z",
            source_uri="local://guide.lua",
            default_map_id=0,
            default_map_name="Azeroth",
            zone_map_bindings={},
        )
        with self.assertRaises(RouteTeacherImportError):
            import_zygor_lua(
                "RegisterGuide(\"x\",{},[[\nstep\n|goto Unknown Zone 1,2\n]])",
                config=config,
            )

    def test_route_teacher_cursor_uses_order_and_completion_without_authority(self) -> None:
        text = '''
ZygorGuidesViewer:RegisterGuide("fixture",{},[[
step
|goto Zone A 10,20
step
talk A Trainer##1
step
|goto Zone A 30,40
step
|goto Zone B 50,60
]])
'''
        config = RouteTeacherImportConfig(
            catalog_id="fixture.zygor.cursor",
            target_profile="tbc243_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            provider_version="8.1.37070",
            retrieved_at="2026-08-31T19:00:00Z",
            source_uri="local://guide.lua",
            default_map_id=0,
            default_map_name="Azeroth",
            zone_map_bindings={"Zone A": (0, "Azeroth"), "Zone B": (1, "Kalimdor")},
        )
        catalog = import_zygor_lua(text, config=config)
        first = next_advisory_route_steps(catalog, map_id=0, level=1, limit=4)
        self.assertEqual([entry.step_order for entry in first], [1, 2, 3])
        completed = frozenset({first[0].entry_id})
        remaining = next_advisory_route_steps(
            catalog,
            map_id=0,
            level=1,
            completed_entry_ids=completed,
            limit=1,
        )
        self.assertEqual(remaining[0].step_order, 2)
        self.assertFalse(remaining[0].execution_authority)
        self.assertEqual(
            next_advisory_route_steps(catalog, map_id=1, level=1),
            (catalog.entries[3],),
        )

    def test_route_teacher_cursor_rejects_bad_cursor_inputs(self) -> None:
        catalog = KnowledgeBrokerCatalog(
            catalog_id="fixture.knowledge.cursor",
            target_profile="tbc243_lab",
            product="wow",
            expansion="the_burning_crusade",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            entries=(
                _entry(
                    kind="route_step",
                    source=_source(provider="route_teacher", origin="route_guidance"),
                    entry_id="route.step.001",
                ),
            ),
        )
        with self.assertRaises(KnowledgeBrokerError):
            next_advisory_route_steps(catalog, map_id=0, level=0)
        with self.assertRaises(KnowledgeBrokerError):
            next_advisory_route_steps(catalog, map_id=0, level=1, limit=0)

    def test_modern_steps_keep_last_explicit_zone_for_coordinate_less_steps(self) -> None:
        text = '''
ZygorGuidesViewer:RegisterGuide("fixture",{},[[
step
|goto Zone A 10,20
step
talk A Trainer##1
step
|goto Zone B 30,40
step
kill A Mob##2
]])
'''
        config = RouteTeacherImportConfig(
            catalog_id="fixture.zygor.zone-context",
            target_profile="tbc243_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            provider_version="8.1.37070",
            retrieved_at="2026-08-31T19:00:00Z",
            source_uri="local://guide.lua",
            default_map_id=0,
            default_map_name="Azeroth",
            zone_map_bindings={
                "Zone A": (0, "Azeroth"),
                "Zone B": (1, "Kalimdor"),
            },
        )
        catalog = import_zygor_lua(text, config=config)
        self.assertEqual([entry.map_id for entry in catalog.entries], [0, 0, 1, 1])

    def test_modern_comment_goto_is_not_imported_as_route_coordinate(self) -> None:
        text = '''
ZygorGuidesViewer:RegisterGuide("fixture",{},[[
step
\tmap Zone A/0
\t|goto Zone A/0 10,20
//step
//\t|goto Instance Only/2 0,0
]])
'''
        config = RouteTeacherImportConfig(
            catalog_id="fixture.zygor.comment-goto",
            target_profile="tbc243_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            provider_version="8.1.37070",
            retrieved_at="2026-08-31T19:00:00Z",
            source_uri="local://guide.lua",
            default_map_id=0,
            default_map_name="Azeroth",
            zone_map_bindings={"Zone A": (0, "Azeroth")},
        )
        catalog = import_zygor_lua(text, config=config)
        self.assertEqual(len(catalog.entries), 1)
        self.assertIsNotNone(catalog.entries[0].position)
        self.assertEqual(catalog.entries[0].map_id, 0)

    def test_legacy_mapzone_keeps_apostrophe_in_zone_name(self) -> None:
        text = '''
ZygorGuidesViewer_HordeGuide = {
  { steps = {
    {
      "Go to Un'Goro Crater",
      completion={{location={mapzone="Un'Goro Crater"}}},
      mapzone="Un'Goro Crater",
      level=54,
    },
  }},
}
'''
        config = RouteTeacherImportConfig(
            catalog_id="fixture.zygor.apostrophe-zone",
            target_profile="tbc243_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            provider_version="8.1.37070",
            retrieved_at="2026-09-01T00:00:00Z",
            source_uri="local://guide.lua",
            default_map_id=0,
            default_map_name="Azeroth",
            zone_map_bindings={"Un'Goro Crater": (1, "Kalimdor")},
        )
        catalog = import_zygor_lua(text, config=config)
        self.assertEqual(len(catalog.entries), 1)
        self.assertEqual(catalog.entries[0].map_name, "Kalimdor")

    def test_npc_data_keeps_zone_area_scope_and_classifies_trainers(self) -> None:
        text = '''
ZGV._NPCData={
  ["TrainerAlchemy"] = [[
    4160=sA|m1453|x64.07|y68.36|wInside the building -- Stormwind City/0, Ainsha Bloodhorn
  ]],
  ["ClassRogue"] = [[
    4583=sH|m1458|x31.20|y48.50|Rogue trainer, Vol'jin
  ]],
  ["Repair"] = [[
    --123=sA|m1453|x1|y2|commented
    1287=sA|m1453|x64.20|y68.59
  ]],
}
'''
        config = NpcDataImportConfig(
            catalog_id="fixture.npcdata.tbc243",
            target_profile="tbc243_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            provider_version="8.1.37070",
            retrieved_at="2026-08-31T19:00:00Z",
            source_uri="local://Zygor-RAR!/Data-TBC/NPCData.lua",
            zone_area_bindings={1453: "Stormwind City", 1458: "The Barrens"},
        )

        catalog = import_zygor_npc_data(text, config=config)
        ContractValidator(SCHEMA).validate(catalog.to_record())
        self.assertEqual(len(catalog.entries), 3)
        self.assertEqual(len(catalog.by_kind("profession_trainer", map_scope="zone_area")), 1)
        self.assertEqual(len(catalog.by_kind("class_trainer", map_scope="zone_area")), 1)
        self.assertEqual(len(catalog.by_map(
            map_id=1453, map_name="Stormwind City", map_scope="zone_area"
        )), 2)
        self.assertEqual(catalog.entries[0].position.position_semantics, "STATIC_SOURCE_CANDIDATE")
        self.assertFalse(catalog.entries[0].execution_authority)

    def test_npc_data_requires_explicit_map_binding_and_rejects_malformed_rows(self) -> None:
        config = NpcDataImportConfig(
            catalog_id="fixture.npcdata.tbc243",
            target_profile="tbc243_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            provider_version="8.1.37070",
            retrieved_at="2026-08-31T19:00:00Z",
            source_uri="local://NPCData.lua",
            zone_area_bindings={},
        )
        with self.assertRaises(NpcDataImportError):
            import_zygor_npc_data(
                'ZGV._NPCData={ ["Repair"] = [[\n1=sA|m9999|x1|y2\n]] }',
                config=config,
            )
        with self.assertRaises(NpcDataImportError):
            import_zygor_npc_data(
                'ZGV._NPCData={ ["Repair"] = [[\n1=sA|m1453|x1\n]] }',
                config=config,
            )


if __name__ == "__main__":
    unittest.main()
