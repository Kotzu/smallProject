from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations" / "windows-input"))
import worker_roles
import run_movement_engine_client as ui
import run_structure_awareness_service as service
from test_journey_combat_supervisor import _command_args, _load_module


class NavigationWorkerRoleTests(unittest.TestCase):
    def test_legacy_graph_identity_uses_actual_navigation_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / "worker.exe"
            worker.write_bytes(b"legacy")
            self.assertEqual(worker_roles.structure_probe_worker_sha256(worker),
                             hashlib.sha256(b"legacy").hexdigest())

    def test_explicit_producer_is_hashed_independently_from_planner(self):
        with tempfile.TemporaryDirectory() as directory:
            producer = Path(directory) / "producer.exe"
            planner = Path(directory) / "planner.exe"
            producer.write_bytes(b"producer")
            planner.write_bytes(b"planner")
            self.assertEqual(worker_roles.structure_probe_worker_sha256(planner, producer),
                             hashlib.sha256(b"producer").hexdigest())
            producer.write_bytes(b"changed")
            self.assertNotEqual(worker_roles.structure_probe_worker_sha256(planner, producer),
                                hashlib.sha256(b"producer").hexdigest())

    def test_missing_explicit_producer_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            planner = Path(directory) / "planner.exe"
            planner.write_bytes(b"planner")
            with self.assertRaises(FileNotFoundError):
                worker_roles.structure_probe_worker_sha256(planner, planner.with_name("absent"))

    def test_supervisor_preserves_distinct_roles_and_legacy_default(self):
        args = _command_args(Path("fixture"))
        supervisor = _load_module()
        legacy = supervisor._navigation_command(args)
        self.assertNotIn("--structure-probe-worker", legacy)
        args.structure_probe_worker = Path("producer.exe")
        command = supervisor._navigation_command(args)
        self.assertEqual(command[command.index("--worker") + 1], str(args.worker))
        self.assertEqual(command[command.index("--structure-probe-worker") + 1], "producer.exe")

    def test_candidate_is_explicit_hash_pinned_and_reversible(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.exe"
            candidate.write_bytes(b"validated candidate")
            with patch.object(ui, "NAVIGATION_WORKER_OVERRIDE", None), \
                 patch.object(ui, "HORIZONTAL_CLEARANCE_CANDIDATE", candidate), \
                 patch.object(ui, "HORIZONTAL_CLEARANCE_CANDIDATE_SHA256",
                              hashlib.sha256(b"validated candidate").hexdigest()):
                self.assertEqual(ui._navigation_worker(), ui.WORKER)
                ui._configure_horizontal_clearance_candidate(True)
                self.assertEqual(ui._navigation_worker(), candidate.resolve())
                ui._configure_horizontal_clearance_candidate(False)
                self.assertEqual(ui._navigation_worker(), ui.WORKER)
                candidate.write_bytes(b"unvalidated")
                with self.assertRaises(RuntimeError):
                    ui._configure_horizontal_clearance_candidate(True)
                self.assertEqual(ui._navigation_worker(), ui.WORKER)

    def test_missing_candidate_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(ui, "NAVIGATION_WORKER_OVERRIDE", None), \
             patch.object(ui, "HORIZONTAL_CLEARANCE_CANDIDATE", Path(directory) / "absent"):
            with self.assertRaises(FileNotFoundError):
                ui._configure_horizontal_clearance_candidate(True)
            self.assertEqual(ui._navigation_worker(), ui.WORKER)

    def test_service_keeps_graph_producer_and_gate_planner_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            producer = Path(directory) / "producer.exe"
            producer.write_bytes(b"producer")
            planner = Path(directory) / "planner.exe"
            binding = SimpleNamespace(pack=SimpleNamespace(manifest={"pack_id": "pack", "content_sha256": "hash"}))
            awareness = SimpleNamespace(record={"index_id": "index", "structure_count": 0,
                                                 "wmo_count": 0, "doodad_count": 0})
            graph = SimpleNamespace(record={"structure_index_sha256": "index-hash", "graph_id": "graph",
                                            "content_sha256": "graph-hash", "access_openings": []})
            argv = ["--world-pack-profile", "profile", "--world-pack-store", "store",
                    "--world-structure-index", "index", "--structure-access-graph", "graph",
                    "--worker", str(producer), "--navigation-worker", str(planner)]
            with patch.object(service, "load_world_pack_runtime_profile", return_value=binding), \
                 patch.object(service, "load_world_structure_index", return_value=awareness), \
                 patch.object(service, "load_structure_access_graph", return_value=graph) as load_graph, \
                 patch.object(service, "semantic_live_gate_identity",
                              return_value=SimpleNamespace(__dataclass_fields__={})) as identity, \
                 patch.object(service, "_serve"), patch.object(service, "_emit") as emit:
                self.assertEqual(service.main(argv), 0)
                self.assertEqual(load_graph.call_args.kwargs["expected_probe_worker_sha256"],
                                 hashlib.sha256(b"producer").hexdigest())
                self.assertEqual(identity.call_args.kwargs["worker_path"], planner)
                self.assertIs(emit.call_args.args[0]["execution_authority"], False)
                self.assertEqual(emit.call_args.args[0]["event"], "READY")


if __name__ == "__main__":
    unittest.main()
