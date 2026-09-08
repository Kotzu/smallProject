from __future__ import annotations

import json
import unittest
from pathlib import Path

from perfect_assassin.domain.capabilities import CapabilityProfile
from perfect_assassin.domain.records import RawFact
from perfect_assassin.observer.firewall import InformationPolicyError, ProvenanceFirewall


ROOT = Path(__file__).resolve().parents[1]


def load_firewall() -> ProvenanceFirewall:
    profile = json.loads(
        (ROOT / "config" / "capabilities" / "tbc_243_lab.json").read_text(encoding="utf-8")
    )
    return ProvenanceFirewall(CapabilityProfile.from_dict(profile))


class FirewallTests(unittest.TestCase):
    def test_server_ground_truth_is_rejected(self) -> None:
        fact = RawFact(
            raw_key="target_guid",
            value="hidden",
            source="server_ground_truth",
            capability="server_spawn_state",
            confidence=1.0,
            observed_at="2026-08-22T12:00:00Z",
        )
        with self.assertRaisesRegex(InformationPolicyError, "server_ground_truth"):
            load_firewall().authorize(fact)

    def test_unknown_capability_is_denied_by_default(self) -> None:
        fact = RawFact(
            raw_key="target_guid",
            value="hidden",
            source="client_observed",
            capability="not_declared",
            confidence=1.0,
            observed_at="2026-08-22T12:00:00Z",
        )
        with self.assertRaisesRegex(InformationPolicyError, "denied"):
            load_firewall().authorize(fact)

    def test_restricted_capability_requires_evidence(self) -> None:
        without_evidence = RawFact(
            raw_key="target_guid",
            value="visible-inspect",
            source="legitimate_inspect",
            capability="inspect_enemy",
            confidence=0.8,
            observed_at="2026-08-22T12:00:00Z",
        )
        with self.assertRaisesRegex(InformationPolicyError, "restriction_evidence"):
            load_firewall().authorize(without_evidence)

        with_evidence = RawFact(
            raw_key="target_guid",
            value="visible-inspect",
            source="legitimate_inspect",
            capability="inspect_enemy",
            confidence=0.8,
            observed_at="2026-08-22T12:00:00Z",
            restriction_evidence="synthetic range/faction/API gate passed",
        )
        load_firewall().authorize(with_evidence)


if __name__ == "__main__":
    unittest.main()
