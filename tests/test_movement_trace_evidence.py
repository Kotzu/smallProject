"""Offline provenance checks, including the real runner's three decision sites."""
import ast
from dataclasses import replace
import json
from math import tau
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness, LocalWallSegment, NavPoint, RadialClearanceProbe,
)
from perfect_assassin.movement.live_trace_quality import evaluate_live_steering_trace
from perfect_assassin.movement.predictive_steering import SteeringState
from perfect_assassin.movement.trace_evidence import (
    decision_observation_record, local_boundary_trace_record,
)

ROOT = Path(__file__).resolve().parents[1]


class MovementTraceEvidenceTests(unittest.TestCase):
    def sample(self):
        return decision_observation_record(SteeringState(10, 20, 0.5, 7, 0.2),
                                           observed_monotonic_s=100, heading_source='VISIBLE')

    def awareness(self):
        return LocalStaticAwareness(
            physical_surfaces=frozenset({'wmo'}), probe_radius_yards=6,
            overhead_clear=False,
            radial_probes=tuple(RadialClearanceProbe(i*tau/8, 0.5+i/2, False) for i in range(8)),
            wall_segments=(LocalWallSegment(NavPoint(10, 21, 30), NavPoint(15, 21, 31), 1),),
            wall_segments_truncated=True,
        )

    def test_before_and_after_pose_are_not_relabelled_as_the_same_observation(self):
        decision = self.sample()
        frame = {'observed_monotonic_s':100.1, 'world_x':10.7, 'world_y':20.1,
                 'cross_track_error_world':1.0, 'decision_observation':decision}
        self.assertEqual(frame['decision_observation']['observed_monotonic_s'], 100)
        self.assertEqual(frame['decision_observation']['world_x'], 10)
        self.assertNotEqual(decision['world_x'], frame['world_x'])
        self.assertFalse(decision['execution_authority'])

    def test_new_capture_cannot_mutate_retained_input_sample(self):
        old = self.sample()
        new = decision_observation_record(SteeringState(30, 40, 1.5, 7),
                                          observed_monotonic_s=101, heading_source='FUSED')
        new['world_x'] = 99
        self.assertEqual(old['world_x'], 10)
        self.assertEqual(old['heading_rad'], 0.5)

    def test_unknown_heading_is_preserved_without_inventing_z(self):
        record = decision_observation_record(SteeringState(1, 2, None, 0),
                                             observed_monotonic_s=5, heading_source='UNAVAILABLE')
        self.assertIsNone(record['heading_rad'])
        self.assertNotIn('world_z', record)
        self.assertNotIn('projected_z_world', record)

    def test_live_geometry_retains_its_own_time_and_truncation(self):
        record = local_boundary_trace_record(self.awareness(), observed_monotonic_s=99.8)
        self.assertEqual(record['observed_monotonic_s'], 99.8)
        self.assertTrue(record['wall_segments_truncated'])
        self.assertEqual(record['wall_segments'][0]['left'], [10, 21, 30])
        self.assertFalse(record['physical_contact_proven'])
        self.assertFalse(record['execution_authority'])
        self.assertEqual(record['radial_probes'][0]['clearance_yards'], 0.5)
        json.dumps(record, allow_nan=False)

    def test_geometry_copy_does_not_mutate_immutable_awareness(self):
        awareness = self.awareness()
        record = local_boundary_trace_record(awareness, observed_monotonic_s=10)
        record['wall_segments'][0]['left'][0] = -999
        self.assertEqual(awareness.wall_segments[0].left.x, 10)

    def test_missing_boundaries_do_not_become_collision_certificate(self):
        record = local_boundary_trace_record(replace(self.awareness(), wall_segments=()),
                                             observed_monotonic_s=10)
        self.assertEqual(record['wall_segments'], [])
        self.assertFalse(record['physical_contact_proven'])
        self.assertTrue(record['wall_segments_truncated'])

    def test_maximum_existing_geometry_bound_remains_small(self):
        awareness = self.awareness()
        record = local_boundary_trace_record(
            replace(awareness, wall_segments=awareness.wall_segments*128),
            observed_monotonic_s=10)
        self.assertEqual(len(record['wall_segments']), 128)
        self.assertLess(len(json.dumps(record)), 25000)
        with self.assertRaises(ValueError):
            replace(awareness, wall_segments=awareness.wall_segments*129)

    def test_every_real_decision_branch_captures_its_exact_state_before_deciding(self):
        tree = ast.parse((ROOT/'integrations/windows-input/run_navmesh_roaming.py').read_text(encoding='utf-8'))
        sites = 0
        for parent in ast.walk(tree):
            for _, statements in ast.iter_fields(parent):
                if not isinstance(statements, list):
                    continue
                for i, node in enumerate(statements):
                    if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                        continue
                    if ast.unparse(node.value.func) != 'engine.decide':
                        continue
                    sites += 1
                    self.assertGreaterEqual(i, 2)
                    self.assertEqual(ast.unparse(node.value.args[0]), 'decision_state')
                    block = ast.Module(body=statements[i-2:i+1], type_ignores=[])
                    engine = SimpleNamespace(decide=Mock(return_value='intent'))
                    namespace = dict(world_x=1643, world_y=1674, heading=2.5, speed=7,
                                     no_progress_s=0.25, last_observed_s=123.4,
                                     heading_source='VISIBLE', steering_corridor=object(), engine=engine,
                                     SteeringState=SteeringState,
                                     decision_observation_record=decision_observation_record)
                    exec(compile(block, '<actual runner decision branch>', 'exec'), namespace)
                    passed_state = engine.decide.call_args.args[0]
                    saved = namespace['decision_observation']
                    self.assertEqual(saved['world_x'], passed_state.x)
                    self.assertEqual(saved['heading_rad'], passed_state.heading_rad)
                    self.assertEqual(saved['no_progress_s'], passed_state.no_progress_s)
                    self.assertEqual(saved['observed_monotonic_s'], 123.4)
        self.assertEqual(sites, 3)  # normal, progress retry, and stale-pose refresh

    def test_evidence_is_additive_and_does_not_change_existing_quality_gate(self):
        result = {'status':'ARRIVED', 'actions':[
            {'kind':'CONTINUOUS_FRAME', 'observed_monotonic_s':100+i/10,
             'controller_state':'FOLLOW', 'requested_mouse_delta_x':0}
            for i in range(60)]}
        original = evaluate_live_steering_trace(result)
        for frame in result['actions']:
            frame['decision_observation'] = self.sample()
            frame['position_phase'] = 'post_command_observation'
        self.assertEqual(evaluate_live_steering_trace(result), original)
        self.assertTrue(original.passed)


if __name__ == '__main__':
    unittest.main()
