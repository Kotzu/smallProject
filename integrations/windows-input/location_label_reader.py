"""Bounded background file reading for the optional CC API-label display."""

from __future__ import annotations

import json
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread

from perfect_assassin.adapter.location_hud import location_display
from perfect_assassin.adapter.sonar_details import SonarDetails, sonar_details
from perfect_assassin.adapter.spatial_sonar import sonar_display


def _object(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("oversized location display input")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError("invalid location display input")
    return value


def read_location(diagnostic, receipt, owner_pid):
    identity = _object(receipt, 65536)
    state = _object(diagnostic, 32768)
    if (
        state.get("owner_pid") != owner_pid
        or state.get("status") != "LIVE"
        or identity.get("target_profile") != "tbc_243_lab"
    ):
        return None, ""
    labels = state.get("location_labels")
    if isinstance(labels, dict):
        labels = {**labels, "spatial_sonar": state.get("spatial_sonar")}
    return labels, f"{identity['pid']}:{identity['process_creation_filetime_utc']}"


class LocationLabelReader:
    def __init__(self, diagnostic, receipt, owner_pid):
        self.arguments = diagnostic, receipt, owner_pid
        self.results = SimpleQueue()
        self.inflight = False
        self.next_read_s = 0.0
        self.record, self.binding = None, ""

    def _read(self):
        try:
            result = read_location(*self.arguments)
        except (OSError, ValueError, KeyError, TypeError):
            result = None, ""
        self.results.put(result)

    def poll_text(self, now_s):
        try:
            self.record, self.binding = self.results.get_nowait()
        except Empty:
            pass
        else:
            self.inflight = False
        if not self.inflight and now_s >= self.next_read_s:
            self.inflight = True
            self.next_read_s = now_s + 0.5
            Thread(target=self._read, daemon=True).start()
        text = location_display(self.record, now_s=now_s, expected_binding=self.binding)
        # Never display geometry after the client identity/freshness gate failed.
        if isinstance(self.record, dict) and text.startswith("Regiune:"):
            text += "\n" + sonar_display(
                self.record.get("spatial_sonar"), labels=self.record, now_s=now_s
            )
        return text

    def details(self, now_s):
        # Reuse the existing read/freshness gate; this method does no I/O.
        text = location_display(self.record, now_s=now_s, expected_binding=self.binding)
        if not isinstance(self.record, dict) or not text.startswith("Regiune:"):
            return SonarDetails(
                "Sonar: identitate client indisponibilă sau date expirate."
            )
        return sonar_details(
            self.record.get("spatial_sonar"), labels=self.record, now_s=now_s
        )
