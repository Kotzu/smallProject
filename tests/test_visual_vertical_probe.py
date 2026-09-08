import numpy as np
import pytest

from perfect_assassin.adapter.visual_vertical_probe import visual_vertical_probe
from perfect_assassin.adapter.visual_vertical_probe import fit_landmark_projection


def setup(top_down=False):
    rng = np.random.default_rng(4831)
    world = rng.uniform([-5, -5, 0], [5, 5, 12], (16, 3))

    def project(p):
        x, y, z = p.T
        if top_down:
            return np.column_stack((800 + 600 * x / (30 - z), 500 + 600 * y / (30 - z)))
        return np.column_stack((800 + 600 * x / (20 + y), 500 - 600 * z / (20 + y)))

    xy = (0.0, 0.0) if top_down else (1.0, 2.0)
    return {
        "fit_world": world[:12],
        "fit_pixels": project(world[:12]),
        "check_world": world[12:],
        "check_pixels": project(world[12:]),
        "actor_xy": xy,
        "foot_pixel": project(np.array([[*xy, 3.0]]))[0],
        "candidate_heights": [3.0, 10.0],
        "image_size": (1600, 1000),
        "maximum_reprojection_error_px": 1.0,
        "pixel_discrimination_budget": 2.0,
    }


def test_oblique_view_separates_levels_without_claiming_actor_z():
    result = visual_vertical_probe(**setup())
    assert result["held_out_max_error_pixels"] < 1e-8
    assert result["all_pairs_separated_under_assumed_budget"]
    assert result["candidates"][0]["foot_residual_pixels"] < 1e-8
    assert result["candidates"][1]["foot_residual_pixels"] > 100
    assert all(c["candidate_retained"] for c in result["candidates"])
    assert result["observed_actor_z"] is result["confirmed_floor_id"] is None
    assert result["execution_authority"] is result["live_calibration_verified"] is False


def test_camera_can_be_checked_without_actor_contact_or_height():
    args = setup()
    args = {k:v for k,v in args.items() if k not in {
        "actor_xy", "foot_pixel", "candidate_heights", "pixel_discrimination_budget"}}
    result = fit_landmark_projection(**args)
    assert np.array(result["projection_matrix"]).shape == (3,4)
    assert result["held_out_max_error_pixels"] < 1e-8
    assert "candidates" not in result
    assert result["observed_actor_z"] is result["confirmed_floor_id"] is None
    assert result["execution_authority"] is result["live_calibration_verified"] is False
    args["check_pixels"] += 20
    with pytest.raises(ValueError, match="check_max="):
        fit_landmark_projection(**args)


def test_top_down_optical_axis_cannot_distinguish_heights():
    result = visual_vertical_probe(**setup(top_down=True))
    assert result["minimum_candidate_separation_pixels"] < 1e-8
    assert not result["all_pairs_separated_under_assumed_budget"]
    assert len(result["candidates"]) == 2


def test_large_world_translation_does_not_break_projection():
    args = setup()
    shift = np.array([1800.0, 1600.0, 100.0])
    args["fit_world"] += shift
    args["check_world"] += shift
    args["actor_xy"] = np.array(args["actor_xy"]) + shift[:2]
    args["candidate_heights"] = [103.0, 110.0]
    assert visual_vertical_probe(**args)["candidates"][0]["foot_residual_pixels"] < 1e-8


@pytest.mark.parametrize(
    "case",
    [
        "planar",
        "wrong_holdout",
        "reused",
        "duplicate",
        "nan",
        "outside",
        "behind",
        "boolean_budget",
    ],
)
def test_invalid_or_ambiguous_calibration_is_rejected(case):
    args = setup()
    if case == "planar":
        args["fit_world"][:, 2] = 0
    elif case == "wrong_holdout":
        args["check_pixels"] += 50
    elif case == "reused":
        args["check_world"][0] = args["fit_world"][0]
    elif case == "duplicate":
        args["fit_world"][1] = args["fit_world"][0]
    elif case == "nan":
        args["candidate_heights"] = [float("nan")]
    elif case == "outside":
        args["foot_pixel"] = [-1, 20]
    elif case == "behind":
        args["actor_xy"] = [0, -30]
    else:
        args["pixel_discrimination_budget"] = True
    with pytest.raises(ValueError):
        visual_vertical_probe(**args)


def test_noisy_points_report_errors_not_perfect_confidence():
    args = setup()
    args["fit_pixels"] += np.random.default_rng(13).normal(0, 0.03, (12, 2))
    result = visual_vertical_probe(**args)
    assert 0 < result["held_out_max_error_pixels"] < 1


def test_single_candidate_is_not_a_discrimination_proof():
    args = setup()
    args["candidate_heights"] = [3.0]
    result = visual_vertical_probe(**args)
    assert not result["all_pairs_separated_under_assumed_budget"]
    assert result["minimum_candidate_separation_pixels"] is None


@pytest.mark.parametrize(
    "case", ["collapsed", "huge", "same_pixels", "counts", "zero_budget"]
)
def test_degenerate_input_is_explicitly_rejected(case):
    args = setup()
    if case == "collapsed":
        args["fit_world"][:] = 0
    elif case == "huge":
        args["fit_world"] *= 1e100
    elif case == "same_pixels":
        args["fit_pixels"][:] = [800, 500]
    elif case == "counts":
        args["fit_pixels"] = args["fit_pixels"][:-1]
    else:
        args["maximum_reprojection_error_px"] = 0
    with pytest.raises(ValueError):
        visual_vertical_probe(**args)
