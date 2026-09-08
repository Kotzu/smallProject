from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.compose_navmesh_repair_candidate import (
    compose_navmesh_repair_candidate,
)


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _fixture(root: Path) -> tuple[Path, Path, dict[str, object]]:
    source = root / "source"
    repairs = root / "repairs"
    _write(source / "Azeroth.map", b"map")
    _write(source / "BVH" / "fixture.bvh", b"bvh")
    _write(source / "semantics" / "Azeroth_01_01.road", b"road-1")
    _write(source / "semantics" / "Azeroth_01_02.road", b"road-2")
    _write(source / "Nav" / "Azeroth" / "01_01.nav", b"good")
    _write(source / "Nav" / "Azeroth" / "01_02.nav", b"broken")
    _write(repairs / "Nav" / "Azeroth" / "01_02.nav", b"repaired")
    report: dict[str, object] = {
        "status": "FAIL",
        "validator_id": "fixture-validator",
        "catalog_sha256": "a" * 64,
        "internal_name": "Azeroth",
        "expected_tile_count": 2,
        "failures": [{
            "artifact": "01_02.nav",
            "code": "DETOUR_PAYLOAD_INVALID",
        }],
    }
    return source, repairs, report


class ComposeNavmeshRepairCandidateTests(unittest.TestCase):
    def test_composes_exact_repair_set_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, repairs, report = _fixture(root)
            destination = root / "candidate"
            evidence = compose_navmesh_repair_candidate(
                source_root=source,
                repair_root=repairs,
                source_geometry_report=report,
                output_root=destination,
                map_name="Azeroth",
            )
            self.assertEqual(
                (destination / "Nav" / "Azeroth" / "01_01.nav").read_bytes(),
                b"good",
            )
            self.assertEqual(
                (destination / "Nav" / "Azeroth" / "01_02.nav").read_bytes(),
                b"repaired",
            )
            self.assertEqual(
                (source / "Nav" / "Azeroth" / "01_02.nav").read_bytes(),
                b"broken",
            )
            self.assertEqual(evidence["replacement_count"], 1)
            stored = json.loads((
                destination / "evidence" / "navmesh-repair-composition.json"
            ).read_text(encoding="utf-8"))
            self.assertEqual(stored, evidence)

    def test_rejects_a_missing_or_extra_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, repairs, report = _fixture(root)
            (repairs / "Nav" / "Azeroth" / "01_02.nav").unlink()
            with self.assertRaisesRegex(ValueError, "repair set is not exact"):
                compose_navmesh_repair_candidate(
                    source_root=source,
                    repair_root=repairs,
                    source_geometry_report=report,
                    output_root=root / "candidate",
                    map_name="Azeroth",
                )

    def test_rejects_an_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, repairs, report = _fixture(root)
            destination = root / "candidate"
            destination.mkdir()
            with self.assertRaises(FileExistsError):
                compose_navmesh_repair_candidate(
                    source_root=source,
                    repair_root=repairs,
                    source_geometry_report=report,
                    output_root=destination,
                    map_name="Azeroth",
                )


if __name__ == "__main__":
    unittest.main()
