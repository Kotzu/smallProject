from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from send_input_backend import CtypesWin32KeyboardBackend

from perfect_assassin.execution.contracts import (
    MOVEMENT_EXECUTION_CAPABILITY,
    MOVEMENT_MODE,
    AuthorityBinding,
    MovementPrimitive,
)
from perfect_assassin.execution.ports import (
    CooperativeCancellation,
    SinkExecutionBudget,
    SystemMonotonicClock,
)
from perfect_assassin.execution.windows_send_input import (
    WindowsInputTargetBinding,
    WindowsSendInputSink,
)

DEFAULT_RECEIPT = (
    ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
)
DEFAULT_RUNTIME_ROOT = ROOT / "data" / "runtime" / "stay-online"
REALM_PORT = 8085
PULSE_CONTROLS = ("JUMP",)
PULSE_HOLD_MS = {"JUMP": 45}


class StayOnlineGuardError(RuntimeError):
    pass


class WindowsForegroundManager:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("foreground restoration is available only on Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.GetForegroundWindow.argtypes = ()
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        self._user32.SetForegroundWindow.restype = wintypes.BOOL
        self._user32.IsWindow.argtypes = (wintypes.HWND,)
        self._user32.IsWindow.restype = wintypes.BOOL

    def current(self) -> int:
        return int(self._user32.GetForegroundWindow() or 0)

    def restore(self, hwnd: int) -> bool:
        if type(hwnd) is not int or hwnd <= 0 or not self._user32.IsWindow(hwnd):
            return False
        return bool(self._user32.SetForegroundWindow(hwnd))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_receipt(path: Path) -> dict[str, object]:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise StayOnlineGuardError("LAB client receipt is unreadable") from error
    if not isinstance(receipt, dict):
        raise StayOnlineGuardError("LAB client receipt is not an object")
    if (
        receipt.get("record_type") != "lab_client_launch_receipt"
        or receipt.get("schema_version") != "1.0"
        or receipt.get("target_profile") != "tbc_243_lab"
        or receipt.get("environment_scope") != "emulator_local"
        or receipt.get("server_kind") != "emulator"
        or receipt.get("decision_context") != "lab_clone"
    ):
        raise StayOnlineGuardError("receipt is outside the exact local LAB scope")
    actor = receipt.get("actor_binding")
    if (
        not isinstance(actor, dict)
        or actor.get("expected_character_name") != "Predator"
    ):
        raise StayOnlineGuardError("receipt is not bound to Predator")
    return receipt


def _target_from_receipt(receipt: dict[str, object]) -> WindowsInputTargetBinding:
    actor = receipt["actor_binding"]
    assert isinstance(actor, dict)
    authority = AuthorityBinding(
        actor_id=str(actor["actor_id"]),
        actor_instance_id=str(actor["instance_id"]),
        actor_role="lab_clone",
        decision_context="lab_clone",
        target_profile="tbc_243_lab",
        target_instance_id=str(actor["instance_id"]),
        authorization_id="authorization:lab-stay-online:v1",
        authorization_sha256=str(receipt["authorization_sha256"]),
    )
    return WindowsInputTargetBinding(
        authority_binding=authority,
        pid=int(receipt["pid"]),
        hwnd=int(str(receipt["hwnd"]), 16),
        process_creation_time_100ns=int(receipt["process_creation_filetime_utc"]),
        executable_path=str(receipt["executable_path"]),
        executable_sha256=str(receipt["executable_sha256"]),
        window_class_exact=str(receipt["window_class"]),
        window_title_exact=str(receipt["window_title"]),
    )


def _realm_connected(pid: int) -> bool:
    # psutil is intentionally a runtime-only guard dependency.  The project's
    # pinned capture venv stays minimal and can still import/test pure policy.
    import psutil

    try:
        connections = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, OSError):
        return False
    for connection in connections:
        if connection.pid != pid or connection.status != psutil.CONN_ESTABLISHED:
            continue
        remote = connection.raddr
        if not remote or int(remote.port) != REALM_PORT:
            continue
        if str(remote.ip) in {"127.0.0.1", "::1"}:
            return True
    return False


def _same_client_renewal(previous: dict, current: dict) -> bool:
    """Accept refreshed evidence, never a different client/window/actor."""
    old_target = _target_from_receipt(previous)
    new_target = _target_from_receipt(current)
    return (
        previous["actor_binding"] == current["actor_binding"]
        and replace(new_target, authority_binding=old_target.authority_binding)
        == old_target
    )


def _verify_receipt_file_identity(receipt: dict[str, object]) -> None:
    executable = Path(str(receipt["executable_path"]))
    digest = hashlib.sha256(executable.read_bytes()).hexdigest().upper()
    if digest != str(receipt["executable_sha256"]).upper():
        raise StayOnlineGuardError("WoW executable hash changed")


def _execute_pulse(
    *,
    target: WindowsInputTargetBinding,
    backend: CtypesWin32KeyboardBackend,
    clock: SystemMonotonicClock,
    interrupted: Callable[[], bool],
    foreground_manager: WindowsForegroundManager,
) -> bool:
    previous_foreground = foreground_manager.current()
    sink = None
    restored = previous_foreground == target.hwnd
    try:
        if previous_foreground != target.hwnd:
            backend.focus_bound_target(target)
        sink = WindowsSendInputSink(target=target, backend=backend, clock=clock)
        cancellation = CooperativeCancellation()
        for sequence, control in enumerate(PULSE_CONTROLS, start=1):
            if interrupted():
                cancellation.cancel()
                raise StayOnlineGuardError("stay-online pulse was stopped")
            if not _realm_connected(target.pid):
                raise StayOnlineGuardError("realm connection disappeared during pulse")
            now_ms = clock.now_ms()
            hold_ms = PULSE_HOLD_MS[control]
            envelope_ms = hold_ms + 150
            primitive = MovementPrimitive(
                primitive_id=f"primitive:stay-online:{target.pid}:{sequence}",
                lease_id=f"lease:stay-online:{target.pid}",
                binding=target.authority_binding,
                owner_id="controller:stay-online:lab",
                runtime_arm_nonce=f"stay-online:{target.pid}",
                mode=MOVEMENT_MODE,
                capability=MOVEMENT_EXECUTION_CAPABILITY,
                sequence=sequence,
                controls=(control,),
                hold_duration_ms=hold_ms,
                max_execution_envelope_ms=envelope_ms,
                clock_id=clock.clock_id,
                issued_at_monotonic_ms=now_ms,
                expires_at_monotonic_ms=now_ms + envelope_ms,
            )
            budget = SinkExecutionBudget(
                clock_id=clock.clock_id,
                started_at_monotonic_ms=now_ms,
                absolute_deadline_monotonic_ms=now_ms + envelope_ms,
                remaining_ms=float(envelope_ms),
                hold_duration_ms=hold_ms,
                max_execution_envelope_ms=envelope_ms,
            )
            sink.apply_bounded(primitive, cancellation, budget)
            time.sleep(0.12)
    finally:
        if sink is not None:
            sink.close()
        if previous_foreground != target.hwnd:
            restored = foreground_manager.restore(previous_foreground)
    return restored


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Keep one exact foreground local-LAB WoW client online."
    )
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument(
        "--state-file", type=Path, default=DEFAULT_RUNTIME_ROOT / "state.json"
    )
    parser.add_argument(
        "--stop-file", type=Path, default=DEFAULT_RUNTIME_ROOT / "stop.request"
    )
    parser.add_argument(
        "--idle-seconds",
        type=float,
        default=240.0,
        help="Deprecated compatibility option; does not trigger input.",
    )
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument(
        "--authorization",
        type=Path,
        default=ROOT / "data/runtime/operator/tbc_243_lab.active.json",
    )
    parser.add_argument("--max-hours", type=float, default=12.0)
    parser.add_argument("--acknowledge-stay-online", action="store_true")
    return parser


def _movement_busy() -> bool:
    import psutil

    names = {
        "run_navmesh_roaming.py",
        "run_journey_combat_supervisor.py",
        "run_controlled_combat.py",
        "run_single_forward_pulse.py",
        "run_navigation_continuity.py",
        "run_manual_path_recorder.py",
    }
    try:
        for process in psutil.process_iter(["name", "cmdline"]):
            if "python" not in (process.info["name"] or "").lower():
                continue
            if any(
                Path(argument).name in names
                for argument in (process.info["cmdline"] or [])
            ):
                return True
    except (psutil.Error, OSError):
        return True
    return False


def run(argv=None) -> int:
    from run_navmesh_roaming import LiveCoordinatePoseSource

    from perfect_assassin.adapter.afk_hud import AfkEpisodeLatch

    args = build_parser().parse_args(argv)
    if args.acknowledge_stay_online is not True:
        raise SystemExit("--acknowledge-stay-online is required")
    if not 1 <= args.poll_seconds <= 30 or not 0.25 <= args.max_hours <= 24:
        raise SystemExit("poll/runtime bounds are invalid")
    receipt = _load_receipt(args.receipt)
    _verify_receipt_file_identity(receipt)
    target = _target_from_receipt(receipt)
    binding_key = f"{target.pid}:{target.process_creation_time_100ns}"
    latch = AfkEpisodeLatch()
    # Same-session restart must not repeat an uncertain/already-sent jump.
    try:
        prior = json.loads(args.state_file.read_text(encoding="utf-8"))
        latch.handled = (
            prior.get("binding_key") == binding_key
            and prior.get("episode_handled") is True
        )
    except (OSError, ValueError, AttributeError):
        pass
    backend = CtypesWin32KeyboardBackend()
    foreground_manager = WindowsForegroundManager()
    clock = SystemMonotonicClock("clock:windows:monotonic")
    deadline = time.monotonic() + args.max_hours * 3600
    source = None
    pulse_count = 0
    last_error = None
    packet = None

    def stopped() -> bool:
        return args.stop_file.exists()

    def publish(status: str) -> None:
        _atomic_json(
            args.state_file,
            {
                "record_type": "lab_stay_online_guard_state",
                "schema_version": "0.2",
                "status": status,
                "pid": os.getpid(),
                "client_pid": target.pid,
                "binding_key": binding_key,
                "episode_handled": latch.handled,
                "pulse_count": pulse_count,
                "last_error": last_error,
                "afk_observation": None if packet is None else asdict(packet),
                "trigger": "CRC_CLIENT_AFK_EPISODE",
                "controls": ["JUMP"],
                "updated_at": _utc_now(),
                "execution_authority": False,
            },
        )

    try:
        while time.monotonic() < deadline and not stopped():
            import psutil

            if not psutil.pid_exists(target.pid):
                publish("CLIENT_EXITED")
                return 0
            busy = _movement_busy()
            packet = None
            if _realm_connected(target.pid) and not busy:
                try:
                    renewed = _load_receipt(args.receipt)
                    if renewed != receipt:
                        if not _same_client_renewal(receipt, renewed):
                            raise StayOnlineGuardError(
                                "client identity changed; restart required"
                            )
                        if source is not None:
                            source.close()
                            source = None
                        receipt = renewed
                        target = _target_from_receipt(receipt)
                        # Existing capture validation checks the refreshed
                        # authorization, receipt and expiry before any input.
                    if source is None:
                        source = LiveCoordinatePoseSource(
                            authorization_file=args.authorization,
                            receipt_file=args.receipt,
                            receipt=receipt,
                            session_id=f"session:stay-online:{os.getpid()}",
                            require_foreground_capture=False,
                            enforce_combat_handoff=False,
                            observe_afk=True,
                        )
                        source.open()
                    source.next_observation()
                    packet = source.latest_afk_packet
                    last_error = None if packet is not None else "AFK_STRIP_UNAVAILABLE"
                except Exception as error:  # noqa: BLE001 -- any capture failure forbids input
                    last_error = type(error).__name__
                    if source is not None:
                        source.close()
                        source = None
            elif source is not None:
                source.close()
                source = None
            if latch.observe(packet, movement_busy=busy):  # noqa: SIM102 -- recheck input ownership
                # Recheck exclusion immediately before issuing the one shot.
                if not _movement_busy() and not stopped():
                    latch.mark_attempted()
                    publish("RUNNING")  # durable BEFORE input; no automatic retry
                    _execute_pulse(
                        target=target,
                        backend=backend,
                        clock=clock,
                        interrupted=lambda: stopped() or _movement_busy(),
                        foreground_manager=foreground_manager,
                    )
                    pulse_count += 1
            publish("RUNNING")
            time.sleep(args.poll_seconds)
        publish("STOPPED" if stopped() else "MAX_RUNTIME_REACHED")
        return 0
    except Exception as error:  # noqa: BLE001 -- top-level fail-closed service boundary
        last_error = type(error).__name__
        publish("STOPPED_FAIL_CLOSED")
        return 1
    finally:
        if source is not None:
            source.close()


if __name__ == "__main__":
    raise SystemExit(run())
