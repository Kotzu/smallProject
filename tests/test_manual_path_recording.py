import math
import unittest

from perfect_assassin.movement.manual_path_recording import (
    ManualPathDiscontinuityError,
    ManualPathRecorder,
    ManualPathRecording,
)


class ManualPathRecorderTests(unittest.TestCase):
    def test_filters_pose_jitter_and_records_forward_segment_facing(self) -> None:
        recorder = ManualPathRecorder("manual:test", "Main road", minimum_spacing_world=0.75)
        self.assertTrue(recorder.observe(
            x=10.0, y=20.0, observed_monotonic_s=1.0,
            observed_facing_rad=1.25,
        ))
        self.assertFalse(recorder.observe(x=10.2, y=20.1, observed_monotonic_s=1.1))
        self.assertTrue(recorder.observe(x=11.0, y=21.0, observed_monotonic_s=1.2))
        self.assertEqual(len(recorder.vertices), 2)
        self.assertAlmostEqual(recorder.vertices[0].facing_rad, math.pi / 4)
        self.assertAlmostEqual(recorder.vertices[1].facing_rad, math.pi / 4)
        self.assertAlmostEqual(recorder.vertices[0].observed_facing_rad, 1.25)

    def test_turn_updates_outgoing_tangent_without_rewriting_previous_segment(self) -> None:
        recorder = ManualPathRecorder("manual:test", "Turn")
        recorder.observe(x=0.0, y=0.0, observed_monotonic_s=1.0)
        recorder.observe(x=1.0, y=0.0, observed_monotonic_s=1.1)
        recorder.observe(x=1.0, y=1.0, observed_monotonic_s=1.2)
        self.assertAlmostEqual(recorder.vertices[0].facing_rad, 0.0)
        self.assertAlmostEqual(recorder.vertices[1].facing_rad, math.pi / 2)
        self.assertAlmostEqual(recorder.vertices[2].facing_rad, math.pi / 2)

    def test_refuses_to_connect_teleport_or_stale_observation_gap(self) -> None:
        recorder = ManualPathRecorder("manual:test", "Continuous")
        recorder.observe(x=0.0, y=0.0, observed_monotonic_s=1.0)
        with self.assertRaises(ManualPathDiscontinuityError):
            recorder.observe(x=20.0, y=0.0, observed_monotonic_s=1.1)

        recorder = ManualPathRecorder("manual:test-2", "Continuous")
        recorder.observe(x=0.0, y=0.0, observed_monotonic_s=1.0)
        with self.assertRaises(ManualPathDiscontinuityError):
            recorder.observe(x=1.0, y=0.0, observed_monotonic_s=3.1)

    def test_complete_record_round_trips_and_converts_to_non_authoritative_vertices(self) -> None:
        recorder = ManualPathRecorder("manual:test", "Lesson")
        recorder.observe(x=1843.5, y=1589.9, observed_monotonic_s=1.0)
        recorder.observe(x=1844.5, y=1589.9, observed_monotonic_s=1.1)
        record = recorder.finish()
        restored = ManualPathRecording.from_record(record.to_record())
        self.assertEqual(restored, record)
        self.assertFalse(restored.execution_authority)
        self.assertEqual(restored.status, "COMPLETE")
        self.assertEqual(len(restored.as_map_knowledge_vertices()), 2)

    def test_import_marker_is_explicit_and_idempotence_can_be_persisted(self) -> None:
        recorder = ManualPathRecorder("manual:test", "Lesson")
        recorder.observe(x=0.0, y=0.0, observed_monotonic_s=1.0)
        recorder.observe(x=1.0, y=0.0, observed_monotonic_s=1.1)
        imported = recorder.finish().mark_imported("feature-004")
        restored = ManualPathRecording.from_record(imported.to_record())
        self.assertEqual(restored.status, "IMPORTED")
        self.assertEqual(restored.imported_feature_id, "feature-004")

    def test_interrupted_recording_preserves_partial_evidence_explicitly(self) -> None:
        recorder = ManualPathRecorder("manual:test", "Interrupted lesson")
        recorder.observe(x=0.0, y=0.0, observed_monotonic_s=1.0)
        recorder.observe(x=1.0, y=0.0, observed_monotonic_s=1.1)

        result = recorder.finish(interrupted=True)

        self.assertEqual(result.status, "INTERRUPTED")
        self.assertEqual(len(result.vertices), 2)
        self.assertEqual(ManualPathRecording.from_record(result.to_record()), result)


if __name__ == "__main__":
    unittest.main()
