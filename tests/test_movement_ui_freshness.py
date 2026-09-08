"""Offline UI regressions. Never construct Tk or invoke a live gateway."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'integrations/windows-input')]
import run_movement_engine_client as ui


class MovementUiFreshnessTests(unittest.TestCase):
    def pose(self, now):
        return ui.LiveMapPose(sequence=int(now * 100), observed_monotonic_s=now,
                              world_x=10.0, world_y=11.0, facing_rad=0.4,
                              facing_source='MINIMAP_VISION_FALLBACK')

    def snapshot(self):
        return ui.MovementLabSnapshot(
            100.0, 'LOST', None, None, controller_state='FOLLOW',
            player_world_x=1.0, player_world_y=2.0,
            corridor_centerline_world=((1.0, 2.0), (3.0, 4.0)),
        )

    def client(self):
        client = object.__new__(ui.MovementEngineClient)
        client.state = 'RUNNING'
        client.process = Mock()
        client.process.poll.return_value = None
        client.movement_state_mtime_ns = 1
        client.raw_movement_snapshot = self.snapshot()
        client.movement_view_started_s = None
        client.last_snapshot = self.snapshot()
        client.last_live_pose = None
        client.cached_local_environment = ({'old': True}, {'old': True})
        client.cached_structure_access = {'old': True}
        client.cached_dynamic_awareness = {'old': True}
        client.cached_target_range_awareness = {'old': True}
        client.cached_dynamic_experience_summary = {'old': True}
        return client

    def refresh(self, client, now, *, pose=True, mtime=1, record=None):
        path = Mock()
        path.stat.return_value = SimpleNamespace(st_mtime_ns=mtime)
        with patch.object(ui, 'MOVEMENT_STATE', path), \
             patch.object(ui.time, 'monotonic', return_value=now), \
             patch.object(ui, '_read_live_map_pose', return_value=self.pose(now) if pose else None), \
             patch.object(ui, '_read_movement_runtime_record', return_value=record) as reader:
            result = client._refresh_runtime_view()
        return result, reader.call_count

    def test_live_pose_does_not_retimestamp_movement_evidence(self):
        merged = ui._snapshot_with_live_pose(self.snapshot(), self.pose(100.25))
        self.assertEqual(merged.observed_monotonic_s, 100.0)
        self.assertEqual(merged.player_world_x, 10.0)

    def test_120_live_updates_cannot_keep_old_follow_or_corridor_alive(self):
        client = self.client()
        for tick in range(1, 121):
            result, reads = self.refresh(client, 100.0 + tick * 0.25)
            self.assertEqual(reads, 0)
        snapshot, local, applicability, structure = result
        self.assertIn('OBSERVE', snapshot.controller_state)
        self.assertEqual(snapshot.corridor_centerline_world, ())
        self.assertEqual(snapshot.player_world_x, 10.0)
        self.assertEqual((local, applicability, structure), (None, None, None))
        self.assertIsNone(client.cached_dynamic_awareness)
        self.assertIsNone(client.cached_target_range_awareness)
        self.assertIsNone(client.cached_dynamic_experience_summary)

    def test_lost_pose_and_expired_movement_show_no_snapshot(self):
        result, _ = self.refresh(self.client(), 102.0, pose=False)
        self.assertIsNone(result[0])

    def test_malformed_replacement_does_not_reuse_last_good_frame(self):
        result, reads = self.refresh(self.client(), 100.2, mtime=2, record=None)
        self.assertEqual(reads, 1)
        self.assertIn('OBSERVE', result[0].controller_state)
        self.assertIsNone(result[1])

    def test_future_epoch_movement_is_rejected(self):
        result, _ = self.refresh(self.client(), 20.0)
        self.assertIn('OBSERVE', result[0].controller_state)

    def test_missing_file_invalidates_cached_geometry(self):
        client = self.client()
        result, reads = self.refresh(client, 100.2, mtime=None)
        self.assertEqual(reads, 1)
        self.assertIn('OBSERVE', result[0].controller_state)
        self.assertIsNone(client.raw_movement_snapshot)

    def test_new_valid_frame_recovers_after_staleness(self):
        client = self.client()
        self.refresh(client, 102.0)
        updated = ui.replace(self.snapshot(), observed_monotonic_s=102.1)
        with patch.object(ui, '_read_snapshot', return_value=updated):
            result, reads = self.refresh(client, 102.2, mtime=2, record={})
        self.assertEqual(reads, 1)
        self.assertEqual(result[0].controller_state, 'FOLLOW')
        self.assertEqual(result[0].observed_monotonic_s, 102.1)

    def test_exited_process_drops_motion_even_before_frame_expires(self):
        client = self.client()
        client.process.poll.return_value = 0
        result, _ = self.refresh(client, 100.2)
        self.assertIn('OBSERVE', result[0].controller_state)
        self.assertIsNone(result[1])

    def test_stopped_ui_never_adopts_previous_run_motion(self):
        client = self.client()
        client.state = 'STOPPED'
        client.process = None
        result, _ = self.refresh(client, 100.2)
        self.assertIn('OBSERVE', result[0].controller_state)

    def test_new_start_rejects_fresh_frame_from_previous_run(self):
        client = self.client()
        client.movement_view_started_s = 100.1
        result, _ = self.refresh(client, 100.2)
        self.assertIn('OBSERVE', result[0].controller_state)

    def test_current_run_retains_geometry_and_source_time(self):
        result, _ = self.refresh(self.client(), 100.2)
        self.assertEqual(result[0].controller_state, 'FOLLOW')
        self.assertEqual(result[0].observed_monotonic_s, 100.0)
        self.assertEqual(len(result[0].corridor_centerline_world), 2)

    def test_controller_text_respects_lifecycle_before_snapshot(self):
        for state, running, expected in (
            ('STOPPED', False, 'oprit'), ('STOPPING', True, 'oprirea'),
            ('PAUSED', True, 'pauză'), ('STARTING', False, 'Pregătesc'),
            ('RUNNING', False, 'oprit'),
        ):
            with self.subTest(state=state):
                text = ui._runtime_controller_text(self.snapshot(), state=state, process_running=running)
                self.assertIn(expected, text)
                self.assertNotIn('Acum: merge', text)

    def test_running_without_fresh_motion_does_not_claim_movement(self):
        for snapshot in (None, ui._snapshot_with_live_pose(None, self.pose(120.0))):
            text = ui._runtime_controller_text(snapshot, state='RUNNING', process_running=True)
            self.assertIn('Aștept', text)
        self.assertEqual(ui._runtime_controller_text(self.snapshot(), state='RUNNING', process_running=True), 'Acum: merge')

    def test_stationary_success_is_explicitly_historical(self):
        record = dict(record_type='stationary_pose_validation', schema_version='1.0',
                      sample_count=21, duration_s=4.0, passed=True, failures=[],
                      expected_location_id='landmark:deathknell-crypt',
                      within_expected_location=True, execution_authority=False)
        text = ui._stationary_pose_text(record)
        self.assertIn('Ultimul test', text)
        self.assertIn('era în criptă', text)
        self.assertNotIn('Este în criptă', text)
        self.assertIn('starea actuală', text)


if __name__ == '__main__':
    unittest.main()
