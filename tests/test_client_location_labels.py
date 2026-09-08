from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from perfect_assassin.adapter.client_location_labels import (
    ClientLocationLabels,
    labels_from_validated_export,
)
from perfect_assassin.adapter.tbc243_saved_variables import (
    Tbc243SavedVariablesObservationSource,
)
from perfect_assassin.contract_validation import ContractValidator

ROOT = Path(__file__).resolve().parents[1]


def sample(**changes):
    return replace(
        ClientLocationLabels(
            "session-a", "event:1", 1700000000, 100, False, "Zone", "Room"
        ),
        **changes,
    )


def view(value, *, age=1, session="session-a"):
    return value.presentation(
        expected_session_id=session,
        now_utc=datetime.fromtimestamp(1700000000 + age, UTC),
    )


def test_api_labels_remain_historical_even_when_file_is_recent():
    result = view(sample())
    assert result["api_functions"] == {
        "zone": "GetZoneText",
        "subzone": "GetSubZoneText",
    }
    assert result["last_recorded_label"] == "Room"
    assert result["current_label"] is None
    assert (
        result["floor_id"]
        is result["observed_z"]
        is result["geometry_identity"]
        is None
    )
    assert result["physical_room_confirmed"] is False
    assert result["execution_authority"] is False
    assert result["transport"] == "SAVED_VARIABLES_ARCHIVE"


@pytest.mark.parametrize("subzone,state", [(None, "UNAVAILABLE"), ("", "EMPTY")])
def test_missing_and_empty_subzone_are_distinct(subzone, state):
    result = view(sample(subzone=subzone))
    assert result["field_states"]["subzone"] == state
    assert result["last_recorded_label"] == "Zone"


@pytest.mark.parametrize(
    "changes,kwargs,reason",
    [
        ({"synthetic": True}, {}, "SYNTHETIC_EVIDENCE"),
        ({}, {"session": "another"}, "SESSION_MISMATCH"),
        ({}, {"age": -1}, "FUTURE_RECORD"),
    ],
)
def test_other_session_synthetic_or_future_never_supplies_display_label(
    changes, kwargs, reason
):
    result = view(sample(**changes), **kwargs)
    assert reason in result["reasons"]
    assert result["last_recorded_label"] is result["current_label"] is None


def test_expired_archive_is_explicit_not_current():
    result = view(sample(), age=3600)
    assert "STALE_RECORD" in result["reasons"]
    assert result["last_recorded_label"] == "Room"
    assert result["current_label"] is None


def test_no_name_does_not_invent_room():
    result = view(sample(zone="", subzone=None))
    assert "NO_LOCATION_LABEL" in result["reasons"]
    assert result["last_recorded_label"] is None


def test_transition_clears_previous_subzone_and_preserves_localized_text():
    events = [
        {
            "kind": "player_snapshot",
            "seq": i,
            "captured_epoch": 1700000000 + i,
            "game_time_ms": i * 100,
            "payload": payload,
        }
        for i, payload in enumerate(
            [
                {"world_zone": "Ținut", "world_subzone": "Criptă"},
                {"world_zone": "Ținut", "world_subzone": ""},
                {"world_zone": "Alt ținut"},
            ],
            1,
        )
    ]
    snapshots = labels_from_validated_export(
        {"session_id": "session-a", "synthetic": False, "events": events}
    )
    assert [s.subzone for s in snapshots] == ["Criptă", "", None]
    assert snapshots[-1].zone == "Alt ținut"


def test_integration_uses_existing_validated_addon_export():
    source = Tbc243SavedVariablesObservationSource(
        ROOT / "data/fixtures/tbc243_observer_saved_variables.synthetic.lua",
        ROOT / "config/semantic-ids/rogue-level-1.json",
        ContractValidator(ROOT / "contracts/tbc243-addon-export.schema.json"),
    )
    labels = list(source.location_labels())
    assert labels[0].zone == "Synthetic Starting Zone"
    assert labels[0].subzone == "Synthetic Camp"
    assert labels[0].synthetic is True
    assert len(list(source.events())) > 0


@pytest.mark.parametrize(
    "changes",
    [
        {"zone": 123},
        {"subzone": "x" * 257},
        {"captured_epoch": True},
        {"game_time_ms": -1},
    ],
)
def test_invalid_labels_rejected(changes):
    with pytest.raises(ValueError):
        sample(**changes)


def test_timezone_and_freshness_bounds_required():
    naive = datetime(2026, 1, 1)  # noqa: DTZ001 -- deliberately invalid evidence
    with pytest.raises(ValueError):
        sample().presentation(expected_session_id="session-a", now_utc=naive)
    for age in (float("nan"), -1, True):
        with pytest.raises(ValueError):
            sample().presentation(
                expected_session_id="session-a",
                now_utc=datetime.now(UTC),
                stale_after_s=age,
            )


def test_existing_addon_observes_api_on_zone_changes():
    code = (
        ROOT
        / "integrations/tbc243-addon/PerfectAssassinObserver/PerfectAssassinObserver.lua"
    ).read_text(encoding="utf-8")
    assert "PAO_Scalar(GetZoneText())" in code
    assert "PAO_Scalar(GetSubZoneText())" in code
    assert 'PAO_Frame:RegisterEvent("ZONE_CHANGED_INDOORS")' in code


def test_schema_accepts_exact_existing_addon_life_flags_without_weakening_types():
    import json

    schema = json.loads(
        (ROOT / "contracts/tbc243-addon-export.schema.json").read_text(encoding="utf-8")
    )
    import jsonschema_rs

    validator = jsonschema_rs.Draft202012Validator(schema["$defs"]["mapPosition"])
    payload = {
        "available": False,
        "reason": "position_unavailable",
        "coordinate_space": "normalized_current_zone_map",
        "player_dead_or_ghost": False,
        "player_ghost": False,
    }
    validator.validate(payload)
    for extra in (
        {"player_ghost": "false"},
        {"player_dead_or_ghost": 0},
        {"unapproved_field": True},
    ):
        with pytest.raises(jsonschema_rs.ValidationError):
            validator.validate({**payload, **extra})
