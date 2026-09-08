from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import rebuild_navmesh_repair_batch as batch
from perfect_assassin.contract_validation import ContractValidator


class RebuildNavmeshRepairBatchTests(unittest.TestCase):
    def test_direct_script_entrypoint_can_load_its_workspace_modules(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts" / "rebuild_navmesh_repair_batch.py"
        )
        completed = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--source-root", completed.stdout)

    def test_batch_evidence_schema_accepts_a_bounded_pass_record(self) -> None:
        digest = "a" * 64
        ContractValidator(batch.BATCH_EVIDENCE_SCHEMA).validate({
            "record_type": "navmesh_repair_batch_evidence",
            "schema_version": "1.0",
            "status": "PASS",
            "map_name": "Azeroth",
            "source_root": "E:/source",
            "destination_root": "E:/destination",
            "builder": "E:/MapBuilder.exe",
            "builder_sha256": digest,
            "expected_artifact_count": 1,
            "validated_artifact_count": 1,
            "results": [{
                "artifact": "39_30.nav",
                "action": "rebuilt",
                "source_sha256": digest,
                "source_failure": "zero-area polygon",
                "result_sha256": digest,
                "detour_tile_count": 256,
                "empty_inner_tile_count": 0,
                "build_log": "E:/work/39_30/build.log",
                "elapsed_seconds": 1.25,
            }],
            "failures": [],
            "execution_authority": False,
        })

    def test_artifact_parser_and_command_keep_coordinates_and_spaced_paths(self) -> None:
        self.assertEqual(batch.parse_adt_artifact("39_30.nav"), (39, 30))
        with self.assertRaises(ValueError):
            batch.parse_adt_artifact("Azeroth.nav")
        command = batch.builder_command(
            builder=Path("C:/Tools/Map Builder.exe"),
            data_root=Path("E:/Games/WoW TBC 2.4.3/Data"),
            output_root=Path("E:/Runtime/39_30"),
            map_name="Azeroth",
            adt_x=39,
            adt_y=30,
            log_level=2,
        )
        self.assertEqual(command[2], "E:\\Games\\WoW TBC 2.4.3\\Data")
        self.assertEqual(command[-4:], ["-x", "39", "-y", "30"])

    def test_valid_source_is_copied_without_invoking_builder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "Nav" / "Azeroth"
            destination = root / "destination" / "Nav" / "Azeroth"
            source.mkdir(parents=True)
            (source / "39_30.nav").write_bytes(b"valid")
            with patch.object(batch, "validate_nav", return_value=(250, 6)), patch.object(
                batch.subprocess, "run"
            ) as run:
                result = batch.process_artifact(
                    "39_30.nav",
                    source_nav_directory=source,
                    destination_nav_directory=destination,
                    work_root=root / "work",
                    builder=root / "MapBuilder.exe",
                    data_root=root / "Data",
                    map_name="Azeroth",
                    log_level=2,
                )
            self.assertEqual(result["action"], "copied_valid")
            self.assertEqual((destination / "39_30.nav").read_bytes(), b"valid")
            run.assert_not_called()

    def test_invalid_source_is_rebuilt_validated_and_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "Nav" / "Azeroth"
            destination = root / "destination" / "Nav" / "Azeroth"
            source.mkdir(parents=True)
            (source / "39_30.nav").write_bytes(b"invalid")

            def fake_run(command, **kwargs):
                output_root = Path(command[command.index("-o") + 1])
                candidate = output_root / "Nav" / "Azeroth" / "39_30.nav"
                candidate.parent.mkdir(parents=True)
                candidate.write_bytes(b"rebuilt")
                return subprocess.CompletedProcess(command, 0)

            def fake_validate(path: Path, *, map_name: str):
                if path.read_bytes() == b"invalid":
                    raise ValueError("zero-area polygon")
                return 256, 0

            with patch.object(batch, "validate_nav", side_effect=fake_validate), patch.object(
                batch.subprocess, "run", side_effect=fake_run
            ) as run:
                result = batch.process_artifact(
                    "39_30.nav",
                    source_nav_directory=source,
                    destination_nav_directory=destination,
                    work_root=root / "work",
                    builder=root / "MapBuilder.exe",
                    data_root=root / "Data",
                    map_name="Azeroth",
                    log_level=2,
                )
            self.assertEqual(result["action"], "rebuilt")
            self.assertEqual((destination / "39_30.nav").read_bytes(), b"rebuilt")
            self.assertEqual(run.call_args.args[0][-4:], ["-x", "39", "-y", "30"])

    def test_valid_interrupted_attempt_is_recovered_without_rebuilding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "Nav" / "Azeroth"
            destination = root / "destination" / "Nav" / "Azeroth"
            work = root / "work"
            source.mkdir(parents=True)
            (source / "39_30.nav").write_bytes(b"invalid")
            recovered = (
                work / "39_30" / "attempt-old" / "Nav" / "Azeroth" / "39_30.nav"
            )
            recovered.parent.mkdir(parents=True)
            recovered.write_bytes(b"recovered")

            def fake_validate(path: Path, *, map_name: str):
                if path.read_bytes() == b"invalid":
                    raise ValueError("zero-area polygon")
                return 255, 1

            with patch.object(batch, "validate_nav", side_effect=fake_validate), patch.object(
                batch.subprocess, "run"
            ) as run:
                result = batch.process_artifact(
                    "39_30.nav",
                    source_nav_directory=source,
                    destination_nav_directory=destination,
                    work_root=work,
                    builder=root / "MapBuilder.exe",
                    data_root=root / "Data",
                    map_name="Azeroth",
                    log_level=2,
                )
            self.assertEqual(result["action"], "recovered_valid")
            self.assertEqual((destination / "39_30.nav").read_bytes(), b"recovered")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
