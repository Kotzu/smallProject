import unittest

from perfect_assassin.movement.operator_map_knowledge import (
    MapKnowledgeVertex, OperatorMapKnowledge,
)


class OperatorMapKnowledgeTests(unittest.TestCase):
    def test_round_trip_preserves_roaming_obstacle_and_interior_semantics(self) -> None:
        knowledge = OperatorMapKnowledge("Azeroth")
        polygon = (
            MapKnowledgeVertex(1, 1), MapKnowledgeVertex(5, 1),
            MapKnowledgeVertex(5, 5),
        )
        knowledge = knowledge.add_feature(kind="roaming_zone", name="PvP roam", vertices=polygon)
        knowledge = knowledge.add_feature(kind="obstacle", name="Wall", vertices=polygon)
        knowledge = knowledge.add_feature(
            kind="interior_route", name="Crypt stairs",
            vertices=(MapKnowledgeVertex(2, 2), MapKnowledgeVertex(3, 4)),
        )
        restored = OperatorMapKnowledge.from_record(knowledge.to_record())
        self.assertEqual(restored, knowledge)
        self.assertEqual(
            [feature.planner_effect for feature in restored.features],
            [
                "preferred_search_region",
                "candidate_blocked_region_requires_runtime_confirmation",
                "preferred_indoor_corridor",
            ],
        )
        self.assertFalse(restored.execution_authority)

    def test_manual_demonstration_can_retain_observed_facing(self) -> None:
        knowledge = OperatorMapKnowledge("Azeroth").add_feature(
            kind="manual_demonstration", name="Manual road lesson",
            vertices=(
                MapKnowledgeVertex(1, 2, 0.25),
                MapKnowledgeVertex(2, 3, 0.5),
            ),
        )
        restored = OperatorMapKnowledge.from_record(knowledge.to_record())
        self.assertEqual(restored.features[0].vertices[1].facing_rad, 0.5)
        self.assertEqual(restored.features[0].planner_effect, "movement_demonstration_prior")

    def test_polygon_requires_three_vertices_and_never_grants_authority(self) -> None:
        with self.assertRaises(ValueError):
            OperatorMapKnowledge("Azeroth").add_feature(
                kind="obstacle", name="Too short",
                vertices=(MapKnowledgeVertex(1, 1), MapKnowledgeVertex(2, 2)),
            )
        with self.assertRaises(ValueError):
            OperatorMapKnowledge("Azeroth", execution_authority=True)


if __name__ == "__main__":
    unittest.main()
