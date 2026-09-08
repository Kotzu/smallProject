import numpy as np
import pytest
from test_wmo_bundle import build, context  # noqa: F401

from perfect_assassin.adapter.wmo_groups import world_to_model
from perfect_assassin.adapter.wmo_landmarks import resolve_landmarks


def test_vertices_keep_provenance_and_instance_transform(context):  # noqa: F811
    bundle, digest = build(context)
    matrix = np.array(
        [[0, -1, 0, 100], [1, 0, 0, 200], [0, 0, 1, 30], [0, 0, 0, 1]], dtype=float
    )
    bundle.structures["0:wmo:0"]["transform_matrix"] = matrix.reshape(-1).tolist()
    result = resolve_landmarks(
        bundle,
        structure_id="0:wmo:0",
        references=[{"group_index": 0, "vertex_index": 1}],
    )
    point = result["points"][0]
    assert point["world_xyz"] == pytest.approx([100, 204, 30])
    assert world_to_model(point["world_xyz"], matrix.reshape(-1)) == pytest.approx(
        point["model_xyz"]
    )
    assert point["group_id"] == 321 and point["used_by_retained_triangle"]
    assert not point["pixel_correspondence_verified"]
    assert result["bundle_sha256"] == digest and not result["execution_authority"]


@pytest.mark.parametrize(
    "refs",
    [
        [],
        [{"group_index": 0, "vertex_index": True}],
        [{"group_index": 99, "vertex_index": 0}],
        [{"group_index": 0, "vertex_index": 999}],
        [{"group_index": 0, "vertex_index": 0}] * 2,
    ],
)
def test_invalid_or_duplicate_refs_fail(context, refs):  # noqa: F811
    bundle, _ = build(context)
    with pytest.raises(ValueError):
        resolve_landmarks(bundle, structure_id="0:wmo:0", references=refs)


def test_uncovered_model_cannot_supply_landmarks(context):  # noqa: F811
    bundle, _ = build(context)
    with pytest.raises(KeyError):
        resolve_landmarks(
            bundle,
            structure_id="0:wmo:1",
            references=[{"group_index": 0, "vertex_index": 0}],
        )


def test_non_asset_context_and_oversized_selection_fail(context):  # noqa: F811
    with pytest.raises(TypeError):
        resolve_landmarks({}, structure_id="x", references=[])
    bundle, _ = build(context)
    with pytest.raises(ValueError):
        resolve_landmarks(bundle, structure_id="0:wmo:0", references=[{}] * 65)
