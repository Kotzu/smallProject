from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "integrations" / "windows-input" / "run_movement_engine_client.py"
)


def _load_module():
    module_directory = str(MODULE_PATH.parent)
    if module_directory not in sys.path:
        sys.path.insert(0, module_directory)
    spec = importlib.util.spec_from_file_location(
        "movement_engine_client_autonomy_test", MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MovementEngineUiAutonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module()

    def test_autonomous_ui_never_invents_a_fallback_route_without_live_pose(self) -> None:
        client = object.__new__(self.module.MovementEngineClient)
        client.last_snapshot = None
        client.semantic_journey_anchor = (1.0, 2.0)
        client.semantic_locations = {
            "settlement:brill": ("Brill", 2259.25, 290.43),
            "settlement:deathknell": ("Deathknell", 2000.0, 1400.0),
        }

        route, diagnostics = client._load_semantic_journey("settlement:brill")

        self.assertEqual(route, ())
        self.assertIsNone(client.semantic_journey_anchor)
        self.assertIn("când apeși PORNEȘTE", diagnostics)
        self.assertEqual(diagnostics, "Aleg drumul când apeși PORNEȘTE")

    def test_starting_state_rejects_a_second_launch_before_process_exists(self) -> None:
        client = object.__new__(self.module.MovementEngineClient)
        client.state = "STARTING"
        client.process = None
        client._apply_autonomous_start_readiness = Mock(
            side_effect=AssertionError("duplicate start reached preparation"),
        )

        client.start()

        client._apply_autonomous_start_readiness.assert_not_called()

    def test_profile_catalog_loader_binds_non_default_map_identity(self) -> None:
        catalog = {
            "record_type": "semantic_location_catalog",
            "schema_version": "1.0",
            "map_name": "SyntheticDungeon",
            "zone_index": 77,
            "coordinate_system": "tbc243_client_world_xy",
            "atlas_calibration": "WorldMapArea.dbc:SyntheticDungeon",
            "locations": [
                {
                    "id": "landmark:entrance",
                    "name": "Synthetic Entrance",
                    "world": [10.0, 20.0],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            locations = self.module.MovementEngineClient._load_semantic_locations(
                path,
                expected_map_name="SyntheticDungeon",
            )
        self.assertEqual(
            locations,
            {"landmark:entrance": ("Synthetic Entrance", 10.0, 20.0)},
        )

    def test_profile_catalog_loader_rejects_cross_map_catalog(self) -> None:
        catalog = {
            "record_type": "semantic_location_catalog",
            "schema_version": "1.0",
            "map_name": "Azeroth",
            "zone_index": 25,
            "coordinate_system": "tbc243_client_world_xy",
            "atlas_calibration": "WorldMapArea.dbc:Tirisfal",
            "locations": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "WorldPack"):
                self.module.MovementEngineClient._load_semantic_locations(
                    path,
                    expected_map_name="Shadowfang",
                )

    def test_profile_catalog_zone_index_is_read_from_selected_catalog(self) -> None:
        catalog = {
            "record_type": "semantic_location_catalog",
            "schema_version": "1.0",
            "map_name": "Kalimdor",
            "zone_index": 14,
            "coordinate_system": "tbc243_client_world_xy",
            "atlas_calibration": "WorldMapArea.dbc:Durotar",
            "locations": [{
                "id": "settlement:orgrimmar",
                "name": "Orgrimmar",
                "world": [-5000.0, 1000.0],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            zone_index = self.module.MovementEngineClient._semantic_catalog_zone_index(
                path,
                expected_map_name="Kalimdor",
            )
        self.assertEqual(zone_index, 14)

    def test_autonomous_launch_passes_selected_zone_transform_catalog(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        launch = source[
            source.index("def _prepare_and_launch(self, destination_id") :
            source.index("def start(self)", source.index("def _prepare_and_launch(self, destination_id"))
        ]
        self.assertIn('"--zone-transform-catalog", str(WORLD_MAP_ZONE_TRANSFORM_CATALOG)', launch)
        self.assertIn('"--expected-zone-index", str(expected_zone_index)', launch)
        self.assertNotIn('"--expected-zone-index", "25"', launch)

    def test_semantic_planning_uses_the_selected_profile_runtime(self) -> None:
        class Planner:
            def __init__(self, *, sidecar_root):
                self.sidecar_root = sidecar_root

            def plan(self, **_kwargs):
                return SimpleNamespace(
                    waypoints=(SimpleNamespace(x=3.0, y=4.0),),
                    offroad_bridge_cell_count=0,
                )

        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "selected-profile.json"
            runtime.write_text("{}", encoding="utf-8")
            client = object.__new__(self.module.MovementEngineClient)
            client.last_snapshot = SimpleNamespace(
                player_world_x=1.0,
                player_world_y=2.0,
            )
            client.semantic_journey_anchor = None
            client.semantic_locations = {
                "landmark:destination": ("Destination", 3.0, 4.0),
            }
            client.active_world_map_profile = SimpleNamespace(
                runtime_profile=runtime,
            )
            binding = SimpleNamespace(
                pack=SimpleNamespace(pack_root=Path(directory) / "pack")
            )
            with (
                patch.object(self.module, "_cached_world_pack_binding", return_value=binding) as loader,
                patch.object(self.module, "ClientRoadSemanticPlanner", Planner),
            ):
                route, diagnostics = client._load_semantic_journey(
                    "landmark:destination"
                )
        self.assertEqual(route, ((3.0, 4.0),))
        self.assertEqual(diagnostics, "Am ales drumul: 1 puncte")
        loader.assert_called_once_with(
            runtime.resolve(), self.module.WORLD_PACK_STORE.resolve(),
        )

    def test_operator_editor_layers_are_hidden_while_autonomous(self) -> None:
        class Variable:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        client = object.__new__(self.module.MovementEngineClient)
        client.journey_mode = Variable("autonomous_destination")
        client.click_add_enabled = Variable(False)
        self.assertFalse(client._show_operator_editor_layers())

        client.click_add_enabled = Variable(True)
        self.assertTrue(client._show_operator_editor_layers())

        client.click_add_enabled = Variable(False)
        client.journey_mode = Variable("operator_route")
        self.assertTrue(client._show_operator_editor_layers())

    def test_destination_label_does_not_call_it_a_mission(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('text="Unde merge?"', source)
        self.assertNotIn('text="Misiune"', source)

    def test_control_center_exposes_closed_loop_sequence_option(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('text="La final, revino la primul loc"', source)
        launch = source[
            source.index("def _prepare_and_launch(self, destination_id") :
            source.index("def start(self)", source.index("def _prepare_and_launch(self, destination_id"))
        ]
        self.assertIn('"close_loop": bool(sequence_close_loop)', launch)

    def test_control_center_labels_topographic_but_not_semantic_profiles(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("def _world_map_readiness_label", source)
        self.assertIn("SE VEDE • NU ȘTIE ÎNCĂ LOCURILE", source)
        self.assertIn("readiness.topographic_ready", source)

    def test_route_teacher_coverage_is_read_only_and_content_minimal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.json"
            path.write_text(json.dumps({
                "record_type": "zygor_guide_coverage",
                "schema_version": "1.0",
                "execution_authority": False,
                "coverage_state": "SELECTED_NON_TRIAL_FILES",
                "step_count": 14748,
                "coordinate_candidate_count": 11687,
                "kind_counts": {
                    "class_trainer": 730,
                    "profession_trainer": 663,
                    "class_quest": 826,
                    "profession_quest": 29,
                },
            }), encoding="utf-8")
            text = self.module._zygor_guide_coverage_text(path)
        self.assertIn("14.748 pași", text)
        self.assertIn("11.687 coordonate candidate", text)
        self.assertIn("read-only", text)
        self.assertNotIn("Zygor RouteTeacher: audit indisponibil", text)

    def test_route_teacher_coverage_rejects_execution_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.json"
            path.write_text(json.dumps({
                "record_type": "zygor_guide_coverage",
                "schema_version": "1.0",
                "execution_authority": True,
                "coverage_state": "SELECTED_NON_TRIAL_FILES",
                "step_count": 1,
                "coordinate_candidate_count": 1,
                "kind_counts": {
                    "class_trainer": 0,
                    "profession_trainer": 0,
                    "class_quest": 0,
                    "profession_quest": 0,
                },
            }), encoding="utf-8")
            text = self.module._zygor_guide_coverage_text(path)
        self.assertIn("audit indisponibil", text)

    def test_route_teacher_map_coverage_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route-coverage.json"
            path.write_text(json.dumps({
                "record_type": "zygor_route_coverage",
                "schema_version": "1.0",
                "execution_authority": False,
                "coverage_state": "BOUND_EXPLICIT_ZONE_MAPS",
                "map_coverage": [
                    {"map_id": 0, "map_name": "Azeroth", "step_count": 6495,
                     "coordinate_candidate_count": 3434},
                    {"map_id": 1, "map_name": "Kalimdor", "step_count": 3918,
                     "coordinate_candidate_count": 3918},
                ],
            }), encoding="utf-8")
            text = self.module._zygor_route_coverage_text(path)
        self.assertIn("Azeroth 6.495", text)
        self.assertIn("Kalimdor 3.918", text)
        self.assertIn("read-only", text)

    def test_route_teacher_map_coverage_rejects_execution_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route-coverage.json"
            path.write_text(json.dumps({
                "record_type": "zygor_route_coverage",
                "schema_version": "1.0",
                "execution_authority": True,
                "coverage_state": "BOUND_EXPLICIT_ZONE_MAPS",
                "map_coverage": [
                    {"map_id": 0, "map_name": "Azeroth", "step_count": 1,
                     "coordinate_candidate_count": 1},
                ],
            }), encoding="utf-8")
            text = self.module._zygor_route_coverage_text(path)
        self.assertIn("audit indisponibil", text)

    def test_route_teacher_transform_coverage_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route-transform-coverage.json"
            path.write_text(json.dumps({
                "record_type": "zygor_route_transform_coverage",
                "schema_version": "1.0",
                "execution_authority": False,
                "coverage_state": "PARTIAL_CLIENT_2D_TRANSFORM",
                "coordinate_candidate_count": 11687,
                "transformed_coordinate_count": 11686,
                "unresolved_coordinate_count": 1,
                "map_coverage": [
                    {"map_id": 0, "map_name": "Azeroth",
                     "coordinate_candidate_count": 3434,
                     "transformed_coordinate_count": 3434},
                    {"map_id": 530, "map_name": "Expansion01",
                     "coordinate_candidate_count": 4334,
                     "transformed_coordinate_count": 4334},
                ],
            }), encoding="utf-8")
            text = self.module._zygor_route_transform_coverage_text(path)
        self.assertIn("11.686/11.687", text)
        self.assertIn("Azeroth 3.434/3.434", text)
        self.assertIn("read-only", text)
        self.assertIn("1 nerezolvate", text)

    def test_route_teacher_transform_coverage_rejects_execution_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route-transform-coverage.json"
            path.write_text(json.dumps({
                "record_type": "zygor_route_transform_coverage",
                "schema_version": "1.0",
                "execution_authority": True,
                "coverage_state": "COMPLETE_CLIENT_2D_TRANSFORM",
                "coordinate_candidate_count": 1,
                "transformed_coordinate_count": 1,
                "unresolved_coordinate_count": 0,
                "map_coverage": [{
                    "map_id": 0, "map_name": "Azeroth",
                    "coordinate_candidate_count": 1,
                    "transformed_coordinate_count": 1,
                }],
            }), encoding="utf-8")
            text = self.module._zygor_route_transform_coverage_text(path)
        self.assertIn("audit indisponibil", text)

    def test_npcdata_coverage_is_static_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "npcdata.json"
            path.write_text(json.dumps({
                "record_type": "zygor_npcdata_audit",
                "schema_version": "1.0",
                "execution_authority": False,
                "row_count": 3255,
                "map_area_count": 66,
                "kind_counts": {
                    "class_trainer": 286,
                    "profession_trainer": 287,
                    "npc_static": 2682,
                },
            }), encoding="utf-8")
            text = self.module._zygor_npcdata_coverage_text(path)
        self.assertIn("3.255 intrări", text)
        self.assertIn("66 zone", text)
        self.assertIn("287 traineri profesie", text)
        self.assertIn("read-only", text)

    def test_npcdata_coverage_rejects_execution_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "npcdata.json"
            path.write_text(json.dumps({
                "record_type": "zygor_npcdata_audit",
                "schema_version": "1.0",
                "execution_authority": True,
                "row_count": 1,
                "map_area_count": 1,
                "kind_counts": {
                    "class_trainer": 1,
                    "profession_trainer": 1,
                    "npc_static": 1,
                },
            }), encoding="utf-8")
            text = self.module._zygor_npcdata_coverage_text(path)
        self.assertIn("audit indisponibil", text)

    def test_zygor_map_area_reconciliation_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reconciliation.json"
            path.write_text(json.dumps({
                "record_type": "zygor_world_map_reconciliation",
                "schema_version": "1.0",
                "execution_authority": False,
                "reconciliation_status": "PARTIAL",
                "map_area_count": 66,
                "resolved_map_area_count": 62,
                "ambiguous_map_area_count": 0,
                "unresolved_map_area_count": 4,
            }), encoding="utf-8")
            text = self.module._zygor_world_map_reconciliation_text(path)
        self.assertIn("62/66 rezolvate", text)
        self.assertIn("4 nerezolvate", text)
        self.assertIn("read-only", text)

    def test_zygor_map_area_reconciliation_rejects_execution_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reconciliation.json"
            path.write_text(json.dumps({
                "record_type": "zygor_world_map_reconciliation",
                "schema_version": "1.0",
                "execution_authority": True,
                "reconciliation_status": "COMPLETE",
                "map_area_count": 1,
                "resolved_map_area_count": 1,
                "ambiguous_map_area_count": 0,
                "unresolved_map_area_count": 0,
            }), encoding="utf-8")
            text = self.module._zygor_world_map_reconciliation_text(path)
        self.assertIn("audit indisponibil", text)

    def test_world_map_zone_transform_coverage_is_read_only(self) -> None:
        text = self.module._world_map_zone_transform_text()
        self.assertIn("68 map-area-uri", text)
        self.assertIn("read-only", text)
        self.assertIn("fără înălțime/execuție", text)

    def test_world_map_zone_transform_coverage_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transforms.json"
            record = json.loads(
                self.module.WORLD_MAP_ZONE_TRANSFORM_CATALOG.read_text(
                    encoding="utf-8"
                )
            )
            record["execution_authority"] = True
            path.write_text(json.dumps(record), encoding="utf-8")
            text = self.module._world_map_zone_transform_text(path)
        self.assertIn("catalog indisponibil", text)

    def test_autonomous_start_uses_journey_combat_supervisor(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        launch = source[
            source.index("def _prepare_and_launch(self, destination_id") :
            source.index("def start(self)", source.index("def _prepare_and_launch(self, destination_id"))
        ]
        self.assertIn("str(JOURNEY_COMBAT_SUPERVISOR)", launch)
        self.assertIn('"--acknowledge-autonomous-journey-combat"', launch)
        self.assertIn('"--session-receipt", str(SESSION_RECEIPT)', launch)
        self.assertIn('"--runtime-arm-wait-seconds", "120"', launch)
        self.assertIn('"--resume-on-runtime-arm-expiry"', launch)
        self.assertNotIn("str(ROUTE_RUNNER)", launch)
        self.assertNotIn('"--acknowledge-navmesh-roaming"', launch)

    def test_autonomous_start_rebinds_verified_gate_before_session_arms(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        launch = source[
            source.index("def _prepare_and_launch(self, destination_id") :
            source.index("def start(self)", source.index("def _prepare_and_launch(self, destination_id"))
        ]
        rebind = "self._set_semantic_live_authority(True)"
        self.assertIn(rebind, launch)
        self.assertLess(launch.index(rebind), launch.index("issue_lab_session_authorization.py"))

    def test_checkbox_updates_and_revokes_semantic_live_gate(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        handler = source[
            source.index("def _continuous_motion_permission_changed") :
            source.index("def _run_hidden_checked", source.index("def _continuous_motion_permission_changed"))
        ]
        self.assertIn("self._set_semantic_live_authority(True)", handler)
        self.assertIn("self._set_semantic_live_authority(False)", handler)

    def test_control_center_exposes_zygor_level_selector_and_plan_launch(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('text="Folosește ghidul"', source)
        self.assertIn('text="Nivel:"', source)
        self.assertIn("LevelingBrain().plan", source)
        launch = source[
            source.index("def _prepare_and_launch(self, destination_id") :
            source.index("def start(self)", source.index("def _prepare_and_launch(self, destination_id"))
        ]
        self.assertIn('"--goal-normalized-x"', launch)
        self.assertIn('"--leveling-plan-file", str(LEVELING_PLAN_FILE)', launch)

    def test_leveling_settings_have_safe_level_defaults(self) -> None:
        with patch.object(self.module, "SETTINGS_FILE", Path("Z:/missing-leveling-settings.json")):
            settings = self.module.MovementEngineClient._load_settings()
        self.assertFalse(settings["leveling_enabled"])
        self.assertEqual(settings["current_level"], 1)
        self.assertTrue(str(settings["zygor_catalog_path"]).endswith("zygor-leveling-catalog.json"))

    def test_autonomous_start_uses_validated_adaptive_steering_profile(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        launch = source[
            source.index("def _prepare_and_launch(self, destination_id") :
            source.index("def start(self)", source.index("def _prepare_and_launch(self, destination_id"))
        ]
        self.assertIn('"--steering-controller", "adaptive_trajectory_v1"', launch)
        self.assertIn('"--mppi-batch-size", "256"', launch)
        self.assertIn('"--mppi-time-steps", "56"', launch)

    def test_autonomous_movement_preserves_operator_requested_lab_protection(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        launch = source[
            source.index("def _prepare_and_launch(self, destination_id") :
            source.index("def start(self)", source.index("def _prepare_and_launch(self, destination_id"))
        ]
        self.assertIn('"-State", "On", "-PlayerName", "Predator"', launch)
        self.assertNotIn('"-State", "Off", "-PlayerName", "Predator"', launch)

    def test_controlled_combat_keeps_protection_scoped_to_combat_path(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        combat = source[
            source.index("def _prepare_and_launch_combat") :
            source.index("def _combat_start", source.index("def _prepare_and_launch_combat"))
        ]
        self.assertIn('"-State", "On", "-PlayerName", "Predator"', combat)

    def test_manual_combat_remains_separate_from_autonomous_supervisor(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        manual = source[
            source.index("def _prepare_and_launch_combat") :
            source.index("def _combat_start", source.index("def _prepare_and_launch_combat"))
        ]
        start = source[
            source.index("def _combat_start") :
            source.index("def _set_combat_running", source.index("def _combat_start"))
        ]
        self.assertIn("str(COMBAT_RUNNER)", manual)
        self.assertIn('"--acknowledge-controlled-combat"', manual)
        self.assertIn("if self.process is not None", start)
        self.assertIn("Oprește mersul singur", start)

    def test_road_semantics_checkbox_redraws_the_map_immediately(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        road_checkbox = source[
            source.index('text="Arată drumurile"') - 80:
            source.index('text="Arată suprafața pe care poate merge"')
        ]
        self.assertIn("command=self._operator_editor_visibility_changed", road_checkbox)

    def test_3d_viewer_is_named_3d_mesh_map(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('text="Hartă 3D"', source)
        self.assertNotIn('text="3D la Predator"', source)
        self.assertIn('messagebox.showerror("Harta 3D"', source)

    def test_3d_viewer_hides_launcher_command_for_server_config_drift(self) -> None:
        error = subprocess.CalledProcessError(
            1,
            ["pwsh", "-File", "operator.ps1"],
            stderr="LAB listener 3443 config hash does not match authorization.",
        )
        detail = self.module._friendly_3d_mesh_map_error(error)
        self.assertEqual(
            detail,
            "Harta s-a schimbat. Închide și deschide din nou Harta 3D.",
        )
        self.assertNotIn("pwsh", detail)

    def test_3d_viewer_can_zero_input_rebind_after_lab_config_change(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        viewer = source[
            source.index("def _prepare_3d_navmesh_viewer") :
            source.index("def _open_3d_navmesh_viewer")
        ]
        self.assertIn('"-AcknowledgeAuthorizationRebind"', viewer)
        self.assertIn('"exact fixed-UI semantic profile"', viewer)
        self.assertNotIn('"-AcknowledgeRuntimeArm"', viewer)

    def test_3d_viewer_does_not_steal_focus_after_live_bridge_starts(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        viewer = source[
            source.index("def _prepare_3d_navmesh_viewer") :
            source.index("def _open_3d_navmesh_viewer")
        ]
        bridge_launch = viewer.index("self.nav_viewer_bridge_process = subprocess.Popen")
        bridge_health_check = viewer.index(
            "if self.nav_viewer_bridge_process.poll() is not None", bridge_launch,
        )
        self.assertNotIn("_focus_exact_wow_window()", viewer[bridge_health_check:])


if __name__ == "__main__":
    unittest.main()
