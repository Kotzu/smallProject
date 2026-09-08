from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any

from perfect_assassin.domain.combat import (
    TARGET_BEARING_CENTER_TOLERANCE,
    CombatObservationState,
    TargetBearingState,
)
from perfect_assassin.domain.facing import MagneticFacingController


ACTION_CONTROL = {
    "combat.stop_player_dead": None,
    "combat.request_safe_retreat": "MOVE_BACKWARD",
    "combat.acquire_hostile_target": "TARGET_NEAREST_HOSTILE",
    "combat.acquire_visible_hostile": "TARGET_VISIBLE_HOSTILE",
    "combat.scan_for_hostile_target": "TURN_RIGHT",
    "combat.scan_for_hostile_target_left": "TURN_LEFT",
    "combat.turn_toward_visible_candidate_left": "TURN_LEFT",
    "combat.turn_toward_visible_candidate_right": "TURN_RIGHT",
    "combat.cycle_hostile_target": "TARGET_NEAREST_HOSTILE",
    "combat.advance_from_looted_corpse": "TARGET_NEAREST_HOSTILE",
    "recovery.select_last_defeated": "TARGET_LAST_HOSTILE",
    "recovery.loot_defeated_target": "INTERACT_TARGET",
    "combat.reject_player_target": None,
    "combat.reject_non_hostile_target": None,
    "combat.target_defeated": None,
    "combat.reject_risky_target": None,
    "combat.stop_action_binding_mismatch": None,
    "combat.approach_target": "MOVE_FORWARD",
    "combat.turn_toward_target_left": "TURN_LEFT",
    "combat.turn_toward_target_right": "TURN_RIGHT",
    "combat.search_selected_target": "TURN_RIGHT",
    "combat.search_selected_target_left": "TURN_LEFT",
    "combat.normalize_camera_pitch_up": "TURN_RIGHT",
    "combat.normalize_camera_pitch_down": "TURN_RIGHT",
    "combat.orbit_target_left": "STRAFE_LEFT",
    "combat.orbit_target_right": "STRAFE_RIGHT",
    "combat.hold_bearing_unavailable": None,
    "combat.monitor_continuous_approach": None,
    "combat.monitor_continuous_facing": None,
    "combat.monitor_continuous_reacquisition": None,
    "rogue.auto_attack": "ACTION_SLOT_1",
    "combat.hold_range_unknown": None,
    "rogue.eviscerate": "ACTION_SLOT_3",
    "rogue.sinister_strike": "ACTION_SLOT_2",
    "combat.monitor_auto_attack": None,
}


def validate_combat_decision_semantics(record: dict[str, Any]) -> None:
    action_id = record.get("action_id")
    if action_id not in ACTION_CONTROL:
        raise ValueError("unsupported combat decision action")
    if record.get("requested_control") != ACTION_CONTROL[action_id]:
        raise ValueError("combat action and requested control diverge")
    if record.get("execution_authority") is not False:
        raise ValueError("combat decisions never carry execution authority")
    observed = record.get("observed_monotonic_s")
    expires = record.get("observation_expires_monotonic_s")
    if (
        isinstance(observed, bool)
        or not isinstance(observed, (int, float))
        or isinstance(expires, bool)
        or not isinstance(expires, (int, float))
        or observed < 0
        or expires < observed
    ):
        raise ValueError("combat decision timing is inconsistent")
    target_identity = record.get("target_identity_crc16")
    if action_id in {
        "rogue.auto_attack",
        "rogue.sinister_strike",
        "rogue.eviscerate",
        "combat.approach_target",
        "combat.monitor_continuous_approach",
        "combat.monitor_continuous_facing",
        "combat.monitor_continuous_reacquisition",
        "combat.cycle_hostile_target",
        "combat.turn_toward_target_left",
        "combat.turn_toward_target_right",
        "combat.search_selected_target", "combat.search_selected_target_left",
        "combat.orbit_target_left",
        "combat.orbit_target_right",
        "recovery.loot_defeated_target",
    } and not (
        type(target_identity) is int and 1 <= target_identity <= 65_535
    ):
        raise ValueError("targeted combat action requires target continuity")
    bearing_id = record.get("bearing_observation_id")
    bearing_sha = record.get("bearing_observation_sha256")
    bearing_state = record.get("bearing_tracking_state")
    bearing_direction = record.get("bearing_direction")
    bearing_offset = record.get("bearing_offset_x_normalized")
    bearing_expires = record.get("bearing_expires_monotonic_s")
    steering_actions = {
        "combat.approach_target",
        "combat.monitor_continuous_approach",
        "combat.monitor_continuous_facing",
        "combat.monitor_continuous_reacquisition",
        "combat.turn_toward_target_left",
        "combat.turn_toward_target_right",
        "combat.search_selected_target", "combat.search_selected_target_left",
        "combat.orbit_target_left",
        "combat.orbit_target_right",
        "combat.turn_toward_visible_candidate_left",
        "combat.turn_toward_visible_candidate_right",
    }
    if action_id in steering_actions:
        if (
            not isinstance(bearing_id, str)
            or not bearing_id
            or not isinstance(bearing_sha, str)
            or len(bearing_sha) != 64
            or isinstance(bearing_expires, bool)
            or not isinstance(bearing_expires, (int, float))
            or bearing_expires < observed
        ):
            raise ValueError("steering decision lacks a fresh bearing fact")
        expected = {
            "combat.approach_target": ("VISIBLE", "CENTER"),
            "combat.orbit_target_left": ("VISIBLE", "CENTER"),
            "combat.orbit_target_right": ("VISIBLE", "CENTER"),
            "combat.turn_toward_visible_candidate_left": ("VISIBLE", "LEFT"),
            "combat.turn_toward_visible_candidate_right": ("VISIBLE", "RIGHT"),
        }.get(action_id)
        if expected is not None and (bearing_state, bearing_direction) != expected:
            raise ValueError("steering decision contradicts target bearing")
        if (
            action_id == "combat.monitor_continuous_approach"
            and bearing_state != "VISIBLE"
        ):
            raise ValueError("continuous approach requires a visible selected target")
        if action_id == "combat.turn_toward_target_left" and not (
            bearing_state == "VISIBLE"
            and isinstance(bearing_offset, (int, float))
            and not isinstance(bearing_offset, bool)
            and bearing_offset < -RogueLevelOneCombatPolicy.MAGNETIC_FACING_TOLERANCE
        ):
            raise ValueError("bearing offset diverges from left magnetic correction")
        if action_id == "combat.turn_toward_target_right" and not (
            bearing_state == "VISIBLE"
            and isinstance(bearing_offset, (int, float))
            and not isinstance(bearing_offset, bool)
            and bearing_offset > RogueLevelOneCombatPolicy.MAGNETIC_FACING_TOLERANCE
        ):
            raise ValueError("bearing offset diverges from right magnetic correction")
        if action_id in {
            "combat.search_selected_target",
            "combat.search_selected_target_left",
            "combat.monitor_continuous_reacquisition",
            "combat.normalize_camera_pitch_up",
            "combat.normalize_camera_pitch_down",
        } and (
            bearing_state not in {"LOST", "AMBIGUOUS"}
            or bearing_direction is not None
            or bearing_offset is not None
        ):
            raise ValueError("search decision requires a non-visible bearing")
        if bearing_state == "VISIBLE":
            if (
                isinstance(bearing_offset, bool)
                or not isinstance(bearing_offset, (int, float))
                or not -1 <= bearing_offset <= 1
            ):
                raise ValueError("steering decision lacks an exact bearing offset")
            expected_direction = (
                "LEFT"
                if bearing_offset < -TARGET_BEARING_CENTER_TOLERANCE
                else "RIGHT"
                if bearing_offset > TARGET_BEARING_CENTER_TOLERANCE
                else "CENTER"
            )
            if bearing_direction != expected_direction:
                raise ValueError("steering direction and bearing offset diverge")


@dataclass(frozen=True, slots=True)
class CombatDecision:
    decision_id: str
    observation: CombatObservationState
    action_id: str
    priority_tier: str
    reason_code: str
    explanation: str
    requested_control: str | None
    preconditions: tuple[str, ...]
    confidence: float
    bearing: TargetBearingState | None = None

    def __post_init__(self) -> None:
        if self.action_id not in ACTION_CONTROL:
            raise ValueError("unsupported combat decision action")
        if self.requested_control != ACTION_CONTROL[self.action_id]:
            raise ValueError("combat action/control binding is invalid")
        if self.priority_tier not in {
            "SURVIVAL",
            "SAFETY",
            "TARGET_CONTROL",
            "DAMAGE",
            "RECOVERY",
        }:
            raise ValueError("combat decision priority is invalid")
        if not self.preconditions or len(self.preconditions) > 12:
            raise ValueError("combat decision preconditions are invalid")
        if not 0 < self.confidence <= 1:
            raise ValueError("combat decision confidence is invalid")
        if self.bearing is not None and not self.bearing.is_bound_to(self.observation):
            raise ValueError("combat decision bearing is not bound to its observation")

    def to_record(self, *, created_at: str) -> dict[str, Any]:
        target_identity = (
            self.observation.target.identity_crc16
            if self.observation.target is not None
            else None
        )
        record = {
            "record_type": "combat_decision",
            "schema_version": "1.0",
            "decision_id": self.decision_id,
            "observation_id": self.observation.observation_id,
            "observation_sha256": self.observation.observation_sha256,
            "authorization_sha256": self.observation.authorization_sha256,
            "actor_id": self.observation.actor_id,
            "actor_instance_id": self.observation.actor_instance_id,
            "target_profile": self.observation.target_profile,
            "created_at": created_at,
            "observed_monotonic_s": self.observation.observed_monotonic_s,
            "observation_expires_monotonic_s": self.observation.expires_monotonic_s,
            "source_sequence": self.observation.sequence,
            "target_identity_crc16": target_identity,
            "bearing_observation_id": (
                None if self.bearing is None else self.bearing.observation_id
            ),
            "bearing_observation_sha256": (
                None if self.bearing is None else self.bearing.observation_sha256
            ),
            "bearing_tracking_state": (
                None if self.bearing is None else self.bearing.tracking_state
            ),
            "bearing_direction": (
                None if self.bearing is None else self.bearing.direction
            ),
            "bearing_offset_x_normalized": (
                None if self.bearing is None else self.bearing.offset_x_normalized
            ),
            "bearing_expires_monotonic_s": (
                None if self.bearing is None else self.bearing.expires_monotonic_s
            ),
            "priority_tier": self.priority_tier,
            "action_id": self.action_id,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "requested_control": self.requested_control,
            "preconditions": list(self.preconditions),
            "confidence": self.confidence,
            "provenance": {
                "origin": "deterministic_combat_policy",
                "policy_id": "rogue_level1_combat_v2",
                "policy_version": "2.0.0",
                "source_scope": self.observation.provenance_scope,
                "evidence_refs": [
                    self.observation.observation_id,
                    f"sha256:{self.observation.observation_sha256}",
                    *(
                        ()
                        if self.bearing is None
                        else (
                            self.bearing.observation_id,
                            f"sha256:{self.bearing.observation_sha256}",
                        )
                    ),
                ],
            },
            "execution_authority": False,
        }
        validate_combat_decision_semantics(record)
        return record


@dataclass(frozen=True, slots=True)
class EviscerateDamageEstimate:
    combo_points: int
    raw_min: int
    raw_max: int
    conservative_after_armor: int
    likely_after_armor: int
    target_health_current: int

    @property
    def conservative_kill(self) -> bool:
        return self.conservative_after_armor >= self.target_health_current

    @property
    def likely_kill(self) -> bool:
        return self.likely_after_armor >= self.target_health_current

    @property
    def likely_overkill(self) -> int:
        return max(0, self.likely_after_armor - self.target_health_current)


def estimate_rank1_eviscerate(
    *, combo_points: int, attack_power: int, target_health_current: int
) -> EviscerateDamageEstimate:
    """Client-build 2.4.3 Rank 1 estimate, before any execution decision.

    Spell.dbc entry 2098 contributes 1..5 base plus 5 per combo point.
    CMaNGOS' TBC spell implementation adds trunc(AP * 0.03 * CP).  Target
    armor is not visible in the current client contract, so the decision uses
    explicit conservative and likely physical-damage retention bands.
    """

    if type(combo_points) is not int or not 1 <= combo_points <= 5:
        raise ValueError("Eviscerate estimate requires one to five combo points")
    if type(attack_power) is not int or not 0 <= attack_power <= 65_535:
        raise ValueError("Eviscerate estimate attack power is invalid")
    if (
        type(target_health_current) is not int
        or not 1 <= target_health_current <= 16_777_215
    ):
        raise ValueError("Eviscerate estimate target health is invalid")
    attack_power_bonus = floor(attack_power * 0.03 * combo_points)
    raw_min = 1 + 5 * combo_points + attack_power_bonus
    raw_max = 5 + 5 * combo_points + attack_power_bonus
    return EviscerateDamageEstimate(
        combo_points=combo_points,
        raw_min=raw_min,
        raw_max=raw_max,
        conservative_after_armor=floor(raw_min * 0.60),
        likely_after_armor=floor(((raw_min + raw_max) / 2.0) * 0.80),
        target_health_current=target_health_current,
    )


class RogueLevelOneCombatPolicy:
    """Deterministic, explainable level-one Rogue policy; never emits input."""

    def __init__(self, *, initial_search_direction: str = "RIGHT") -> None:
        if initial_search_direction not in {"LEFT", "RIGHT"}:
            raise ValueError("initial_search_direction must be LEFT or RIGHT")
        self._initial_search_direction = initial_search_direction

    MIN_SURVIVAL_HEALTH_PCT = 25.0
    SINISTER_STRIKE_ENERGY = 45
    EVISCERATE_ENERGY = 35
    MAGNETIC_FACING_TOLERANCE = 0.025

    def decide_facing_only(
        self,
        observation: CombatObservationState,
        *,
        decision_id: str,
        bearing: TargetBearingState,
    ) -> CombatDecision:
        """Adapt MovementEngine facing into a no-damage decision record."""

        target = observation.target
        if (
            not observation.player_alive
            or target is None
            or target.is_player
            or target.dead
            or not bearing.is_bound_to(observation)
        ):
            raise ValueError("facing-only calibration requires one live NPC target")
        intent = MagneticFacingController().decide(bearing)
        if intent.control not in {"TURN_LEFT", "TURN_RIGHT"}:
            raise ValueError("facing-only calibration requires an off-center target")
        direction = "left" if intent.control == "TURN_LEFT" else "right"
        return CombatDecision(
            decision_id=decision_id,
            observation=observation,
            action_id=f"combat.turn_toward_target_{direction}",
            priority_tier="TARGET_CONTROL",
            reason_code=f"calibration_{intent.reason}",
            explanation=(
                "MovementEngine aligns the selected calibration NPC; this decision "
                "cannot request movement, targeting, or a damage slot."
            ),
            requested_control=intent.control,
            preconditions=(
                "target.is_player=false",
                "target.dead=false",
                f"target_bearing={direction.upper()}",
                "calibration.no_attack=true",
            ),
            confidence=observation.confidence,
            bearing=bearing,
        )

    def decide_acquisition_scan(
        self,
        observation: CombatObservationState,
        *,
        decision_id: str,
    ) -> CombatDecision:
        """Propose one bounded, non-damaging view scan after Tab found no target."""

        if (
            not observation.player_alive
            or observation.player_health_pct <= self.MIN_SURVIVAL_HEALTH_PCT
            or observation.in_combat
            or observation.target is not None
        ):
            raise ValueError("acquisition scan requires a safe, target-free pre-combat frame")
        return CombatDecision(
            decision_id=decision_id,
            observation=observation,
            action_id=(
                "combat.scan_for_hostile_target_left"
                if self._initial_search_direction == "LEFT"
                else "combat.scan_for_hostile_target"
            ),
            priority_tier="TARGET_CONTROL",
            reason_code="target_absent_after_nearest_hostile_probe",
            explanation=(
                "The nearest-hostile probe found no target; rotate the view once within "
                "the bounded search budget before probing again."
            ),
            requested_control=f"TURN_{self._initial_search_direction}",
            preconditions=("target=null", "in_combat=false", "player_health_pct>25"),
            confidence=observation.confidence,
            bearing=None,
        )

    def decide(
        self,
        observation: CombatObservationState,
        *,
        decision_id: str,
        bearing: TargetBearingState | None = None,
        motion_managed: bool = False,
    ) -> CombatDecision:
        common = {
            "decision_id": decision_id,
            "observation": observation,
            "confidence": observation.confidence,
            "bearing": bearing,
        }
        if not observation.player_alive:
            return CombatDecision(
                **common,
                action_id="combat.stop_player_dead",
                priority_tier="SURVIVAL",
                reason_code="player_dead",
                explanation="Player death is observed; every combat action must stop.",
                requested_control=None,
                preconditions=("player_alive=false",),
            )
        if observation.player_health_pct <= self.MIN_SURVIVAL_HEALTH_PCT:
            return CombatDecision(
                **common,
                action_id="combat.request_safe_retreat",
                priority_tier="SURVIVAL",
                reason_code="player_health_critical",
                explanation="Health crossed the bounded survival threshold; damage is subordinate to retreat.",
                requested_control="MOVE_BACKWARD",
                preconditions=("player_alive=true", "player_health_pct<=25"),
            )
        target = observation.target
        if target is None:
            return CombatDecision(
                **common,
                action_id="combat.acquire_hostile_target",
                priority_tier="TARGET_CONTROL",
                reason_code="target_absent",
                explanation="No target is observed; no damage action is valid.",
                requested_control="TARGET_NEAREST_HOSTILE",
                preconditions=("target=null",),
            )
        if target.is_player:
            return CombatDecision(
                **common,
                action_id="combat.reject_player_target",
                priority_tier="SAFETY",
                reason_code="player_target_forbidden",
                explanation="The bounded LAB PvE policy never attacks a player target.",
                requested_control=None,
                preconditions=("target.is_player=true",),
            )
        if not target.attackable_npc:
            return CombatDecision(
                **common,
                action_id="combat.reject_non_hostile_target",
                priority_tier="SAFETY",
                reason_code="target_not_hostile",
                explanation="The observed target is not attackable by the player.",
                requested_control=None,
                preconditions=("target.hostile=false",),
            )
        if target.dead or target.health_pct == 0:
            return CombatDecision(
                **common,
                action_id="combat.target_defeated",
                priority_tier="RECOVERY",
                reason_code="target_dead",
                explanation="The target is dead; stop damage and hand off to loot/recovery.",
                requested_control=None,
                preconditions=("target.dead=true",),
            )
        if target.level is None or target.level > observation.player_level + 1:
            return CombatDecision(
                **common,
                action_id="combat.reject_risky_target",
                priority_tier="SAFETY",
                reason_code="target_level_out_of_bounds",
                explanation="The first LAB gate accepts only known targets at most one level above Predator.",
                requested_control=None,
                preconditions=("target.level<=player.level+1",),
            )
        if not all(
            action.exact_binding
            for action in (
                observation.attack,
                observation.sinister_strike,
                observation.eviscerate,
            )
        ):
            return CombatDecision(
                **common,
                action_id="combat.stop_action_binding_mismatch",
                priority_tier="SAFETY",
                reason_code="action_binding_mismatch",
                explanation="One or more required action slots do not match the reviewed Rogue abilities.",
                requested_control=None,
                preconditions=("slots_1_2_3_exact=true",),
            )
        known_ranges = tuple(
            action.in_range
            for action in (observation.attack, observation.sinister_strike)
            if action.in_range is not None
        )
        if bearing is None or not bearing.is_bound_to(observation):
            return CombatDecision(
                **common,
                action_id="combat.hold_bearing_unavailable",
                priority_tier="TARGET_CONTROL",
                reason_code="target_bearing_unavailable",
                explanation="Damage and movement wait for an exact selected-target bearing from the same captured frame.",
                requested_control=None,
                preconditions=("target.hostile=true", "target_bearing=unavailable"),
            )
        magnetic_error = (
            bearing.offset_x_normalized
            if bearing.tracking_state == "VISIBLE"
            else None
        )
        if (
            not motion_managed
            and magnetic_error is not None
            and magnetic_error < -self.MAGNETIC_FACING_TOLERANCE
        ):
            return CombatDecision(
                **common,
                action_id="combat.turn_toward_target_left",
                priority_tier="TARGET_CONTROL",
                reason_code="selected_target_visible_left",
                explanation="The selected-target indicator is left of the bounded center corridor; face it before movement or damage.",
                requested_control="TURN_LEFT",
                preconditions=("target.hostile=true", "target_bearing=LEFT"),
            )
        if (
            not motion_managed
            and magnetic_error is not None
            and magnetic_error > self.MAGNETIC_FACING_TOLERANCE
        ):
            return CombatDecision(
                **common,
                action_id="combat.turn_toward_target_right",
                priority_tier="TARGET_CONTROL",
                reason_code="selected_target_visible_right",
                explanation="The selected-target indicator is right of the bounded center corridor; face it before movement or damage.",
                requested_control="TURN_RIGHT",
                preconditions=("target.hostile=true", "target_bearing=RIGHT"),
            )
        if bearing.tracking_state != "VISIBLE":
            if motion_managed:
                return CombatDecision(
                    **common,
                    action_id="combat.monitor_continuous_reacquisition",
                    priority_tier="TARGET_CONTROL",
                    reason_code="continuous_motion_reacquiring_selected_target",
                    explanation="The movement engine owns a continuous held-RMB search until the exact selected-target marker is visible.",
                    requested_control=None,
                    preconditions=("target.hostile=true", "target_bearing!=VISIBLE", "continuous_motion=true"),
                )
            return CombatDecision(
                **common,
                action_id=(
                    "combat.search_selected_target_left"
                    if self._initial_search_direction == "LEFT"
                    else "combat.search_selected_target"
                ),
                priority_tier="TARGET_CONTROL",
                reason_code="selected_target_not_visible",
                explanation="The exact hostile target remains selected but its visual indicator is absent or ambiguous; use one bounded spatial-memory search pulse.",
                requested_control=f"TURN_{self._initial_search_direction}",
                preconditions=("target.hostile=true", "target_bearing!=VISIBLE"),
            )
        if (
            motion_managed
            and magnetic_error is not None
            and abs(magnetic_error) > self.MAGNETIC_FACING_TOLERANCE
        ):
            return CombatDecision(
                **common,
                action_id="combat.monitor_continuous_facing",
                priority_tier="TARGET_CONTROL",
                reason_code="continuous_motion_aligning_selected_target",
                explanation=(
                    "The magnetic held-RMB servo must center the exact selected "
                    "target before any melee action is authorized."
                ),
                requested_control=None,
                preconditions=(
                    "target.hostile=true",
                    "target_bearing=VISIBLE",
                    "target_facing_aligned=false",
                    "continuous_motion=true",
                ),
            )
        if known_ranges and not any(known_ranges):
            if motion_managed:
                return CombatDecision(
                    **common,
                    action_id="combat.monitor_continuous_approach",
                    priority_tier="TARGET_CONTROL",
                    reason_code="continuous_motion_approaching_target",
                    explanation="The movement engine owns held forward motion and magnetic mouse-facing; the spell policy waits for melee range.",
                    requested_control=None,
                    preconditions=("target.hostile=true", "melee_range=false", "continuous_motion=true"),
                )
            return CombatDecision(
                **common,
                action_id="combat.approach_target",
                priority_tier="TARGET_CONTROL",
                reason_code="target_out_of_melee_range",
                explanation="The exact melee actions report out of range; approach is required before damage.",
                requested_control="MOVE_FORWARD",
                preconditions=("target.hostile=true", "melee_range=false"),
            )
        if not observation.attack.current:
            auto_attack_range_confirmed = (
                observation.attack.in_range is True
                or (
                    observation.attack.in_range is None
                    and observation.sinister_strike.exact_binding
                    and observation.sinister_strike.in_range is True
                )
            )
            if observation.attack.usable and auto_attack_range_confirmed:
                return CombatDecision(
                    **common,
                    action_id="rogue.auto_attack",
                    priority_tier="DAMAGE",
                    reason_code="auto_attack_not_started",
                    explanation="Start the exact auto-attack slot once after the Attack slot or exact Sinister Strike slot confirms melee range, then verify the next frame.",
                    requested_control="ACTION_SLOT_1",
                    preconditions=("slot1.exact=true", "slot1.usable=true", "melee_range_witness=true"),
                )
            return CombatDecision(
                **common,
                action_id="combat.hold_range_unknown",
                priority_tier="TARGET_CONTROL",
                reason_code="auto_attack_not_actionable",
                explanation="Auto-attack is not active and its usable/range state is not safely actionable.",
                requested_control=None,
                preconditions=("slot1.current=false",),
            )
        finisher_estimate = None
        should_finish = False
        if observation.combo_points >= 1:
            finisher_estimate = estimate_rank1_eviscerate(
                combo_points=observation.combo_points,
                attack_power=observation.player_attack_power,
                target_health_current=target.health_current,
            )
            should_finish = (
                finisher_estimate.likely_kill
                or observation.combo_points == 5
            )
        if should_finish and observation.player_energy >= self.EVISCERATE_ENERGY:
            if (
                observation.eviscerate.usable
                and observation.eviscerate.cooldown_ready
                and observation.eviscerate.in_range is True
            ):
                assert finisher_estimate is not None
                if finisher_estimate.conservative_kill:
                    reason_code = "finisher_conservative_kill_window"
                elif finisher_estimate.likely_kill:
                    reason_code = "finisher_likely_kill_window"
                else:
                    reason_code = "finisher_combo_cap_window"
                return CombatDecision(
                    **common,
                    action_id="rogue.eviscerate",
                    priority_tier="DAMAGE",
                    reason_code=reason_code,
                    explanation=(
                        "Eviscerate is exact, ready and in range; its client-build "
                        f"damage band is {finisher_estimate.raw_min}-"
                        f"{finisher_estimate.raw_max}, its conservative and likely "
                        f"post-armor estimates are {finisher_estimate.conservative_after_armor} "
                        f"and {finisher_estimate.likely_after_armor}, and the "
                        f"target has {target.health_current} health."
                    ),
                    requested_control="ACTION_SLOT_3",
                    preconditions=(
                        "combo_points>=1",
                        f"target.health_current={target.health_current}",
                        f"eviscerate.raw_min={finisher_estimate.raw_min}",
                        f"eviscerate.raw_max={finisher_estimate.raw_max}",
                        f"eviscerate.likely_after_armor={finisher_estimate.likely_after_armor}",
                        f"eviscerate.likely_overkill={finisher_estimate.likely_overkill}",
                        "slot3.ready=true",
                        "slot3.in_range=true",
                    ),
                )
        if observation.player_energy >= self.SINISTER_STRIKE_ENERGY:
            if (
                observation.sinister_strike.usable
                and observation.sinister_strike.cooldown_ready
                and observation.sinister_strike.in_range is True
            ):
                return CombatDecision(
                    **common,
                    action_id="rogue.sinister_strike",
                    priority_tier="DAMAGE",
                    reason_code="builder_window_open",
                    explanation="Sinister Strike is exact, usable, ready, in range and energy-funded.",
                    requested_control="ACTION_SLOT_2",
                    preconditions=("energy>=45", "slot2.ready=true", "slot2.in_range=true"),
                )
        if not observation.sinister_strike.cooldown_ready:
            reason_code = "global_cooldown_active"
            explanation = "The builder is cooling down; preserve auto-attack and wait for a fresh frame."
        else:
            reason_code = "energy_regeneration"
            explanation = "Energy is below the next safe ability cost; preserve auto-attack and wait."
        if (
            not motion_managed
            and
            observation.in_combat
            and known_ranges
            and any(known_ranges)
            and observation.sequence % 8 == 7
        ):
            orbit_left = bool(target.identity_crc16 & 1)
            return CombatDecision(
                **common,
                action_id=(
                    "combat.orbit_target_left"
                    if orbit_left
                    else "combat.orbit_target_right"
                ),
                priority_tier="TARGET_CONTROL",
                reason_code=f"magnetic_orbit_{reason_code}",
                explanation=(
                    "The selected hostile is centered and in melee range; use one short "
                    "target-relative strafe pulse during the ability wait, then reacquire "
                    "a fresh bearing before any further movement or damage."
                ),
                requested_control="STRAFE_LEFT" if orbit_left else "STRAFE_RIGHT",
                preconditions=(
                    "in_combat=true",
                    "target_bearing=CENTER",
                    "melee_range=true",
                    "slot1.current=true",
                ),
            )
        return CombatDecision(
            **common,
            action_id="combat.monitor_auto_attack",
            priority_tier="DAMAGE",
            reason_code=reason_code,
            explanation=explanation,
            requested_control=None,
            preconditions=("slot1.current=true",),
        )
