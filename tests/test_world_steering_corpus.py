from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import (
    NavCorridor,
    NavPoint,
    NavPortal,
)
from perfect_assassin.movement.world_steering_corpus import (
    ADT_SIZE_WORLD,
    WorldSteeringCourseRequest,
    build_world_steering_course_requests,
    build_world_steering_scenario,
    classify_world_corridor_risk,
    simulation_runs_for_risk,
    tile_world_bounds,
)

ROOT = Path(__file__).resolve().parents[1]
_RUNNER_SPEC = importlib.util.spec_from_file_location(
    "pa_test_world_steering_corpus_runner",
    ROOT / "scripts" / "run_world_steering_corpus.py",
)
if _RUNNER_SPEC is None or _RUNNER_SPEC.loader is None:
    raise RuntimeError("cannot load world steering corpus runner")
world_corpus_runner = importlib.util.module_from_spec(_RUNNER_SPEC)
sys.modules[_RUNNER_SPEC.name] = world_corpus_runner
_RUNNER_SPEC.loader.exec_module(world_corpus_runner)


class WorldSteeringCorpusTests(unittest.TestCase):
    def test_runner_rejects_timeout_outside_native_query_bound(self) -> None:
        original_argv = sys.argv
        try:
            sys.argv = [
                "run_world_steering_corpus.py",
                "--world-pack-profile", "profile.json",
                "--world-pack-store", "packs",
                "--map-name", "Azeroth",
                "--output", "report.json",
                "--query-timeout-seconds", "15",
            ]
            with self.assertRaises(SystemExit) as raised:
                world_corpus_runner._arguments()
            self.assertEqual(raised.exception.code, 2)
        finally:
            sys.argv = original_argv

    def test_every_catalog_tile_receives_the_same_data_derived_patterns(self) -> None:
        world_map = SimpleNamespace(
            map_id=530,
            internal_name="Expansion01",
            tiles=(
                SimpleNamespace(grid_x=31, grid_y=31),
                SimpleNamespace(grid_x=30, grid_y=29),
            ),
        )

        requests = build_world_steering_course_requests(
            world_map, courses_per_tile=4,
        )

        self.assertEqual(len(requests), 8)
        self.assertEqual({item.map_name for item in requests}, {"Expansion01"})
        self.assertEqual(
            {item.request_id.rsplit(":", 1)[1] for item in requests},
            {"p0", "p1", "p2", "p3"},
        )
        for request in requests:
            x_low, x_high, y_low, y_high = tile_world_bounds(
                request.grid_x, request.grid_y,
            )
            self.assertLess(x_low, request.start.x)
            self.assertLess(request.start.x, x_high)
            self.assertLess(y_low, request.start.y)
            self.assertLess(request.start.y, y_high)
            self.assertGreater(
                request.start.distance_2d(request.stop),
                0.139 * ADT_SIZE_WORLD,
            )

    def test_request_generator_is_generic_and_deterministic(self) -> None:
        world_map = SimpleNamespace(
            map_id=1,
            internal_name="Kalimdor",
            tiles=(
                SimpleNamespace(grid_x=40, grid_y=20),
                SimpleNamespace(grid_x=10, grid_y=50),
            ),
        )

        first = build_world_steering_course_requests(world_map, courses_per_tile=2)
        second = build_world_steering_course_requests(world_map, courses_per_tile=2)

        self.assertEqual(first, second)
        self.assertEqual(first[0].grid_x, 10)
        self.assertEqual(first[0].grid_y, 50)
        rendered = repr(first).lower()
        self.assertNotIn("deathknell", rendered)
        self.assertNotIn("brill", rendered)
        self.assertNotIn("shadowfang", rendered)

    def test_duplicate_or_invalid_tiles_fail_closed(self) -> None:
        duplicate = SimpleNamespace(
            map_id=0,
            internal_name="Azeroth",
            tiles=(
                SimpleNamespace(grid_x=31, grid_y=31),
                SimpleNamespace(grid_x=31, grid_y=31),
            ),
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_world_steering_course_requests(duplicate)
        with self.assertRaisesRegex(ValueError, "outside"):
            tile_world_bounds(64, 31)

    def test_fifty_candidates_cover_a_tile_lattice_in_two_directions(self) -> None:
        world_map = SimpleNamespace(
            map_id=0,
            internal_name="Azeroth",
            tiles=(SimpleNamespace(grid_x=31, grid_y=31),),
        )

        requests = build_world_steering_course_requests(
            world_map, courses_per_tile=50,
        )

        self.assertEqual(len(requests), 50)
        self.assertEqual(len({item.request_id for item in requests}), 50)
        self.assertTrue(any(item.start.x == item.stop.x for item in requests))
        self.assertTrue(any(item.start.y == item.stop.y for item in requests))

    def test_sharp_actor_scale_portal_escalates_to_ten_thousand(self) -> None:
        points = (
            NavPoint(0.0, 0.0, 0.0),
            NavPoint(15.0, 0.0, 0.0),
            NavPoint(4.0, -10.0, 0.0),
        )
        corridor = NavCorridor(
            "Azeroth", 31, 31, points[0], points[-1], points,
            portals=(
                NavPortal(
                    0, 1,
                    NavPoint(15.0, -1.0, 0.0),
                    NavPoint(15.0, 1.0, 0.0),
                    2.0,
                ),
            ),
        )

        risk = classify_world_corridor_risk(corridor)

        self.assertEqual(risk.tier, "EXTREME")
        self.assertIn("HAIRPIN_TURN", risk.reasons)
        self.assertIn("ACTOR_SCALE_PORTAL", risk.reasons)
        self.assertEqual(simulation_runs_for_risk(risk), 10_000)

    def test_open_straight_corridor_stays_at_one_hundred(self) -> None:
        points = (NavPoint(0.0, 0.0, 0.0), NavPoint(80.0, 0.0, 0.0))
        corridor = NavCorridor(
            "Kalimdor", 31, 31, points[0], points[-1], points,
        )
        world_map = SimpleNamespace(
            map_id=1,
            internal_name="Kalimdor",
            tiles=(SimpleNamespace(grid_x=31, grid_y=31),),
        )
        request = build_world_steering_course_requests(world_map)[0]

        risk = classify_world_corridor_risk(corridor)
        scenario = build_world_steering_scenario(request, corridor, runs=100)

        self.assertEqual(risk.tier, "BASE")
        self.assertEqual(simulation_runs_for_risk(risk), 100)
        self.assertEqual(scenario.runs, 100)
        self.assertEqual(scenario.maximum_allowed_cross_track_world, 2.5)

    def test_tile_checkpoint_is_schema_valid_and_resumable(self) -> None:
        arguments = SimpleNamespace(
            controller_id="geometric_predictive_v1",
            mppi_batch_size=256,
            mppi_time_steps=56,
            mppi_replan_interval_ticks=4,
            candidate_patterns_per_tile=50,
            corridors_per_tile=1,
            base_runs=100,
            risk_runs=1_000,
            extreme_runs=10_000,
        )
        policy = world_corpus_runner._policy_record(arguments, tile_limit=None)
        world_pack = {
            "profile_id": "fixture-profile",
            "pack_id": "fixture-pack",
            "content_sha256": "a" * 64,
            "catalog_id": "fixture-catalog",
            "client_version": "2.4.3",
            "client_build": "8606",
            "map_id": 0,
            "map_name": "Azeroth",
        }
        request = WorldSteeringCourseRequest(
            request_id="Azeroth:31_31:p0",
            map_id=0,
            map_name="Azeroth",
            grid_x=31,
            grid_y=31,
            start=NavPoint(0.0, 0.0, 0.0),
            stop=NavPoint(20.0, 0.0, 0.0),
        )
        report = world_corpus_runner._tile_report(
            world_pack=world_pack,
            policy=policy,
            catalog_tile_count=687,
            grid_x=31,
            grid_y=31,
            query_results=(world_corpus_runner._QueryResult(
                request, None, "ENDPOINT_UNAVAILABLE", "fixture gap",
            ),),
            simulation_results=(),
        )
        validator = ContractValidator(
            ROOT / "contracts" / "world-steering-corpus-report.schema.json",
        )
        validator.validate(report)
        with TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "checkpoint.json"
            world_corpus_runner._atomic_write_json(path, report)
            loaded = world_corpus_runner._load_checkpoint(
                path,
                validator=validator,
                world_pack=world_pack,
                policy=policy,
                grid_x=31,
                grid_y=31,
            )
            self.assertEqual(loaded, report)
            stale_policy = {**policy, "base_runs": 200}
            self.assertIsNone(world_corpus_runner._load_checkpoint(
                path,
                validator=validator,
                world_pack=world_pack,
                policy=stale_policy,
                grid_x=31,
                grid_y=31,
            ))
            legacy_report = json.loads(json.dumps(report))
            del legacy_report["policy"]["course_generator"]
            world_corpus_runner._atomic_write_json(path, legacy_report)
            self.assertIsNone(world_corpus_runner._load_checkpoint(
                path,
                validator=validator,
                world_pack=world_pack,
                policy=policy,
                grid_x=31,
                grid_y=31,
            ))

    def test_checkpoint_path_cannot_escape_its_root(self) -> None:
        with (
            TemporaryDirectory() as raw_directory,
            self.assertRaisesRegex(ValueError, "unsafe"),
        ):
            world_corpus_runner._tile_checkpoint_path(
                Path(raw_directory),
                map_name="../Azeroth",
                grid_x=31,
                grid_y=31,
            )

    def test_mppi_policy_is_explicit_and_schema_bound(self) -> None:
        arguments = SimpleNamespace(
            controller_id="pa_mppi_v1",
            mppi_batch_size=512,
            mppi_time_steps=56,
            mppi_replan_interval_ticks=4,
            candidate_patterns_per_tile=50,
            corridors_per_tile=1,
            base_runs=100,
            risk_runs=1_000,
            extreme_runs=10_000,
        )

        policy = world_corpus_runner._policy_record(arguments, tile_limit=None)

        self.assertEqual(policy["controller_id"], "pa_mppi_v1")
        configuration = policy["controller_configuration"]
        self.assertEqual(
            configuration["configuration_id"],
            "pa-mppi-v1-default-critics",
        )
        self.assertRegex(
            configuration.pop("implementation_sha256"),
            r"^[0-9a-f]{64}$",
        )
        self.assertEqual(configuration, {
            "configuration_id": "pa-mppi-v1-default-critics",
            "batch_size": 512,
            "time_steps": 56,
            "replan_interval_ticks": 4,
        })


if __name__ == "__main__":
    unittest.main()
