from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from perfect_assassin.adapter.client_location_labels import (
    ClientLocationLabels,
    labels_from_validated_export,
)
from perfect_assassin.adapter.saved_variables import parse_saved_variables
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.records import RawEvent, RawFact


class Tbc243SavedVariablesError(ValueError):
    pass


def _normalize_empty_saved_variables_arrays(export: dict[str, Any]) -> None:
    """WoW serializes an empty Lua array as {}, which the data parser sees as a map."""
    list_fields_by_kind = {
        "loot_snapshot": ("items",),
        "quest_npc_snapshot": ("available_quests", "active_quests"),
        "quest_log_snapshot": ("quests",),
        "spellbook_snapshot": ("spells",),
        "action_bar_snapshot": ("slots",),
    }
    for event in export.get("events", []):
        if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
            continue
        payload = event["payload"]
        for field in list_fields_by_kind.get(event.get("kind"), ()):
            if payload.get(field) == {}:
                payload[field] = []
        if event.get("kind") == "quest_log_snapshot" and isinstance(
            payload.get("quests"), list
        ):
            for quest in payload["quests"]:
                if isinstance(quest, dict) and quest.get("objectives") == {}:
                    quest["objectives"] = []


_FIELD_POLICY: dict[str, tuple[str, str]] = {
    "player_level": ("player_level", "self_state"),
    "player_xp": ("player_xp", "level_progress"),
    "player_level_reached": ("player_level_reached", "level_progress"),
    "player_dead": ("player_dead", "self_state"),
    "world_zone": ("world_zone", "world_location"),
    "world_subzone": ("world_subzone", "world_location"),
    "target_guid": ("target_guid", "target_state"),
    "target_name": ("target_name", "target_state"),
    "target_kind": ("target_kind", "target_state"),
    "target_health_pct": ("target_health_pct", "target_state"),
    "target_dead": ("target_dead", "target_state"),
    "state": ("combat_state", "combat_log"),
    "source": ("quest_dialog_source", "quest_state"),
    "npc_guid": ("quest_npc_guid", "quest_state"),
    "npc_name": ("quest_npc_name", "quest_state"),
    "dialog_text": ("quest_dialog_text", "quest_state"),
    "available_quests": ("quest_available", "quest_state"),
    "active_quests": ("quest_active_at_npc", "quest_state"),
    "quest_title": ("quest_title", "quest_state"),
    "quest_text": ("quest_text", "quest_state"),
    "quest_objective_text": ("quest_objective_text", "quest_state"),
    "quest_suggested_group": ("quest_suggested_group", "quest_state"),
    "quests": ("quest_log", "quest_state"),
    "spells": ("player_spellbook", "self_spellbook"),
    "profile_id": ("action_bar_profile", "player_action_bars"),
    "current_page": ("action_bar_current_page", "player_action_bars"),
    "directly_bound_slots": ("action_bar_directly_bound_slots", "player_action_bars"),
    "visible_bars": ("action_bar_visibility", "player_action_bars"),
    "slots": ("action_bar_slots", "player_action_bars"),
    "focus_exists": ("focus_exists", "focus_state"),
    "focus_guid": ("focus_guid", "focus_state"),
    "focus_name": ("focus_name", "focus_state"),
    "focus_kind": ("focus_kind", "focus_state"),
    "focus_health_pct": ("focus_health_pct", "focus_state"),
    "focus_health_current": ("focus_health_current", "focus_state"),
    "focus_health_max": ("focus_health_max", "focus_state"),
    "focus_hostile": ("focus_hostile", "focus_state"),
    "focus_dead": ("focus_dead", "focus_state"),
    "focus_casting": ("focus_casting", "focus_state"),
    "focus_cast_name": ("focus_cast_name", "focus_state"),
    "focus_cast_rank": ("focus_cast_rank", "focus_state"),
    "focus_cast_display_name": ("focus_cast_display_name", "focus_state"),
    "focus_cast_icon": ("focus_cast_icon", "focus_state"),
    "focus_cast_start_ms": ("focus_cast_start_ms", "focus_state"),
    "focus_cast_end_ms": ("focus_cast_end_ms", "focus_state"),
    "mouseover_exists": ("mouseover_exists", "mouseover_state"),
    "mouseover_guid": ("mouseover_guid", "mouseover_state"),
    "mouseover_name": ("mouseover_name", "mouseover_state"),
    "mouseover_kind": ("mouseover_kind", "mouseover_state"),
    "mouseover_health_pct": ("mouseover_health_pct", "mouseover_state"),
    "mouseover_health_current": ("mouseover_health_current", "mouseover_state"),
    "mouseover_health_max": ("mouseover_health_max", "mouseover_state"),
    "mouseover_hostile": ("mouseover_hostile", "mouseover_state"),
    "mouseover_dead": ("mouseover_dead", "mouseover_state"),
    "available": ("map_position_available", "self_map_position"),
    "reason": ("map_position_reason", "self_map_position"),
    "coordinate_space": ("map_coordinate_space", "self_map_position"),
    "x": ("map_position_x", "self_map_position"),
    "y": ("map_position_y", "self_map_position"),
    "map_continent_index": ("map_continent_index", "self_map_position"),
    "map_zone_index": ("map_zone_index", "self_map_position"),
    "map_info": ("map_info", "self_map_position"),
}


class Tbc243SavedVariablesObservationSource:
    """Offline adapter for the addon-owned, client-persisted SavedVariables export."""

    def __init__(
        self,
        saved_variables_path: Path,
        semantic_registry_path: Path,
        export_validator: ContractValidator,
    ) -> None:
        export = parse_saved_variables(saved_variables_path)
        _normalize_empty_saved_variables_arrays(export)
        export_validator.validate(export)
        if export["target_profile"] != "tbc_243_lab":
            raise Tbc243SavedVariablesError("TBC SavedVariables intake accepts only tbc_243_lab")
        if export["event_format"] != "tbc243-legacy-v1":
            raise Tbc243SavedVariablesError("Unknown TBC 2.4.3 addon event format")

        registry = json.loads(semantic_registry_path.read_text(encoding="utf-8"))
        self._semantic_facts = dict(registry["facts"])
        self.target_profile = str(export["target_profile"])
        self.adapter_name = str(export["adapter"])
        self.session_id = str(export["session_id"])
        self.champion_id = str(export["champion_id"])
        self.synthetic = bool(export["synthetic"])
        self._validate_event_order(export["events"])
        self._location_labels = labels_from_validated_export(export)
        self.archived_raw_events = sum(
            1 for event in export["events"] if event["kind"] == "combat_log_raw"
        )
        translated_events: list[RawEvent] = []
        active_target_guid: str | None = None
        self.interpreted_raw_events = 0
        for event in export["events"]:
            active_target_guid = self._next_active_target_guid(event, active_target_guid)
            translated = self._translate_event(event, active_target_guid)
            if translated is not None:
                translated_events.append(translated)
                if event["kind"] == "combat_log_raw":
                    self.interpreted_raw_events += 1
        self._events = tuple(translated_events)

    @staticmethod
    def _validate_event_order(events: list[dict[str, Any]]) -> None:
        previous_sequence: int | None = None
        previous_game_time: int | None = None
        for item in events:
            sequence = int(item["seq"])
            game_time = int(item["game_time_ms"])
            if previous_sequence is not None and sequence <= previous_sequence:
                raise Tbc243SavedVariablesError("Event sequence must be strictly increasing")
            if previous_game_time is not None and game_time < previous_game_time:
                raise Tbc243SavedVariablesError("Client game time must be monotonic")
            previous_sequence = sequence
            previous_game_time = game_time
    def events(self) -> Iterable[RawEvent]:
        return iter(self._events)

    def location_labels(self) -> Iterable[ClientLocationLabels]:
        """API-derived historical snapshots, never a live current-location feed."""
        return iter(self._location_labels)

    def semantic_key(self, raw_key: str) -> str:
        try:
            return self._semantic_facts[raw_key]
        except KeyError as error:
            raise Tbc243SavedVariablesError(f"Unknown raw fact key: {raw_key}") from error

    def semantic_value(self, raw_key: str, raw_value: Any) -> Any:
        return raw_value

    @staticmethod
    def _next_active_target_guid(
        event: dict[str, Any], current: str | None
    ) -> str | None:
        payload = event["payload"]
        target: dict[str, Any] | None = None
        if event["kind"] == "target_snapshot":
            target = payload
        elif event["kind"] == "player_snapshot" and isinstance(payload.get("target"), dict):
            target = payload["target"]
        if target is None:
            return current
        if not target.get("target_exists"):
            return None
        guid = target.get("target_guid")
        # A newly visible target without a client-observed GUID must not inherit
        # the identity of the previous target.
        return str(guid) if guid else None

    def _translate_event(
        self, event: dict[str, Any], active_target_guid: str | None
    ) -> RawEvent | None:
        timestamp = datetime.fromtimestamp(event["captured_epoch"], tz=UTC).isoformat().replace(
            "+00:00", "Z"
        )
        payload = dict(event["payload"])
        if event["kind"] == "combat_log_raw":
            return self._translate_verified_combat_event(
                event, payload, active_target_guid, timestamp
            )
        raw_facts: list[RawFact] = []
        if event["kind"] == "player_snapshot":
            target = payload.pop("target", None)
            if isinstance(target, dict) and target.get("target_exists"):
                for key, value in target.items():
                    if key != "target_exists":
                        self._append_fact(raw_facts, key, value, timestamp)
        if event["kind"] == "loot_snapshot":
            for item in payload.pop("items", []):
                if not isinstance(item, dict):
                    raise Tbc243SavedVariablesError("Loot item must be a table")
                observed = item.get("link") or item.get("name")
                if observed:
                    raw_facts.append(
                        RawFact(
                            raw_key="loot_item",
                            value=observed,
                            source="client_observed",
                            capability="loot_observation",
                            confidence=1.0,
                            observed_at=timestamp,
                        )
                    )
        for key, value in payload.items():
            self._append_fact(raw_facts, key, value, timestamp)
        if not raw_facts:
            return None
        return RawEvent(
            raw_event_id=f"addon:{self.session_id}:{int(event['seq']):06d}",
            kind=str(event["kind"]),
            game_time_ms=int(event["game_time_ms"]),
            captured_at=timestamp,
            facts=tuple(raw_facts),
        )

    def _translate_verified_combat_event(
        self,
        event: dict[str, Any],
        payload: dict[str, Any],
        active_target_guid: str | None,
        timestamp: str,
    ) -> RawEvent | None:
        # PA-019: verified against the first real 2.4.3 capture. No other
        # legacy combat-log subevent is interpreted until separately proven.
        if payload.get("a02") != "PARTY_KILL":
            return None
        destination_guid = payload.get("a06")
        if not destination_guid or str(destination_guid) != active_target_guid:
            return None

        facts = [
            RawFact(
                raw_key="target_dead",
                value=True,
                source="client_observed",
                capability="combat_log",
                confidence=1.0,
                observed_at=timestamp,
            ),
            RawFact(
                raw_key="target_guid",
                value=str(destination_guid),
                source="client_observed",
                capability="combat_log",
                confidence=1.0,
                observed_at=timestamp,
            ),
        ]
        if payload.get("a07"):
            facts.append(
                RawFact(
                    raw_key="target_name",
                    value=str(payload["a07"]),
                    source="client_observed",
                    capability="combat_log",
                    confidence=1.0,
                    observed_at=timestamp,
                )
            )
        return RawEvent(
            raw_event_id=f"addon:{self.session_id}:{int(event['seq']):06d}",
            kind="target_killed",
            game_time_ms=int(event["game_time_ms"]),
            captured_at=timestamp,
            facts=tuple(facts),
        )

    @staticmethod
    def _append_fact(facts: list[RawFact], field: str, value: Any, timestamp: str) -> None:
        if field not in _FIELD_POLICY:
            return
        raw_key, capability = _FIELD_POLICY[field]
        facts.append(
            RawFact(
                raw_key=raw_key,
                value=value,
                source="client_observed",
                capability=capability,
                confidence=1.0,
                observed_at=timestamp,
            )
        )
