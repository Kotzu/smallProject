from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import re
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

from perfect_assassin.contract_validation import ContractValidator


class CaptureTargetIdentityError(RuntimeError):
    pass


class ProcessImageQueryUnavailableError(CaptureTargetIdentityError):
    pass


_FrameT = TypeVar("_FrameT")
SCREEN_CAPTURE_READ_ONLY = "SCREEN_CAPTURE_READ_ONLY"
VISIBLE_COORDINATE_HUD_READ_ONLY = "VISIBLE_COORDINATE_HUD_READ_ONLY"
VISIBLE_COMBAT_HUD_READ_ONLY = "VISIBLE_COMBAT_HUD_READ_ONLY"
READ_ONLY_CAPTURE_CAPABILITIES = frozenset(
    {
        SCREEN_CAPTURE_READ_ONLY,
        VISIBLE_COORDINATE_HUD_READ_ONLY,
        VISIBLE_COMBAT_HUD_READ_ONLY,
    }
)
MAX_AUTHORIZATION_BYTES = 1024 * 1024
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
ERROR_ACCESS_DENIED = 5
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF
FILETIME_TICKS_PER_SECOND = 10_000_000
FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
_PROCESS_CREATED_UTC = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"\.(?P<fraction>[0-9]{7})Z$"
)


def _read_bounded_file_snapshot(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> bytes:
    """Read one immutable bounded snapshot from one opened file handle."""

    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        raise CaptureTargetIdentityError(f"{label} byte bound is invalid")
    try:
        with path.open("rb") as stream:
            raw = stream.read(maximum_bytes + 1)
    except OSError as error:
        raise CaptureTargetIdentityError(f"{label} cannot be loaded") from error
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum_bytes:
        raise CaptureTargetIdentityError(f"{label} exceeds its exact byte bound")
    return raw


def _strict_json_object(
    raw: bytes,
    *,
    label: str,
    maximum_bytes: int,
) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum_bytes:
        raise CaptureTargetIdentityError(f"{label} exceeds its exact byte bound")

    def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CaptureTargetIdentityError(
                    f"{label} contains a duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    def reject_non_finite_constant(token: str) -> None:
        raise CaptureTargetIdentityError(
            f"{label} contains a non-finite JSON constant: {token}"
        )

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_non_finite_constant,
        )
    except CaptureTargetIdentityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise CaptureTargetIdentityError(f"{label} is not strict UTF-8 JSON") from error
    if type(value) is not dict:
        raise CaptureTargetIdentityError(f"{label} root must be an object")

    def reject_nested_non_finite(node: Any, path: str = "<root>") -> None:
        if isinstance(node, float) and not math.isfinite(node):
            raise CaptureTargetIdentityError(
                f"{label} contains a non-finite JSON number at {path}"
            )
        if isinstance(node, dict):
            for key, child in node.items():
                reject_nested_non_finite(
                    child,
                    str(key) if path == "<root>" else f"{path}.{key}",
                )
        elif isinstance(node, list):
            for index, child in enumerate(node):
                reject_nested_non_finite(child, f"{path}[{index}]")

    reject_nested_non_finite(value)
    return value


def _authorization_rollover_semantic_sha256(record: dict[str, Any]) -> str:
    """Match the operator's canonical hash while excluding temporal rollover fields."""

    projection = dict(record)
    approval = projection.get("approval")
    if type(approval) is not dict:
        raise CaptureTargetIdentityError(
            "authorization semantic hash requires a bounded approval"
        )
    stable_approval = dict(approval)
    for field in (
        "recorded_at",
        "expires_at",
        "renews_authorization_sha256",
        "renewal_scope",
    ):
        stable_approval.pop(field, None)
    projection["approval"] = stable_approval
    try:
        canonical = json.dumps(
            projection,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CaptureTargetIdentityError(
            "authorization cannot be represented canonically"
        ) from error
    return hashlib.sha256(canonical).hexdigest().upper()


def _filetime_to_process_created_at_utc(filetime_ticks: int) -> str:
    if type(filetime_ticks) is not int or filetime_ticks < 0:
        raise CaptureTargetIdentityError("process creation FILETIME is invalid")
    seconds, fractional_ticks = divmod(filetime_ticks, FILETIME_TICKS_PER_SECOND)
    try:
        created_at = FILETIME_EPOCH + timedelta(seconds=seconds)
    except OverflowError as error:
        raise CaptureTargetIdentityError(
            "process creation FILETIME is outside the supported UTC range"
        ) from error
    return (
        f"{created_at.year:04d}-{created_at.month:02d}-{created_at.day:02d}"
        f"T{created_at.hour:02d}:{created_at.minute:02d}:{created_at.second:02d}"
        f".{fractional_ticks:07d}Z"
    )


def _process_created_at_utc_to_filetime(value: str) -> int:
    if type(value) is not str:
        raise CaptureTargetIdentityError(
            "receipt process_created_at_utc must be canonical UTC"
        )
    match = _PROCESS_CREATED_UTC.fullmatch(value)
    if match is None:
        raise CaptureTargetIdentityError(
            "receipt process_created_at_utc must use seven-digit canonical UTC"
        )
    try:
        whole_second = datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second")),
            tzinfo=timezone.utc,
        )
    except ValueError as error:
        raise CaptureTargetIdentityError(
            "receipt process_created_at_utc is not a valid UTC timestamp"
        ) from error
    if whole_second < FILETIME_EPOCH:
        raise CaptureTargetIdentityError(
            "receipt process_created_at_utc predates the Windows FILETIME epoch"
        )
    delta = whole_second - FILETIME_EPOCH
    whole_seconds = delta.days * 86400 + delta.seconds
    return (
        whole_seconds * FILETIME_TICKS_PER_SECOND
        + int(match.group("fraction"))
    )


@dataclass(frozen=True, slots=True)
class RunningProcessIdentityMetadata:
    pid: int
    executable_path: Path
    process_created_at_utc: str
    process_creation_filetime_utc: str
    windows_session_id: int

    def __post_init__(self) -> None:
        if type(self.pid) is not int or self.pid <= 0:
            raise CaptureTargetIdentityError(
                "running process metadata PID must be a positive integer"
            )
        if not isinstance(self.executable_path, Path):
            raise CaptureTargetIdentityError(
                "running process metadata executable path is invalid"
            )
        if (
            type(self.process_creation_filetime_utc) is not str
            or re.fullmatch(
                r"[0-9]{17,20}", self.process_creation_filetime_utc
            )
            is None
        ):
            raise CaptureTargetIdentityError(
                "running process creation FILETIME is invalid"
            )
        filetime_ticks = int(self.process_creation_filetime_utc)
        if (
            _process_created_at_utc_to_filetime(self.process_created_at_utc)
            != filetime_ticks
            or _filetime_to_process_created_at_utc(filetime_ticks)
            != self.process_created_at_utc
        ):
            raise CaptureTargetIdentityError(
                "running process creation UTC and FILETIME identities disagree"
            )
        if (
            type(self.windows_session_id) is not int
            or not 0 <= self.windows_session_id <= 0xFFFFFFFF
        ):
            raise CaptureTargetIdentityError(
                "running process Windows session identity is invalid"
            )


class _WtsProcessInfo(ctypes.Structure):
    _fields_ = (
        ("session_id", wintypes.DWORD),
        ("process_id", wintypes.DWORD),
        ("process_name", wintypes.LPWSTR),
        ("user_sid", wintypes.LPVOID),
    )


@dataclass(frozen=True, slots=True)
class CaptureTargetIdentity:
    authorization_id: str
    target_profile: str
    permitted_capabilities: tuple[str, ...]
    instance_id: str
    actor_role: str
    actor_id: str
    decision_context: str
    memory_namespace: str
    expected_character_name: str
    credential_alias: str
    binding_assurance_state: str
    binding_assurance_evidence_refs: tuple[str, ...]
    client_build: str
    build_signature: str
    executable_sha256: str
    authorization_sha256: str
    environment_scope: str
    server_kind: str
    expected_realm_fingerprint: str
    realmlist_relative_path: str | None
    realmlist_sha256: str | None
    realmlist_directive: str | None
    expected_realm_routing_sha256: str | None
    max_session_minutes: int
    authorization_expires_at: str | None
    authorization_recorded_at: str
    authorization_semantic_sha256: str

    def __post_init__(self) -> None:
        expected_context = {
            "champion_journey": "champion",
            "lab_clone": "lab_clone",
        }.get(self.actor_role)
        if expected_context is None or self.decision_context != expected_context:
            raise CaptureTargetIdentityError(
                "capture target actor role and decision context are inconsistent"
            )
        expected_namespace_prefix = (
            "memory:champion:"
            if self.actor_role == "champion_journey"
            else "memory:lab:"
        )
        if not self.memory_namespace.startswith(expected_namespace_prefix):
            raise CaptureTargetIdentityError(
                "capture target memory namespace does not match actor role"
            )
        if any(
            not value
            for value in (
                self.instance_id,
                self.actor_id,
                self.memory_namespace,
                self.expected_character_name,
                self.credential_alias,
            )
        ):
            raise CaptureTargetIdentityError(
                "capture target actor binding fields must not be empty"
            )
        if (
            self.binding_assurance_state != "configured_expected_only"
            or not self.binding_assurance_evidence_refs
            or len(self.binding_assurance_evidence_refs) > 4
            or len(set(self.binding_assurance_evidence_refs))
            != len(self.binding_assurance_evidence_refs)
            or any(
                not isinstance(reference, str)
                or not reference
                or len(reference) > 256
                for reference in self.binding_assurance_evidence_refs
            )
        ):
            raise CaptureTargetIdentityError(
                "capture target actor binding assurance must remain configured-only"
            )
        if (
            not self.permitted_capabilities
            or len(set(self.permitted_capabilities)) != len(self.permitted_capabilities)
            or any(
                capability not in READ_ONLY_CAPTURE_CAPABILITIES
                for capability in self.permitted_capabilities
            )
        ):
            raise CaptureTargetIdentityError(
                "capture target must carry bounded read-only capabilities"
            )
        if (
            type(self.authorization_sha256) is not str
            or len(self.authorization_sha256) != 64
            or any(
                character not in "0123456789ABCDEF"
                for character in self.authorization_sha256
            )
        ):
            raise CaptureTargetIdentityError(
                "capture target authorization SHA-256 is invalid"
            )
        if (
            type(self.authorization_semantic_sha256) is not str
            or len(self.authorization_semantic_sha256) != 64
            or any(
                character not in "0123456789ABCDEF"
                for character in self.authorization_semantic_sha256
            )
        ):
            raise CaptureTargetIdentityError(
                "capture target authorization semantic SHA-256 is invalid"
            )
        if (
            type(self.max_session_minutes) is not int
            or not 1 <= self.max_session_minutes <= 60
            or type(self.authorization_recorded_at) is not str
        ):
            raise CaptureTargetIdentityError(
                "capture target authorization approval window is invalid"
            )
        recorded_at = _parse_utc_timestamp(
            self.authorization_recorded_at,
            "authorization recorded_at",
        )
        if self.authorization_expires_at is not None:
            if type(self.authorization_expires_at) is not str:
                raise CaptureTargetIdentityError(
                    "capture target authorization expiry is invalid"
                )
            expires_at = _parse_utc_timestamp(
                self.authorization_expires_at,
                "authorization expires_at",
            )
            if expires_at <= recorded_at:
                raise CaptureTargetIdentityError(
                    "capture target authorization approval window is inverted"
                )

    @property
    def evidence_ref(self) -> str:
        return f"authorization:{self.authorization_id}"

    @property
    def actor_evidence_ref(self) -> str:
        return f"actor-binding:{self.actor_id}@{self.instance_id}"


def validate_actor_binding_set(identities: Iterable[CaptureTargetIdentity]) -> None:
    """Reject instance collisions and cross-clone memory namespace sharing."""

    instance_owners: dict[str, tuple[str, str]] = {}
    lab_namespace_owners: dict[str, tuple[str, str]] = {}
    for identity in identities:
        owner = (identity.actor_id, identity.authorization_id)
        previous_instance_owner = instance_owners.setdefault(identity.instance_id, owner)
        if previous_instance_owner != owner:
            raise CaptureTargetIdentityError(
                "distinct actor authorizations cannot share an instance_id"
            )
        if identity.actor_role != "lab_clone":
            continue
        clone_owner = (identity.actor_id, identity.instance_id)
        previous_namespace_owner = lab_namespace_owners.setdefault(
            identity.memory_namespace,
            clone_owner,
        )
        if previous_namespace_owner != clone_owner:
            raise CaptureTargetIdentityError(
                "distinct LAB clones cannot share a memory namespace"
            )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _open_process_identity_handle(
    open_process: Callable[[int, bool, int], Any],
    get_last_error: Callable[[], int],
    pid: int,
) -> Any:
    """Open one metadata/liveness handle with the exact legacy fallback policy."""

    preferred_access = PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    handle = open_process(preferred_access, False, pid)
    if handle:
        return handle
    first_error = int(get_last_error())
    if first_error != ERROR_ACCESS_DENIED:
        raise ProcessImageQueryUnavailableError(
            f"cannot open PID {pid} for process-image identity (Win32 {first_error})"
        )

    legacy_access = PROCESS_QUERY_INFORMATION | SYNCHRONIZE
    handle = open_process(legacy_access, False, pid)
    if handle:
        return handle
    fallback_error = int(get_last_error())
    raise ProcessImageQueryUnavailableError(
        "cannot open PID "
        f"{pid} for legacy process-image identity (Win32 {fallback_error})"
    )


def _assert_process_handle_alive(
    wait_for_single_object: Callable[[Any, int], int],
    get_last_error: Callable[[], int],
    handle: Any,
    pid: int,
) -> None:
    result = int(wait_for_single_object(handle, 0))
    if result == WAIT_TIMEOUT:
        return
    if result == WAIT_OBJECT_0:
        raise ProcessImageQueryUnavailableError(f"PID {pid} is no longer running")
    if result == WAIT_FAILED:
        raise ProcessImageQueryUnavailableError(
            f"cannot query liveness for PID {pid} (Win32 {int(get_last_error())})"
        )
    raise ProcessImageQueryUnavailableError(
        f"cannot establish liveness for PID {pid} (wait result {result})"
    )


def _query_wts_process_session_id(pid: int) -> int:
    """Resolve a local process session from the documented WTS process snapshot."""

    wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
    enumerate_processes = wtsapi32.WTSEnumerateProcessesW
    enumerate_processes.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_WtsProcessInfo)),
        ctypes.POINTER(wintypes.DWORD),
    )
    enumerate_processes.restype = wintypes.BOOL
    free_memory = wtsapi32.WTSFreeMemory
    free_memory.argtypes = (wintypes.LPVOID,)
    free_memory.restype = None

    records = ctypes.POINTER(_WtsProcessInfo)()
    count = wintypes.DWORD()
    if not enumerate_processes(
        wintypes.HANDLE(),
        0,
        1,
        ctypes.byref(records),
        ctypes.byref(count),
    ):
        raise ProcessImageQueryUnavailableError(
            "cannot enumerate WTS process session metadata "
            f"(Win32 {int(ctypes.get_last_error())})"
        )
    try:
        if count.value > 1_000_000:
            raise ProcessImageQueryUnavailableError(
                "WTS process session metadata exceeds the bounded record count"
            )
        matches = [
            int(records[index].session_id)
            for index in range(int(count.value))
            if int(records[index].process_id) == pid
        ]
    finally:
        if records:
            free_memory(records)
    if len(matches) != 1:
        raise ProcessImageQueryUnavailableError(
            f"cannot resolve one exact WTS session for PID {pid}"
        )
    return matches[0]


def query_process_identity_metadata(pid: int) -> RunningProcessIdentityMetadata:
    """Resolve path, creation identity, session and liveness without VM rights."""

    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise CaptureTargetIdentityError("process PID must be a positive integer")
    if os.name != "nt":
        raise CaptureTargetIdentityError(
            "running process image identity is available only on Windows"
        )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    query_image = kernel32.QueryFullProcessImageNameW
    query_image.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    query_image.restype = wintypes.BOOL
    get_process_times = kernel32.GetProcessTimes
    get_process_times.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    get_process_times.restype = wintypes.BOOL
    process_id_to_session_id = kernel32.ProcessIdToSessionId
    process_id_to_session_id.argtypes = (
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    process_id_to_session_id.restype = wintypes.BOOL
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    wait_for_single_object.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = _open_process_identity_handle(
        open_process,
        ctypes.get_last_error,
        pid,
    )
    try:
        _assert_process_handle_alive(
            wait_for_single_object,
            ctypes.get_last_error,
            handle,
            pid,
        )
        capacity = 32768
        buffer = ctypes.create_unicode_buffer(capacity)
        size = wintypes.DWORD(capacity)
        if not query_image(handle, 0, buffer, ctypes.byref(size)):
            raise ProcessImageQueryUnavailableError(
                "cannot query executable path for PID "
                f"{pid} (Win32 {int(ctypes.get_last_error())})"
            )
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not get_process_times(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            raise ProcessImageQueryUnavailableError(
                "cannot query creation time for PID "
                f"{pid} (Win32 {int(ctypes.get_last_error())})"
            )
        session_id = wintypes.DWORD()
        if not process_id_to_session_id(pid, ctypes.byref(session_id)):
            session_error = int(ctypes.get_last_error())
            if session_error != ERROR_ACCESS_DENIED:
                raise ProcessImageQueryUnavailableError(
                    "cannot query Windows session for PID "
                    f"{pid} (Win32 {session_error})"
                )
            session_id = wintypes.DWORD(_query_wts_process_session_id(pid))
        _assert_process_handle_alive(
            wait_for_single_object,
            ctypes.get_last_error,
            handle,
            pid,
        )
        creation_ticks = (
            int(creation.dwHighDateTime) << 32
        ) | int(creation.dwLowDateTime)
        creation_ticks_text = str(creation_ticks)
        return RunningProcessIdentityMetadata(
            pid=pid,
            executable_path=Path(buffer.value),
            process_created_at_utc=_filetime_to_process_created_at_utc(
                creation_ticks
            ),
            process_creation_filetime_utc=creation_ticks_text,
            windows_session_id=int(session_id.value),
        )
    finally:
        close_handle(handle)


def query_process_image_path(pid: int) -> Path:
    """Resolve a live PID's executable without reading process memory."""

    return query_process_identity_metadata(pid).executable_path


def query_current_windows_session_id() -> int:
    """Resolve the capture sidecar's own Windows session without process access."""

    if os.name != "nt":
        raise CaptureTargetIdentityError(
            "current Windows session identity is available only on Windows"
        )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process_id_to_session_id = kernel32.ProcessIdToSessionId
    process_id_to_session_id.argtypes = (
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    process_id_to_session_id.restype = wintypes.BOOL
    session_id = wintypes.DWORD()
    if not process_id_to_session_id(os.getpid(), ctypes.byref(session_id)):
        raise CaptureTargetIdentityError(
            "cannot query the capture sidecar Windows session "
            f"(Win32 {int(ctypes.get_last_error())})"
        )
    return int(session_id.value)


def verify_running_process_identity(
    pid: int,
    expected_executable: Path,
    identity: CaptureTargetIdentity,
    *,
    process_path_resolver=query_process_image_path,
) -> Path:
    """Bind a selected PID to the exact allowlisted executable file and hash."""

    try:
        expected_path = expected_executable.resolve(strict=True)
        process_path = Path(process_path_resolver(pid)).resolve(strict=True)
    except OSError as error:
        raise CaptureTargetIdentityError(
            "cannot resolve expected or running process executable"
        ) from error
    if os.path.normcase(str(process_path)) != os.path.normcase(str(expected_path)):
        raise CaptureTargetIdentityError(
            "selected PID does not run the allowlisted client executable"
        )
    try:
        same_file = os.path.samefile(process_path, expected_path)
    except OSError as error:
        raise CaptureTargetIdentityError(
            "cannot compare running process executable identity"
        ) from error
    if not same_file:
        raise CaptureTargetIdentityError(
            "selected PID does not run the allowlisted client executable"
        )
    actual_hash = sha256_file(process_path)
    if actual_hash != identity.executable_sha256:
        raise CaptureTargetIdentityError(
            "running process executable SHA-256 does not match authorization"
        )
    return process_path


def run_process_bound_capture(
    capture_frame: Callable[[], _FrameT],
    verify_identity: Callable[[], object],
) -> _FrameT:
    """Capture one frame between two exact running-process identity checks."""

    verify_identity()
    try:
        return capture_frame()
    finally:
        verify_identity()


def _parse_utc_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CaptureTargetIdentityError(
            f"launch receipt {field} is not a valid timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise CaptureTargetIdentityError(
            f"launch receipt {field} must include a timezone"
        )
    return parsed.astimezone(timezone.utc)


def _verify_exact_emulator_realmlist(
    expected_executable: Path,
    identity: CaptureTargetIdentity,
) -> Path:
    relative_path = identity.realmlist_relative_path
    directive = identity.realmlist_directive
    expected_hash = identity.realmlist_sha256
    if not relative_path or not directive or not expected_hash:
        raise CaptureTargetIdentityError(
            "emulator authorization does not pin an exact client realmlist"
        )
    configured_relative_path = Path(relative_path)
    if configured_relative_path.is_absolute() or ".." in configured_relative_path.parts:
        raise CaptureTargetIdentityError(
            "emulator realmlist path must be relative to the exact client root"
        )
    try:
        client_root = expected_executable.resolve(strict=True).parent
        realmlist_path = (client_root / configured_relative_path).resolve(strict=True)
    except OSError as error:
        raise CaptureTargetIdentityError(
            "cannot resolve the receipt-bound emulator realmlist"
        ) from error
    try:
        realmlist_path.relative_to(client_root)
    except ValueError as error:
        raise CaptureTargetIdentityError(
            "receipt-bound emulator realmlist path is outside the exact client root"
        ) from error
    try:
        actual_bytes = realmlist_path.read_bytes()
    except OSError as error:
        raise CaptureTargetIdentityError(
            "cannot inspect the receipt-bound emulator realmlist"
        ) from error
    canonical_bytes = directive.encode("utf-8")
    if actual_bytes != canonical_bytes:
        raise CaptureTargetIdentityError(
            "emulator realmlist differs from the exact authorized directive"
        )
    if sha256_file(realmlist_path) != expected_hash:
        raise CaptureTargetIdentityError(
            "emulator realmlist SHA-256 does not match authorization"
        )
    return realmlist_path


def verify_lab_launch_receipt(
    receipt_path: Path,
    receipt_schema_path: Path,
    *,
    pid: int,
    hwnd: int,
    expected_executable: Path,
    identity: CaptureTargetIdentity,
    expected_title: str,
    expected_class: str,
    window_resolver: Callable[[], Any],
    process_metadata_resolver: Callable[
        [int], RunningProcessIdentityMetadata
    ] = query_process_identity_metadata,
    current_session_id_resolver: Callable[[], int] = query_current_windows_session_id,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Path:
    """Validate the operator-created identity receipt for one LAB clone only."""

    if identity.decision_context != "lab_clone":
        raise CaptureTargetIdentityError(
            "launch receipt fallback is forbidden outside LAB clone context"
        )
    if identity.environment_scope != "emulator_local" or identity.server_kind != "emulator":
        raise CaptureTargetIdentityError(
            "launch receipt fallback requires an exact local emulator authorization"
        )
    if (
        identity.realmlist_relative_path is None
        or identity.realmlist_sha256 is None
        or identity.realmlist_directive is None
    ):
        raise CaptureTargetIdentityError(
            "launch receipt fallback requires an exact LAB realmlist authorization"
        )
    if (
        hwnd <= 0
        or expected_title != "World of Warcraft"
        or expected_class != "GxWindowClassD3d"
    ):
        raise CaptureTargetIdentityError(
            "launch receipt fallback requires exact PID/HWND/title/class"
        )
    receipt_bytes = _read_bounded_file_snapshot(
        receipt_path,
        label="LAB launch receipt",
        maximum_bytes=65536,
    )
    receipt = _strict_json_object(
        receipt_bytes,
        label="LAB launch receipt",
        maximum_bytes=65536,
    )
    ContractValidator(receipt_schema_path).validate(receipt)

    current = now()
    if current.tzinfo is None:
        raise CaptureTargetIdentityError("receipt verifier clock must include a timezone")
    current = current.astimezone(timezone.utc)
    created_at = _parse_utc_timestamp(str(receipt["created_at"]), "created_at")
    expires_at = _parse_utc_timestamp(str(receipt["expires_at"]), "expires_at")
    realm_verified_at = _parse_utc_timestamp(
        str(receipt["realm_assurance"]["verified_at"]),
        "realm_assurance.verified_at",
    )
    if created_at > current or expires_at <= current or expires_at <= created_at:
        raise CaptureTargetIdentityError("LAB launch receipt is not currently valid")
    if realm_verified_at < created_at or realm_verified_at > current:
        raise CaptureTargetIdentityError(
            "LAB launch receipt realm assurance is outside its validation window"
        )
    maximum_duration_s = identity.max_session_minutes * 60
    if (expires_at - created_at).total_seconds() > maximum_duration_s:
        raise CaptureTargetIdentityError(
            "LAB launch receipt exceeds the authorized session duration"
        )
    if identity.authorization_expires_at is not None:
        authorization_expiry = _parse_utc_timestamp(
            identity.authorization_expires_at,
            "authorization expires_at",
        )
        if expires_at > authorization_expiry:
            raise CaptureTargetIdentityError(
                "LAB launch receipt exceeds authorization expiry"
            )
    authorization_recorded_at = _parse_utc_timestamp(
        identity.authorization_recorded_at,
        "authorization recorded_at",
    )
    if created_at < authorization_recorded_at:
        raise CaptureTargetIdentityError(
            "LAB launch receipt predates the active authorization"
        )

    if receipt["identity_origin"] != "operator_launch" or any(
        receipt[field] is not None
        for field in (
            "parent_receipt_nonce",
            "parent_receipt_sha256",
            "parent_authorization_sha256",
        )
    ):
        raise CaptureTargetIdentityError(
            "LAB capture fallback cannot verify adopted or renewed receipt lineage"
        )

    metadata_before = process_metadata_resolver(pid)
    if type(metadata_before) is not RunningProcessIdentityMetadata:
        raise CaptureTargetIdentityError(
            "running process metadata resolver returned an invalid snapshot"
        )
    if metadata_before.pid != pid:
        raise CaptureTargetIdentityError(
            "running process metadata PID does not match the selected target"
        )
    current_session_id = current_session_id_resolver()
    if (
        type(current_session_id) is not int
        or not 0 <= current_session_id <= 0xFFFFFFFF
        or metadata_before.windows_session_id != current_session_id
    ):
        raise CaptureTargetIdentityError(
            "receipt-bound process is outside the capture sidecar Windows session"
        )
    process_created_at = _parse_utc_timestamp(
        metadata_before.process_created_at_utc,
        "process_created_at_utc",
    )
    if process_created_at > created_at:
        raise CaptureTargetIdentityError(
            "LAB launch receipt predates the running process identity"
        )

    expected_fields = {
        "pid": pid,
        "hwnd": f"0x{hwnd:X}",
        "window_title": expected_title,
        "window_class": expected_class,
        "executable_sha256": identity.executable_sha256,
        "client_build": identity.client_build,
        "build_signature": identity.build_signature,
        "target_profile": identity.target_profile,
        "authorization_id": identity.authorization_id,
        "authorization_sha256": identity.authorization_sha256,
        "authorization_semantic_sha256": identity.authorization_semantic_sha256,
        "process_created_at_utc": metadata_before.process_created_at_utc,
        "process_creation_filetime_utc": (
            metadata_before.process_creation_filetime_utc
        ),
        "windows_session_id": metadata_before.windows_session_id,
        "identity_origin": "operator_launch",
        "parent_receipt_nonce": None,
        "parent_receipt_sha256": None,
        "parent_authorization_sha256": None,
        "actor_binding": {
            "schema_version": "1.0",
            "instance_id": identity.instance_id,
            "actor_role": identity.actor_role,
            "actor_id": identity.actor_id,
            "decision_context": identity.decision_context,
            "memory_namespace": identity.memory_namespace,
            "expected_character_name": identity.expected_character_name,
            "credential_alias": identity.credential_alias,
            "binding_assurance": {
                "state": identity.binding_assurance_state,
                "evidence_refs": list(identity.binding_assurance_evidence_refs),
            },
        },
        "decision_context": identity.decision_context,
        "environment_scope": identity.environment_scope,
        "server_kind": identity.server_kind,
        "expected_realm_fingerprint": identity.expected_realm_fingerprint,
        "realmlist_relative_path": identity.realmlist_relative_path,
        "realmlist_sha256": identity.realmlist_sha256,
        "realmlist_directive": identity.realmlist_directive,
        "realm_routing_sha256": identity.expected_realm_routing_sha256,
    }
    for field, expected in expected_fields.items():
        if receipt.get(field) != expected:
            raise CaptureTargetIdentityError(
                f"LAB launch receipt {field} does not match the active target"
            )

    try:
        expected_path = expected_executable.resolve(strict=True)
        receipt_executable = Path(str(receipt["executable_path"])).resolve(strict=True)
        metadata_executable = metadata_before.executable_path.resolve(strict=True)
    except OSError as error:
        raise CaptureTargetIdentityError(
            "cannot resolve the receipt-bound client executable"
        ) from error
    if os.path.normcase(str(receipt_executable)) != os.path.normcase(str(expected_path)):
        raise CaptureTargetIdentityError(
            "LAB launch receipt executable path does not match the configured client"
        )
    if os.path.normcase(str(metadata_executable)) != os.path.normcase(str(expected_path)):
        raise CaptureTargetIdentityError(
            "running process metadata path does not match the configured client"
        )
    try:
        if not (
            os.path.samefile(receipt_executable, expected_path)
            and os.path.samefile(metadata_executable, expected_path)
        ):
            raise CaptureTargetIdentityError(
                "LAB launch receipt executable is not the configured client file"
            )
    except OSError as error:
        raise CaptureTargetIdentityError(
            "cannot compare the receipt-bound client executable"
        ) from error
    if sha256_file(expected_path) != identity.executable_sha256:
        raise CaptureTargetIdentityError(
            "receipt-bound client executable changed after launch"
        )
    _verify_exact_emulator_realmlist(expected_path, identity)

    window = window_resolver()
    window_fields = {
        "pid": pid,
        "hwnd": hwnd,
        "title": expected_title,
        "class_name": expected_class,
        "visible": True,
        "minimized": False,
        "foreground": True,
    }
    for field, expected in window_fields.items():
        if getattr(window, field, None) != expected:
            raise CaptureTargetIdentityError(
                f"receipt-bound window {field} changed or is unavailable"
            )
    metadata_after = process_metadata_resolver(pid)
    if (
        type(metadata_after) is not RunningProcessIdentityMetadata
        or metadata_after != metadata_before
    ):
        raise CaptureTargetIdentityError(
            "running process native identity changed during receipt verification"
        )
    return expected_path


def verify_capture_process_identity(
    pid: int,
    expected_executable: Path,
    identity: CaptureTargetIdentity,
    *,
    hwnd: int | None,
    expected_title: str | None,
    expected_class: str | None,
    receipt_path: Path,
    receipt_schema_path: Path,
    window_resolver: Callable[[], Any],
    process_path_resolver=query_process_image_path,
    process_metadata_resolver: Callable[
        [int], RunningProcessIdentityMetadata
    ] = query_process_identity_metadata,
    current_session_id_resolver: Callable[[], int] = query_current_windows_session_id,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Path:
    """Use direct image identity, or the narrow LAB receipt on query denial."""

    try:
        resolved = verify_running_process_identity(
            pid,
            expected_executable,
            identity,
            process_path_resolver=process_path_resolver,
        )
        if (
            identity.environment_scope
            in {"emulator_local", "emulator_lan", "emulator_remote"}
            and identity.server_kind == "emulator"
        ):
            _verify_exact_emulator_realmlist(resolved, identity)
        return resolved
    except ProcessImageQueryUnavailableError as error:
        if identity.decision_context != "lab_clone":
            raise CaptureTargetIdentityError(
                "process-image query failed and receipt fallback is forbidden for Champion"
            ) from error
        if hwnd is None or expected_title is None or expected_class is None:
            raise CaptureTargetIdentityError(
                "LAB receipt fallback requires exact window identity"
            ) from error
        return verify_lab_launch_receipt(
            receipt_path,
            receipt_schema_path,
            pid=pid,
            hwnd=hwnd,
            expected_executable=expected_executable,
            identity=identity,
            expected_title=expected_title,
            expected_class=expected_class,
            window_resolver=window_resolver,
            process_metadata_resolver=process_metadata_resolver,
            current_session_id_resolver=current_session_id_resolver,
            now=now,
        )


def load_capture_target_identity(
    authorization_path: Path,
    authorization_schema_path: Path,
    client_executable: Path,
    client_build: str,
    *,
    required_capabilities: Iterable[str],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> CaptureTargetIdentity:
    authorization_bytes = _read_bounded_file_snapshot(
        authorization_path,
        label="capture authorization",
        maximum_bytes=MAX_AUTHORIZATION_BYTES,
    )
    authorization = _strict_json_object(
        authorization_bytes,
        label="capture authorization",
        maximum_bytes=MAX_AUTHORIZATION_BYTES,
    )
    authorization_sha256 = hashlib.sha256(authorization_bytes).hexdigest().upper()
    ContractValidator(authorization_schema_path).validate(authorization)
    if authorization.get("status") != "approved_bounded":
        raise CaptureTargetIdentityError(
            "capture requires an approved_bounded authorization"
        )
    if isinstance(required_capabilities, (str, bytes)):
        raise CaptureTargetIdentityError(
            "required capture capabilities must be an explicit collection"
        )
    required = tuple(required_capabilities)
    if (
        not required
        or len(set(required)) != len(required)
        or any(capability not in READ_ONLY_CAPTURE_CAPABILITIES for capability in required)
    ):
        raise CaptureTargetIdentityError(
            "required capture capabilities are empty, duplicated or unknown"
        )
    permitted_capabilities = authorization.get("permitted_capabilities")
    if not isinstance(permitted_capabilities, list) or not permitted_capabilities:
        raise CaptureTargetIdentityError(
            "capture authorization has no read-only capability"
        )
    missing_capabilities = [
        capability
        for capability in required
        if capability not in permitted_capabilities
    ]
    if missing_capabilities:
        raise CaptureTargetIdentityError(
            "capture authorization is missing required read-only capability: "
            + ", ".join(missing_capabilities)
        )
    approval = authorization.get("approval")
    if not isinstance(approval, dict):
        raise CaptureTargetIdentityError("authorization has no bounded approval")
    authorization_semantic_sha256 = _authorization_rollover_semantic_sha256(
        authorization
    )
    current = now()
    if current.tzinfo is None:
        raise CaptureTargetIdentityError(
            "authorization verifier clock must include a timezone"
        )
    current = current.astimezone(timezone.utc)
    recorded_at = _parse_utc_timestamp(
        str(approval["recorded_at"]),
        "approval.recorded_at",
    )
    if recorded_at > current:
        raise CaptureTargetIdentityError("capture authorization is not active yet")
    max_session_minutes = approval.get("max_session_minutes")
    if (
        type(max_session_minutes) is not int
        or not 1 <= max_session_minutes <= 60
    ):
        raise CaptureTargetIdentityError(
            "authorization max_session_minutes is outside the bounded range"
        )
    try:
        policy_expires_at = recorded_at + timedelta(minutes=max_session_minutes)
    except OverflowError as error:
        raise CaptureTargetIdentityError(
            "authorization approval window cannot be represented safely"
        ) from error
    if "expires_at" in approval:
        expires_at = _parse_utc_timestamp(
            str(approval["expires_at"]),
            "approval.expires_at",
        )
        if expires_at > policy_expires_at:
            raise CaptureTargetIdentityError(
                "capture authorization expiry exceeds max_session_minutes"
            )
        if expires_at <= recorded_at or expires_at <= current:
            raise CaptureTargetIdentityError("capture authorization has expired")
    else:
        expires_at = policy_expires_at
        if expires_at <= current:
            raise CaptureTargetIdentityError("capture authorization has expired")
    client_match = authorization.get("client_match")
    if not isinstance(client_match, dict):
        raise CaptureTargetIdentityError("authorization has no pinned client identity")
    configured_build = str(client_match["client_build"])
    configured_signature = str(client_match["build_signature"])
    if client_build != configured_build:
        raise CaptureTargetIdentityError(
            "requested client build does not exactly match authorization"
        )
    actual_hash = sha256_file(client_executable)
    expected_hash = str(client_match["executable_sha256"]).upper()
    if actual_hash != expected_hash:
        raise CaptureTargetIdentityError(
            "client executable SHA-256 does not match authorization"
        )
    realm_match = authorization.get("realm_match")
    actor_binding = authorization.get("actor_binding")
    if (
        not isinstance(approval, dict)
        or not isinstance(realm_match, dict)
        or not isinstance(actor_binding, dict)
    ):
        raise CaptureTargetIdentityError(
            "authorization has no bounded actor, approval or realm identity"
        )
    actor_role = str(actor_binding["actor_role"])
    decision_context = str(actor_binding["decision_context"])
    binding_assurance = actor_binding["binding_assurance"]
    expected_context = {
        "champion_journey": "champion",
        "lab_clone": "lab_clone",
    }.get(actor_role)
    if expected_context is None or decision_context != expected_context:
        raise CaptureTargetIdentityError(
            "authorization actor role and decision context are inconsistent"
        )
    return CaptureTargetIdentity(
        authorization_id=str(authorization["authorization_id"]),
        target_profile=str(authorization["target_profile"]),
        # A capture identity carries only the read-only capabilities requested
        # for this operation. Other authorization capabilities (for example the
        # separately bounded fixed-UI LAB helper) never cross this boundary.
        permitted_capabilities=required,
        instance_id=str(actor_binding["instance_id"]),
        actor_role=actor_role,
        actor_id=str(actor_binding["actor_id"]),
        decision_context=decision_context,
        memory_namespace=str(actor_binding["memory_namespace"]),
        expected_character_name=str(actor_binding["expected_character_name"]),
        credential_alias=str(actor_binding["credential_alias"]),
        binding_assurance_state=str(binding_assurance["state"]),
        binding_assurance_evidence_refs=tuple(binding_assurance["evidence_refs"]),
        client_build=configured_build,
        build_signature=f"{configured_signature}:sha256:{actual_hash}",
        executable_sha256=actual_hash,
        authorization_sha256=authorization_sha256,
        environment_scope=str(authorization["environment_scope"]),
        server_kind=str(realm_match["server_kind"]),
        expected_realm_fingerprint=str(realm_match["expected_realm_fingerprint"]),
        realmlist_relative_path=(
            str(realm_match["realmlist_relative_path"])
            if "realmlist_relative_path" in realm_match
            else None
        ),
        realmlist_sha256=(
            str(realm_match["realmlist_sha256"]).upper()
            if "realmlist_sha256" in realm_match
            else None
        ),
        realmlist_directive=(
            str(realm_match["realmlist_directive"])
            if "realmlist_directive" in realm_match
            else None
        ),
        expected_realm_routing_sha256=(
            str(realm_match["expected_routing_sha256"]).upper()
            if "expected_routing_sha256" in realm_match
            else None
        ),
        max_session_minutes=max_session_minutes,
        authorization_expires_at=expires_at.isoformat(),
        authorization_recorded_at=recorded_at.isoformat(),
        authorization_semantic_sha256=authorization_semantic_sha256,
    )
