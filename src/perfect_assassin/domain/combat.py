from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


TARGET_BEARING_CENTER_TOLERANCE = 0.12


@dataclass(frozen=True, slots=True)
class CombatActionState:
    exact_binding: bool
    usable: bool
    current: bool
    in_range: bool | None
    cooldown_ready: bool
    cooldown_remaining_ms: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not bool
            for value in (
                self.exact_binding,
                self.usable,
                self.current,
                self.cooldown_ready,
            )
        ):
            raise ValueError("combat action flags must be booleans")
        if self.in_range is not None and type(self.in_range) is not bool:
            raise ValueError("combat action range must be boolean or null")
        if type(self.cooldown_remaining_ms) is not int or not 0 <= self.cooldown_remaining_ms <= 12_750:
            raise ValueError("combat action cooldown is out of bounds")
        if not self.exact_binding and (
            self.usable
            or self.current
            or self.in_range is not None
            or self.cooldown_ready
            or self.cooldown_remaining_ms
        ):
            raise ValueError("unbound combat action cannot publish actionable state")


@dataclass(frozen=True, slots=True)
class CombatTargetState:
    identity_crc16: int
    hostile: bool
    dead: bool
    is_player: bool
    health_pct: float
    health_current: int
    health_max: int
    level: int | None
    reaction: int
    interact_x_normalized: float | None = None
    interact_y_normalized: float | None = None

    def __post_init__(self) -> None:
        if type(self.identity_crc16) is not int or not 1 <= self.identity_crc16 <= 65_535:
            raise ValueError("target identity fingerprint is invalid")
        if any(type(value) is not bool for value in (self.hostile, self.dead, self.is_player)):
            raise ValueError("target flags must be booleans")
        if not isfinite(self.health_pct) or not 0 <= self.health_pct <= 100:
            raise ValueError("target health is invalid")
        if (
            type(self.health_current) is not int
            or type(self.health_max) is not int
            or not 0 <= self.health_current <= 16_777_215
            or not 1 <= self.health_max <= 16_777_215
            or self.health_current > self.health_max
        ):
            raise ValueError("target absolute health is invalid")
        expected_health_pct = self.health_current * 100.0 / self.health_max
        if abs(self.health_pct - expected_health_pct) > 100.0 / 255.0 + 1e-9:
            raise ValueError("target percent and absolute health diverge")
        if self.dead and (self.health_pct != 0 or self.health_current != 0):
            raise ValueError("dead target must have zero health")
        if self.level is not None and (type(self.level) is not int or not 1 <= self.level <= 254):
            raise ValueError("target level is invalid")
        if type(self.reaction) is not int or not 1 <= self.reaction <= 8:
            raise ValueError("target reaction is invalid")
        if (self.interact_x_normalized is None) != (self.interact_y_normalized is None):
            raise ValueError("target interact point must be complete")
        if self.interact_x_normalized is not None:
            if not self.dead:
                raise ValueError("only a dead target can publish an interact point")
            if not (
                isfinite(self.interact_x_normalized)
                and isfinite(self.interact_y_normalized)
                and 0.0 < self.interact_x_normalized < 1.0
                and 0.0 < self.interact_y_normalized < 1.0
            ):
                raise ValueError("target interact point is outside the client area")

    @property
    def attackable_npc(self) -> bool:
        # WoW reactions 1-3 are hostile/red and 4 is neutral/yellow.  The HUD's
        # historical `hostile` bit is UnitCanAttack; retain it as an additional
        # exact witness while explicitly accepting neutral yellow NPCs.
        return not self.is_player and (self.hostile or self.reaction <= 4)


@dataclass(frozen=True, slots=True)
class CombatObservationState:
    observation_id: str
    frame_id: str
    observation_sha256: str
    authorization_sha256: str
    actor_id: str
    actor_instance_id: str
    target_profile: str
    sequence: int
    observed_monotonic_s: float
    expires_monotonic_s: float
    confidence: float
    provenance_scope: str
    player_alive: bool
    player_health_pct: float
    player_energy: int
    player_attack_power: int
    player_level: int
    in_combat: bool
    combo_points: int
    target: CombatTargetState | None
    attack: CombatActionState
    sinister_strike: CombatActionState
    eviscerate: CombatActionState
    loot_event_sequence: int = 0
    visible_attackable_candidate_count: int = 0
    acquisition_x_normalized: float | None = None
    acquisition_y_normalized: float | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("observation_id", self.observation_id),
            ("frame_id", self.frame_id),
            ("actor_id", self.actor_id),
            ("actor_instance_id", self.actor_instance_id),
            ("target_profile", self.target_profile),
        ):
            if not isinstance(value, str) or not value or len(value) > 160:
                raise ValueError(f"{label} is invalid")
        for label, value in (
            ("observation_sha256", self.observation_sha256),
            ("authorization_sha256", self.authorization_sha256),
        ):
            if len(value) != 64 or any(character not in "0123456789ABCDEF" for character in value):
                raise ValueError(f"{label} is invalid")
        if type(self.sequence) is not int or not 0 <= self.sequence <= 255:
            raise ValueError("combat sequence is invalid")
        if (
            not isfinite(self.observed_monotonic_s)
            or not isfinite(self.expires_monotonic_s)
            or self.observed_monotonic_s < 0
            or self.expires_monotonic_s < self.observed_monotonic_s
            or self.expires_monotonic_s - self.observed_monotonic_s > 0.600001
        ):
            raise ValueError("combat observation timing is invalid")
        if not isfinite(self.confidence) or not 0 < self.confidence <= 1:
            raise ValueError("combat observation confidence is invalid")
        if self.provenance_scope not in {
            "synthetic_fixture",
            "lab_evaluation_only",
            "unpromoted_evaluation_only",
        }:
            raise ValueError("combat provenance scope is invalid")
        if type(self.player_alive) is not bool or type(self.in_combat) is not bool:
            raise ValueError("player state flags must be booleans")
        if not isfinite(self.player_health_pct) or not 0 <= self.player_health_pct <= 100:
            raise ValueError("player health is invalid")
        if not self.player_alive and self.player_health_pct != 0:
            raise ValueError("dead player must have zero health")
        if type(self.player_energy) is not int or not 0 <= self.player_energy <= 100:
            raise ValueError("player energy is invalid")
        if (
            type(self.player_attack_power) is not int
            or not 0 <= self.player_attack_power <= 65_535
        ):
            raise ValueError("player attack power is invalid")
        if type(self.player_level) is not int or not 1 <= self.player_level <= 255:
            raise ValueError("player level is invalid")
        if type(self.combo_points) is not int or not 0 <= self.combo_points <= 5:
            raise ValueError("combo points are invalid")
        if (
            type(self.loot_event_sequence) is not int
            or not 0 <= self.loot_event_sequence <= 31
        ):
            raise ValueError("loot event sequence is invalid")
        if (
            type(self.visible_attackable_candidate_count) is not int
            or not 0 <= self.visible_attackable_candidate_count <= 255
        ):
            raise ValueError("visible attackable candidate count is invalid")
        if (self.acquisition_x_normalized is None) != (
            self.acquisition_y_normalized is None
        ):
            raise ValueError("acquisition candidate screen geometry is incomplete")
        if self.visible_attackable_candidate_count:
            if self.target is not None or self.acquisition_x_normalized is None:
                raise ValueError("acquisition candidates conflict with selected target")
            if not (
                isfinite(self.acquisition_x_normalized)
                and isfinite(self.acquisition_y_normalized)
                and 0 < self.acquisition_x_normalized < 1
                and 0 < self.acquisition_y_normalized < 1
            ):
                raise ValueError("acquisition candidate geometry is invalid")
        elif (
            self.acquisition_x_normalized is not None
            or self.acquisition_y_normalized is not None
        ):
            raise ValueError("absent acquisition candidate contains geometry")


@dataclass(frozen=True, slots=True)
class TargetBearingState:
    observation_id: str
    observation_sha256: str
    frame_id: str
    combat_observation_id: str
    combat_observation_sha256: str
    authorization_sha256: str
    actor_id: str
    actor_instance_id: str
    target_profile: str
    target_identity_crc16: int | None
    tracking_state: str
    direction: str | None
    offset_x_normalized: float | None
    center_y_normalized: float | None
    observed_monotonic_s: float
    expires_monotonic_s: float
    confidence: float
    provenance_scope: str

    def __post_init__(self) -> None:
        for label, value in (
            ("observation_id", self.observation_id),
            ("frame_id", self.frame_id),
            ("combat_observation_id", self.combat_observation_id),
            ("actor_id", self.actor_id),
            ("actor_instance_id", self.actor_instance_id),
            ("target_profile", self.target_profile),
        ):
            if not isinstance(value, str) or not value or len(value) > 160:
                raise ValueError(f"bearing {label} is invalid")
        for label, value in (
            ("observation_sha256", self.observation_sha256),
            ("combat_observation_sha256", self.combat_observation_sha256),
            ("authorization_sha256", self.authorization_sha256),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789ABCDEF" for character in value)
            ):
                raise ValueError(f"bearing {label} is invalid")
        if self.target_identity_crc16 is not None and (
            type(self.target_identity_crc16) is not int
            or not 1 <= self.target_identity_crc16 <= 65_535
        ):
            raise ValueError("bearing target identity is invalid")
        if self.tracking_state not in {"VISIBLE", "LOST", "AMBIGUOUS"}:
            raise ValueError("bearing tracking state is invalid")
        if (
            not isfinite(self.observed_monotonic_s)
            or not isfinite(self.expires_monotonic_s)
            or self.observed_monotonic_s < 0
            or self.expires_monotonic_s < self.observed_monotonic_s
            or self.expires_monotonic_s - self.observed_monotonic_s > 0.450001
        ):
            raise ValueError("bearing timing is invalid")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("bearing confidence is invalid")
        if self.provenance_scope not in {
            "synthetic_fixture",
            "lab_evaluation_only",
            "unpromoted_evaluation_only",
        }:
            raise ValueError("bearing provenance scope is invalid")
        if self.tracking_state == "VISIBLE":
            if (
                self.direction not in {"LEFT", "CENTER", "RIGHT"}
                or self.offset_x_normalized is None
                or not isfinite(self.offset_x_normalized)
                or not -1 <= self.offset_x_normalized <= 1
                or self.confidence <= 0
            ):
                raise ValueError("visible bearing is incomplete")
            if self.center_y_normalized is not None and (
                not isfinite(self.center_y_normalized)
                or not 0 <= self.center_y_normalized <= 1
            ):
                raise ValueError("visible bearing vertical geometry is invalid")
        elif (
            self.direction is not None
            or self.offset_x_normalized is not None
            or self.center_y_normalized is not None
            or self.confidence != 0
        ):
            raise ValueError("non-visible bearing contains visual facts")

    def is_bound_to(self, observation: CombatObservationState) -> bool:
        target_identity = (
            None if observation.target is None else observation.target.identity_crc16
        )
        return (
            self.frame_id == observation.frame_id
            and self.combat_observation_id == observation.observation_id
            and self.combat_observation_sha256 == observation.observation_sha256
            and self.authorization_sha256 == observation.authorization_sha256
            and self.actor_id == observation.actor_id
            and self.actor_instance_id == observation.actor_instance_id
            and self.target_profile == observation.target_profile
            and self.target_identity_crc16 == target_identity
        )
