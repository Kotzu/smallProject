from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic_ns
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from pause_hotkey import PauseHotkeySource
from send_input_backend import CtypesWin32KeyboardBackend
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.execution import SystemMonotonicClock
from perfect_assassin.execution.movement_runtime_arm import (
    issue_movement_authorization_snapshot,
    issue_movement_runtime_arm_snapshot,
    load_movement_authorization_profile,
    load_movement_runtime_arm,
)
from perfect_assassin.execution.single_forward_pulse import SingleForwardPulseCoordinator
from perfect_assassin.execution.windows_send_input import (
    WindowsInputTargetBinding,
    WindowsSendInputSink,
)


AUTH_SCHEMA = ROOT / "contracts" / "execution-target-authorization.schema.json"
RECEIPT_SCHEMA = ROOT / "contracts" / "lab-client-launch-receipt.schema.json"
ARM_SCHEMA = ROOT / "contracts" / "movement-runtime-arm.schema.json"
OBS_SCHEMA = ROOT / "contracts" / "coordinate-hud.schema.json"
RESULT_SCHEMA = ROOT / "contracts" / "single-forward-pulse-result.schema.json"
MOVEMENT_TEMPLATE = ROOT / "config" / "execution-targets" / "tbc_243_lab_movement_f3a.json"
OPERATOR = ROOT / "scripts" / "Invoke-LabClientOperator.ps1"
HUD_PROBE = ROOT / "integrations" / "windows-capture" / "probe_coordinate_hud.py"
RUNTIME_ROOT = ROOT / "data" / "runtime" / "movement-f3a"
OPERATOR_RUNTIME = ROOT / "data" / "runtime" / "operator"


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _exact_json_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class CliHudObservationSource:
    def __init__(
        self,
        *,
        arm,
        authorization_file: Path,
        launch_receipt: Path,
        session_id: str,
    ) -> None:
        self._arm = arm
        self._authorization_file = authorization_file
        self._launch_receipt = launch_receipt
        self._session_id = session_id
        self._counter = 0

    def next_observation(self):
        self._counter += 1
        command = [
            sys.executable,
            str(HUD_PROBE),
            "--backend", "dxgi",
            "--window-pid", str(self._arm.pid),
            "--window-hwnd", self._arm.hwnd,
            "--window-title-exact", self._arm.window_title,
            "--window-class-exact", self._arm.window_class,
            "--session-id", self._session_id,
            "--observation-id", f"f3a:{self._counter}:{uuid4()}",
            "--samples", "1",
            "--client-build", self._arm.client_build,
            "--authorization-file", str(self._authorization_file),
            "--client-executable", self._arm.executable_path,
            "--lab-launch-receipt", str(self._launch_receipt),
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=2.5,
            check=False,
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("coordinate HUD probe returned no JSON")
        record = json.loads(lines[-1])
        if completed.returncode == 3:
            return None
        if completed.returncode != 0:
            raise RuntimeError(
                f"coordinate HUD probe failed closed: {record.get('detail', 'unknown')}"
            )
        return record


def _invoke_revalidation(
    *,
    session_authorization: Path,
    movement_authorization: Path,
) -> Path:
    completed = subprocess.run(
        [
            "pwsh", "-NoProfile", "-NonInteractive", "-File", str(OPERATOR),
            "-Action", "IssueMovementRealmRevalidation",
            "-RepositoryRoot", str(ROOT),
            "-AuthorizationFile", str(session_authorization),
            "-MovementAuthorizationFile", str(movement_authorization),
            "-AcknowledgeSinglePulse",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15.0,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "movement realm revalidation failed closed: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    prefix = "LAB_MOVEMENT_REALM_REVALIDATION="
    for line in completed.stdout.splitlines():
        if line.startswith(prefix):
            return Path(line[len(prefix):])
    raise RuntimeError("movement realm revalidation path was not returned")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute one exact 100/150ms LAB forward pulse and prove HUD displacement."
    )
    parser.add_argument("--session-authorization-file", type=Path, required=True)
    parser.add_argument(
        "--session-receipt",
        type=Path,
        default=OPERATOR_RUNTIME / "lab-client-launch-receipt.json",
    )
    parser.add_argument("--acknowledge-single-pulse", action="store_true")
    return parser


def run(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.acknowledge_single_pulse is not True:
        raise SystemExit("--acknowledge-single-pulse is required")
    if not args.session_authorization_file.is_file() or not args.session_receipt.is_file():
        raise SystemExit("active session authorization and receipt are required")

    run_uuid = uuid4()
    run_id = f"run:f3a:{run_uuid}"
    movement_auth_path = RUNTIME_ROOT / f"movement-authorization-{run_uuid}.json"
    arm_path = RUNTIME_ROOT / f"movement-arm-{run_uuid}.json"
    result_path = RUNTIME_ROOT / "results" / f"single-forward-pulse-{run_uuid}.json"
    sink = None
    try:
        movement_raw = issue_movement_authorization_snapshot(
            MOVEMENT_TEMPLATE.read_bytes(),
            schema_path=AUTH_SCHEMA,
            now_utc=datetime.now(timezone.utc),
            evidence_refs=(f"gate:{run_id}",),
            acknowledge_single_pulse=True,
        )
        _atomic_write(movement_auth_path, movement_raw)
        revalidation_path = _invoke_revalidation(
            session_authorization=args.session_authorization_file,
            movement_authorization=movement_auth_path,
        )
        receipt_raw = args.session_receipt.read_bytes()
        session_auth_raw = args.session_authorization_file.read_bytes()
        revalidation_raw = revalidation_path.read_bytes()
        now_utc = datetime.now(timezone.utc)
        now_monotonic_ms = monotonic_ns() / 1_000_000.0
        profile = load_movement_authorization_profile(
            movement_raw,
            schema_path=AUTH_SCHEMA,
            now_utc=now_utc,
        )
        arm_raw = issue_movement_runtime_arm_snapshot(
            authorization=profile,
            authorization_raw=movement_raw,
            session_receipt_raw=receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            session_authorization_raw=session_auth_raw,
            authorization_schema_path=AUTH_SCHEMA,
            realm_revalidation_raw=revalidation_raw,
            arm_schema_path=ARM_SCHEMA,
            now_utc=now_utc,
            now_monotonic_ms=now_monotonic_ms,
            clock_id="clock:windows:monotonic",
            acknowledge_single_pulse=True,
        )
        _atomic_write(arm_path, arm_raw)
        arm = load_movement_runtime_arm(
            arm_raw,
            schema_path=ARM_SCHEMA,
            authorization=profile,
            session_receipt_raw=receipt_raw,
            session_receipt_schema_path=RECEIPT_SCHEMA,
            session_authorization_raw=session_auth_raw,
            authorization_schema_path=AUTH_SCHEMA,
            realm_revalidation_raw=revalidation_raw,
            acknowledge_single_pulse=True,
            now_utc=now_utc,
            now_monotonic_ms=now_monotonic_ms,
        )
        clock = SystemMonotonicClock(arm.clock_id)
        target = WindowsInputTargetBinding(
            authority_binding=arm.binding,
            pid=arm.pid,
            hwnd=int(arm.hwnd, 16),
            process_creation_time_100ns=int(arm.process_creation_filetime_utc),
            executable_path=arm.executable_path,
            executable_sha256=arm.executable_sha256,
            window_class_exact=arm.window_class,
            window_title_exact=arm.window_title,
        )
        sink = WindowsSendInputSink(
            target=target,
            backend=CtypesWin32KeyboardBackend(),
            clock=clock,
        )
        observations = CliHudObservationSource(
            arm=arm,
            authorization_file=movement_auth_path,
            launch_receipt=args.session_receipt,
            session_id=f"session:f3a:{run_uuid}",
        )
        result = SingleForwardPulseCoordinator(
            arm=arm,
            clock=clock,
            sink=sink,
            observations=observations,
            observation_validator=ContractValidator(OBS_SCHEMA),
            result_validator=ContractValidator(RESULT_SCHEMA),
            manual_takeover=PauseHotkeySource(),
        ).run(run_id=run_id, owner_id="controller:f3a:single-forward")
        _atomic_write(result_path, _exact_json_bytes(result))
        print(json.dumps({"result_path": str(result_path), **result}, sort_keys=True))
        return 0 if result["status"] == "PROVEN_DISPLACEMENT" else 3
    except Exception as error:
        print(
            json.dumps(
                {
                    "record_type": "single_forward_pulse_failure",
                    "status": "failed_closed",
                    "error_type": type(error).__name__,
                    "detail": str(error),
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 1
    finally:
        if sink is not None:
            try:
                sink.close()
            except Exception:
                pass
        arm_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(run())
