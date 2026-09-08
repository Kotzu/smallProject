from __future__ import annotations

import tempfile
import unittest
import json
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from perfect_assassin.adapter.saved_variables import SavedVariablesParseError, parse_saved_variables
from perfect_assassin.adapter.tbc243_saved_variables import (
    Tbc243SavedVariablesError,
    Tbc243SavedVariablesObservationSource,
)
from perfect_assassin.application.tbc243_intake import RunTbc243SavedVariablesIntake
from perfect_assassin.contract_validation import ContractValidationError, ContractValidator
from perfect_assassin.domain.capabilities import CapabilityProfile
from perfect_assassin.observer.firewall import ProvenanceFirewall
from perfect_assassin.observer.normalizer import ObservationNormalizer


ROOT = Path(__file__).resolve().parents[1]


def live_hot_reload_test_args() -> list[str]:
    if not shutil.which("pwsh"):
        return []
    probe = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "if (Get-Process -Name Wow -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }",
        ],
        capture_output=True,
        check=False,
    )
    return ["-AcknowledgeLiveHotReload"] if probe.returncode == 0 else []
FIXTURE = ROOT / "data" / "fixtures" / "tbc243_observer_saved_variables.synthetic.lua"
QUEST_FIXTURE = (
    ROOT / "data" / "fixtures" / "tbc243_quest_observer_saved_variables.synthetic.lua"
)


class SavedVariablesParserTests(unittest.TestCase):
    def test_restricted_parser_reads_fixture_without_executing_lua(self) -> None:
        export = parse_saved_variables(FIXTURE)
        self.assertTrue(export["synthetic"])
        self.assertEqual(len(export["events"]), 6)
        self.assertEqual(export["events"][3]["payload"]["a02"], "SPELL_DAMAGE")

    def test_executable_expression_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "malicious.lua"
            path.write_text(
                'PerfectAssassinObserverDB = { payload = os.execute("forbidden") }',
                encoding="utf-8",
            )
            with self.assertRaises(SavedVariablesParseError):
                parse_saved_variables(path)

    def test_wrong_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong.lua"
            path.write_text('OtherAddonDB = { ["events"] = {} }', encoding="utf-8")
            with self.assertRaises(SavedVariablesParseError):
                parse_saved_variables(path)

    def test_legacy_client_implicit_boolean_arrays_are_parsed_as_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "implicit-booleans.lua"
            path.write_text(
                "PerfectAssassinObserverDB = { flags = { false, true, false, true } }",
                encoding="utf-8",
            )
            self.assertEqual(
                parse_saved_variables(path)["flags"],
                [False, True, False, True],
            )


class Tbc243SavedVariablesAdapterTests(unittest.TestCase):
    def _source(self) -> Tbc243SavedVariablesObservationSource:
        return Tbc243SavedVariablesObservationSource(
            FIXTURE,
            ROOT / "config" / "semantic-ids" / "rogue-level-1.json",
            ContractValidator(ROOT / "contracts" / "tbc243-addon-export.schema.json"),
        )

    def test_raw_combat_log_is_archived_but_not_interpreted(self) -> None:
        source = self._source()
        events = list(source.events())
        self.assertEqual(source.archived_raw_events, 1)
        self.assertEqual(source.interpreted_raw_events, 0)
        self.assertEqual(len(events), 5)
        self.assertNotIn("combat_log_raw", {event.kind for event in events})

    def test_verified_party_kill_maps_only_when_destination_is_active_target(self) -> None:
        capture = FIXTURE.read_text(encoding="utf-8")
        capture = capture.replace('["a02"] = "SPELL_DAMAGE",', '["a02"] = "PARTY_KILL",')
        capture = capture.replace(
            '["a07"] = "fixture-creature-0001",',
            '["a06"] = "fixture-creature-0001",\n                ["a07"] = "Synthetic Young Wolf",',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "verified-kill.lua"
            path.write_text(capture, encoding="utf-8")
            source = Tbc243SavedVariablesObservationSource(
                path,
                ROOT / "config" / "semantic-ids" / "rogue-level-1.json",
                ContractValidator(ROOT / "contracts" / "tbc243-addon-export.schema.json"),
            )
            kill = next(event for event in source.events() if event.kind == "target_killed")
            self.assertEqual(source.archived_raw_events, 1)
            self.assertEqual(source.interpreted_raw_events, 1)
            self.assertEqual(
                {(fact.raw_key, fact.value) for fact in kill.facts},
                {
                    ("target_dead", True),
                    ("target_guid", "fixture-creature-0001"),
                    ("target_name", "Synthetic Young Wolf"),
                },
            )
            self.assertTrue(all(fact.capability == "combat_log" for fact in kill.facts))

            unmatched_path = Path(directory) / "unmatched-kill.lua"
            unmatched_path.write_text(
                capture.replace(
                    '["a06"] = "fixture-creature-0001",',
                    '["a06"] = "unrelated-creature",',
                ),
                encoding="utf-8",
            )
            unmatched_source = Tbc243SavedVariablesObservationSource(
                unmatched_path,
                ROOT / "config" / "semantic-ids" / "rogue-level-1.json",
                ContractValidator(ROOT / "contracts" / "tbc243-addon-export.schema.json"),
            )
            self.assertEqual(unmatched_source.interpreted_raw_events, 0)
            self.assertNotIn(
                "target_killed", {event.kind for event in unmatched_source.events()}
            )

    def test_translated_events_pass_firewall_and_semantic_normalization(self) -> None:
        source = self._source()
        profile = CapabilityProfile.from_dict(
            __import__("json").loads(
                (ROOT / "config" / "capabilities" / "tbc_243_lab.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        normalizer = ObservationNormalizer(
            source,
            profile,
            ProvenanceFirewall(profile),
            ContractValidator(ROOT / "contracts" / "core.schema.json"),
        )
        observations = [normalizer.normalize(event) for event in source.events()]
        keys = {fact["key"] for observation in observations for fact in observation["facts"]}
        self.assertIn("world.zone", keys)
        self.assertIn("combat.state", keys)
        self.assertIn("target.dead", keys)
        self.assertIn("loot.item_observed", keys)
        self.assertTrue(all(fact["source"] == "client_observed" for observation in observations for fact in observation["facts"]))

    def test_offline_intake_runs_through_telemetry_replay_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            result = RunTbc243SavedVariablesIntake(ROOT).run(
                FIXTURE, temp / "telemetry.jsonl", temp / "journal.md"
            )
            self.assertTrue(result.synthetic)
            self.assertEqual(result.archived_raw_combat_events, 1)
            self.assertEqual(result.interpreted_raw_combat_events, 0)
            self.assertEqual(result.pipeline.observations, 5)
            self.assertEqual(result.pipeline.decisions, 5)
            self.assertEqual(result.pipeline.encounters, 1)
            records = [
                json.loads(line)
                for line in result.pipeline.telemetry_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(
                all(
                    record.get("execution_mode", "OBSERVE_ONLY") == "OBSERVE_ONLY"
                    for record in records
                )
            )
            self.assertIn(
                "This is not Champion lived memory",
                result.pipeline.journal_path.read_text(encoding="utf-8"),
            )

    def test_duplicate_or_reordered_sequence_is_rejected_before_telemetry(self) -> None:
        source_text = FIXTURE.read_text(encoding="utf-8")
        duplicate = source_text.replace('["seq"] = 2,', '["seq"] = 1,', 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.lua"
            path.write_text(duplicate, encoding="utf-8")
            with self.assertRaises(Tbc243SavedVariablesError):
                Tbc243SavedVariablesObservationSource(
                    path,
                    ROOT / "config" / "semantic-ids" / "rogue-level-1.json",
                    ContractValidator(ROOT / "contracts" / "tbc243-addon-export.schema.json"),
                )

    def test_quest_spellbook_action_bars_and_focus_are_client_observed(self) -> None:
        source = Tbc243SavedVariablesObservationSource(
            QUEST_FIXTURE,
            ROOT / "config" / "semantic-ids" / "rogue-level-1.json",
            ContractValidator(ROOT / "contracts" / "tbc243-addon-export.schema.json"),
        )
        profile = CapabilityProfile.from_dict(
            json.loads(
                (ROOT / "config" / "capabilities" / "tbc_243_lab.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        normalizer = ObservationNormalizer(
            source,
            profile,
            ProvenanceFirewall(profile),
            ContractValidator(ROOT / "contracts" / "core.schema.json"),
        )
        observations = [normalizer.normalize(event) for event in source.events()]
        facts = {
            fact["key"]: fact
            for observation in observations
            for fact in observation["facts"]
        }
        self.assertEqual(facts["quest.npc_name"]["value"], "Synthetic Undertaker")
        self.assertEqual(
            facts["quest.description"]["value"],
            "Rise and report to the shadow priest.",
        )
        self.assertEqual(
            facts["quest.log"]["value"][0]["title"], "Synthetic Rude Awakening"
        )
        self.assertEqual(
            {spell["name"] for spell in facts["player.spellbook"]["value"]},
            {"Attack", "Sinister Strike"},
        )
        self.assertTrue(facts["player.map_position.available"]["value"])
        self.assertAlmostEqual(facts["player.map_position.x"]["value"], 0.42125)
        self.assertAlmostEqual(facts["player.map_position.y"]["value"], 0.61875)
        self.assertEqual(facts["player.action_bars.profile"]["value"], "tbc243_default_24_direct_v1")
        self.assertEqual(facts["player.action_bars.directly_bound_slots"]["value"], 24)
        self.assertEqual(facts["player.action_bars.slots"]["value"][0]["binding_key_1"], "1")
        self.assertEqual(facts["focus.id"]["value"], "fixture-healer-0001")
        self.assertEqual(facts["focus.cast.name"]["value"], "Healing Wave")
        self.assertTrue(facts["focus.casting"]["value"])
        self.assertTrue(all(fact["source"] == "client_observed" for fact in facts.values()))

    def test_mouseover_snapshot_is_a_client_observed_unit_witness(self) -> None:
        capture = QUEST_FIXTURE.read_text(encoding="utf-8")
        capture = capture.replace(
            "        },\n    },\n}\n",
            """        },
        [9] = {
            [\"seq\"] = 9,
            [\"kind\"] = \"mouseover_snapshot\",
            [\"game_time_ms\"] = 2400,
            [\"captured_epoch\"] = 1787389305,
            [\"payload\"] = {
                [\"mouseover_exists\"] = true,
                [\"mouseover_guid\"] = \"fixture-wolf-0001\",
                [\"mouseover_name\"] = \"Synthetic Young Wolf\",
                [\"mouseover_kind\"] = \"npc\",
                [\"mouseover_health_pct\"] = 75,
                [\"mouseover_health_current\"] = 900,
                [\"mouseover_health_max\"] = 1200,
                [\"mouseover_hostile\"] = true,
                [\"mouseover_dead\"] = false,
            },
        },
    },
}
""",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mouseover.lua"
            path.write_text(capture, encoding="utf-8")
            source = Tbc243SavedVariablesObservationSource(
                path,
                ROOT / "config" / "semantic-ids" / "rogue-level-1.json",
                ContractValidator(ROOT / "contracts" / "tbc243-addon-export.schema.json"),
            )
            mouseover = next(
                event for event in source.events() if event.kind == "mouseover_snapshot"
            )
            facts = {fact.raw_key: fact for fact in mouseover.facts}
            self.assertEqual(facts["mouseover_guid"].value, "fixture-wolf-0001")
            self.assertEqual(facts["mouseover_name"].value, "Synthetic Young Wolf")
            self.assertTrue(facts["mouseover_hostile"].value)
            self.assertTrue(all(fact.capability == "mouseover_state" for fact in facts.values()))
            profile = CapabilityProfile.from_dict(
                json.loads(
                    (ROOT / "config" / "capabilities" / "tbc_243_lab.json").read_text(
                        encoding="utf-8"
                    )
                )
            )
            normalizer = ObservationNormalizer(
                source,
                profile,
                ProvenanceFirewall(profile),
                ContractValidator(ROOT / "contracts" / "core.schema.json"),
            )
            normalized = normalizer.normalize(mouseover)
            self.assertTrue(
                all(fact["source"] == "client_observed" for fact in normalized["facts"])
            )
            self.assertFalse(
                any(
                    fact["key"] in {"mouseover.world_position", "mouseover.distance_yards"}
                    for fact in normalized["facts"]
                )
            )

    def test_map_position_payload_rejects_server_only_coordinates(self) -> None:
        capture = QUEST_FIXTURE.read_text(encoding="utf-8").replace(
            '["map_info"] = "SyntheticTirisfal",',
            '["map_info"] = "SyntheticTirisfal",\n'
            '                ["server_world_x"] = 1234.5,',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "server-coordinate-contaminated.lua"
            path.write_text(capture, encoding="utf-8")
            with self.assertRaises(ContractValidationError):
                Tbc243SavedVariablesObservationSource(
                    path,
                    ROOT / "config" / "semantic-ids" / "rogue-level-1.json",
                    ContractValidator(ROOT / "contracts" / "tbc243-addon-export.schema.json"),
                )

    def test_quest_payload_rejects_unknown_server_field(self) -> None:
        capture = QUEST_FIXTURE.read_text(encoding="utf-8").replace(
            '["dialog_text"] = "The crypt is not as quiet as it should be.",',
            '["dialog_text"] = "The crypt is not as quiet as it should be.",\n'
            '                ["server_quest_id"] = 999999,',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "server-contaminated.lua"
            path.write_text(capture, encoding="utf-8")
            with self.assertRaises(ContractValidationError):
                Tbc243SavedVariablesObservationSource(
                    path,
                    ROOT / "config" / "semantic-ids" / "rogue-level-1.json",
                    ContractValidator(ROOT / "contracts" / "tbc243-addon-export.schema.json"),
                )


class Tbc243AddonStaticBoundaryTests(unittest.TestCase):
    def test_addon_declares_20400_and_saved_variables(self) -> None:
        toc = (
            ROOT
            / "integrations"
            / "tbc243-addon"
            / "PerfectAssassinObserver"
            / "PerfectAssassinObserver.toc"
        ).read_text(encoding="utf-8")
        self.assertIn("## Interface: 20400", toc)
        self.assertIn("## SavedVariables: PerfectAssassinObserverDB", toc)

    def test_addon_contains_no_execution_or_external_transport_api(self) -> None:
        lua = (
            ROOT
            / "integrations"
            / "tbc243-addon"
            / "PerfectAssassinObserver"
            / "PerfectAssassinObserver.lua"
        ).read_text(encoding="utf-8")
        forbidden = {
            "AttackTarget",
            "CastSpell",
            "UseAction",
            "TargetUnit",
            "InteractUnit",
            "MoveForwardStart",
            "TurnLeftStart",
            "RunMacro",
            "SendChatMessage",
            "SendAddonMessage",
            "AcceptQuest",
            "CompleteQuest",
            "GetQuestReward",
            "SelectGossipOption",
            "SelectGossipAvailableQuest",
            "SelectAvailableQuest",
        }
        violations = sorted(api for api in forbidden if api in lua)
        self.assertEqual(violations, [])

    def test_coordinate_hud_is_visible_versioned_and_checksummed(self) -> None:
        lua = (
            ROOT
            / "integrations"
            / "tbc243-addon"
            / "PerfectAssassinObserver"
            / "PerfectAssassinObserver.lua"
        ).read_text(encoding="utf-8")
        self.assertIn('PAO_HUD_MAGIC = 165', lua)
        self.assertIn('PAO_HUD_PROTOCOL_VERSION = 3', lua)
        self.assertIn('player_facing_api = type(GetPlayerFacing) == "function"', lua)
        self.assertIn('UnitIsGhost("player")', lua)
        self.assertIn('PAO_Crc16Ccitt', lua)
        self.assertIn('PA TELEMETRY v2', lua)
        self.assertIn('CreateFrame("Frame", "PerfectAssassinObserverHUD", UIParent)', lua)
        self.assertIn('local function PAO_HudOnUpdate(frame, elapsed)', lua)
        self.assertIn('type(delta) ~= "number" and type(arg1) == "number"', lua)
        self.assertIn('local function PAO_SafeUpdateHud()', lua)
        self.assertIn('pcall(PAO_UpdateHud)', lua)
        self.assertIn('PAO_HudText:SetText("HUD ERROR\\n"', lua)
        self.assertIn('local function PAO_Mod(value, divisor)', lua)
        self.assertNotIn('math.mod', lua)
        self.assertIn('PAO_SetHudMarkersVisible(false)', lua)
        self.assertIn('PAO_SetHudMarkersVisible(true)', lua)
        self.assertIn('local payload = PAO_MapPositionPayload(true)', lua)
        self.assertNotIn('PAO_MapPositionPayload(not PAO_MAP_CONTEXT_READY)', lua)
        self.assertIn('PAO_Append("mouseover_snapshot", PAO_MouseoverPayload())', lua)
        self.assertIn('PAO_Frame:RegisterEvent("UPDATE_MOUSEOVER_UNIT")', lua)
        self.assertLess(
            lua.index('PAO_SetHudMarkersVisible(false)'),
            lua.index('PAO_HudText:SetText("HUD ERROR'),
        )

    def test_coordinate_hud_ctrl_drag_is_click_through_persistent_and_capture_safe(self) -> None:
        addon = ROOT / "integrations" / "tbc243-addon" / "PerfectAssassinObserver"
        lua = (addon / "PerfectAssassinObserver.lua").read_text(encoding="utf-8")
        toc = (addon / "PerfectAssassinObserver.toc").read_text(encoding="utf-8")
        profile = json.loads(
            (ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertIn("## Version: 0.5.10", toc)
        self.assertIn("local PAO_NAMEPLATE_REGISTRY = {}", lua)
        self.assertIn("PAO_RefreshNameplateRegistry()", lua)
        self.assertIn("local alpha = frame:GetAlpha()", lua)
        self.assertNotIn("local alpha = healthBar:GetAlpha()", lua)
        self.assertEqual(toc.count("PerfectAssassinObserverDB"), 1)
        self.assertNotIn("PerfectAssassinObserverUI", toc)
        self.assertIn('PAO_HUD_DEFAULT_X = 16', lua)
        self.assertIn('PAO_HUD_DEFAULT_Y = -100', lua)
        self.assertIn('PAO_TARGET_ARROW_BELOW_THRESHOLD = 0.62', lua)
        self.assertIn(
            'if topOriginY > PAO_TARGET_ARROW_BELOW_THRESHOLD then state = "BELOW" end',
            lua,
        )
        self.assertNotIn('if topOriginY > 0.40 then state = "BELOW" end', lua)
        self.assertIn('PAO_Hud:SetMovable(true)', lua)
        self.assertIn('PAO_Hud:SetClampedToScreen(true)', lua)
        self.assertIn('PAO_Hud:SetUserPlaced(true)', lua)
        self.assertIn('PAO_HudMover:RegisterForDrag("LeftButton")', lua)
        self.assertIn('if not PAO_ControlKeyDown() then return end', lua)
        self.assertIn('PAO_Hud:StartMoving()', lua)
        self.assertIn('PAO_Hud:StopMovingOrSizing()', lua)
        self.assertIn('PAO_ClampHudToCaptureRegion()', lua)
        self.assertIn('PAO_ClampHudIfParentChanged()', lua)
        self.assertIn('PAO_HudMover:EnableMouse(shouldEnable)', lua)
        self.assertIn('SLASH_PERFECTASSASSINOBSERVERHUD1 = "/paohud"', lua)
        self.assertLess(
            lua.index('if not PAO_ControlKeyDown() then return end'),
            lua.index('PAO_Hud:StartMoving()'),
        )
        self.assertLess(
            lua.index('PAO_UpdateHudMoverMouse()', lua.index('local function PAO_HudOnUpdate')),
            lua.index('PAO_HUD_ACCUMULATOR = PAO_HUD_ACCUMULATOR + delta'),
        )

        width_fraction = float(
            re.search(r"PAO_HUD_CAPTURE_WIDTH_FRACTION = ([0-9.]+)", lua).group(1)
        )
        height_fraction = float(
            re.search(r"PAO_HUD_CAPTURE_HEIGHT_FRACTION = ([0-9.]+)", lua).group(1)
        )
        self.assertEqual(width_fraction, profile["search_width_fraction"])
        self.assertEqual(height_fraction, profile["search_height_fraction"])

    def test_compact_combat_hud_is_read_only_crc_bound_and_slot_specific(self) -> None:
        addon = ROOT / "integrations" / "tbc243-addon" / "PerfectAssassinObserver"
        lua = (addon / "PerfectAssassinObserver.lua").read_text(encoding="utf-8")
        combat_profile = json.loads(
            (ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("local PAO_HUD_WIDTH = 170", lua)
        self.assertIn("local PAO_HUD_HEIGHT = 79", lua)
        self.assertIn("local PAO_COMBAT_HUD_MAGIC = 198", lua)
        self.assertIn("local PAO_COMBAT_HUD_PROTOCOL_VERSION = 6", lua)
        self.assertIn('PAO_ActionMatchesSpell(2, "Sinister Strike")', lua)
        self.assertIn('PAO_ActionMatchesSpell(3, "Eviscerate")', lua)
        self.assertIn("IsAttackAction(1)", lua)
        self.assertIn("PAO_TargetIdentityCrc16()", lua)
        self.assertIn("PAO_Crc16Ccitt(bytes)", lua)
        self.assertIn("PAO_HudText:Hide()", lua)
        self.assertIn("PAO_CombatHudText:Hide()", lua)
        self.assertEqual(combat_profile["grid_columns"], 16)
        self.assertEqual(combat_profile["grid_rows"], 14)
        self.assertFalse(combat_profile["execution_authority"])

    def test_action_bar_profile_is_operator_invoked_reversible_and_focus_aware(self) -> None:
        lua = (
            ROOT
            / "integrations"
            / "tbc243-addon"
            / "PerfectAssassinObserver"
            / "PerfectAssassinObserver.lua"
        ).read_text(encoding="utf-8")
        self.assertIn('SLASH_PERFECTASSASSINOBSERVERBARS1 = "/paobars"', lua)
        self.assertIn('{ key = "A", command = "STRAFELEFT" }', lua)
        self.assertIn('{ key = "D", command = "STRAFERIGHT" }', lua)
        self.assertIn('{ key = "F", command = "FOCUSTARGET" }', lua)
        self.assertIn('{ key = "SHIFT-F", command = "TARGETFOCUS" }', lua)
        self.assertIn('{ key = "Y", command = "TURNORACTION" }', lua)
        self.assertIn('SetActionBarToggles(true, true, true, true)', lua)
        self.assertIn('SHOW_MULTI_ACTIONBAR_1 = 1', lua)
        self.assertIn('not MultiBarBottomLeft:IsShown()', lua)
        self.assertIn('"MULTIACTIONBAR1BUTTON" .. tostring(index)', lua)
        self.assertIn('PerfectAssassinObserverDB.operator_ui_backup = PAO_CaptureUiBackup()', lua)
        self.assertIn('PAO_TransitionCombatActionSlots(slotState, "profile")', lua)
        self.assertIn('"profile", backup.combat_slots_previous_state', lua)
        self.assertIn('combat_slots_previous_state = nil', lua)
        self.assertIn('return "legacy_3_only"', lua)
        self.assertIn('PAO_FindSpellIndex("Eviscerate")', lua)
        self.assertIn('local function PAO_NormalizedFrameCenter(frame)', lua)
        self.assertIn('local frameScale = frame:GetEffectiveScale()', lua)
        self.assertIn('local parentScale = UIParent:GetEffectiveScale()', lua)
        self.assertIn('PickupSpell(eviscerateIndex, BOOKTYPE_SPELL or "spell")', lua)
        self.assertIn('PAO_ApplyUiBackup(PerfectAssassinObserverDB.operator_ui_backup)', lua)
        self.assertIn('PAO_Append("action_bar_snapshot", PAO_ActionBarPayload())', lua)
        self.assertIn('PAO_Append("focus_snapshot", PAO_FocusPayload())', lua)
        self.assertIn('PAO_Frame:RegisterEvent("PLAYER_FOCUS_CHANGED")', lua)
        self.assertIn("PAO_TARGET_ARROW_CENTER_TOLERANCE = 0.12", lua)

    def test_installer_pins_the_current_addon_artifact_hashes(self) -> None:
        addon = (
            ROOT / "integrations" / "tbc243-addon" / "PerfectAssassinObserver"
        )
        installer = (ROOT / "scripts" / "Install-Tbc243ObserverAddon.ps1").read_text(
            encoding="utf-8"
        )
        for filename in (
            "PerfectAssassinObserver.toc",
            "PerfectAssassinObserver.lua",
            "README.md",
        ):
            digest = hashlib.sha256((addon / filename).read_bytes()).hexdigest().upper()
            self.assertIn(digest, installer)
        self.assertIn("function Assert-NoReparsePointInExistingPath", installer)
        self.assertIn("function Assert-SafeFlatArtifactDirectory", installer)
        self.assertIn("function Remove-ExactArtifactDirectory", installer)
        self.assertIn("Installed observer addon changed after verified-previous classification", installer)
        self.assertNotIn("Remove-Item -LiteralPath $target -Recurse", installer)
        self.assertNotIn("Copy-Item -LiteralPath $target -Destination $backupPath -Recurse", installer)

    def test_live_hot_reload_is_explicit_upgrade_only_and_preserves_default_guard(self) -> None:
        installer = (ROOT / "scripts" / "Install-Tbc243ObserverAddon.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[switch]$AcknowledgeLiveHotReload", installer)
        self.assertIn("if (-not $AcknowledgeLiveHotReload)", installer)
        self.assertIn("-not $UpgradeVerifiedPrevious", installer)
        self.assertIn("$RestoreLatestVerifiedPrevious", installer)
        self.assertIn("requires exactly one running Wow.exe", installer)
        self.assertIn("Stop the client before installing", installer)

    def test_installer_restores_only_the_latest_exact_previous_stable_backup(self) -> None:
        installer = (ROOT / "scripts" / "Install-Tbc243ObserverAddon.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[switch]$RestoreLatestVerifiedPrevious", installer)
        self.assertIn("Microsoft.PowerShell.Management\\Get-Process -Name Wow", installer)
        self.assertIn("function Get-LatestVerifiedPreviousBackup", installer)
        self.assertIn(
            "574B1772464BEE479CD42FCA22F8ADB428CD99DD38DA781AEAE2BD03836BF9C6",
            installer,
        )
        self.assertIn(
            "B0DC944A68B99F1315BFF84EEF947CF3B7B7F866BB56DE9DB502DF0064C3BFA5",
            installer,
        )
        self.assertIn(
            "377EEFA79A9DEF2AE6370628CCE17D9850E70AF1F45781600999C0B590990451",
            installer,
        )
        self.assertIn("data\\runtime\\addon-backups", installer)
        self.assertNotIn("RestoreBackupPath", installer)
        self.assertIn("Assert-SafeFlatArtifactDirectory -Directory $candidate", installer)
        self.assertIn("[DateTime]::TryParseExact", installer)
        self.assertIn("Sort-Object Timestamp, Name -Descending", installer)
        self.assertIn("Observer backup root contains an unexpected or unsafe entry", installer)
        self.assertIn("No exact verified 0.5.9 observer backup", installer)
        self.assertIn("PerfectAssassinObserver-current-before-restore-", installer)
        self.assertIn("Current 0.5.10 observer backup failed validation", installer)
        self.assertIn("Selected previous-stable observer backup changed before restore", installer)
        self.assertIn("Restored observer addon failed exact 0.5.9 hash validation", installer)
        self.assertNotIn("Copy-Item -LiteralPath $previousBackup -Recurse", installer)
        self.assertLess(
            installer.index("Current 0.5.10 observer backup failed validation"),
            installer.index("Remove-ExactArtifactDirectory -Directory $target"),
        )

    def test_installer_only_upgrades_the_immediately_previous_stable(self) -> None:
        installer = (ROOT / "scripts" / "Install-Tbc243ObserverAddon.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "$verifiedPreviousHashSets = @($previousStableHashes)",
            installer,
        )
        for legacy_digest in (
            "AEE9A4F99DE291EEC54C762E5374BA87637D33BE34884568FEB1E20FE9013BC3",
            "EF5C6AF41DF6DD2E223B8C82F8C856DC56E53A908DDE239CF7E06694D9498F3F",
            "CB8C716CA799996C744D028B3FB124C203C434DCC47B2A817BAA84D528CF9FE5",
            "75E93A20179447705A462EF3443FEE38DA244A94E5179576275D43B152461FF2",
            "2FA3DE465C9602E9EBE11E00C05D1C24205DFF2D0500B8B725D0E82ADFD16334",
            "38F6F1922922F4E3744E4F928C038AAF0CBF5D32058E0B28F431F4166622DED1",
        ):
            self.assertNotIn(legacy_digest, installer)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_incomplete_previous_backup_is_removed_after_injected_copy_failure(self) -> None:
        source = (
            ROOT / "integrations" / "tbc243-addon" / "PerfectAssassinObserver"
        )
        original_installer = (
            ROOT / "scripts" / "Install-Tbc243ObserverAddon.ps1"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            staged_source = (
                root
                / "integrations"
                / "tbc243-addon"
                / "PerfectAssassinObserver"
            )
            staged_source.parent.mkdir(parents=True)
            shutil.copytree(source, staged_source)

            client_root = Path(directory) / "client"
            target = (
                client_root
                / "Interface"
                / "AddOns"
                / "PerfectAssassinObserver"
            )
            target.mkdir(parents=True)
            previous_toc = (staged_source / "PerfectAssassinObserver.toc").read_bytes()
            previous_lua = b"fixture previous stable lua\n"
            (target / "PerfectAssassinObserver.toc").write_bytes(previous_toc)
            (target / "PerfectAssassinObserver.lua").write_bytes(previous_lua)
            shutil.copyfile(
                staged_source / "README.md",
                target / "README.md",
            )

            injected = original_installer.replace(
                "574B1772464BEE479CD42FCA22F8ADB428CD99DD38DA781AEAE2BD03836BF9C6",
                hashlib.sha256(previous_toc).hexdigest().upper(),
            ).replace(
                "B0DC944A68B99F1315BFF84EEF947CF3B7B7F866BB56DE9DB502DF0064C3BFA5",
                hashlib.sha256(previous_lua).hexdigest().upper(),
            ).replace(
                "377EEFA79A9DEF2AE6370628CCE17D9850E70AF1F45781600999C0B590990451",
                hashlib.sha256((target / "README.md").read_bytes()).hexdigest().upper(),
            )
            backup_copy = "Copy-ExactArtifactSet -From $target -To $backupPath"
            self.assertEqual(injected.count(backup_copy), 1)
            injected = injected.replace(
                backup_copy,
                "Copy-Item -LiteralPath (Join-Path $target 'PerfectAssassinObserver.toc') -Destination $backupPath\n            throw 'INJECTED_BACKUP_COPY_FAILURE'",
            )
            script_path = root / "scripts" / "Install-Tbc243ObserverAddon.ps1"
            script_path.parent.mkdir(parents=True)
            script_path.write_text(injected, encoding="utf-8")

            command = [
                    "pwsh",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(script_path),
                    "-RepositoryRoot",
                    str(root),
                    "-ClientRoot",
                    str(client_root),
                    "-UpgradeVerifiedPrevious",
                ] + live_hot_reload_test_args()
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "INJECTED_BACKUP_COPY_FAILURE",
                result.stdout + result.stderr,
            )
            self.assertEqual(
                (target / "PerfectAssassinObserver.toc").read_bytes(),
                previous_toc,
            )
            self.assertEqual(
                (target / "PerfectAssassinObserver.lua").read_bytes(),
                previous_lua,
            )
            backup_root = root / "data" / "runtime" / "addon-backups"
            self.assertTrue(backup_root.is_dir())
            self.assertEqual(list(backup_root.iterdir()), [])
            addons_root = client_root / "Interface" / "AddOns"
            self.assertFalse(
                any(path.name.startswith(".PerfectAssassinObserver.stage-") for path in addons_root.iterdir())
            )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_poisoned_backup_root_blocks_upgrade_before_target_removal(self) -> None:
        source = (
            ROOT / "integrations" / "tbc243-addon" / "PerfectAssassinObserver"
        )
        original_installer = (
            ROOT / "scripts" / "Install-Tbc243ObserverAddon.ps1"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            staged_source = (
                root
                / "integrations"
                / "tbc243-addon"
                / "PerfectAssassinObserver"
            )
            staged_source.parent.mkdir(parents=True)
            shutil.copytree(source, staged_source)

            client_root = Path(directory) / "client"
            target = (
                client_root
                / "Interface"
                / "AddOns"
                / "PerfectAssassinObserver"
            )
            target.mkdir(parents=True)
            previous_toc = (staged_source / "PerfectAssassinObserver.toc").read_bytes()
            previous_lua = b"fixture previous stable lua\n"
            (target / "PerfectAssassinObserver.toc").write_bytes(previous_toc)
            (target / "PerfectAssassinObserver.lua").write_bytes(previous_lua)
            shutil.copyfile(staged_source / "README.md", target / "README.md")

            patched = original_installer.replace(
                "574B1772464BEE479CD42FCA22F8ADB428CD99DD38DA781AEAE2BD03836BF9C6",
                hashlib.sha256(previous_toc).hexdigest().upper(),
            ).replace(
                "B0DC944A68B99F1315BFF84EEF947CF3B7B7F866BB56DE9DB502DF0064C3BFA5",
                hashlib.sha256(previous_lua).hexdigest().upper(),
            ).replace(
                "377EEFA79A9DEF2AE6370628CCE17D9850E70AF1F45781600999C0B590990451",
                hashlib.sha256((target / "README.md").read_bytes()).hexdigest().upper(),
            )
            script_path = root / "scripts" / "Install-Tbc243ObserverAddon.ps1"
            script_path.parent.mkdir(parents=True)
            script_path.write_text(patched, encoding="utf-8")
            backup_root = root / "data" / "runtime" / "addon-backups"
            backup_root.mkdir(parents=True)
            (backup_root / "unexpected.partial").write_text(
                "poison",
                encoding="utf-8",
            )

            command = [
                    "pwsh",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(script_path),
                    "-RepositoryRoot",
                    str(root),
                    "-ClientRoot",
                    str(client_root),
                    "-UpgradeVerifiedPrevious",
                ] + live_hot_reload_test_args()
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "unexpected or unsafe entry",
                result.stdout + result.stderr,
            )
            self.assertEqual(
                (target / "PerfectAssassinObserver.toc").read_bytes(),
                previous_toc,
            )
            self.assertEqual(
                (target / "PerfectAssassinObserver.lua").read_bytes(),
                previous_lua,
            )


if __name__ == "__main__":
    unittest.main()
