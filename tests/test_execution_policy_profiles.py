from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


ROOT = Path(__file__).resolve().parents[1]


def load_profile(name: str) -> dict[str, Any]:
    path = ROOT / "config" / "capabilities" / name
    return json.loads(path.read_text(encoding="utf-8"))


def load_execution_target(name: str) -> dict[str, Any]:
    path = ROOT / "config" / "execution-targets" / name
    return json.loads(path.read_text(encoding="utf-8"))


class ExecutionPolicyProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization_validator = ContractValidator(
            ROOT / "contracts" / "execution-target-authorization.schema.json"
        )

    def test_public_anniversary_profile_denies_synthetic_execution(self) -> None:
        profile = load_profile("tbc_anniversary.json")
        capabilities = profile["capabilities"]
        self.assertEqual(capabilities["autonomous_input"], "unavailable")
        self.assertEqual(capabilities["user_mode_synthetic_input"], "unavailable")

    def test_client_intrusive_capabilities_are_unavailable_everywhere(self) -> None:
        for name in ("tbc_243_lab.json", "tbc_anniversary.json"):
            with self.subTest(profile=name):
                capabilities = load_profile(name)["capabilities"]
                self.assertEqual(
                    capabilities["client_process_memory_read"], "unavailable"
                )
                self.assertEqual(capabilities["kernel_hid_input"], "unavailable")

    def test_lab_synthetic_execution_still_requires_restricted_approval(self) -> None:
        profile = load_profile("tbc_243_lab.json")
        capabilities = profile["capabilities"]
        self.assertEqual(capabilities["autonomous_input"], "restricted")
        self.assertEqual(capabilities["user_mode_synthetic_input"], "restricted")

    def test_execution_target_configs_are_valid(self) -> None:
        paths = sorted((ROOT / "config" / "execution-targets").glob("*.json"))
        self.assertGreaterEqual(len(paths), 2)
        for path in paths:
            with self.subTest(target=path.name):
                self.authorization_validator.validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )

    def test_authorization_v2_binds_approved_target_to_exact_actor_instance(self) -> None:
        target = load_execution_target("tbc_243_lab.json")
        self.assertEqual(target["schema_version"], "2.0")
        binding = target["actor_binding"]
        self.assertEqual(binding["schema_version"], "1.0")
        self.assertEqual(binding["actor_role"], "lab_clone")
        self.assertEqual(binding["decision_context"], "lab_clone")
        self.assertTrue(binding["instance_id"])
        self.assertTrue(binding["actor_id"])
        self.assertTrue(binding["memory_namespace"])
        self.assertEqual(binding["expected_character_name"], "Predator")
        self.assertNotIn("character_name", binding)
        self.assertTrue(binding["credential_alias"])
        self.assertEqual(
            binding["binding_assurance"]["state"],
            "configured_expected_only",
        )
        self.assertEqual(
            set(target["permitted_capabilities"]),
            {
                "SCREEN_CAPTURE_READ_ONLY",
                "VISIBLE_COORDINATE_HUD_READ_ONLY",
                "LAB_OPERATOR_FIXED_UI",
            },
        )
        self.assertEqual(target["permitted_modes"], [])

        missing_binding = copy.deepcopy(target)
        missing_binding["actor_binding"] = None
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(missing_binding)

        falsely_verified = load_execution_target("tbc_243_lab.json")
        falsely_verified["actor_binding"]["binding_assurance"]["state"] = (
            "client_visible_verified"
        )
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(falsely_verified)

    def test_actor_role_cannot_be_relabelled_as_another_decision_context(self) -> None:
        target = load_execution_target("tbc_243_lab.json")
        target["actor_binding"]["decision_context"] = "champion"
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(target)

        target = load_execution_target("tbc_243_lab.json")
        target["actor_binding"]["actor_role"] = "champion_journey"
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(target)

    def test_approved_client_match_requires_structured_exact_build(self) -> None:
        target = load_execution_target("tbc_243_lab.json")
        del target["client_match"]["client_build"]
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(target)

    def test_local_listener_binding_requires_exact_instance_pins(self) -> None:
        for missing_field in (
            "command_line_arguments",
            "config_path",
            "config_sha256",
        ):
            with self.subTest(missing_field=missing_field):
                target = load_execution_target("tbc_243_lab.json")
                del target["realm_match"]["listener_bindings"][0][missing_field]
                with self.assertRaises(ContractValidationError):
                    self.authorization_validator.validate(target)

    def test_local_realm_route_requires_sanitized_exact_database_record(self) -> None:
        for missing_field in (
            "routing_probe",
            "expected_routing_records",
            "expected_routing_sha256",
        ):
            with self.subTest(missing_field=missing_field):
                target = load_execution_target("tbc_243_lab.json")
                del target["realm_match"][missing_field]
                with self.assertRaises(ContractValidationError):
                    self.authorization_validator.validate(target)

        target = load_execution_target("tbc_243_lab.json")
        route = target["realm_match"]["expected_routing_records"][0]
        self.assertEqual(route["realm_id"], 1)
        self.assertEqual(route["address"], "127.0.0.1")
        self.assertEqual(route["port"], 8085)
        self.assertEqual(route["client_builds"], ["8606"])

    def test_remote_emulator_can_be_allowlisted_without_loopback(self) -> None:
        target = load_execution_target("tbc_243_lab.json")
        target["authorization_id"] = "execution:remote-emulator:test"
        target["environment_scope"] = "emulator_remote"
        target["realm_match"]["expected_realm_fingerprint"] = (
            "remote-emulator:allowlisted"
        )
        target["realm_match"]["realmlist_directive"] = (
            "set realmlist private.example"
        )
        target["realm_match"]["realmlist_sha256"] = "A" * 64
        target["realm_match"].pop("listener_bindings")
        target["realm_match"].pop("routing_probe")
        target["realm_match"].pop("expected_routing_records")
        target["realm_match"].pop("expected_routing_sha256")
        target["realm_match"]["remote_assurance"] = {
            "state": "configured_endpoint_only",
            "evidence_refs": ["fixture:remote-endpoint-config"],
        }
        target["permitted_modes"] = []
        self.authorization_validator.validate(target)

        missing_assurance = copy.deepcopy(target)
        missing_assurance["realm_match"].pop("remote_assurance")
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(missing_assurance)

        remote_input = copy.deepcopy(target)
        remote_input["permitted_modes"] = ["MOVEMENT_ONLY"]
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(remote_input)

    def test_approved_observe_only_target_has_no_input_mode(self) -> None:
        target = load_execution_target("tbc_243_lab.json")
        target["authorization_id"] = "execution:tbc243-lab:observe-only"
        target["permitted_modes"] = []
        self.authorization_validator.validate(target)
        self.assertEqual(target["permitted_modes"], [])
        self.assertIn(
            "SCREEN_CAPTURE_READ_ONLY",
            target["permitted_capabilities"],
        )
        for input_mode in ("MOVEMENT_ONLY", "COMBAT_ONLY", "FULL_AI"):
            self.assertNotIn(input_mode, target["permitted_modes"])

    def test_fixed_ui_capability_is_independent_of_predator_execution_modes(self) -> None:
        target = load_execution_target("tbc_243_lab.json")
        self.authorization_validator.validate(target)
        self.assertIn("LAB_OPERATOR_FIXED_UI", target["permitted_capabilities"])
        self.assertEqual(target["permitted_modes"], [])

        missing_fixed_ui = copy.deepcopy(target)
        missing_fixed_ui["permitted_capabilities"].remove("LAB_OPERATOR_FIXED_UI")
        self.authorization_validator.validate(missing_fixed_ui)

    def test_approval_session_has_an_absolute_sixty_minute_cap(self) -> None:
        target = load_execution_target("tbc_243_lab.json")
        target["approval"]["max_session_minutes"] = 61
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(target)

    def test_ptr_stays_pending_until_platform_evidence_is_recorded(self) -> None:
        pending = load_execution_target("tbc_classic_ptr_education_pending.json")
        self.authorization_validator.validate(pending)
        self.assertEqual(pending["status"], "pending_evidence")
        self.assertEqual(pending["permitted_modes"], [])
        self.assertEqual(pending["permitted_capabilities"], [])

        approved = copy.deepcopy(pending)
        approved["status"] = "approved_bounded"
        approved["client_match"] = {
            "client_build": "ptr-fixture-build",
            "build_signature": "ptr:fixture",
            "executable_sha256": "a" * 64,
        }
        approved["realm_match"] = {
            "expected_realm_fingerprint": "ptr:fixture",
            "server_kind": "blizzard_ptr",
        }
        approved["actor_binding"] = {
            "schema_version": "1.0",
            "instance_id": "instance:ptr:predator-champion",
            "actor_role": "champion_journey",
            "actor_id": "actor:predator:champion",
            "decision_context": "champion",
            "memory_namespace": "memory:champion:predator-journey",
            "expected_character_name": "Predator",
            "credential_alias": "credential:ptr:predator-champion",
            "binding_assurance": {
                "state": "configured_expected_only",
                "evidence_refs": ["authorization:fixture:actor-expected"],
            },
        }
        approved["permitted_modes"] = ["MOVEMENT_ONLY"]
        approved["permitted_capabilities"] = ["SCREEN_CAPTURE_READ_ONLY"]
        approved["approval"] = {
            "granted_by": "operator",
            "evidence_refs": ["email:redacted:fixture"],
            "recorded_at": "2026-08-22T20:30:00+03:00",
            "max_session_minutes": 30,
        }
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(approved)

        approved["approval"]["granted_by"] = "platform_owner"
        self.authorization_validator.validate(approved)

    def test_public_live_cannot_be_approved(self) -> None:
        target = load_execution_target("tbc_243_lab.json")
        target["environment_scope"] = "public_live"
        target["realm_match"]["server_kind"] = "public_live"
        with self.assertRaises(ContractValidationError):
            self.authorization_validator.validate(target)


if __name__ == "__main__":
    unittest.main()
