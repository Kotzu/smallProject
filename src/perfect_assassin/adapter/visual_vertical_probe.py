"""Offline pinhole-projection diagnostic using independently supplied landmarks.

No image matching, live calibration, actor detector or runtime pose authority.
All correspondences must belong to one unchanged camera/viewport. A small
residual does not establish that these correspondences are truthful.
"""

import numpy as np


def _points(value, dimensions, minimum, maximum=64):
    array = np.asarray(value)
    if (
        array.dtype.kind not in "fiu"
        or array.ndim != 2
        or array.shape[1] != dimensions
        or not minimum <= len(array) <= maximum
        or not np.isfinite(array).all()
        or np.any(np.abs(array.astype(np.float64)) > 1e7)
    ):
        raise ValueError("invalid visual probe coordinates")
    return array.astype(np.float64)


def _positive(value):
    if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
        raise ValueError("invalid explicit pixel budget")
    return float(value)


def _normalize(points):
    centered = points - points.mean(axis=0)
    radius = np.sqrt(np.mean(np.sum(centered**2, axis=1)))
    if not np.isfinite(radius) or radius <= 1e-10:
        raise ValueError("collapsed landmark set")
    scale = np.sqrt(points.shape[1]) / radius
    transform = np.eye(points.shape[1] + 1)
    transform[:-1, :-1] *= scale
    transform[:-1, -1] = -scale * points.mean(axis=0)
    homogeneous = np.column_stack((points, np.ones(len(points))))
    return (homogeneous @ transform.T)[:, :-1], transform


def _project(matrix, points):
    homogeneous = np.column_stack((points, np.ones(len(points)))) @ matrix.T
    depth = homogeneous[:, 2]
    if np.any(depth <= 1e-9):
        raise ValueError("landmark/candidate behind camera or on projection plane")
    return homogeneous[:, :2] / depth[:, None]


def fit_landmark_projection(
    *,
    fit_world,
    fit_pixels,
    check_world,
    check_pixels,
    image_size,
    maximum_reprojection_error_px,
):
    """Camera-only diagnostic; no invented actor/foot observation is required."""
    world = _points(fit_world, 3, 8)
    pixels = _points(fit_pixels, 2, 8)
    checks = _points(check_world, 3, 4)
    check_uv = _points(check_pixels, 2, 4)
    if len(world) != len(pixels) or len(checks) != len(check_uv):
        raise ValueError("landmark correspondence count mismatch")
    if len(image_size) != 2 or any(
        type(v) is not int or not 1 <= v <= 16384 for v in image_size
    ):
        raise ValueError("invalid viewport")
    for uv in (pixels, check_uv):
        if np.any(uv < 0) or np.any(uv >= np.array(image_size)):
            raise ValueError("observed point outside viewport")
    error_budget = _positive(maximum_reprojection_error_px)
    # Held-out points cannot be copies of the fit points; names alone are not evidence.
    if np.any(np.linalg.norm(checks[:, None, :] - world[None, :, :], axis=2) < 1e-8):
        raise ValueError("held-out landmarks reused from fit")
    normalized, world_transform = _normalize(world)
    uv, image_transform = _normalize(pixels)
    spread = np.linalg.svd(normalized, compute_uv=False)
    if spread[-1] / spread[0] < 1e-3:
        raise ValueError("planar or poorly conditioned landmark geometry")
    if len(np.unique(world, axis=0)) != len(world) or len(
        np.unique(pixels, axis=0)
    ) != len(pixels):
        raise ValueError("duplicate fit landmarks")
    homogeneous = np.column_stack((normalized, np.ones(len(normalized))))
    equations = []
    for point, (u, v) in zip(homogeneous, uv):
        equations.extend(
            (
                np.concatenate((point, np.zeros(4), -u * point)),
                np.concatenate((np.zeros(4), point, -v * point)),
            )
        )
    _, singular, vectors = np.linalg.svd(np.array(equations), full_matrices=False)
    if singular[-2] / singular[0] < 1e-6:
        raise ValueError("underdetermined camera projection")
    matrix = (
        np.linalg.solve(image_transform, vectors[-1].reshape(3, 4)) @ world_transform
    )
    norm = np.linalg.norm(matrix[2, :3])
    if not np.isfinite(matrix).all() or norm <= 1e-12:
        raise ValueError("degenerate projection matrix")
    matrix /= norm
    if np.median(np.column_stack((world, np.ones(len(world)))) @ matrix[2]) < 0:
        matrix = -matrix
    fit_error = np.linalg.norm(_project(matrix, world) - pixels, axis=1)
    check_error = np.linalg.norm(_project(matrix, checks) - check_uv, axis=1)
    if max(fit_error.max(), check_error.max()) > error_budget:
        raise ValueError(
            "projection failed independent landmark check: "
            f"fit_max={fit_error.max():.3f}px check_max={check_error.max():.3f}px"
        )
    return {
        "source": "OFFLINE_LANDMARK_CAMERA_DIAGNOSTIC",
        "projection_matrix": matrix.tolist(),
        "fit_landmark_count": len(world),
        "held_out_landmark_count": len(checks),
        "fit_max_error_pixels": float(fit_error.max()),
        "held_out_max_error_pixels": float(check_error.max()),
        "observed_actor_z": None, "confirmed_floor_id": None,
        "live_calibration_verified": False, "execution_authority": False,
    }


def visual_vertical_probe(
    *, fit_world, fit_pixels, check_world, check_pixels, actor_xy, foot_pixel,
    candidate_heights, image_size, maximum_reprojection_error_px,
    pixel_discrimination_budget,
):
    """Compare all heights only when a separate actor contact observation exists."""
    xy = _points([actor_xy], 2, 1)[0]
    foot = _points([foot_pixel], 2, 1)
    heights = _points([[z] for z in candidate_heights], 1, 1)[:, 0]
    discrimination = _positive(pixel_discrimination_budget)
    camera = fit_landmark_projection(
        fit_world=fit_world, fit_pixels=fit_pixels, check_world=check_world,
        check_pixels=check_pixels, image_size=image_size,
        maximum_reprojection_error_px=maximum_reprojection_error_px,
    )
    if np.any(foot < 0) or np.any(foot >= np.array(image_size)):
        raise ValueError("observed point outside viewport")
    matrix = np.array(camera["projection_matrix"])
    candidates = np.column_stack((np.tile(xy, (len(heights), 1)), heights))
    projected = _project(matrix, candidates)
    distances = np.linalg.norm(projected - foot, axis=1)
    pairs = [
        float(np.linalg.norm(projected[i] - projected[j]))
        for i in range(len(heights))
        for j in range(i)
    ]
    return {
        "schema_version": 1,
        "source": "OFFLINE_LANDMARK_PROJECTION_DIAGNOSTIC",
        "fit_landmark_count": camera["fit_landmark_count"],
        "held_out_landmark_count": camera["held_out_landmark_count"],
        "fit_max_error_pixels": camera["fit_max_error_pixels"],
        "held_out_max_error_pixels": camera["held_out_max_error_pixels"],
        "minimum_candidate_separation_pixels": min(pairs) if pairs else None,
        "discrimination_budget_pixels": discrimination,
        "all_pairs_separated_under_assumed_budget": bool(pairs)
        and min(pairs) > 2 * discrimination,
        "candidates": [
            {
                "height": float(z),
                "predicted_foot_pixel": point.tolist(),
                "foot_residual_pixels": float(distance),
                "candidate_retained": True,
            }
            for z, point, distance in zip(heights, projected, distances)
        ],
        "observed_actor_z": None,
        "confirmed_floor_id": None,
        "live_calibration_verified": False,
        "execution_authority": False,
        "limitations": [
            "CORRESPONDENCES_REQUIRE_INDEPENDENT_VERIFICATION",
            "SAME_CAMERA_FRAME_REQUIRED",
            "ACTOR_XY_ERROR_NOT_CALIBRATED",
            "VISIBLE_FOOT_CONTACT_NOT_AUTOMATICALLY_DETECTED",
            "PINHOLE_MODEL_MUST_BE_VALIDATED_ON_REAL_FRAMES",
        ],
    }
