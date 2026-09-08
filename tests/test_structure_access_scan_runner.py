from __future__ import annotations

import importlib.util
from concurrent.futures import Future
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from perfect_assassin.movement.client_navmesh import NavPoint


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_structure_access_scan.py"


def _load_runner():
    specification = importlib.util.spec_from_file_location(
        "run_structure_access_scan_test_module", SCRIPT,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("structure scan runner cannot be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


runner = _load_runner()


class FakeNavigator:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = []

    def find_corridor(self, **values):
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        return self.result


class FakePersistentPool:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = []

    def sample(self, requested: NavPoint):
        self.calls.append(requested)
        if self.error is not None:
            raise self.error
        return self.result


class ImmediateExecutor:
    def __init__(self) -> None:
        self.submit_count = 0

    def submit(self, function, item):
        self.submit_count += 1
        future = Future()
        future.set_result(function(item))
        return future


class StructureAccessScanRunnerTests(unittest.TestCase):
    def test_resume_reuses_the_precompiled_awareness_validator(self) -> None:
        class RecordingValidator:
            def __init__(self) -> None:
                self.records = []

            def validate(self, record) -> None:
                self.records.append(record)

        record = {
            "task_id": "task:portable",
            "seed_id": "seed:" + "1" * 24,
            "expected_structure_id": "77:wmo:5",
            "requested_position": [1.0, 2.0, 3.0],
            "awareness_artifact": "seed-portable.awareness.json",
            "awareness_sha256": "a" * 64,
        }
        task = {
            "task_id": record["task_id"],
            "structure_id": record["expected_structure_id"],
        }
        seed = {
            "seed_id": record["seed_id"],
            "position": record["requested_position"],
        }
        validator = RecordingValidator()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fragment = root / "seed-portable.observation.json"
            fragment.write_text("{}", encoding="utf-8")
            awareness = {"record_type": "portable_fixture"}
            (root / record["awareness_artifact"]).write_text(
                json.dumps(awareness), encoding="utf-8",
            )
            with (
                mock.patch.object(
                    runner, "load_scan_observation", return_value=record,
                ),
                mock.patch.object(runner, "file_sha256", return_value="a" * 64),
                mock.patch.object(
                    runner,
                    "ContractValidator",
                    side_effect=AssertionError("validator must already exist"),
                ),
            ):
                loaded = runner._verify_existing(
                    fragment,
                    plan={},
                    task=task,
                    seed=seed,
                    local_validator=validator,
                    fragment_validator=validator,
                )

        self.assertIs(loaded, record)
        self.assertEqual(validator.records, [awareness])

    def test_persistent_awareness_avoids_one_process_per_successful_seed(self) -> None:
        requested = NavPoint(10.0, 20.0, 30.0)
        resolved = NavPoint(10.5, 20.5, 31.0)
        awareness = object()
        pool = FakePersistentPool(result=(resolved, awareness))
        navigator = FakeNavigator(error=AssertionError("one-shot must not run"))

        result = runner._query_static_awareness(
            navigator,
            persistent_pool=pool,
            map_name="SyntheticWorld",
            requested=requested,
        )

        self.assertEqual(result, (resolved, awareness, None, "PERSISTENT_AWARENESS"))
        self.assertEqual(pool.calls, [requested])
        self.assertEqual(navigator.calls, [])

    def test_persistent_failure_uses_one_shot_for_exact_classification(self) -> None:
        requested = NavPoint(10.0, 20.0, 30.0)
        awareness = object()
        corridor = type("Corridor", (), {
            "start": NavPoint(10.5, 20.5, 31.0),
            "start_awareness": awareness,
        })()
        pool = FakePersistentPool(error=RuntimeError("opaque persistent error"))
        navigator = FakeNavigator(result=corridor)

        resolved, actual, error, source = runner._query_static_awareness(
            navigator,
            persistent_pool=pool,
            map_name="SyntheticWorld",
            requested=requested,
        )

        self.assertEqual(resolved, corridor.start)
        self.assertIs(actual, awareness)
        self.assertIsNone(error)
        self.assertEqual(source, "ONE_SHOT_CLASSIFICATION_FALLBACK")
        self.assertEqual(len(navigator.calls), 1)

    def test_large_scan_keeps_only_a_bounded_future_window(self) -> None:
        executor = ImmediateExecutor()
        completed = runner._bounded_parallel_results(
            executor,
            tuple(range(20)),
            lambda item: item * 2,
            maximum_in_flight=3,
        )

        first = next(completed)
        self.assertEqual(executor.submit_count, 3)
        results = [first, *completed]

        self.assertEqual(executor.submit_count, 20)
        self.assertEqual(
            sorted(results),
            [(item, item * 2) for item in range(20)],
        )

    def test_global_probe_budget_is_supported_without_unbounded_futures(self) -> None:
        self.assertGreaterEqual(runner.MAX_PROBES_PER_RUN, 65_536)

    def test_query_adapter_preserves_exact_seed_and_returns_result(self) -> None:
        expected = object()
        navigator = FakeNavigator(result=expected)
        requested = NavPoint(10.0, 20.0, 30.0)

        corridor, error = runner._query_corridor(
            navigator, map_name="Azeroth", requested=requested,
        )

        self.assertIs(corridor, expected)
        self.assertIsNone(error)
        self.assertEqual(navigator.calls, [{
            "map_name": "Azeroth",
            "start": requested,
            "stop_x": 11.0,
            "stop_y": 20.0,
        }])

    def test_query_adapter_contains_one_worker_failure(self) -> None:
        navigator = FakeNavigator(error=RuntimeError("fixture failure"))

        corridor, error = runner._query_corridor(
            navigator,
            map_name="Azeroth",
            requested=NavPoint(10.0, 20.0, 30.0),
        )

        self.assertIsNone(corridor)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "fixture failure")

    def test_parallelism_is_bounded_to_four_workers(self) -> None:
        required = [
            "--profile", "profile.json",
            "--store-root", "packs",
            "--index", "index.json",
            "--plan", "plan.json",
            "--worker", "worker.exe",
            "--output-dir", "fragments",
            "--jobs", "5",
        ]
        with self.assertRaises(SystemExit) as raised:
            runner.run(required)
        self.assertEqual(raised.exception.code, 2)

    def test_incomplete_worker_semantics_are_not_reported_as_runtime_errors(self) -> None:
        self.assertEqual(
            runner._failure_status(
                RuntimeError("start awareness physical surfaces are empty")
            ),
            "REJECTED_INCOMPLETE_STATIC_AWARENESS",
        )
        self.assertEqual(
            runner._failure_status(
                RuntimeError("local surface transition semantics are invalid")
            ),
            "REJECTED_INCOMPLETE_STATIC_AWARENESS",
        )
        self.assertEqual(
            runner._failure_status(RuntimeError("unexpected worker failure")),
            "PROBE_ERROR",
        )

    def test_unknown_height_is_a_no_nav_seed_not_a_runtime_failure(self) -> None:
        self.assertEqual(
            runner._failure_status(
                RuntimeError("find_heights failed with result 84")
            ),
            "REJECTED_NO_NAV_POLYGON",
        )

    def test_unattended_scan_can_fail_closed_on_a_probe_error(self) -> None:
        self.assertEqual(
            runner._scan_exit_code(
                probe_error_count=1, fail_on_probe_error=True,
            ),
            2,
        )
        self.assertEqual(
            runner._scan_exit_code(
                probe_error_count=1, fail_on_probe_error=False,
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
