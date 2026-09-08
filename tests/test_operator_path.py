import unittest

from perfect_assassin.movement.operator_path import OperatorAuthoredPath


class OperatorAuthoredPathTests(unittest.TestCase):
    def test_add_undo_and_round_trip_preserve_order_and_provenance(self) -> None:
        path = OperatorAuthoredPath("draft", "Crypt exit", "Azeroth")
        path = path.add(x=1.25, y=2.5, z=3.75).add(x=4.0, y=5.0, label="Stairs")

        restored = OperatorAuthoredPath.from_record(path.to_record())

        self.assertEqual(restored, path)
        self.assertEqual([point.order for point in restored.waypoints], [1, 2])
        self.assertEqual(restored.waypoints[0].provenance, "operator_authored_external_tool")
        self.assertFalse(restored.execution_authority)
        self.assertEqual(len(restored.undo().waypoints), 1)

    def test_rejects_execution_authority(self) -> None:
        with self.assertRaises(ValueError):
            OperatorAuthoredPath("draft", "Unsafe", "Azeroth", execution_authority=True)

    def test_rejects_non_finite_waypoint(self) -> None:
        with self.assertRaises(ValueError):
            OperatorAuthoredPath("draft", "Invalid", "Azeroth").add(x=float("nan"), y=2.0)

    def test_resume_rejoins_at_nearest_waypoint_and_preserves_order(self) -> None:
        path = OperatorAuthoredPath("patrol", "Deathknell to Brill", "Azeroth")
        path = path.add(x=0.0, y=0.0).add(x=10.0, y=0.0).add(x=20.0, y=0.0)

        self.assertEqual(path.resume_index_nearest_to(x=7.0, y=4.0), 1)
        self.assertEqual(
            tuple(point.order for point in path.resume_waypoints_nearest_to(x=7.0, y=4.0)),
            (2, 3),
        )

    def test_resume_advances_from_waypoint_under_actor_but_keeps_final(self) -> None:
        path = OperatorAuthoredPath("patrol", "Patrol", "Azeroth")
        path = path.add(x=0.0, y=0.0).add(x=10.0, y=0.0)

        self.assertEqual(path.resume_index_nearest_to(x=0.5, y=0.0), 1)
        self.assertEqual(path.resume_index_nearest_to(x=10.0, y=0.0), 1)

    def test_resume_rejects_empty_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "resume"):
            OperatorAuthoredPath("empty", "Empty", "Azeroth").resume_index_nearest_to(
                x=0.0, y=0.0,
            )


if __name__ == "__main__":
    unittest.main()
