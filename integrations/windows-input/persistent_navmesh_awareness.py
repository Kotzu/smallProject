from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import json
from math import hypot, isfinite
from pathlib import Path
import subprocess
import time
from queue import Empty, Queue
from threading import Thread
from typing import Any

from client_navmesh_backend import (
    ClientAssetNavmeshQuery,
    nav_worker_creation_flags,
)
from perfect_assassin.movement.client_navmesh import LocalStaticAwareness, NavPoint
from perfect_assassin.adapter.vertical_candidates import (
    VerticalSurfaceCandidates, parse_vertical_candidates,
)
from perfect_assassin.adapter.height_scan import HeightScan, parse_height_scan


@dataclass(frozen=True, slots=True)
class PersistentAwarenessSample:
    source: NavPoint
    resolved: NavPoint
    observed_monotonic_s: float
    awareness: LocalStaticAwareness
    vertical_candidates: VerticalSurfaceCandidates | None = None
    height_scan: HeightScan | None = None


def awareness_sample_from_server_response(
    response: object,
    *,
    expected_sequence: int,
    observed_monotonic_s: float,
) -> PersistentAwarenessSample:
    if not isinstance(response, dict):
        raise RuntimeError("awareness server response is not an object")
    if response.get("status") != "OK":
        raise RuntimeError("awareness server rejected the query")
    if response.get("sequence") != expected_sequence:
        raise RuntimeError("awareness server response sequence is invalid")
    source = ClientAssetNavmeshQuery._point(response.get("source"))
    resolved = ClientAssetNavmeshQuery._point(response.get("resolved"))
    awareness = ClientAssetNavmeshQuery._start_awareness(
        response.get("awareness")
    )
    observed = float(observed_monotonic_s)
    if not isfinite(observed):
        raise RuntimeError("awareness observation time is invalid")
    return PersistentAwarenessSample(
        source=source,
        resolved=resolved,
        observed_monotonic_s=observed,
        awareness=awareness,
        vertical_candidates=parse_vertical_candidates(response.get("vertical_candidates")),
        height_scan=parse_height_scan(response.get("height_scan"),
                                      expected_origin=(resolved.x, resolved.y, resolved.z)),
    )


class PersistentNavmeshAwarenessService:
    """Own exactly one native process and keep its client map loaded."""

    def __init__(self, *, worker: Path, nav_root: Path, map_name: str,
                 protocol_timeout_s: float | None = None, spatial_scan: bool = False) -> None:
        if type(spatial_scan) is not bool:
            raise ValueError("invalid spatial scan flag")
        self._spatial_scan = spatial_scan
        if protocol_timeout_s is not None and not 0.1 <= protocol_timeout_s <= 30:
            raise ValueError("invalid awareness protocol timeout")
        self._protocol_timeout_s = protocol_timeout_s
        worker = worker.resolve()
        nav_root = nav_root.resolve()
        if not worker.is_file():
            raise RuntimeError(f"awareness worker is missing: {worker}")
        if not nav_root.is_dir():
            raise RuntimeError(f"awareness nav root is missing: {nav_root}")
        self._sequence = 0
        self._process = subprocess.Popen(
            [str(worker), "--spatial-awareness-server" if spatial_scan else "--awareness-server",
             str(nav_root), map_name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            # Awareness is read-only background evidence.  Keep its long-lived
            # worker below the realtime capture/control clock on Windows so a
            # tile load cannot starve the visible pose loop.
            creationflags=nav_worker_creation_flags(),
        )
        assert self._process.stdout is not None
        try:
            ready = json.loads(self._readline())
        except (json.JSONDecodeError, OSError) as error:
            self.close()
            raise RuntimeError("awareness service did not start") from error
        if ready != {"status": "READY", "protocol": 1}:
            self.close()
            raise RuntimeError("awareness service handshake is invalid")

    @property
    def pid(self) -> int:
        return self._process.pid

    def _readline(self) -> str:
        if self._protocol_timeout_s is None:
            return self._process.stdout.readline()
        result = Queue(maxsize=1)
        def read():
            try:
                result.put(self._process.stdout.readline())
            except Exception as error:
                result.put(error)
        Thread(target=read, daemon=True).start()
        try:
            value = result.get(timeout=self._protocol_timeout_s)
        except Empty:
            self.close()
            raise RuntimeError("awareness response timed out") from None
        if isinstance(value, Exception):
            raise RuntimeError("awareness response read failed") from value
        return value

    @property
    def query_count(self) -> int:
        return self._sequence

    def sample(
        self, world_x: float, world_y: float, z_hint: float,
    ) -> PersistentAwarenessSample:
        if self._process.poll() is not None:
            raise RuntimeError("awareness service stopped unexpectedly")
        if any(
            not isfinite(value) or abs(value) > 100_000
            for value in (world_x, world_y, z_hint)
        ):
            raise RuntimeError("awareness request pose is invalid")
        self._sequence += 1
        sequence = self._sequence
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        try:
            self._process.stdin.write(
                f"{sequence} {world_x:.9f} {world_y:.9f} {z_hint:.9f}\n"
            )
            self._process.stdin.flush()
            response: Any = json.loads(self._readline())
        except (BrokenPipeError, json.JSONDecodeError, OSError) as error:
            raise RuntimeError("awareness service communication failed") from error
        if self._spatial_scan and (not isinstance(response, dict) or response.get("height_scan") is None):
            raise RuntimeError("requested height scan is missing from worker response")
        return awareness_sample_from_server_response(
            response,
            expected_sequence=sequence,
            observed_monotonic_s=time.monotonic(),
        )

    def close(self) -> None:
        process = getattr(self, "_process", None)
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.write("QUIT\n")
                process.stdin.flush()
            process.wait(timeout=2.0)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)


class AsyncPersistentNavmeshAwareness:
    """Event-driven local topology; stationary actors generate no queries."""

    def __init__(
        self,
        *,
        worker: Path,
        nav_root: Path,
        map_name: str,
        initial_z: float,
        movement_threshold_yards: float = 1.5,
        floor_threshold_yards: float = 0.5,
        validity_radius_yards: float = 3.0,
    ) -> None:
        if not isfinite(initial_z):
            raise ValueError("awareness initial floor must be finite")
        if not 0.5 <= movement_threshold_yards <= 3.0:
            raise ValueError("awareness movement threshold is invalid")
        if not 0.1 <= floor_threshold_yards <= 2.0:
            raise ValueError("awareness floor threshold is invalid")
        if not 1.0 <= validity_radius_yards <= 6.0:
            raise ValueError("awareness validity radius is invalid")
        self._service = PersistentNavmeshAwarenessService(
            worker=worker, nav_root=nav_root, map_name=map_name,
        )
        self._z_hint = float(initial_z)
        self._movement_threshold_yards = float(movement_threshold_yards)
        self._floor_threshold_yards = float(floor_threshold_yards)
        self._validity_radius_yards = float(validity_radius_yards)
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pa-nav-awareness",
        )
        self._future: Future[PersistentAwarenessSample] | None = None
        self._latest: PersistentAwarenessSample | None = None
        self._last_requested: tuple[float, float, float] | None = None
        self._retry_after_s = 0.0
        self.last_error: str | None = None

    def _needs_sample(self, world_x: float, world_y: float, z_hint: float) -> bool:
        if self._last_requested is None:
            return True
        previous_x, previous_y, previous_z = self._last_requested
        return (
            hypot(previous_x - world_x, previous_y - world_y)
            >= self._movement_threshold_yards
            or abs(previous_z - z_hint) >= self._floor_threshold_yards
        )

    def poll(
        self, *, world_x: float, world_y: float, now_s: float, z_hint: float,
    ) -> PersistentAwarenessSample | None:
        if isfinite(z_hint):
            self._z_hint = float(z_hint)
        if self._future is not None and self._future.done():
            try:
                self._latest = self._future.result()
                self._z_hint = self._latest.resolved.z
                self.last_error = None
            except Exception as error:
                self.last_error = f"{type(error).__name__}: {error}"
                self._retry_after_s = now_s + 2.0
            finally:
                self._future = None
        if (
            self._future is None
            and now_s >= self._retry_after_s
            and self._needs_sample(world_x, world_y, self._z_hint)
        ):
            self._last_requested = (float(world_x), float(world_y), self._z_hint)
            self._future = self._executor.submit(
                self._service.sample,
                float(world_x),
                float(world_y),
                self._z_hint,
            )
        latest = self._latest
        if (
            latest is None
            or latest.source.distance_2d(NavPoint(world_x, world_y, self._z_hint))
            > self._validity_radius_yards
        ):
            return None
        return latest

    @property
    def z_hint(self) -> float:
        return self._z_hint

    @property
    def service_pid(self) -> int:
        return self._service.pid

    @property
    def query_count(self) -> int:
        return self._service.query_count

    def close(self) -> None:
        if self._future is not None:
            try:
                self._future.result(timeout=5.0)
            except Exception:
                self._service.close()
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._service.close()
