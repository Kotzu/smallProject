"""Dedicated, read-only persistent topology worker; caller owns freshness/map binding."""

from hashlib import sha256
import json
from math import hypot
from pathlib import Path
import subprocess

from client_navmesh_backend import nav_worker_creation_flags
from persistent_navmesh_awareness import PersistentNavmeshAwarenessService
from perfect_assassin.adapter.vertical_connection import parse_connection, point
from perfect_assassin.adapter.wmo_bundle import read_bounded


class VerticalContinuityService:
    # Reuse existing bounded pipe timeout/cleanup, but not its query protocol.
    _readline = PersistentNavmeshAwarenessService._readline
    close = PersistentNavmeshAwarenessService.close

    def __init__(self, *, worker, expected_sha256, nav_root, map_name, timeout_s=3):
        worker, nav_root = Path(worker).resolve(), Path(nav_root).resolve()
        if sha256(read_bounded(worker, 32*1024*1024)).hexdigest() != expected_sha256:
            raise ValueError("continuity worker hash mismatch")
        if not nav_root.is_dir() or not 0.1 <= timeout_s <= 10:
            raise ValueError("invalid continuity configuration")
        self._protocol_timeout_s = timeout_s
        self._sequence = 0
        self._process = subprocess.Popen(
            [str(worker), "--vertical-continuity-server", str(nav_root), map_name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1, creationflags=nav_worker_creation_flags())
        try:
            if json.loads(self._readline()) != {"status":"READY", "protocol":1, "mode":"VERTICAL_CONTINUITY"}:
                raise ValueError("invalid continuity handshake")
        except Exception:
            self.close()
            raise

    def query(self, *, start, stop):
        start, stop = point(start), point(stop)
        if hypot(start[0]-stop[0], start[1]-stop[1]) > 64:
            raise ValueError("transition outside bounded local scope")
        if self._process.poll() is not None:
            raise RuntimeError("continuity worker exited")
        self._sequence += 1
        try:
            values = " ".join(f"{v:.9f}" for v in (*start, *stop))
            self._process.stdin.write(f"{self._sequence} {values}\n")
            self._process.stdin.flush()
            line = self._readline()
            if len(line) > 8192:
                raise ValueError("continuity response exceeds budget")
            record = json.loads(line)
            return parse_connection(record, sequence=self._sequence, start=start, stop=stop)
        except Exception:
            # A failed/desynchronized stream is never reused as fresh evidence.
            self.close()
            raise
