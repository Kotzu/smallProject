from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import subprocess
from typing import Sequence
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts" / "Run-StandaloneLabBootstrap.ps1"
STATE = ROOT / "data" / "runtime" / "operator" / "standalone-lab-launch.json"
STDOUT = ROOT / "data" / "runtime" / "operator" / "standalone-lab-bootstrap.stdout.log"
STDERR = ROOT / "data" / "runtime" / "operator" / "standalone-lab-bootstrap.stderr.log"


def detached_creation_flags() -> int:
    if os.name != "nt":
        raise RuntimeError("standalone LAB detachment is Windows-only")
    return (
        subprocess.CREATE_BREAKAWAY_FROM_JOB
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_NO_WINDOW
    )


def build_bootstrap_command(
    *,
    repository_root: Path,
    lab_root: Path,
    powershell_executable: Path | None = None,
) -> tuple[str, ...]:
    powershell = powershell_executable or Path(
        os.environ.get("SystemRoot", r"C:\Windows")
    ) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return (
        str(powershell),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repository_root / "scripts" / "Run-StandaloneLabBootstrap.ps1"),
        "-RepositoryRoot",
        str(repository_root),
        "-LabRoot",
        str(lab_root),
    )


def _write_json_atomic(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    temporary.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def launch(command: Sequence[str]) -> int:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with (
        STDOUT.open("a", encoding="utf-8") as stdout,
        STDERR.open("a", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(
            tuple(command),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            creationflags=detached_creation_flags(),
        )
    _write_json_atomic(
        STATE,
        {
            "record_type": "standalone_lab_launch",
            "schema_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "bootstrap_pid": process.pid,
            "repository_root": str(ROOT),
            "status": "BOOTSTRAP_STARTED_OUTSIDE_CODEX_JOB",
        },
    )
    return process.pid


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch the complete LAB outside the calling Codex process job."
    )
    parser.add_argument("--lab-root", type=Path, default=Path(r"E:\WoWserver\TBC-LAB"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not BOOTSTRAP.is_file():
        raise SystemExit(f"missing standalone bootstrap: {BOOTSTRAP}")
    command = build_bootstrap_command(repository_root=ROOT, lab_root=args.lab_root)
    pid = launch(command)
    print(f"STANDALONE_LAB_BOOTSTRAP_STARTED:PID={pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
