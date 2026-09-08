import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "minimap_displacement_audit", Path(__file__).resolve().parents[1] / "tools/audit_minimap_displacement.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def record():
    return {"structure": {"transform_matrix": np.eye(4).ravel().tolist()}, "results": [
        {"second": 1, "world_xy": [0, 0], "fit": {"factor": 2, "angle_degrees": 270,
                                                  "scale": 1, "offset_xy": [30, 40]}},
        {"second": 2, "world_xy": [4, 2], "fit": {"factor": 2, "angle_degrees": 270,
                                                  "scale": 1, "offset_xy": [26, 32]}},
    ]}


def test_exact_displacement_is_not_height_or_accuracy_certification():
    source = record()
    original = copy.deepcopy(source)
    result = module.audit(source)
    assert result["comparisons"][0]["residual_px"] == pytest.approx(0, abs=1e-10)
    assert result["metric_pose_accuracy_yards"] is None
    assert result["observed_actor_z"] is None
    assert result["source_provenance_reverified"] is False
    assert source == original


@pytest.mark.parametrize("field", ["factor", "angle_degrees", "scale"])
def test_changed_view_is_not_fixed_view_evidence(field):
    source = record()
    source["results"][1]["fit"][field] += 0.1
    with pytest.raises(ValueError, match="view changes"):
        module.audit(source)


def test_bad_sequence_and_offsets():
    source = record()
    source["results"] = source["results"][:1]
    with pytest.raises(ValueError):
        module.audit(source)
    source = record()
    source["results"][1]["fit"]["offset_xy"][0] = np.inf
    with pytest.raises(ValueError):
        module.audit(source)
