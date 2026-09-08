import io
import json
import sys
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations/windows-input"))
import vertical_continuity_service as module
from test_vertical_connection import record


class Process:
    def __init__(self, lines):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("\n".join(lines) + "\n")
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.returncode = 0
        return 0


@pytest.fixture
def factory(tmp_path, monkeypatch):
    worker = tmp_path / "observer.exe"
    worker.write_bytes(b"fixture-only")
    calls = []

    def make(lines, expected=None):
        process = Process(lines)

        def launch(args, **kwargs):
            calls.append(args)
            return process

        monkeypatch.setattr(module.subprocess, "Popen", launch)
        service = module.VerticalContinuityService(
            worker=worker, expected_sha256=expected or sha256(b"fixture-only").hexdigest(),
            nav_root=tmp_path, map_name="Azeroth")
        return service, process

    return make, calls


READY = json.dumps({"status": "READY", "protocol": 1, "mode": "VERTICAL_CONTINUITY"})


def test_hash_rejected_before_launch(factory):
    make, calls = factory
    with pytest.raises(ValueError, match="hash mismatch"):
        make([READY], expected="0" * 64)
    assert calls == []


def test_persistent_queries_and_explicit_observation_mode(factory):
    make, calls = factory
    records = [dict(record(), sequence=i) for i in (1, 2)]
    service, process = make([READY, *(json.dumps(r) for r in records)])
    for i in (1, 2):
        result = service.query(start=(1, 2, 3), stop=(4, 5, 6))
        assert result["sequence"] == i
        assert result["execution_authority"] is False
    assert len(calls) == 1
    assert calls[0][1] == "--vertical-continuity-server"
    service.close()
    assert process.poll() == 0
    assert process.stdin.getvalue().endswith("QUIT\n")


@pytest.mark.parametrize("response", ["not json", json.dumps(record()), "x" * 8193])
def test_failed_stream_is_closed_not_reused(factory, response):
    make, _ = factory
    service, process = make([READY, response])
    with pytest.raises(ValueError):
        service.query(start=(1, 2, 3), stop=(4, 5, 6))
    assert process.poll() == 0
    with pytest.raises(RuntimeError, match="exited"):
        service.query(start=(1, 2, 3), stop=(4, 5, 6))


def test_out_of_scope_request_does_not_write(factory):
    make, _ = factory
    service, process = make([READY])
    with pytest.raises(ValueError, match="bounded local scope"):
        service.query(start=(0, 0, 0), stop=(65, 0, 0))
    assert process.stdin.getvalue() == ""
    service.close()
