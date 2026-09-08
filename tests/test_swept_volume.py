import math
import unittest

from perfect_assassin.movement.swept_volume import swept_capsule_surface_distance as sweep


def wall(x):
    return [(x,-10,-10),(x,10,-10),(x,0,10)]


def horizontal(z):
    return [(-10,-10,z),(10,-10,z),(0,10,z)]


class SweptVolumeTests(unittest.TestCase):
    def evaluate(self, triangles, start=(0,0,0), stop=(0,0,0), radius=.4, height=2):
        return sweep(start,stop,radius_yards=radius,height_yards=height,triangles=triangles)

    def test_stationary_wall_clearance_is_from_body_not_center(self):
        self.assertAlmostEqual(self.evaluate([wall(1)]).minimum_separation_yards,.6)

    def test_thin_obstacle_between_clear_endpoints_is_detected(self):
        triangle=[(0,.17,1),(0,.19,1),(0,.18,1.02)]
        self.assertGreater(self.evaluate([triangle],(-2,0,0),(-2,0,0)).minimum_separation_yards,0)
        self.assertGreater(self.evaluate([triangle],(2,0,0),(2,0,0)).minimum_separation_yards,0)
        self.assertLess(self.evaluate([triangle],(-2,0,0),(2,0,0)).minimum_separation_yards,0)

    def test_mid_sweep_face_interior_not_just_edges_is_detected(self):
        self.assertAlmostEqual(self.evaluate([wall(0)],(-2,0,0),(2,0,0)).minimum_separation_yards,-.4)

    def test_ceiling_uses_full_body_height(self):
        self.assertAlmostEqual(self.evaluate([horizontal(2.1)]).minimum_separation_yards,.1)

    def test_floor_contact_is_not_silently_filtered(self):
        self.assertAlmostEqual(self.evaluate([horizontal(0)]).minimum_separation_yards,0)

    def test_narrow_gap_overlaps_body(self):
        self.assertAlmostEqual(self.evaluate([wall(-.3),wall(.3)]).minimum_separation_yards,-.1)

    def test_rising_sweep_catches_intermediate_floor(self):
        self.assertLess(self.evaluate([horizontal(3)],stop=(2,0,4)).minimum_separation_yards,0)

    def test_upper_floor_does_not_become_lower_wall(self):
        self.assertAlmostEqual(self.evaluate([horizontal(5)]).minimum_separation_yards,3)

    def test_sphere_and_point_triangle_degeneracies(self):
        self.assertAlmostEqual(self.evaluate([[(1,0,.4)]*3],height=.8).minimum_separation_yards,.6)

    def test_coplanar_sweep_intersection(self):
        triangle=[(0,0,.6),(1,0,.6),(.5,0,1.4)]
        self.assertAlmostEqual(self.evaluate([triangle],(-1,0,0),(2,0,0)).minimum_separation_yards,-.4)

    def test_translation_and_triangle_winding_do_not_change_result(self):
        offset=(1700,1650,120)
        triangle=[tuple(v+d for v,d in zip(p,offset)) for p in wall(1)]
        result=self.evaluate([triangle[::-1]],offset,offset)
        self.assertAlmostEqual(result.minimum_separation_yards,.6)
        self.assertFalse(result.execution_authority)

    def test_empty_mesh_is_unknown_not_clear(self):
        result=self.evaluate([])
        self.assertIsNone(result.minimum_separation_yards)
        self.assertIsNone(result.nearest_triangle_index)

    def test_nearest_face_identity_survives_broad_phase(self):
        result=self.evaluate([wall(10),wall(1),wall(20)])
        self.assertEqual(result.nearest_triangle_index,1)
        self.assertEqual(result.triangle_count,3)

    def test_invalid_dimensions_and_nonfinite_points_are_rejected(self):
        for radius,height in [(0,2),(.4,.5),(math.nan,2),(.4,math.inf)]:
            with self.subTest(radius=radius,height=height), self.assertRaises(ValueError):
                self.evaluate([],radius=radius,height=height)
        with self.assertRaises(ValueError):
            self.evaluate([[(math.nan,0,0)]*3])
        with self.assertRaises(ValueError):
            self.evaluate([],stop=(101,0,0))

    def test_oblique_edge_distance(self):
        # Entire triangle is horizontally 1 yd from the upright axis.
        triangle=[(1,0,1),(2,1,1),(2,-1,1)]
        self.assertAlmostEqual(self.evaluate([triangle]).minimum_separation_yards,.6)

    def test_whole_sweep_is_no_farther_than_any_stationary_sample(self):
        triangles=[[(.25,.5,.7),(.5,.5,1.4),(.5,.8,.9)],wall(3)]
        result=self.evaluate(triangles,(-1,0,0),(1,0,.5)).minimum_separation_yards
        for i in range(21):
            point=(-1+i/10,0,i/40)
            distance=self.evaluate(triangles,point,point).minimum_separation_yards
            self.assertLessEqual(result,distance+1e-10)


if __name__=='__main__':
    unittest.main()
