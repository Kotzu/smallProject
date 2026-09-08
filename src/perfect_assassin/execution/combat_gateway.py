from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from threading import Lock, RLock
from typing import Any, Callable, Protocol

from perfect_assassin.brain.combat import CombatDecision, RogueLevelOneCombatPolicy
from perfect_assassin.domain.combat import CombatObservationState, TargetBearingState
from perfect_assassin.domain.combat_range import RangeBand, rogue_ability_range
from perfect_assassin.domain.facing import ContinuousMagneticFacingController
from perfect_assassin.execution.combat_authorization import (
    ALLOWED_COMBAT_CONTROLS,
    COMBAT_EXECUTION_CAPABILITY,
    COMBAT_MODE,
)
from perfect_assassin.execution.combat_runtime_arm import CombatRuntimeArm
from perfect_assassin.execution.contracts import AuthorityBinding
from perfect_assassin.execution.ports import (
    CooperativeCancellation,
    InputCancelledError,
    InputSink,
    MonotonicClock,
    SinkExecutionBudget,
)


class CombatExecutionError(RuntimeError):
    pass


class CombatMotionPort(Protocol):
    """Optional client-only motion engine; no realm/server API dependency."""

    def update(
        self,
        observation: CombatObservationState,
        bearing: TargetBearingState | None,
    ) -> dict[str, Any]: ...

    def release(self) -> None: ...

    def close(self) -> None: ...


class CombatRunControlPort(Protocol):
    @property
    def total_paused_ms(self) -> float: ...

    def checkpoint(self, release_motion: Callable[[], None]) -> None: ...


class ControlledCombatEncounterFailure(CombatExecutionError):
    """Fail-closed encounter stop carrying immutable evidence collected so far."""

    def __init__(self, detail: str, *, record: dict[str, Any]) -> None:
        super().__init__(detail)
        self._record = record

    def to_record(self) -> dict[str, Any]:
        return copy.deepcopy(self._record)


MAX_TARGET_CYCLES = 2
TARGET_CHANGE_OBSERVATION_BUDGET = 8
VISIBLE_ACQUISITION_SAFE_X_MIN = 0.12
VISIBLE_ACQUISITION_SAFE_X_MAX = 0.88
# A target-free nameplate has no CRC binding yet.  Do not click the first frame
# exposed by a camera turn: stop input and require the same candidate cluster to
# remain at nearly the same screen point in a second fresh observation.
VISIBLE_ACQUISITION_STABILITY_MAX_DISPLACEMENT = 0.035
VISIBLE_ACQUISITION_STABILITY_WAIT_MS = 75
# The selected-target circle can disappear briefly behind terrain, foliage, or
# the player model while the target remains selected.  At the live capture rate
# ten observations are roughly half a second: long enough to absorb that visual
# flicker, but still bounded before the coarse search controller is allowed.
TRANSIENT_BEARING_LOSS_OBSERVATION_BUDGET = 10
DAMAGE_CONFIRMATION_OBSERVATION_BUDGET = 8
# A lethal strike clears the selected unit one or two rendered frames before
# PLAYER_REGEN_ENABLED reaches the visible HUD.  Permit only a short, target-null
# settling window; selecting a different unit still fails continuity closed.
LETHAL_TARGET_CLEAR_SETTLE_OBSERVATION_BUDGET = 12
# A lethal auto-attack can land while the visual servo is correcting facing.
# Once damage progress is proven, stop issuing input at the turn budget and let
# the HUD settle long enough to expose target=null/out-of-combat or target.dead.
POST_DAMAGE_TARGET_SETTLE_OBSERVATION_BUDGET = 50
# The screen transport is sampled while the 3D scene is moving.  A single
# otherwise-valid CRC can therefore be a torn frame.  Never act on a new
# identity while continuity is uncertain; require the same mismatch in three
# consecutive fresh observations before failing closed.
UNEXPECTED_TARGET_MISMATCH_OBSERVATION_BUDGET = 2
# The addon already converts the selected nameplate center into a model/corpse
# point (+0.11 in top-origin client coordinates).  Search only a tiny cross
# around that reviewed point; never apply a second large compensation here.
CORPSE_INTERACT_OFFSETS = (
    (0.00, 0.00),
    (0.00, 0.04),
    (-0.04, 0.02),
    (0.04, 0.02),
    (0.00, -0.04),
)
# Dead 2.4.3 units can lose their nameplate immediately.  When the exact dead
# CRC is still selected, its melee corpse is normally at the player's feet.
# This bounded lower-center point is a last-resort visible-world click anchor;
# LOOT_OPENED remains mandatory, and the tiny cross stays globally bounded.
CORPSE_FALLBACK_INTERACT_X_NORMALIZED = 0.50
CORPSE_FALLBACK_INTERACT_Y_NORMALIZED = 0.67
LOOT_CONFIRMATION_OBSERVATIONS_PER_ATTEMPT = 4


@dataclass(slots=True)
class _PendingDamageConfirmation:
    action_id: str
    reason_code: str
    target_identity_crc16: int
    target_health_current: int
    player_energy: int
    combo_points: int
    observations: int = 0

    @property
    def conservative_lethal_finisher(self) -> bool:
        return (
            self.action_id == "rogue.eviscerate"
            and self.reason_code == "finisher_conservative_kill_window"
        )


@dataclass(frozen=True, slots=True)
class _PendingVisibleAcquisition:
    x_normalized: float
    y_normalized: float
    candidate_count: int
    sequence: int

    def matches(self, observation: CombatObservationState) -> bool:
        x_normalized = observation.acquisition_x_normalized
        y_normalized = observation.acquisition_y_normalized
        return (
            observation.sequence != self.sequence
            and x_normalized is not None
            and y_normalized is not None
            and observation.visible_attackable_candidate_count
            == self.candidate_count
            and abs(x_normalized - self.x_normalized)
            <= VISIBLE_ACQUISITION_STABILITY_MAX_DISPLACEMENT
            and abs(y_normalized - self.y_normalized)
            <= VISIBLE_ACQUISITION_STABILITY_MAX_DISPLACEMENT
        )


@dataclass(frozen=True, slots=True)
class CombatInputPrimitive:
    primitive_id: str
    lease_id: str
    binding: AuthorityBinding
    owner_id: str
    runtime_arm_nonce: str
    mode: str
    capability: str
    sequence: int
    controls: tuple[str, ...]
    hold_duration_ms: int
    max_execution_envelope_ms: int
    mouse_delta_x: int | None
    clock_id: str
    issued_at_monotonic_ms: float
    expires_at_monotonic_ms: float
    mouse_click_x_normalized: float | None = None
    mouse_click_y_normalized: float | None = None
    mouse_delta_y: int | None = None

    def __post_init__(self) -> None:
        if self.mode != COMBAT_MODE or self.capability != COMBAT_EXECUTION_CAPABILITY:
            raise ValueError("combat primitive mode/capability mismatch")
        if self.controls not in tuple((control,) for control in ALLOWED_COMBAT_CONTROLS):
            raise ValueError("combat primitive control is not allowlisted")
        if self.controls == ("MOVE_FORWARD",):
            if (self.hold_duration_ms, self.max_execution_envelope_ms) != (250, 300):
                raise ValueError("combat primitive forward timing is not exact")
            expected_hold = self.hold_duration_ms
            expected_envelope = self.max_execution_envelope_ms
        elif self.controls in {("STRAFE_LEFT",), ("STRAFE_RIGHT",)}:
            expected_hold, expected_envelope = 90, 140
        elif self.controls in {("TURN_LEFT",), ("TURN_RIGHT",)}:
            allowed_turn_timings = {
                (25, 175),
                (35, 185),
                (50, 200),
                (200, 350),
            }
            if (
                self.hold_duration_ms,
                self.max_execution_envelope_ms,
            ) not in allowed_turn_timings:
                raise ValueError("combat primitive turn timing is not exact")
            expected_hold = self.hold_duration_ms
            expected_envelope = self.max_execution_envelope_ms
            if (
                type(self.mouse_delta_x) is not int
                or self.mouse_delta_x == 0
                or abs(self.mouse_delta_x) not in {
                    1, 2, 3, 4, 5, 6, 7, 8, 14, 24, 28, 200,
                }
                or (self.controls == ("TURN_LEFT",) and self.mouse_delta_x >= 0)
                or (self.controls == ("TURN_RIGHT",) and self.mouse_delta_x <= 0)
            ):
                raise ValueError("combat mouse turn delta is not exact")
        elif self.controls in {
            ("INTERACT_TARGET",),
            ("TARGET_VISIBLE_HOSTILE",),
        }:
            expected_hold, expected_envelope = 25, 125
        else:
            expected_hold, expected_envelope = 25, 75
        if self.controls not in {("TURN_LEFT",), ("TURN_RIGHT",)} and self.mouse_delta_x is not None:
            raise ValueError("keyboard combat primitive cannot carry mouse delta")
        if self.mouse_delta_y is not None and (
            self.controls != ("TURN_RIGHT",)
            or self.mouse_delta_x != 28
            or self.mouse_delta_y not in {-60, 120}
        ):
            raise ValueError("combat camera-pitch correction is not exact")
        if (self.mouse_click_x_normalized is None) != (self.mouse_click_y_normalized is None):
            raise ValueError("mouse click point must be complete")
        if self.controls in {
            ("INTERACT_TARGET",),
            ("TARGET_VISIBLE_HOSTILE",),
        }:
            if (
                self.mouse_click_x_normalized is None
                or not 0.0 < self.mouse_click_x_normalized < 1.0
                or not 0.0 < self.mouse_click_y_normalized < 1.0
            ):
                raise ValueError("visible mouse action requires a bounded click point")
        elif self.mouse_click_x_normalized is not None:
            raise ValueError("only a reviewed visible mouse action can carry a click point")
        if (
            self.hold_duration_ms != expected_hold
            or self.max_execution_envelope_ms != expected_envelope
        ):
            raise ValueError("combat primitive timing is not exact")
        if (
            not isfinite(self.issued_at_monotonic_ms)
            or not isfinite(self.expires_at_monotonic_ms)
            or self.expires_at_monotonic_ms
            < self.issued_at_monotonic_ms + self.max_execution_envelope_ms
        ):
            raise ValueError("combat primitive lifetime is invalid")


class CombatObservationSource(Protocol):
    def next_observation(self) -> CombatObservationState: ...

    def bearing_for(
        self, observation: CombatObservationState
    ) -> TargetBearingState | None: ...


class CombatActionGateway:
    """One-arm combat action gate; decisions remain non-authoritative proposals."""

    def __init__(
        self,
        *,
        arm: CombatRuntimeArm,
        sink: InputSink,
        clock: MonotonicClock,
    ) -> None:
        if clock.clock_id != arm.clock_id:
            raise ValueError("combat gate clock identity mismatch")
        self._arm = arm
        self._sink = sink
        self._clock = clock
        self._cancel = CooperativeCancellation()
        self._action_count = 0
        self._approach_count = 0
        self._turn_count = 0
        self._facing_turn_count = 0
        self._loot_interact_count = 0
        self._defeated_target_identity: int | None = None
        self._closed = False
        self._state_epoch = 0
        self._state_lock = RLock()
        self._execution_lock = Lock()
        # The compatibility gateway emits one reviewed bounded primitive at a
        # time.  Predictive braking and the faster 16 px tracking envelope are
        # reserved for the continuous held-RMB motion engine.
        self._facing_servo = ContinuousMagneticFacingController(
            proportional_gain_px=60.0,
            prediction_horizon_s=0.0,
            prediction_coast_tolerance=0.0,
            max_delta_px=8,
        )
        self._binding = AuthorityBinding(
            actor_id=arm.actor_id,
            actor_instance_id=arm.actor_instance_id,
            actor_role="lab_clone",
            decision_context="lab_clone",
            target_profile="tbc_243_lab",
            target_instance_id=arm.actor_instance_id,
            authorization_id="execution:tbc243-lab:combat-f4a-bounded",
            authorization_sha256=arm.authorization_sha256,
        )

    @property
    def action_count(self) -> int:
        return self._action_count

    @property
    def approach_count(self) -> int:
        return self._approach_count

    @property
    def max_approach_pulses(self) -> int:
        return int(self._arm.policy["max_approach_pulses"])

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def max_turn_pulses(self) -> int:
        return int(self._arm.policy["max_turn_pulses"])

    @property
    def facing_turn_count(self) -> int:
        return self._facing_turn_count

    @property
    def max_facing_turn_pulses(self) -> int:
        return int(self._arm.policy["max_facing_turn_pulses"])

    @property
    def max_target_level_delta(self) -> int:
        return int(self._arm.policy["max_target_level_delta"])

    @property
    def max_encounter_seconds(self) -> int:
        return int(self._arm.policy["max_encounter_seconds"])

    @property
    def max_acquisition_seconds(self) -> int:
        return int(self._arm.policy["max_acquisition_seconds"])

    @property
    def max_combat_seconds(self) -> int:
        return int(self._arm.policy["max_combat_seconds"])

    @property
    def max_recovery_seconds(self) -> int:
        return int(self._arm.policy["max_recovery_seconds"])

    def cancel_for_manual_takeover(self) -> None:
        with self._state_lock:
            self._cancel.cancel()
            self._state_epoch += 1
        self._sink.release_all()

    def bind_defeated_target(self, target_identity_crc16: int) -> None:
        if (
            type(target_identity_crc16) is not int
            or not 1 <= target_identity_crc16 <= 65_535
        ):
            raise CombatExecutionError("defeated target identity is invalid")
        with self._state_lock:
            if self._closed or self._cancel.is_cancelled:
                raise CombatExecutionError("combat gate is cancelled")
            if (
                self._defeated_target_identity is not None
                and self._defeated_target_identity != target_identity_crc16
            ):
                raise CombatExecutionError("defeated target identity cannot be rebound")
            self._defeated_target_identity = target_identity_crc16

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._cancel.cancel()
            self._state_epoch += 1
        self._sink.release_all()

    def execute(
        self,
        decision: CombatDecision,
        observation: CombatObservationState,
    ) -> dict[str, Any]:
        if not self._execution_lock.acquire(blocking=False):
            raise CombatExecutionError("combat gate permits only one in-flight action")
        try:
            return self._execute_single_flight(decision, observation)
        finally:
            self._execution_lock.release()

    def _execute_single_flight(
        self,
        decision: CombatDecision,
        observation: CombatObservationState,
    ) -> dict[str, Any]:
        with self._state_lock:
            if self._closed or self._cancel.is_cancelled:
                raise CombatExecutionError("combat gate is cancelled")
            execution_epoch = self._state_epoch
        if decision.observation != observation:
            raise CombatExecutionError("decision is not bound to this observation")
        control = decision.requested_control
        if control not in ALLOWED_COMBAT_CONTROLS:
            raise CombatExecutionError("decision control is not authorized")
        now_ms = self._clock.now_ms()
        if (
            now_ms < self._arm.issued_at_monotonic_ms
            or now_ms >= self._arm.expires_at_monotonic_ms
        ):
            raise CombatExecutionError("combat runtime arm is inactive")
        if not (
            observation.observed_monotonic_s * 1000.0
            <= now_ms
            <= observation.expires_monotonic_s * 1000.0
        ):
            raise CombatExecutionError("combat observation is stale")
        if (
            observation.authorization_sha256 != self._arm.authorization_sha256
            or observation.actor_id != self._arm.actor_id
            or observation.actor_instance_id != self._arm.actor_instance_id
            or observation.target_profile != "tbc_243_lab"
            or observation.provenance_scope != "lab_evaluation_only"
        ):
            raise CombatExecutionError("combat observation authority binding diverges")
        policy = self._arm.policy
        if self._action_count >= policy["max_actions"]:
            raise CombatExecutionError("combat action budget is exhausted")
        if not observation.player_alive:
            raise CombatExecutionError("player is not alive")
        if observation.player_health_pct <= policy["retreat_health_pct"]:
            raise CombatExecutionError("survival threshold blocks further combat")
        target = observation.target
        acquisition_scan = decision.action_id in {
            "combat.scan_for_hostile_target",
            "combat.scan_for_hostile_target_left",
        }
        facing_only = (
            decision.action_id in {
                "combat.turn_toward_target_left",
                "combat.turn_toward_target_right",
            }
            and control in {"TURN_LEFT", "TURN_RIGHT"}
        )
        candidate_facing = decision.action_id in {
            "combat.turn_toward_visible_candidate_left",
            "combat.turn_toward_visible_candidate_right",
        }
        mouse_delta_x: int | None = None
        mouse_delta_y: int | None = None
        mouse_click_x_normalized: float | None = None
        mouse_click_y_normalized: float | None = None
        if control == "TARGET_LAST_HOSTILE":
            if (
                decision.action_id
                not in {
                    "recovery.select_last_defeated",
                    "recovery.reselect_last_defeated_after_miss",
                }
                or self._defeated_target_identity is None
                or observation.in_combat
            ):
                raise CombatExecutionError(
                    "last-hostile recovery requires a bound defeated target out of combat"
                )
            if (
                decision.action_id == "recovery.reselect_last_defeated_after_miss"
                and target is not None
                and target.dead
                and target.identity_crc16 == self._defeated_target_identity
            ):
                raise CombatExecutionError(
                    "miss recovery cannot replace an already exact dead selection"
                )
        elif control == "INTERACT_TARGET":
            if (
                decision.action_id != "recovery.loot_defeated_target"
                or self._defeated_target_identity is None
                or target is None
                or not target.dead
                or target.is_player
                or target.identity_crc16 != self._defeated_target_identity
                or observation.in_combat
            ):
                raise CombatExecutionError(
                    "loot recovery requires the exact selected defeated NPC"
                )
            if self._loot_interact_count >= len(CORPSE_INTERACT_OFFSETS):
                raise CombatExecutionError("corpse interaction search budget is exhausted")
            base_x = (
                target.interact_x_normalized
                if target.interact_x_normalized is not None
                else CORPSE_FALLBACK_INTERACT_X_NORMALIZED
            )
            base_y = (
                target.interact_y_normalized
                if target.interact_y_normalized is not None
                else CORPSE_FALLBACK_INTERACT_Y_NORMALIZED
            )
            x_offset, y_offset = CORPSE_INTERACT_OFFSETS[self._loot_interact_count]
            mouse_click_x_normalized = max(0.05, min(0.95, base_x + x_offset))
            mouse_click_y_normalized = max(0.05, min(0.90, base_y + y_offset))
        elif control == "TARGET_VISIBLE_HOSTILE":
            acquisition_x = observation.acquisition_x_normalized
            acquisition_y = observation.acquisition_y_normalized
            bearing = decision.bearing
            if (
                decision.action_id != "combat.acquire_visible_hostile"
                or target is not None
                or observation.in_combat
                or observation.visible_attackable_candidate_count <= 0
                or acquisition_x is None
                or acquisition_y is None
                or bearing is None
                or not bearing.is_bound_to(observation)
                or bearing.tracking_state != "VISIBLE"
                or bearing.target_identity_crc16 is not None
                or bearing.offset_x_normalized is None
                or bearing.center_y_normalized is None
                or abs((acquisition_x * 2.0 - 1.0) - bearing.offset_x_normalized)
                > 0.01
                or abs(acquisition_y - bearing.center_y_normalized) > 0.01
            ):
                raise CombatExecutionError(
                    "visible hostile selection requires one fresh screen-bound candidate"
                )
            mouse_click_x_normalized = acquisition_x
            mouse_click_y_normalized = acquisition_y
        elif control == "TARGET_NEAREST_HOSTILE":
            if decision.action_id == "combat.acquire_hostile_target":
                if target is not None:
                    raise CombatExecutionError("target acquisition requires target=null")
            elif decision.action_id == "combat.cycle_hostile_target":
                search_budget_exhausted = (
                    self._turn_count >= policy["max_turn_pulses"]
                )
                approach_budget_exhausted = (
                    self._approach_count >= policy["max_approach_pulses"]
                )
                unsafe_level_rejected = (
                    decision.reason_code == "current_target_level_out_of_bounds"
                    and target is not None
                    and target.attackable_npc
                    and (
                        target.level is None
                        or target.level
                        > observation.player_level + policy["max_target_level_delta"]
                    )
                )
                if (
                    target is None
                    or target.dead
                    or not target.hostile
                    or target.is_player
                    or observation.in_combat
                    or not (
                        approach_budget_exhausted
                        or search_budget_exhausted
                        or unsafe_level_rejected
                    )
                ):
                    raise CombatExecutionError(
                        "target cycle requires a bounded pre-combat hostile rejection"
                    )
            elif decision.action_id == "combat.advance_from_looted_corpse":
                if (
                    target is None
                    or not target.dead
                    or target.is_player
                    or observation.in_combat
                ):
                    raise CombatExecutionError(
                        "post-loot target advance requires a selected dead NPC out of combat"
                    )
            else:
                raise CombatExecutionError("target control decision is unsupported")
        elif candidate_facing:
            if (
                control not in {"TURN_LEFT", "TURN_RIGHT"}
                or target is not None
                or observation.in_combat
            ):
                raise CombatExecutionError(
                    "visible-candidate facing requires a target-free pre-combat frame"
                )
        elif acquisition_scan:
            if (
                control not in {"TURN_LEFT", "TURN_RIGHT"}
                or target is not None
                or observation.in_combat
                or decision.bearing is not None
            ):
                raise CombatExecutionError(
                    "target acquisition scan requires a target-free pre-combat frame"
                )
            if self._turn_count >= policy["max_turn_pulses"]:
                raise CombatExecutionError("combat turn-search budget is exhausted")
        elif control not in {
            "TARGET_VISIBLE_HOSTILE",
            "TARGET_LAST_HOSTILE",
            "INTERACT_TARGET",
        }:
            if target is None or target.dead:
                raise CombatExecutionError("combat action requires a live attackable NPC")
            if target.is_player:
                raise CombatExecutionError("player targets are forbidden")
            if not target.attackable_npc:
                raise CombatExecutionError("combat action requires a live attackable NPC")
            if not facing_only and (
                target.level is None
                or target.level > observation.player_level + policy["max_target_level_delta"]
            ):
                raise CombatExecutionError("target level exceeds the controlled gate")
        if control == "MOVE_FORWARD":
            known = tuple(
                state.in_range
                for state in (observation.attack, observation.sinister_strike)
                if state.in_range is not None
            )
            if not known or any(known):
                raise CombatExecutionError("approach requires known out-of-range melee state")
            if self._approach_count >= policy["max_approach_pulses"]:
                raise CombatExecutionError("combat approach budget is exhausted")
        if control in {
            "MOVE_FORWARD",
            "STRAFE_LEFT",
            "STRAFE_RIGHT",
            "TURN_LEFT",
            "TURN_RIGHT",
        } and not acquisition_scan:
            bearing = decision.bearing
            if bearing is None or not bearing.is_bound_to(observation):
                raise CombatExecutionError("combat steering lacks exact bearing binding")
            if not (
                bearing.observed_monotonic_s * 1000.0
                <= now_ms
                <= bearing.expires_monotonic_s * 1000.0
            ):
                raise CombatExecutionError("combat target bearing is stale")
            if (
                bearing.authorization_sha256 != self._arm.authorization_sha256
                or bearing.provenance_scope != "lab_evaluation_only"
            ):
                raise CombatExecutionError("combat target bearing authority diverges")
            expected_direction = {
                "combat.approach_target": ("VISIBLE", "CENTER"),
                "combat.search_selected_target": (None, None),
                "combat.search_selected_target_left": (None, None),
                "combat.normalize_camera_pitch_up": (None, None),
                "combat.normalize_camera_pitch_down": (None, None),
                "combat.orbit_target_left": ("VISIBLE", "CENTER"),
                "combat.orbit_target_right": ("VISIBLE", "CENTER"),
                "combat.turn_toward_visible_candidate_left": ("VISIBLE", "LEFT"),
                "combat.turn_toward_visible_candidate_right": ("VISIBLE", "RIGHT"),
            }.get(decision.action_id)
            if expected_direction is None and decision.action_id not in {
                "combat.turn_toward_target_left",
                "combat.turn_toward_target_right",
            }:
                raise CombatExecutionError("combat steering decision is unsupported")
            if decision.action_id in {
                "combat.search_selected_target",
                "combat.search_selected_target_left",
                "combat.normalize_camera_pitch_up",
                "combat.normalize_camera_pitch_down",
            }:
                if bearing.tracking_state not in {"LOST", "AMBIGUOUS"} or bearing.direction is not None:
                    raise CombatExecutionError("combat search requires a non-visible target bearing")
            elif expected_direction is not None and (
                bearing.tracking_state, bearing.direction
            ) != expected_direction:
                raise CombatExecutionError("combat steering contradicts the target bearing")
            if decision.action_id == "combat.turn_toward_target_left" and not (
                bearing.tracking_state == "VISIBLE"
                and bearing.offset_x_normalized is not None
                and bearing.offset_x_normalized
                < -RogueLevelOneCombatPolicy.MAGNETIC_FACING_TOLERANCE
            ):
                raise CombatExecutionError("left magnetic correction contradicts the target bearing")
            if decision.action_id == "combat.turn_toward_target_right" and not (
                bearing.tracking_state == "VISIBLE"
                and bearing.offset_x_normalized is not None
                and bearing.offset_x_normalized
                > RogueLevelOneCombatPolicy.MAGNETIC_FACING_TOLERANCE
            ):
                raise CombatExecutionError("right magnetic correction contradicts the target bearing")
            if (
                decision.action_id
                in {"combat.search_selected_target", "combat.search_selected_target_left"}
                and self._turn_count >= policy["max_turn_pulses"]
            ):
                raise CombatExecutionError("combat turn-search budget is exhausted")
            if (
                decision.action_id
                in {"combat.turn_toward_target_left", "combat.turn_toward_target_right"}
                and self._facing_turn_count >= policy["max_facing_turn_pulses"]
            ):
                raise CombatExecutionError("combat visible-facing budget is exhausted")
        if control in {"STRAFE_LEFT", "STRAFE_RIGHT"}:
            known = tuple(
                state.in_range
                for state in (observation.attack, observation.sinister_strike)
                if state.in_range is not None
            )
            if (
                not observation.in_combat
                or not observation.attack.current
                or not known
                or not any(known)
            ):
                raise CombatExecutionError(
                    "combat orbit requires active auto-attack and exact melee range"
                )
        action_states = {
            "ACTION_SLOT_1": observation.attack,
            "ACTION_SLOT_2": observation.sinister_strike,
            "ACTION_SLOT_3": observation.eviscerate,
        }
        action_abilities = {
            "ACTION_SLOT_1": "rogue.auto_attack",
            "ACTION_SLOT_2": "rogue.sinister_strike",
            "ACTION_SLOT_3": "rogue.eviscerate",
        }
        if control in action_states:
            action = action_states[control]
            ability_id = action_abilities[control]
            range_confirmed = (
                rogue_ability_range(ability_id).classify(
                    client_in_range=action.in_range,
                )
                is RangeBand.IN_RANGE
            )
            if control == "ACTION_SLOT_1" and action.in_range is None:
                range_confirmed = (
                    observation.sinister_strike.exact_binding
                    and rogue_ability_range("rogue.sinister_strike").classify(
                        client_in_range=observation.sinister_strike.in_range,
                    )
                    is RangeBand.IN_RANGE
                )
            if not (
                action.exact_binding
                and action.usable
                and action.cooldown_ready
                and range_confirmed
            ):
                raise CombatExecutionError("requested action is not exact and actionable")
        if control == "MOVE_FORWARD":
            hold_ms = policy["approach_hold_duration_ms"]
            envelope_ms = hold_ms + 50
        elif control in {"STRAFE_LEFT", "STRAFE_RIGHT"}:
            hold_ms = policy["orbit_hold_duration_ms"]
            envelope_ms = hold_ms + 50
        elif control in {"TURN_LEFT", "TURN_RIGHT"}:
            bearing = decision.bearing
            if bearing is None and not acquisition_scan:
                raise CombatExecutionError("combat turn lacks bearing evidence")
            if decision.action_id == "combat.normalize_camera_pitch_up":
                hold_ms = policy["turn_far_hold_duration_ms"]
                delta_magnitude = policy["turn_far_mouse_delta_x"]
                mouse_delta_y = -60
            elif decision.action_id == "combat.normalize_camera_pitch_down":
                hold_ms = policy["turn_far_hold_duration_ms"]
                delta_magnitude = policy["turn_far_mouse_delta_x"]
                mouse_delta_y = 120
            elif decision.action_id in {
                "combat.search_selected_target",
                "combat.search_selected_target_left",
                "combat.scan_for_hostile_target",
                "combat.scan_for_hostile_target_left",
            }:
                hold_ms = policy["search_turn_hold_duration_ms"]
                delta_magnitude = policy["search_turn_mouse_delta_x"]
            elif decision.action_id in {
                "combat.turn_toward_target_left",
                "combat.turn_toward_target_right",
            }:
                servo = self._facing_servo.decide(bearing)
                if servo.state != "TRACK" or servo.mouse_delta_x == 0:
                    raise CombatExecutionError("magnetic facing servo produced no correction")
                hold_ms = policy["turn_near_hold_duration_ms"]
                delta_magnitude = abs(servo.mouse_delta_x)
            else:
                offset = bearing.offset_x_normalized
                if offset is None or not isfinite(offset):
                    raise CombatExecutionError("combat turn offset is invalid")
                magnitude = abs(offset)
                if magnitude >= policy["turn_far_offset_threshold"]:
                    hold_ms = policy["turn_far_hold_duration_ms"]
                    delta_magnitude = policy["turn_far_mouse_delta_x"]
                elif magnitude >= policy["turn_medium_offset_threshold"]:
                    hold_ms = policy["turn_medium_hold_duration_ms"]
                    delta_magnitude = policy["turn_medium_mouse_delta_x"]
                else:
                    hold_ms = policy["turn_near_hold_duration_ms"]
                    delta_magnitude = policy["turn_near_mouse_delta_x"]
            # Win32 relative mouse-X and the bound TBC client use the native
            # direction: negative RMB motion yaws left, positive yaws right.
            mouse_delta_x = (
                -int(delta_magnitude) if control == "TURN_LEFT" else int(delta_magnitude)
            )
            envelope_ms = hold_ms + policy["turn_execution_slack_ms"]
        elif control in {"INTERACT_TARGET", "TARGET_VISIBLE_HOSTILE"}:
            hold_ms = policy["action_key_hold_ms"]
            envelope_ms = 125
        else:
            hold_ms = policy["action_key_hold_ms"]
            envelope_ms = 75
        if now_ms + envelope_ms > self._arm.expires_at_monotonic_ms:
            raise CombatExecutionError("combat action cannot fit inside the arm")
        sequence = self._action_count + 1
        primitive = CombatInputPrimitive(
            primitive_id=f"primitive:combat:{self._arm.arm_nonce}:{sequence}",
            lease_id=f"lease:combat:{self._arm.arm_nonce}",
            binding=self._binding,
            owner_id="controller:combat:f4a",
            runtime_arm_nonce=self._arm.arm_nonce,
            mode=COMBAT_MODE,
            capability=COMBAT_EXECUTION_CAPABILITY,
            sequence=sequence,
            controls=(control,),
            hold_duration_ms=hold_ms,
            max_execution_envelope_ms=envelope_ms,
            mouse_delta_x=mouse_delta_x,
            clock_id=self._arm.clock_id,
            issued_at_monotonic_ms=now_ms,
            expires_at_monotonic_ms=min(
                now_ms + 1_000.0,
                self._arm.expires_at_monotonic_ms,
            ),
            mouse_click_x_normalized=mouse_click_x_normalized,
            mouse_click_y_normalized=mouse_click_y_normalized,
            mouse_delta_y=mouse_delta_y,
        )
        budget = SinkExecutionBudget(
            clock_id=self._arm.clock_id,
            started_at_monotonic_ms=now_ms,
            absolute_deadline_monotonic_ms=now_ms + envelope_ms,
            remaining_ms=float(envelope_ms),
            hold_duration_ms=hold_ms,
            max_execution_envelope_ms=envelope_ms,
        )
        if (
            getattr(self._sink, "supports_cooperative_cancellation", None) is not True
            or type(getattr(self._sink, "max_apply_block_ms", None)) is not int
            or not 1 <= self._sink.max_apply_block_ms <= 1_250
        ):
            raise CombatExecutionError("combat input sink safety contract is invalid")
        with self._state_lock:
            if (
                self._closed
                or self._cancel.is_cancelled
                or self._state_epoch != execution_epoch
            ):
                raise CombatExecutionError("manual takeover cancelled combat")
        try:
            self._sink.apply_bounded(primitive, self._cancel, budget)
        except InputCancelledError as error:
            raise CombatExecutionError("manual takeover cancelled combat") from error
        except Exception as error:
            raise CombatExecutionError(
                "combat input sink failed closed: "
                f"{type(error).__name__}: {error}"
            ) from error
        finally:
            try:
                self._sink.release_all()
            except Exception as error:
                with self._state_lock:
                    self._closed = True
                    self._state_epoch += 1
                    self._cancel.cancel()
                raise CombatExecutionError("combat input release failed closed") from error
        completed_ms = self._clock.now_ms()
        with self._state_lock:
            if (
                self._closed
                or self._cancel.is_cancelled
                or self._state_epoch != execution_epoch
            ):
                raise CombatExecutionError("manual takeover cancelled combat")
            if completed_ms > budget.absolute_deadline_monotonic_ms:
                self._closed = True
                self._state_epoch += 1
                self._cancel.cancel()
                raise CombatExecutionError("combat action exceeded its execution envelope")
            self._action_count += 1
            if control == "MOVE_FORWARD":
                self._approach_count += 1
                self._turn_count = 0
            elif decision.action_id in {
                "combat.scan_for_hostile_target",
                "combat.scan_for_hostile_target_left",
                "combat.search_selected_target",
                "combat.search_selected_target_left",
            }:
                self._turn_count += 1
                self._facing_turn_count = 0
            elif control in {"TURN_LEFT", "TURN_RIGHT"}:
                # A visible selected target ends the blind-search phase. Fine
                # magnetic corrections are still bounded by max_actions and
                # the encounter deadline, but must not consume the next
                # off-screen reacquisition budget.
                self._turn_count = 0
                self._facing_turn_count += 1
            elif decision.action_id in {
                "combat.acquire_visible_hostile",
                "combat.acquire_hostile_target",
                "combat.cycle_hostile_target",
                "combat.advance_from_looted_corpse",
            }:
                self._approach_count = 0
                self._turn_count = 0
                self._facing_turn_count = 0
            elif control == "INTERACT_TARGET":
                self._loot_interact_count += 1
        return {
            "record_type": "combat_action_execution",
            "schema_version": "0.1",
            "primitive_id": primitive.primitive_id,
            "decision_id": decision.decision_id,
            "observation_id": observation.observation_id,
            "observation_sha256": observation.observation_sha256,
            "target_identity_crc16": (
                None if target is None else target.identity_crc16
            ),
            "control": control,
            "bearing_offset_x_normalized": (
                None if decision.bearing is None else decision.bearing.offset_x_normalized
            ),
            "sequence": sequence,
            "hold_duration_ms": hold_ms,
            "max_execution_envelope_ms": envelope_ms,
            "mouse_delta_x": mouse_delta_x,
            "mouse_delta_y": mouse_delta_y,
            "mouse_click_x_normalized": mouse_click_x_normalized,
            "mouse_click_y_normalized": mouse_click_y_normalized,
            "execution_authority": False,
        }


class ControlledCombatEncounter:
    def __init__(
        self,
        *,
        gateway: CombatActionGateway,
        observations: CombatObservationSource,
        policy: RogueLevelOneCombatPolicy,
        clock: MonotonicClock,
        wait_ms: Callable[[int], None],
        preserve_selected_target: bool = False,
        recover_after_kill: bool = False,
        advance_past_initial_dead_target: bool = False,
        motion: CombatMotionPort | None = None,
        run_control: CombatRunControlPort | None = None,
    ) -> None:
        self._gateway = gateway
        self._observations = observations
        self._policy = policy
        self._clock = clock
        self._wait_ms = wait_ms
        self._preserve_selected_target = preserve_selected_target
        self._recover_after_kill = recover_after_kill
        self._advance_past_initial_dead_target = advance_past_initial_dead_target
        self._motion = motion
        self._run_control = run_control

    def _control_checkpoint(self) -> None:
        if self._run_control is None:
            return
        self._run_control.checkpoint(
            self._motion.release if self._motion is not None else (lambda: None)
        )

    def _active_elapsed_ms(self, started_ms: float, paused_baseline_ms: float) -> float:
        paused_ms = (
            0.0
            if self._run_control is None
            else self._run_control.total_paused_ms - paused_baseline_ms
        )
        return self._clock.now_ms() - started_ms - max(0.0, paused_ms)

    def _complete_with_recovery(
        self,
        result: dict[str, Any],
        *,
        completion_observation: CombatObservationState,
        decisions: list[dict[str, Any]],
        executions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self._recover_after_kill:
            return result
        recovery_started_ms = self._clock.now_ms()
        recovery_paused_ms = (
            0.0 if self._run_control is None else self._run_control.total_paused_ms
        )

        def assert_recovery_deadline() -> None:
            self._control_checkpoint()
            if self._active_elapsed_ms(recovery_started_ms, recovery_paused_ms) > (
                self._gateway.max_recovery_seconds * 1_000
            ):
                raise CombatExecutionError("post-kill recovery deadline expired")

        target_identity = result.get("target_identity_crc16")
        if type(target_identity) is not int:
            raise CombatExecutionError("loot recovery lacks a defeated target identity")
        self._gateway.bind_defeated_target(target_identity)
        selected = completion_observation
        exact_dead_selected = (
            selected.target is not None
            and selected.target.dead
            and not selected.target.is_player
            and selected.target.identity_crc16 == target_identity
            and not selected.in_combat
        )
        if not exact_dead_selected:
            if selected.in_combat:
                raise CombatExecutionError(
                    "last-hostile recovery cannot replace a target during combat"
                )
            select_decision = CombatDecision(
                decision_id=f"decision:{result['encounter_id']}:recovery:select",
                observation=selected,
                action_id="recovery.select_last_defeated",
                priority_tier="RECOVERY",
                reason_code="select_exact_last_defeated_target",
                explanation=(
                    "Select the last hostile only after a CRC-bound kill confirmation, "
                    "then require that exact dead NPC before interaction."
                ),
                requested_control="TARGET_LAST_HOSTILE",
                preconditions=(
                    "in_combat=false",
                    "target is not already the exact defeated NPC",
                    f"defeated_target_crc16={target_identity}",
                ),
                confidence=selected.confidence,
            )
            decisions.append(
                select_decision.to_record(
                    created_at=datetime.now(timezone.utc)
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
            )
            executions.append(self._gateway.execute(select_decision, selected))
            for _ in range(8):
                assert_recovery_deadline()
                self._wait_ms(100)
                selected = self._observations.next_observation()
                if (
                    selected.target is not None
                    and selected.target.dead
                    and not selected.target.is_player
                    and selected.target.identity_crc16 == target_identity
                    and not selected.in_combat
                ):
                    break
            else:
                raise CombatExecutionError(
                    "last-hostile recovery did not select the exact defeated NPC"
                )
        if (
            selected.target is None
            or not selected.target.dead
            or selected.target.is_player
            or selected.target.identity_crc16 != target_identity
            or selected.in_combat
        ):
            raise CombatExecutionError(
                "loot recovery is not bound to the exact defeated NPC"
            )
        loot_sequence_before = selected.loot_event_sequence
        confirmed = None
        for attempt_index in range(len(CORPSE_INTERACT_OFFSETS)):
            suffix = "" if attempt_index == 0 else f":{attempt_index + 1}"
            loot_decision = CombatDecision(
                decision_id=(
                    f"decision:{result['encounter_id']}:recovery:loot{suffix}"
                ),
                observation=selected,
                action_id="recovery.loot_defeated_target",
                priority_tier="RECOVERY",
                reason_code="interact_exact_defeated_target",
                explanation=(
                    "Interact only inside the bounded screen-space search around "
                    "the CRC-bound dead NPC and require a visible LOOT_OPENED "
                    "sequence transition before recovery succeeds."
                ),
                requested_control="INTERACT_TARGET",
                preconditions=(
                    "in_combat=false",
                    "target.dead=true",
                    f"target.identity_crc16={target_identity}",
                    f"corpse_search_attempt={attempt_index + 1}",
                ),
                confidence=selected.confidence,
            )
            decisions.append(
                loot_decision.to_record(
                    created_at=datetime.now(timezone.utc)
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
            )
            executions.append(self._gateway.execute(loot_decision, selected))
            last_observed = selected
            for _ in range(LOOT_CONFIRMATION_OBSERVATIONS_PER_ATTEMPT):
                assert_recovery_deadline()
                self._wait_ms(100)
                observed = self._observations.next_observation()
                last_observed = observed
                if observed.loot_event_sequence != loot_sequence_before:
                    confirmed = observed
                    break
            if confirmed is not None:
                break
            exact_dead_selection = (
                last_observed.target is not None
                and last_observed.target.dead
                and not last_observed.target.is_player
                and last_observed.target.identity_crc16 == target_identity
                and not last_observed.in_combat
            )
            if not exact_dead_selection and last_observed.in_combat:
                raise CombatExecutionError(
                    "corpse interaction miss entered combat; recovery stopped"
                )
            if not exact_dead_selection:
                reselect_decision = CombatDecision(
                    decision_id=(
                        f"decision:{result['encounter_id']}:recovery:reselect:"
                        f"{attempt_index + 1}"
                    ),
                    observation=last_observed,
                    action_id="recovery.reselect_last_defeated_after_miss",
                    priority_tier="RECOVERY",
                    reason_code="restore_exact_defeated_after_missed_click",
                    explanation=(
                        "A missed visible corpse click changed or cleared selection; "
                        "use the normal last-hostile binding once and require the "
                        "same CRC-bound dead NPC before the next bounded point."
                    ),
                    requested_control="TARGET_LAST_HOSTILE",
                    preconditions=(
                        "in_combat=false",
                        f"defeated_target_crc16={target_identity}",
                        "previous_corpse_click_unconfirmed=true",
                    ),
                    confidence=last_observed.confidence,
                )
                decisions.append(
                    reselect_decision.to_record(
                        created_at=datetime.now(timezone.utc)
                        .isoformat(timespec="microseconds")
                        .replace("+00:00", "Z")
                    )
                )
                executions.append(
                    self._gateway.execute(reselect_decision, last_observed)
                )
                restored = None
                for _ in range(TARGET_CHANGE_OBSERVATION_BUDGET):
                    assert_recovery_deadline()
                    self._wait_ms(50)
                    candidate = self._observations.next_observation()
                    if (
                        candidate.target is not None
                        and candidate.target.dead
                        and not candidate.target.is_player
                        and candidate.target.identity_crc16 == target_identity
                        and not candidate.in_combat
                    ):
                        restored = candidate
                        break
                if restored is None:
                    raise CombatExecutionError(
                        "corpse interaction search could not restore the exact defeated NPC"
                    )
                selected = restored
            else:
                selected = last_observed
        if confirmed is None:
            raise CombatExecutionError(
                "LOOT_OPENED was not observed within the bounded corpse search budget"
            )
        assert_recovery_deadline()
        result["actions_executed"] = len(executions)
        result["decisions"] = decisions
        result["executions"] = executions
        result["recovery"] = {
            "status": "LOOT_CONFIRMED",
            "target_identity_crc16": target_identity,
            "loot_event_sequence_before": loot_sequence_before,
            "loot_event_sequence_after": confirmed.loot_event_sequence,
            "confirmation_observation_id": confirmed.observation_id,
            "confirmation_observation_sha256": confirmed.observation_sha256,
            "manual_takeover_available": True,
            "execution_authority": False,
        }
        return result

    def run(self, *, encounter_id: str) -> dict[str, Any]:
        started = self._clock.now_ms()
        started_paused_ms = (
            0.0 if self._run_control is None else self._run_control.total_paused_ms
        )
        target_identity: int | None = None
        observed_target_identity: int | None = None
        expected_target_change = False
        target_change_observations = 0
        target_cycles = 0
        last_visible_bearing_target: int | None = None
        transient_bearing_loss_observations = 0
        post_damage_target_settle_observations = 0
        last_sequence: int | None = None
        duplicate_sequence_count = 0
        pending_damage: _PendingDamageConfirmation | None = None
        pending_visible_acquisition: _PendingVisibleAcquisition | None = None
        last_locked_target_health: int | None = None
        last_locked_target_health_max: int | None = None
        observed_damage_progress = False
        unexpected_target_identity: int | None = None
        unexpected_target_mismatch_observations = 0
        combat_phase_started_ms: float | None = None
        decisions: list[dict[str, Any]] = []
        executions: list[dict[str, Any]] = []
        motion_records: list[dict[str, Any]] = []
        try:
            execution_budget_ms = self._gateway.max_encounter_seconds * 1_000
            if self._recover_after_kill:
                execution_budget_ms -= self._gateway.max_recovery_seconds * 1_000
            while True:
                self._control_checkpoint()
                phase_now_ms = self._clock.now_ms()
                if self._active_elapsed_ms(started, started_paused_ms) > execution_budget_ms:
                    raise CombatExecutionError("controlled encounter total deadline expired")
                if combat_phase_started_ms is None:
                    if (
                        phase_now_ms - started
                        > self._gateway.max_acquisition_seconds * 1_000
                    ):
                        raise CombatExecutionError("combat acquisition deadline expired")
                elif (
                    phase_now_ms - combat_phase_started_ms
                    > self._gateway.max_combat_seconds * 1_000
                ):
                    raise CombatExecutionError("active combat deadline expired")
                observation = self._observations.next_observation()
                bearing = self._observations.bearing_for(observation)
                if last_sequence is not None and observation.sequence == last_sequence:
                    duplicate_sequence_count += 1
                    if duplicate_sequence_count > 12:
                        raise CombatExecutionError(
                            "combat observation did not advance within the duplicate budget"
                        )
                    self._wait_ms(25)
                    continue
                duplicate_sequence_count = 0
                last_sequence = observation.sequence
                if self._motion is not None:
                    motion_target = observation.target
                    motion_safe = (
                        observation.player_alive
                        and observation.player_health_pct
                        > self._policy.MIN_SURVIVAL_HEALTH_PCT
                        and motion_target is not None
                        and not motion_target.dead
                        and not motion_target.is_player
                        and motion_target.attackable_npc
                        and motion_target.level is not None
                        and motion_target.level
                        <= observation.player_level
                        + self._gateway.max_target_level_delta
                        and all(
                            action.exact_binding
                            for action in (
                                observation.attack,
                                observation.sinister_strike,
                                observation.eviscerate,
                            )
                        )
                        and (
                            target_identity is None
                            or motion_target.identity_crc16 == target_identity
                        )
                        and (
                            observed_target_identity is None
                            or (
                                not expected_target_change
                                and motion_target.identity_crc16
                                == observed_target_identity
                            )
                        )
                        and (
                            pending_damage is None
                            or motion_target.identity_crc16
                            == pending_damage.target_identity_crc16
                        )
                    )
                    if motion_safe:
                        motion_record = self._motion.update(observation, bearing)
                        motion_records.append(motion_record)
                        if motion_record.get("state") == "HOLD_WORLD_REPOSITION":
                            raise CombatExecutionError(
                                "selected target is occluded behind an unresolved "
                                "navmesh obstacle; world reposition is required"
                            )
                    else:
                        self._motion.release()
                if pending_damage is not None:
                    current_target_identity = (
                        None
                        if observation.target is None
                        else observation.target.identity_crc16
                    )
                    if current_target_identity != pending_damage.target_identity_crc16:
                        if (
                            self._recover_after_kill
                            and observation.player_alive
                            and not observation.in_combat
                        ):
                            # A true one-shot can clear or replace the selected
                            # unit before the HUD ever renders an intermediate
                            # lower-health frame.  Treat this only as a
                            # provisional kill: recovery must select the exact
                            # previous CRC as dead and observe LOOT_OPENED, or
                            # the encounter still fails closed.
                            return self._complete_with_recovery({
                                "record_type": "controlled_combat_result",
                                "schema_version": "0.1",
                                "encounter_id": encounter_id,
                                "status": "TARGET_DEFEATED",
                                "motion_records": list(motion_records),
                                "completion_reason": (
                                    "one_shot_target_transition_validated_by_recovery"
                                ),
                                "completion_observation_id": observation.observation_id,
                                "completion_observation_sha256": (
                                    observation.observation_sha256
                                ),
                                "final_target_health_before_action": (
                                    pending_damage.target_health_current
                                ),
                                "target_identity_crc16": (
                                    pending_damage.target_identity_crc16
                                ),
                                "actions_executed": len(executions),
                                "decisions": decisions,
                                "executions": executions,
                                "manual_takeover_available": True,
                                "execution_authority": False,
                            }, completion_observation=observation, decisions=decisions, executions=executions)
                        if (
                            pending_damage.conservative_lethal_finisher
                            and observation.player_alive
                            and not observation.in_combat
                        ):
                            return self._complete_with_recovery({
                                "record_type": "controlled_combat_result",
                                "schema_version": "0.1",
                                "encounter_id": encounter_id,
                                "status": "TARGET_DEFEATED",
                                "motion_records": list(motion_records),
                                "completion_reason": (
                                    "conservative_lethal_finisher_target_transition"
                                ),
                                "completion_observation_id": observation.observation_id,
                                "completion_observation_sha256": (
                                    observation.observation_sha256
                                ),
                                "final_target_health_before_finisher": (
                                    pending_damage.target_health_current
                                ),
                                "target_identity_crc16": (
                                    pending_damage.target_identity_crc16
                                ),
                                "actions_executed": len(executions),
                                "decisions": decisions,
                                "executions": executions,
                                "manual_takeover_available": True,
                                "execution_authority": False,
                            }, completion_observation=observation, decisions=decisions, executions=executions)
                        if (
                            current_target_identity is None
                            and observation.player_alive
                        ):
                            lethal_clear_candidate = (
                                pending_damage.conservative_lethal_finisher
                                or observed_damage_progress
                            )
                            if lethal_clear_candidate and not observation.in_combat:
                                completion_reason = (
                                    "conservative_lethal_finisher_target_transition"
                                    if pending_damage.conservative_lethal_finisher
                                    else "damaged_locked_target_cleared_out_of_combat"
                                )
                                return self._complete_with_recovery({
                                    "record_type": "controlled_combat_result",
                                    "schema_version": "0.1",
                                    "encounter_id": encounter_id,
                                    "status": "TARGET_DEFEATED",
                                    "motion_records": list(motion_records),
                                    "completion_reason": completion_reason,
                                    "completion_observation_id": observation.observation_id,
                                    "completion_observation_sha256": (
                                        observation.observation_sha256
                                    ),
                                    "final_target_health_before_finisher": (
                                        pending_damage.target_health_current
                                    ),
                                    "target_identity_crc16": (
                                        pending_damage.target_identity_crc16
                                    ),
                                    "actions_executed": len(executions),
                                    "decisions": decisions,
                                    "executions": executions,
                                    "manual_takeover_available": True,
                                    "execution_authority": False,
                                }, completion_observation=observation, decisions=decisions, executions=executions)
                            if lethal_clear_candidate:
                                pending_damage.observations += 1
                                if (
                                    pending_damage.observations
                                    <= LETHAL_TARGET_CLEAR_SETTLE_OBSERVATION_BUDGET
                                ):
                                    self._wait_ms(50)
                                    continue
                        raise CombatExecutionError(
                            "target continuity changed before damage confirmation"
                        )
                    target = observation.target
                    assert target is not None
                    damage_observed = (
                        target.dead
                        or target.health_current
                        < pending_damage.target_health_current
                    )
                    if pending_damage.action_id == "rogue.sinister_strike":
                        damage_observed = damage_observed or (
                            observation.player_energy < pending_damage.player_energy
                            or observation.combo_points != pending_damage.combo_points
                            or not observation.sinister_strike.cooldown_ready
                            or not observation.sinister_strike.usable
                        )
                    if damage_observed:
                        pending_damage = None
                    else:
                        pending_damage.observations += 1
                        if (
                            pending_damage.observations
                            > DAMAGE_CONFIRMATION_OBSERVATION_BUDGET
                        ):
                            if (
                                (
                                    observation.in_combat
                                    or observation.attack.current
                                )
                                and observation.target is not None
                                and not observation.target.dead
                                and observation.target.identity_crc16
                                == pending_damage.target_identity_crc16
                            ):
                                # A melee special may miss, be dodged or be parried.
                                # Those are legitimate zero-damage outcomes in TBC.
                                # Auto-attack can be armed before the first weapon
                                # swing marks the unit in combat, so its exact
                                # current state is also a bounded progress witness.
                                # Release the confirmation latch but preserve strict
                                # target continuity and the global action/deadline caps.
                                pending_damage = None
                                continue
                            raise CombatExecutionError(
                                "damage action outcome was not observed within the confirmation budget"
                            )
                        self._wait_ms(100)
                        continue
                if target_identity is not None and observation.target is None:
                    if (
                        not observation.in_combat
                        and observed_damage_progress
                        and last_locked_target_health is not None
                        and last_locked_target_health_max is not None
                        and last_locked_target_health < last_locked_target_health_max
                    ):
                        return self._complete_with_recovery({
                            "record_type": "controlled_combat_result",
                            "schema_version": "0.1",
                            "encounter_id": encounter_id,
                            "status": "TARGET_DEFEATED",
                            "motion_records": list(motion_records),
                            "completion_reason": (
                                "damaged_locked_target_cleared_out_of_combat"
                            ),
                            "completion_observation_id": observation.observation_id,
                            "completion_observation_sha256": (
                                observation.observation_sha256
                            ),
                            "final_target_health_observed": (
                                last_locked_target_health
                            ),
                            "target_identity_crc16": target_identity,
                            "actions_executed": len(executions),
                            "decisions": decisions,
                            "executions": executions,
                            "manual_takeover_available": True,
                            "execution_authority": False,
                        }, completion_observation=observation, decisions=decisions, executions=executions)
                    if (
                        observed_damage_progress
                        and post_damage_target_settle_observations
                        < POST_DAMAGE_TARGET_SETTLE_OBSERVATION_BUDGET
                    ):
                        post_damage_target_settle_observations += 1
                        self._wait_ms(50)
                        continue
                    raise CombatExecutionError(
                        "locked combat target disappeared without defeat evidence"
                    )
                if expected_target_change:
                    current_target_identity = (
                        None
                        if observation.target is None
                        else observation.target.identity_crc16
                    )
                    if (
                        current_target_identity is None
                        or current_target_identity == observed_target_identity
                    ):
                        target_change_observations += 1
                        if (
                            target_change_observations
                            > TARGET_CHANGE_OBSERVATION_BUDGET
                        ):
                            raise CombatExecutionError(
                                "authorized target cycle did not produce a new target "
                                "within the observation budget"
                            )
                        self._wait_ms(50)
                        continue
                    observed_target_identity = current_target_identity
                    expected_target_change = False
                    target_change_observations = 0
                if observation.target is not None and not observation.target.dead:
                    current_target_identity = observation.target.identity_crc16
                    if target_identity is not None and current_target_identity != target_identity:
                        if unexpected_target_identity == current_target_identity:
                            unexpected_target_mismatch_observations += 1
                        else:
                            unexpected_target_identity = current_target_identity
                            unexpected_target_mismatch_observations = 1
                        if (
                            unexpected_target_mismatch_observations
                            <= UNEXPECTED_TARGET_MISMATCH_OBSERVATION_BUDGET
                        ):
                            self._wait_ms(50)
                            continue
                        raise CombatExecutionError("target continuity changed mid-encounter")
                    unexpected_target_identity = None
                    unexpected_target_mismatch_observations = 0
                    if observed_target_identity is None:
                        observed_target_identity = current_target_identity
                    elif current_target_identity != observed_target_identity:
                        reactive_hostile_acquisition = (
                            target_identity is None
                            and observation.in_combat
                            and observation.target.hostile
                            and not observation.target.is_player
                            and observation.target.level is not None
                            and observation.target.level
                            <= observation.player_level
                            + self._gateway.max_target_level_delta
                        )
                        stable_precombat_rebind = (
                            target_identity is None
                            and not observation.in_combat
                            and observation.target.hostile
                            and not observation.target.is_player
                            and observation.target.level is not None
                            and observation.target.level
                            <= observation.player_level
                            + self._gateway.max_target_level_delta
                        )
                        if stable_precombat_rebind and not reactive_hostile_acquisition:
                            if unexpected_target_identity == current_target_identity:
                                unexpected_target_mismatch_observations += 1
                            else:
                                unexpected_target_identity = current_target_identity
                                unexpected_target_mismatch_observations = 1
                            if (
                                unexpected_target_mismatch_observations
                                <= UNEXPECTED_TARGET_MISMATCH_OBSERVATION_BUDGET
                            ):
                                self._wait_ms(50)
                                continue
                        elif not reactive_hostile_acquisition:
                            raise CombatExecutionError(
                                "target continuity changed without an authorized search step"
                            )
                        # WoW can retarget the hostile NPC that initiated combat.
                        # Accept that reactive acquisition only before this executor
                        # has issued damage; continuity becomes strict again below.
                        observed_target_identity = current_target_identity
                        unexpected_target_identity = None
                        unexpected_target_mismatch_observations = 0
                        last_visible_bearing_target = None
                        transient_bearing_loss_observations = 0
                    else:
                        unexpected_target_identity = None
                        unexpected_target_mismatch_observations = 0
                    if target_identity == current_target_identity:
                        if (
                            last_locked_target_health is not None
                            and observation.target.health_current
                            < last_locked_target_health
                        ):
                            observed_damage_progress = True
                        last_locked_target_health = observation.target.health_current
                        last_locked_target_health_max = observation.target.health_max
                    if bearing is not None and bearing.tracking_state == "VISIBLE":
                        last_visible_bearing_target = current_target_identity
                        transient_bearing_loss_observations = 0
                    elif (
                        bearing is not None
                        and bearing.tracking_state in {"LOST", "AMBIGUOUS"}
                        and last_visible_bearing_target == current_target_identity
                        and transient_bearing_loss_observations
                        < TRANSIENT_BEARING_LOSS_OBSERVATION_BUDGET
                    ):
                        # A flying target can cross terrain or foliage for a few frames.
                        # Debounce that short visual occlusion before authorizing a
                        # coarse search turn which could otherwise overshoot it.
                        transient_bearing_loss_observations += 1
                        self._wait_ms(50)
                        continue
                else:
                    last_visible_bearing_target = None
                    transient_bearing_loss_observations = 0
                decision_id = f"decision:{encounter_id}:{len(decisions) + 1}"
                safe_visible_acquisition = (
                    observation.target is None
                    and bearing is not None
                    and bearing.tracking_state == "VISIBLE"
                    and bearing.direction in {"LEFT", "RIGHT", "CENTER"}
                    and observation.visible_attackable_candidate_count > 0
                    and observation.acquisition_x_normalized is not None
                    and observation.acquisition_y_normalized is not None
                    and VISIBLE_ACQUISITION_SAFE_X_MIN
                    <= observation.acquisition_x_normalized
                    <= VISIBLE_ACQUISITION_SAFE_X_MAX
                )
                if not safe_visible_acquisition:
                    # Any search turn, occlusion, edge clipping, selected target,
                    # or changed sensor state invalidates the target-free point.
                    pending_visible_acquisition = None
                if (
                    self._advance_past_initial_dead_target
                    and target_identity is None
                    and observation.target is not None
                    and observation.target.dead
                    and not observation.in_combat
                ):
                    decision = CombatDecision(
                        decision_id=decision_id,
                        observation=observation,
                        action_id="combat.advance_from_looted_corpse",
                        priority_tier="TARGET_CONTROL",
                        reason_code="previous_looted_corpse_still_selected",
                        explanation=(
                            "The previous dead NPC is still selected after recovery; "
                            "use the normal nearest-hostile binding once and require a "
                            "fresh live identity before movement or damage."
                        ),
                        requested_control="TARGET_NEAREST_HOSTILE",
                        preconditions=(
                            "in_combat=false",
                            "target.dead=true",
                            "encounter_target_unbound=true",
                        ),
                        confidence=observation.confidence,
                        bearing=bearing,
                    )
                elif (
                    observation.target is None
                    and bearing is not None
                    and bearing.tracking_state == "VISIBLE"
                    and bearing.direction in {"LEFT", "RIGHT"}
                    and observation.visible_attackable_candidate_count > 0
                    and observation.acquisition_x_normalized is not None
                    and not (
                        VISIBLE_ACQUISITION_SAFE_X_MIN
                        <= observation.acquisition_x_normalized
                        <= VISIBLE_ACQUISITION_SAFE_X_MAX
                    )
                ):
                    direction = bearing.direction.lower()
                    decision = CombatDecision(
                        decision_id=decision_id,
                        observation=observation,
                        action_id=f"combat.turn_toward_visible_candidate_{direction}",
                        priority_tier="TARGET_CONTROL",
                        reason_code="visible_candidate_outside_safe_click_corridor",
                        explanation=(
                            "Bring the partially clipped red/yellow nameplate into "
                            "the safe click corridor before target selection."
                        ),
                        requested_control=(
                            "TURN_LEFT" if bearing.direction == "LEFT" else "TURN_RIGHT"
                        ),
                        preconditions=(
                            "target=null",
                            "in_combat=false",
                            "visible_candidate_count>0",
                            "acquisition_screen_point=edge_clipped",
                        ),
                        confidence=observation.confidence,
                        bearing=bearing,
                    )
                elif (
                    safe_visible_acquisition
                ):
                    assert observation.acquisition_x_normalized is not None
                    assert observation.acquisition_y_normalized is not None
                    if (
                        pending_visible_acquisition is None
                        or not pending_visible_acquisition.matches(observation)
                    ):
                        pending_visible_acquisition = _PendingVisibleAcquisition(
                            x_normalized=observation.acquisition_x_normalized,
                            y_normalized=observation.acquisition_y_normalized,
                            candidate_count=(
                                observation.visible_attackable_candidate_count
                            ),
                            sequence=observation.sequence,
                        )
                        # No input during this settling sample.  A second fresh
                        # frame must confirm the nameplate did not move with the
                        # camera before an exact screen click is authorized.
                        self._wait_ms(VISIBLE_ACQUISITION_STABILITY_WAIT_MS)
                        continue
                    pending_visible_acquisition = None
                    decision = CombatDecision(
                        decision_id=decision_id,
                        observation=observation,
                        action_id="combat.acquire_visible_hostile",
                        priority_tier="TARGET_CONTROL",
                        reason_code="visible_attackable_candidate_screen_bound",
                        explanation=(
                            "Select the evaluated red/yellow nameplate only after "
                            "its exact screen coordinate remained stable across two "
                            "fresh frames."
                        ),
                        requested_control="TARGET_VISIBLE_HOSTILE",
                        preconditions=(
                            "target=null",
                            "in_combat=false",
                            "visible_candidate_count>0",
                            "acquisition_screen_point=stable_two_fresh_frames",
                        ),
                        confidence=observation.confidence,
                        bearing=bearing,
                    )
                elif (
                    observation.target is None
                    and (bearing is None or bearing.tracking_state != "VISIBLE")
                    and self._gateway.turn_count < self._gateway.max_turn_pulses
                ):
                    decision = self._policy.decide_acquisition_scan(
                        observation,
                        decision_id=decision_id,
                    )
                elif observation.target is None and not (
                    bearing is not None
                    and bearing.tracking_state == "VISIBLE"
                    and bearing.direction == "CENTER"
                    and observation.visible_attackable_candidate_count > 0
                ):
                    # Exhausting the visual sweep is not evidence that a TAB
                    # target is the red/yellow nameplate we meant to acquire.
                    # A hidden unit behind a wall can otherwise become selected
                    # and make the camera search look like autonomous hunting.
                    # Stop here so the hunting engine can move to another
                    # vantage point; only a centered, visible candidate may
                    # authorize the normal target binding below.
                    raise CombatExecutionError(
                        "no visible attackable candidate within bounded search"
                    )
                else:
                    decision = self._policy.decide(
                        observation,
                        decision_id=decision_id,
                        bearing=bearing,
                        motion_managed=self._motion is not None,
                    )
                if (
                    decision.action_id == "combat.reject_risky_target"
                    and decision.reason_code == "target_level_out_of_bounds"
                    and target_identity is None
                    and not observation.in_combat
                    and not self._preserve_selected_target
                    and target_cycles < MAX_TARGET_CYCLES
                ):
                    decision = CombatDecision(
                        decision_id=decision.decision_id,
                        observation=observation,
                        action_id="combat.cycle_hostile_target",
                        priority_tier="TARGET_CONTROL",
                        reason_code="current_target_level_out_of_bounds",
                        explanation=(
                            "The selected NPC is outside the safe level gate; do not "
                            "damage or approach it, and use the normal nearest-hostile "
                            "binding once to evaluate a different nearby identity."
                        ),
                        requested_control="TARGET_NEAREST_HOSTILE",
                        preconditions=(
                            "in_combat=false",
                            "encounter_target_unbound=true",
                            "target_level_not_within_safe_gate=true",
                        ),
                        confidence=observation.confidence,
                        bearing=bearing,
                    )
                elif (
                    decision.action_id == "combat.approach_target"
                    and self._gateway.approach_count
                    >= self._gateway.max_approach_pulses
                ):
                    if self._preserve_selected_target:
                        raise CombatExecutionError(
                            "exact selected target remained unreachable before combat"
                        )
                    if target_cycles >= MAX_TARGET_CYCLES:
                        raise CombatExecutionError("combat target-search budget is exhausted")
                    decision = CombatDecision(
                        decision_id=decision.decision_id,
                        observation=observation,
                        action_id="combat.cycle_hostile_target",
                        priority_tier="TARGET_CONTROL",
                        reason_code="current_target_unreachable_before_combat",
                        explanation=(
                            "The current hostile remained out of melee range after the exact "
                            "approach budget; cycle once and re-evaluate before any damage."
                        ),
                        requested_control="TARGET_NEAREST_HOSTILE",
                        preconditions=(
                            "in_combat=false",
                            "target.hostile=true",
                            "approach_budget_exhausted=true",
                        ),
                        confidence=observation.confidence,
                        bearing=bearing,
                    )
                elif (
                    decision.action_id
                    in {
                        "combat.turn_toward_target_left",
                        "combat.turn_toward_target_right",
                        "combat.turn_toward_visible_candidate_left",
                        "combat.turn_toward_visible_candidate_right",
                    }
                    and self._gateway.facing_turn_count
                    >= self._gateway.max_facing_turn_pulses
                ):
                    if (
                        observation.in_combat
                        and observed_damage_progress
                        and post_damage_target_settle_observations
                        < POST_DAMAGE_TARGET_SETTLE_OBSERVATION_BUDGET
                    ):
                        post_damage_target_settle_observations += 1
                        self._wait_ms(50)
                        continue
                    if self._preserve_selected_target:
                        raise CombatExecutionError(
                            "exact selected target was not visually reacquired within the turn budget"
                        )
                    raise CombatExecutionError(
                        "combat visible-facing budget is exhausted"
                    )
                elif (
                    decision.action_id
                    in {"combat.search_selected_target", "combat.search_selected_target_left"}
                    and self._gateway.turn_count >= self._gateway.max_turn_pulses
                ):
                    if observation.in_combat:
                        if (
                            observed_damage_progress
                            and post_damage_target_settle_observations
                            < POST_DAMAGE_TARGET_SETTLE_OBSERVATION_BUDGET
                        ):
                            post_damage_target_settle_observations += 1
                            self._wait_ms(50)
                            continue
                        raise CombatExecutionError(
                            "combat target bearing was lost after combat started"
                        )
                    if self._preserve_selected_target:
                        raise CombatExecutionError(
                            "exact selected target was not visually reacquired within the turn budget"
                        )
                    if target_cycles >= MAX_TARGET_CYCLES:
                        raise CombatExecutionError(
                            "combat target-search budget is exhausted"
                        )
                    decision = CombatDecision(
                        decision_id=decision.decision_id,
                        observation=observation,
                        action_id="combat.cycle_hostile_target",
                        priority_tier="TARGET_CONTROL",
                        reason_code="current_target_not_visually_reacquired",
                        explanation=(
                            "The selected hostile stayed outside the bounded visual bearing "
                            "search; cycle once to the next nearby hostile and require a new "
                            "exact identity before movement or damage."
                        ),
                        requested_control="TARGET_NEAREST_HOSTILE",
                        preconditions=(
                            "in_combat=false",
                            "target.hostile=true",
                            "turn_search_budget_exhausted=true",
                        ),
                        confidence=observation.confidence,
                        bearing=bearing,
                    )
                decisions.append(
                    decision.to_record(
                        created_at=datetime.now(timezone.utc)
                        .isoformat(timespec="microseconds")
                        .replace("+00:00", "Z")
                    )
                )
                if decision.action_id == "combat.target_defeated":
                    if target_identity is None and observation.target is not None:
                        target_identity = observation.target.identity_crc16
                    return self._complete_with_recovery({
                        "record_type": "controlled_combat_result",
                        "schema_version": "0.1",
                        "encounter_id": encounter_id,
                        "status": "TARGET_DEFEATED",
                        "motion_records": list(motion_records),
                        "target_identity_crc16": target_identity,
                        "actions_executed": len(executions),
                        "decisions": decisions,
                        "executions": executions,
                        "manual_takeover_available": True,
                        "execution_authority": False,
                    }, completion_observation=observation, decisions=decisions, executions=executions)
                if decision.requested_control is None:
                    if decision.action_id in {
                        "combat.monitor_auto_attack",
                        "combat.hold_range_unknown",
                        "combat.hold_bearing_unavailable",
                        "combat.monitor_continuous_approach",
                        "combat.monitor_continuous_facing",
                        "combat.monitor_continuous_reacquisition",
                    }:
                        self._wait_ms(100)
                        continue
                    raise CombatExecutionError(
                        f"policy stopped encounter: {decision.reason_code}"
                    )
                execution = self._gateway.execute(decision, observation)
                executions.append(execution)
                if decision.action_id in {
                    "combat.cycle_hostile_target",
                    "combat.advance_from_looted_corpse",
                }:
                    target_cycles += 1
                    expected_target_change = True
                    target_change_observations = 0
                    last_visible_bearing_target = None
                    transient_bearing_loss_observations = 0
                elif decision.action_id in {
                    "combat.acquire_visible_hostile",
                    "combat.acquire_hostile_target",
                }:
                    expected_target_change = True
                    target_change_observations = 0
                elif decision.requested_control in {
                    "ACTION_SLOT_1",
                    "ACTION_SLOT_2",
                    "ACTION_SLOT_3",
                }:
                    if observation.target is None:
                        raise CombatExecutionError("damage action lost its target binding")
                    target_identity = observation.target.identity_crc16
                    if combat_phase_started_ms is None:
                        combat_phase_started_ms = self._clock.now_ms()
                    last_locked_target_health = observation.target.health_current
                    last_locked_target_health_max = observation.target.health_max
                    if decision.requested_control in {
                        "ACTION_SLOT_2",
                        "ACTION_SLOT_3",
                    }:
                        pending_damage = _PendingDamageConfirmation(
                            action_id=decision.action_id,
                            reason_code=decision.reason_code,
                            target_identity_crc16=observation.target.identity_crc16,
                            target_health_current=observation.target.health_current,
                            player_energy=observation.player_energy,
                            combo_points=observation.combo_points,
                        )
                self._wait_ms(100)
        except ControlledCombatEncounterFailure:
            raise
        except Exception as error:
            raise ControlledCombatEncounterFailure(
                str(error),
                record={
                    "record_type": "controlled_combat_failure",
                    "schema_version": "0.1",
                    "encounter_id": encounter_id,
                    "status": "STOPPED_FAIL_CLOSED",
                    "target_identity_crc16": target_identity,
                    "error_type": type(error).__name__,
                    "detail": str(error),
                    "actions_executed": len(executions),
                    "decisions": list(decisions),
                    "executions": list(executions),
                    "motion_records": list(motion_records),
                    "manual_takeover_available": True,
                    "execution_authority": False,
                },
            ) from error
        finally:
            if self._motion is not None:
                self._motion.close()
            self._gateway.close()
