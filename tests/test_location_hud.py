from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from perfect_assassin.adapter.coordinate_hud import crc16_ccitt_false
from perfect_assassin.adapter.location_hud import (
    LocationStream,
    decode_location_packet,
    location_display,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "integrations/windows-capture"),
    str(ROOT / "integrations/windows-input"),
]
from location_hud_detector import detect_location_strip
from location_label_reader import read_location


def encoded(
    region="Tirisfal Glades",
    subzone="Deathknell",
    *,
    flags=7,
    millis=1000,
    tag=23,
    seq=9,
    version=1,
    environment=0,
    capabilities=0,
):
    a, b = region.encode("utf-8"), subzone.encode("utf-8")
    raw = bytearray((215, version, seq, flags))
    raw.extend(tag.to_bytes(2, "big"))
    raw.extend((len(a), len(b)))
    raw.extend(millis.to_bytes(4, "big"))
    raw.extend((environment, capabilities))
    raw.extend(a.ljust(64, b"\x00"))
    raw.extend(b.ljust(64, b"\x00"))
    raw.extend(crc16_ccitt_false(raw).to_bytes(2, "big"))
    return bytes(raw)


def packet(**kwargs):
    return decode_location_packet(encoded(**kwargs))


def test_api_pair_is_preserved_in_one_packet():
    p = packet()
    assert (p.region, p.subzone, p.client_time_ms) == (
        "Tirisfal Glades",
        "Deathknell",
        1000,
    )
    assert packet(region="Ținut", subzone="Criptă").subzone == "Criptă"
    assert packet(subzone="").subzone == ""
    assert packet(subzone="", flags=5).subzone is None
    assert packet(region="", flags=15).region_overflow is True


@pytest.mark.parametrize("index", [0, 1, 2, 3, 7, 8, 40, 78, 130, 143])
def test_corruption_rejected(index):
    raw = bytearray(encoded())
    raw[index] ^= 1
    with pytest.raises(ValueError):
        decode_location_packet(bytes(raw))


@pytest.mark.parametrize(
    "index,value", [(3, 255), (6, 65), (7, 65), (12, 1), (77, 1), (14, 255)]
)
def test_valid_crc_cannot_hide_invalid_structure(index, value):
    raw = bytearray(encoded())
    raw[index] = value
    raw[-2:] = crc16_ccitt_false(raw[:-2]).to_bytes(2, "big")
    with pytest.raises(ValueError):
        decode_location_packet(bytes(raw))


@pytest.mark.parametrize("scale", [0.8, 1, 1.25, 2])
@pytest.mark.parametrize("version", [1, 2])
def test_rgb_transport_round_trip_with_small_channel_noise(scale, version):
    raw = encoded(version=version)
    frame = np.zeros((250, 500, 4), dtype=np.uint8)
    markers = (
        (30, 70, 36),
        (30 + 92 * scale, 70, 36),
        (30, 70 + 34 * scale, 36),
        (0, 0, 0),
    )
    nibbles = [v for byte in raw for v in (byte >> 4, byte & 15)]
    for index in range(96):
        x = round(30 + (6 + index % 48 * 3) * scale)
        y = round(70 + (-8 + index // 48 * 3) * scale)
        frame[y, x, :3] = [
            8 + 16 * v + 3 for v in nibbles[index * 3 : index * 3 + 3][::-1]
        ]
    assert detect_location_strip(frame, markers, 9) == packet(version=version)
    assert detect_location_strip(frame, markers, 10) is None
    assert detect_location_strip(frame, None, 9) is None
    frame[round(70 - 8 * scale), round(30 + 6 * scale), 0] = 0
    assert detect_location_strip(frame, markers, 9) is None


def test_advancing_clock_required_and_duplicates_never_refresh():
    stream = LocationStream("client:one")
    assert stream.observe(packet(), 10) is None
    assert stream.observe(packet(), 10.1) is None
    report = stream.observe(packet(millis=1200), 10.2)
    assert report["region"] == "Tirisfal Glades"
    duplicate = stream.observe(packet(millis=1200), 40)
    assert duplicate["observed_monotonic_s"] == 10.2
    assert "expirate" in location_display(
        duplicate, now_s=40, expected_binding="client:one"
    )
    assert "indisponibile" in location_display(
        report, now_s=10.3, expected_binding="client:two"
    )


def test_session_change_invalid_capture_and_logout_clear_labels():
    stream = LocationStream("client:one")
    stream.observe(packet(), 1)
    assert stream.observe(packet(millis=1100), 1.1)
    assert stream.observe(packet(tag=24, millis=1200), 1.2) is None
    assert stream.observe(packet(tag=24, millis=1300), 1.3)
    assert stream.observe(None, 1.4) is None
    assert stream.observe(packet(tag=24, millis=1400), 1.5) is None
    assert stream.observe(packet(tag=24, millis=1500, flags=3), 1.6) is None


def test_subzone_transition_clears_old_label_and_clock_wrap_is_valid():
    stream = LocationStream("client:one")
    stream.observe(packet(millis=2**32 - 20), 1)
    report = stream.observe(packet(millis=20, subzone=""), 1.1)
    assert report["subzone"] == ""
    assert "nespecificată" in location_display(
        report, now_s=1.2, expected_binding="client:one"
    )
    assert stream.observe(packet(millis=10), 1.3) is None


def test_reader_requires_current_cc_owner_and_client_identity(tmp_path):
    receipt, diagnostic = tmp_path / "receipt.json", tmp_path / "diag.json"
    receipt.write_text(
        json.dumps(
            {
                "target_profile": "tbc_243_lab",
                "pid": 10,
                "process_creation_filetime_utc": 20,
            }
        ),
        encoding="utf-8",
    )
    stream = LocationStream("10:20")
    stream.observe(packet(), 1)
    report = stream.observe(packet(millis=1100), 1.1)
    diagnostic.write_text(
        json.dumps({"owner_pid": 100, "status": "LIVE", "location_labels": report}),
        encoding="utf-8",
    )
    record, binding = read_location(diagnostic, receipt, 100)
    assert "Deathknell" in location_display(record, now_s=1.2, expected_binding=binding)
    assert read_location(diagnostic, receipt, 101) == (None, "")
    receipt.write_text(
        json.dumps(
            {
                "target_profile": "tbc_243_lab",
                "pid": 11,
                "process_creation_filetime_utc": 21,
            }
        ),
        encoding="utf-8",
    )
    record, binding = read_location(diagnostic, receipt, 100)
    assert "indisponibile" in location_display(
        record, now_s=1.2, expected_binding=binding
    )


def test_invalid_time_and_display_record_fail_closed():
    stream = LocationStream("client:one")
    with pytest.raises(ValueError):
        stream.observe(packet(), float("nan"))
    assert "indisponibile" in location_display(
        None, now_s=1, expected_binding="client:one"
    )


@pytest.mark.parametrize("value", ["\ud800", "bad\nlabel", 42, "x" * 65])
def test_malformed_file_label_cannot_break_ui(value):
    stream = LocationStream("client:one")
    stream.observe(packet(), 1)
    report = stream.observe(packet(millis=1100), 1.1)
    report["region"] = value
    assert "indisponibile" in location_display(
        report, now_s=1.2, expected_binding="client:one"
    )


def test_location_label_does_not_grow_dense_controls_column():
    code = (ROOT / "integrations/windows-input/run_movement_engine_client.py").read_text(
        encoding="utf-8"
    )
    assert "ttk.Label(right, textvariable=self.location_label_text)" in code


def test_background_read_stall_cannot_refresh_labels_or_spawn_more_threads(monkeypatch):
    import location_label_reader as reader_module

    starts = []

    class BlockedThread:
        def __init__(self, *, target, daemon):
            assert daemon is True

        def start(self):
            starts.append(True)

    monkeypatch.setattr(reader_module, "Thread", BlockedThread)
    reader = reader_module.LocationLabelReader("diagnostic", "receipt", 100)
    stream = LocationStream("client:one")
    stream.observe(packet(), 1)
    reader.record = stream.observe(packet(millis=1100), 1.1)
    reader.binding = "client:one"
    assert "Deathknell" in reader.poll_text(1.2)
    assert "expirate" in reader.poll_text(4)
    assert "expirate" in reader.poll_text(100)
    assert len(starts) == 1


def test_background_read_failure_clears_previous_labels(tmp_path):
    from location_label_reader import LocationLabelReader

    reader = LocationLabelReader(tmp_path / "missing", tmp_path / "receipt", 100)
    reader._read()
    assert reader.results.get_nowait() == (None, "")


def test_addon_preserves_existing_wire_versions_and_region_api():
    code = (
        ROOT
        / "integrations/tbc243-addon/PerfectAssassinObserver/PerfectAssassinObserver.lua"
    ).read_text(encoding="utf-8")
    assert "PAO_HUD_PROTOCOL_VERSION = 3" in code
    assert "PAO_COMBAT_HUD_PROTOCOL_VERSION = 6" in code
    assert "local bytes = {175, 1, PAO_HUD_SEQUENCE, flags}" in code
    assert "bytes[143] = math.floor(crc / 256)" in code
    assert "string.len(region) > 64" in code
    assert "GetSubZoneText()" in code
