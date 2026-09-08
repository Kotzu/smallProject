"""Single background-thread owner of optional continuity state and worker."""

from pathlib import Path
from time import monotonic

from perfect_assassin.adapter.vertical_transition import snapshot, compatible, compare
from vertical_continuity_service import VerticalContinuityService

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "data/runtime/native-build/pa-nav-continuity-observer/Debug/pa_nav_probe.exe"
SHA256 = "2b6448ce97c7be4f69784ec6663740d2d7d54fbd0cc063408e7552f2fb31ca64"


class VerticalTransitionObserver:
    def __init__(self, *, factory=VerticalContinuityService, clock=monotonic):
        self.factory, self.clock = factory, clock
        self.previous = self.service = self.binding = None
        self.retry_s = 0

    def close(self):
        if self.service is not None:
            self.service.close()
        self.service = self.previous = self.binding = None

    def observe(self, record, *, nav_root, map_name):
        try:
            current = snapshot(record)
            identity = (tuple(current["key"]), current["pack"], str(nav_root), map_name)
            if identity != self.binding:
                self.close()
                self.binding = identity
                self.retry_s = 0
            previous, self.previous = self.previous, current
            now = self.clock()
            if previous is None or not compatible(previous, current, now):
                record["vertical_transition_status"] = "WAITING"
                return
            if now < self.retry_s:
                record["vertical_transition_status"] = "UNAVAILABLE"
                return
            if self.service is None:
                self.service = self.factory(worker=WORKER, expected_sha256=SHA256,
                    nav_root=nav_root, map_name=map_name, timeout_s=1)
            record["vertical_transition"] = compare(previous, current, self.service.query, clock=self.clock)
            record["vertical_transition_status"] = "AVAILABLE"
        except Exception:  # Optional evidence never suppresses the base sonar.
            self.close()
            self.binding = identity if "identity" in locals() else None
            self.retry_s = self.clock() + 10
            record["vertical_transition_status"] = "UNAVAILABLE"
