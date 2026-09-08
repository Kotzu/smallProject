"""Cross-check fixed-view minimap displacements in an explicit offline record.

Input: structure.transform_matrix and results containing world_xy, second,
fit.offset_xy, fit.factor, fit.angle_degrees, fit.scale. This diagnostic does
not certify source provenance, capture freshness, pose accuracy, or floor.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from perfect_assassin.adapter.minimap_layout import expected_texture_translation
from perfect_assassin.adapter.wmo_bundle import read_bounded


def audit(record):
    results = record["results"]
    if not isinstance(results, list) or not 2 <= len(results) <= 64:
        raise ValueError("invalid bounded frame sequence")
    base = results[0]
    rows = []
    for current in results[1:]:
        for key in ("factor", "angle_degrees", "scale"):
            if current["fit"][key] != base["fit"][key]:
                raise ValueError("view changes cannot be treated as fixed calibration")
        expected = expected_texture_translation(
            base["world_xy"], current["world_xy"], record["structure"]["transform_matrix"],
            pixels_per_model_unit=base["fit"]["factor"],
            rotation_degrees=base["fit"]["angle_degrees"], scale=base["fit"]["scale"],
        )
        offsets = np.asarray([base["fit"]["offset_xy"], current["fit"]["offset_xy"]], float)
        if offsets.shape != (2, 2) or not np.isfinite(offsets).all():
            raise ValueError("invalid fitted offsets")
        actual = offsets[1] - offsets[0]
        rows.append({"from_second": base["second"], "to_second": current["second"],
                     "predicted_shift_px": expected, "fitted_shift_px": actual.tolist(),
                     "residual_px": float(np.linalg.norm(actual - expected))})
    return {"source": "OFFLINE_MINIMAP_DISPLACEMENT_AUDIT", "comparisons": rows,
            "source_provenance_reverified": False, "metric_pose_accuracy_yards": None,
            "observed_actor_z": None, "floor_id": None, "execution_authority": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    data = read_bounded(args.input, 16 * 1024 * 1024)
    result = audit(json.loads(data))
    result["input_sha256"] = sha256(data).hexdigest()
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, allow_nan=False)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
