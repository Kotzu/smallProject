from __future__ import annotations

import copy
from datetime import datetime
from math import hypot, isclose, isfinite
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from perfect_assassin.contract_validation import ContractValidator


class MotionCalibrationError(ValueError):
    """Raised when a trace cannot produce a trustworthy motion model."""


class DeterministicMotionModelFitter:
    """Fit a read-only motion model from synchronized manual or replay traces.

    This component only transforms versioned records.  It has no clock, capture,
    process, window, keyboard, mouse, or execution dependency.
    """

    version = "0.1.0"
    _axis_epsilon = 1e-6
    _minimum_interval_s = 1e-4
    _identity_fields = (
        "session_id",
        "target_profile",
        "actor_binding",
        "authorization_sha256",
        "decision_context",
        "client_build",
        "build_signature",
        "map_ref",
        "map_signature",
        "coordinate_space",
        "trace_kind",
    )

    def __init__(
        self,
        validator: ContractValidator,
        *,
        fitter_id: str = "pa_deterministic_motion_fit",
    ) -> None:
        if not isinstance(fitter_id, str) or not fitter_id:
            raise ValueError("fitter_id cannot be empty")
        self._validator = validator
        self.fitter_id = fitter_id

    def fit(
        self,
        traces: Iterable[Mapping[str, Any]],
        *,
        model_id: str,
        created_at: str,
    ) -> dict[str, Any]:
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("model_id cannot be empty")
        self._require_timestamp(created_at)

        owned = [copy.deepcopy(dict(trace)) for trace in traces]
        if not owned:
            raise MotionCalibrationError("At least one calibration trace is required")
        owned.sort(key=lambda trace: str(trace.get("trace_id", "")))

        trace_ids: set[str] = set()
        for trace in owned:
            self._validator.validate(trace)
            if trace.get("record_type") != "motion_calibration_trace":
                raise MotionCalibrationError("The fitter accepts trace records only")
            trace_id = str(trace["trace_id"])
            if trace_id in trace_ids:
                raise MotionCalibrationError(f"Duplicate trace_id: {trace_id}")
            trace_ids.add(trace_id)
            self._require_trace_integrity(trace)

        self._require_same_identity(owned)
        trace_kind = str(owned[0]["trace_kind"])
        if trace_kind not in {"manual_trace", "synthetic_fixture"}:
            raise MotionCalibrationError(
                "LAB/server oracle traces are evaluation-only and cannot fit this model"
            )
        scopes = {str(trace["provenance"]["scope"]) for trace in owned}
        if len(scopes) != 1:
            raise MotionCalibrationError("Calibration provenance scopes cannot be mixed")

        forward_candidates = self._rate_candidates(owned, component="forward")
        turn_candidates = self._rate_candidates(owned, component="turn")
        forward_latency = self._latency_bounds(owned, component="forward")
        turn_latency = self._latency_bounds(owned, component="turn")

        first = owned[0]
        all_samples = [sample for trace in owned for sample in trace["samples"]]
        first_monotonic = min(
            self._finite(sample["timing"]["sample_monotonic_s"], "sample_monotonic_s")
            for sample in all_samples
        )
        last_monotonic = max(
            self._finite(sample["timing"]["sample_monotonic_s"], "sample_monotonic_s")
            for sample in all_samples
        )
        covered_duration_ms = sum(
            self._finite(trace["timing"]["duration_ms"], "duration_ms")
            for trace in owned
        )
        if not isfinite(covered_duration_ms) or covered_duration_ms <= 0:
            raise MotionCalibrationError("Covered duration must be finite and positive")

        trace_id_list = [str(trace["trace_id"]) for trace in owned]
        origin = {
            "manual_trace": "deterministic_manual_trace_fit",
            "synthetic_fixture": "deterministic_synthetic_fit",
        }[trace_kind]
        model = {
            "record_type": "calibrated_motion_model",
            "schema_version": "0.1",
            "model_id": model_id,
            "session_id": first["session_id"],
            "target_profile": first["target_profile"],
            "actor_binding": copy.deepcopy(first["actor_binding"]),
            "authorization_sha256": first["authorization_sha256"],
            "decision_context": first["decision_context"],
            "client_build": first["client_build"],
            "build_signature": first["build_signature"],
            "map_ref": first["map_ref"],
            "map_signature": first["map_signature"],
            "coordinate_space": first["coordinate_space"],
            "source_trace_kind": trace_kind,
            "fitter_id": self.fitter_id,
            "fitter_version": self.version,
            "timing": {
                "monotonic_clock_id": first["timing"]["monotonic_clock_id"],
                "first_sample_monotonic_s": first_monotonic,
                "last_sample_monotonic_s": last_monotonic,
                "covered_duration_ms": covered_duration_ms,
                "trace_count": len(owned),
                "sample_count": len(all_samples),
            },
            "estimates": {
                "forward_speed_world_units_per_s": self._point_estimate(
                    forward_candidates
                ),
                "turn_rate_deg_per_s": self._point_estimate(turn_candidates),
                "forward_input_latency_ms": forward_latency,
                "turn_input_latency_ms": turn_latency,
            },
            "provenance": {
                "origin": origin,
                "capability": "calibrated_motion_model",
                "scope": next(iter(scopes)),
                "confidence": min(
                    self._finite(trace["provenance"]["confidence"], "confidence")
                    for trace in owned
                ),
                "input_trace_ids": trace_id_list,
                "evidence_refs": trace_id_list,
            },
            "execution_authority": False,
            "created_at": created_at,
        }
        self._validator.validate(model)
        return model

    def _require_same_identity(self, traces: Sequence[Mapping[str, Any]]) -> None:
        first = traces[0]
        first_clock = first["timing"]["monotonic_clock_id"]
        for trace in traces[1:]:
            for field in self._identity_fields:
                if trace[field] != first[field]:
                    raise MotionCalibrationError(
                        f"Calibration trace identity mismatch: {field}"
                    )
            if trace["timing"]["monotonic_clock_id"] != first_clock:
                raise MotionCalibrationError(
                    "Calibration monotonic_clock_id values cannot be mixed"
                )

    def _require_trace_integrity(self, trace: Mapping[str, Any]) -> None:
        samples = trace["samples"]
        expected_indexes = list(range(len(samples)))
        actual_indexes = [sample["sample_index"] for sample in samples]
        if actual_indexes != expected_indexes:
            raise MotionCalibrationError(
                "sample_index values must be contiguous and ordered from zero"
            )

        sample_times: list[float] = []
        pose_times: list[float] = []
        action_times: list[float] = []
        pose_ids: set[str] = set()
        action_ids: set[str] = set()
        maximum_sync_skew = self._finite(
            trace["timing"]["maximum_sync_skew_ms"], "maximum_sync_skew_ms"
        )

        for sample in samples:
            timing = sample["timing"]
            sample_time = self._finite(
                timing["sample_monotonic_s"], "sample_monotonic_s"
            )
            pose_time = self._finite(timing["pose_monotonic_s"], "pose_monotonic_s")
            action_time = self._finite(
                timing["action_monotonic_s"], "action_monotonic_s"
            )
            reported_skew = self._finite(timing["sync_skew_ms"], "sync_skew_ms")
            actual_skew = abs(pose_time - action_time) * 1000.0
            if not isfinite(actual_skew):
                raise MotionCalibrationError("Synchronization skew is not finite")
            if sample_time + 1e-12 < max(pose_time, action_time):
                raise MotionCalibrationError(
                    "sample_monotonic_s cannot precede its pose/action observations"
                )
            if actual_skew > reported_skew + 1e-6:
                raise MotionCalibrationError(
                    "sync_skew_ms understates the pose/action clock difference"
                )
            if reported_skew > maximum_sync_skew + 1e-6:
                raise MotionCalibrationError(
                    "A sample exceeds timing.maximum_sync_skew_ms"
                )
            sample_times.append(sample_time)
            pose_times.append(pose_time)
            action_times.append(action_time)

            pose_id = str(sample["pose_observation_id"])
            action_id = str(sample["action_observation_id"])
            if pose_id in pose_ids or action_id in action_ids:
                raise MotionCalibrationError(
                    "Pose and action observation ids must be unique inside a trace"
                )
            pose_ids.add(pose_id)
            action_ids.add(action_id)

            for axis in ("x", "y"):
                self._finite(sample["pose"]["position"][axis], f"position.{axis}")
            if sample["pose"]["position"].get("z") is not None:
                self._finite(sample["pose"]["position"]["z"], "position.z")
            self._finite(sample["pose"]["body_yaw_deg"], "body_yaw_deg")
            self._finite(sample["action"]["forward_axis"], "forward_axis")
            self._finite(sample["action"]["turn_axis"], "turn_axis")
            for field in (
                "position_radius_95",
                "yaw_error_95_deg",
                "timing_error_95_ms",
            ):
                self._finite(sample["uncertainty"][field], field)

        self._require_strictly_increasing(sample_times, "sample_monotonic_s")
        self._require_strictly_increasing(pose_times, "pose_monotonic_s")
        self._require_strictly_increasing(action_times, "action_monotonic_s")

        started = self._finite(
            trace["timing"]["started_monotonic_s"], "started_monotonic_s"
        )
        ended = self._finite(
            trace["timing"]["ended_monotonic_s"], "ended_monotonic_s"
        )
        duration_ms = self._finite(trace["timing"]["duration_ms"], "duration_ms")
        if not isclose(started, sample_times[0], rel_tol=0.0, abs_tol=1e-9):
            raise MotionCalibrationError(
                "started_monotonic_s must equal the first sample time"
            )
        if not isclose(ended, sample_times[-1], rel_tol=0.0, abs_tol=1e-9):
            raise MotionCalibrationError(
                "ended_monotonic_s must equal the last sample time"
            )
        expected_duration_ms = (ended - started) * 1000.0
        if not isfinite(expected_duration_ms) or not isclose(
            duration_ms, expected_duration_ms, rel_tol=1e-9, abs_tol=1e-6
        ):
            raise MotionCalibrationError(
                "duration_ms must match the monotonic sample interval"
            )

    def _rate_candidates(
        self,
        traces: Sequence[Mapping[str, Any]],
        *,
        component: str,
    ) -> list[tuple[float, float]]:
        candidates: list[tuple[float, float]] = []
        for trace in traces:
            samples = trace["samples"]
            for index in range(1, len(samples)):
                previous = samples[index - 1]
                current = samples[index]
                dt = (
                    self._finite(
                        current["timing"]["pose_monotonic_s"], "pose_monotonic_s"
                    )
                    - self._finite(
                        previous["timing"]["pose_monotonic_s"],
                        "pose_monotonic_s",
                    )
                )
                if dt < self._minimum_interval_s:
                    raise MotionCalibrationError(
                        "Pose samples are too close for a stable rate estimate"
                    )

                if component == "forward":
                    axis = self._pure_forward_axis(previous, current)
                    if axis is None:
                        continue
                    position_a = previous["pose"]["position"]
                    position_b = current["pose"]["position"]
                    distance = hypot(
                        self._finite(position_b["x"], "position.x")
                        - self._finite(position_a["x"], "position.x"),
                        self._finite(position_b["y"], "position.y")
                        - self._finite(position_a["y"], "position.y"),
                    )
                    signal_floor = (
                        self._finite(
                            previous["uncertainty"]["position_radius_95"],
                            "position_radius_95",
                        )
                        + self._finite(
                            current["uncertainty"]["position_radius_95"],
                            "position_radius_95",
                        )
                    )
                    if distance <= max(1e-12, signal_floor):
                        continue
                    value = distance / (dt * axis)
                    error = signal_floor / (dt * axis)
                elif component == "turn":
                    axis = self._pure_turn_axis(previous, current)
                    if axis is None:
                        continue
                    angle = abs(
                        self._wrapped_yaw_delta(
                            self._finite(
                                previous["pose"]["body_yaw_deg"], "body_yaw_deg"
                            ),
                            self._finite(
                                current["pose"]["body_yaw_deg"], "body_yaw_deg"
                            ),
                        )
                    )
                    signal_floor = (
                        self._finite(
                            previous["uncertainty"]["yaw_error_95_deg"],
                            "yaw_error_95_deg",
                        )
                        + self._finite(
                            current["uncertainty"]["yaw_error_95_deg"],
                            "yaw_error_95_deg",
                        )
                    )
                    if angle <= max(1e-12, signal_floor):
                        continue
                    value = angle / (dt * axis)
                    error = signal_floor / (dt * axis)
                else:
                    raise AssertionError(f"Unknown calibration component: {component}")

                if not isfinite(value) or value <= 0 or not isfinite(error):
                    raise MotionCalibrationError(
                        f"{component} rate candidate is not finite and positive"
                    )
                candidates.append((value, error))

        if len(candidates) < 2:
            raise MotionCalibrationError(
                f"At least two observable {component} intervals are required"
            )
        return candidates

    def _latency_bounds(
        self,
        traces: Sequence[Mapping[str, Any]],
        *,
        component: str,
    ) -> dict[str, Any]:
        bounds: list[tuple[float, float]] = []
        for trace in traces:
            samples = trace["samples"]
            for onset_index in range(1, len(samples)):
                previous = samples[onset_index - 1]
                onset = samples[onset_index]
                if not self._is_onset(previous, onset, component):
                    continue
                detected = self._first_effect(samples, onset_index, component)
                if detected is None:
                    continue
                effect_index = detected
                bracket_start = samples[effect_index - 1]
                effect = samples[effect_index]
                action_started = self._finite(
                    onset["timing"]["action_monotonic_s"], "action_monotonic_s"
                )
                onset_error = self._finite(
                    onset["uncertainty"]["timing_error_95_ms"],
                    "timing_error_95_ms",
                )
                lower = max(
                    0.0,
                    (
                        self._finite(
                            bracket_start["timing"]["pose_monotonic_s"],
                            "pose_monotonic_s",
                        )
                        - action_started
                    )
                    * 1000.0
                    - onset_error
                    - self._finite(
                        bracket_start["uncertainty"]["timing_error_95_ms"],
                        "timing_error_95_ms",
                    ),
                )
                upper = max(
                    lower,
                    (
                        self._finite(
                            effect["timing"]["pose_monotonic_s"],
                            "pose_monotonic_s",
                        )
                        - action_started
                    )
                    * 1000.0
                    + onset_error
                    + self._finite(
                        effect["uncertainty"]["timing_error_95_ms"],
                        "timing_error_95_ms",
                    ),
                )
                if not isfinite(lower) or not isfinite(upper):
                    raise MotionCalibrationError("Latency bounds are not finite")
                bounds.append((lower, upper))

        if not bounds:
            raise MotionCalibrationError(
                f"No observable {component} input-to-motion transition was found"
            )
        lower_bound = min(bound[0] for bound in bounds)
        upper_bound = max(bound[1] for bound in bounds)
        midpoint = (lower_bound + upper_bound) / 2.0
        uncertainty = (upper_bound - lower_bound) / 2.0
        values = (lower_bound, upper_bound, midpoint, uncertainty)
        if any(not isfinite(value) or value < 0 for value in values):
            raise MotionCalibrationError("Combined latency bounds are invalid")
        return {
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "midpoint": midpoint,
            "uncertainty_95": uncertainty,
            "transition_count": len(bounds),
        }

    def _first_effect(
        self,
        samples: Sequence[Mapping[str, Any]],
        onset_index: int,
        component: str,
    ) -> int | None:
        baseline = samples[onset_index - 1]
        for index in range(onset_index, len(samples)):
            current = samples[index]
            if not self._axis_remains_active(current, component):
                break
            if component == "forward":
                baseline_position = baseline["pose"]["position"]
                current_position = current["pose"]["position"]
                signal = hypot(
                    self._finite(current_position["x"], "position.x")
                    - self._finite(baseline_position["x"], "position.x"),
                    self._finite(current_position["y"], "position.y")
                    - self._finite(baseline_position["y"], "position.y"),
                )
                floor = self._finite(
                    baseline["uncertainty"]["position_radius_95"],
                    "position_radius_95",
                ) + self._finite(
                    current["uncertainty"]["position_radius_95"],
                    "position_radius_95",
                )
            else:
                signal = abs(
                    self._wrapped_yaw_delta(
                        self._finite(
                            baseline["pose"]["body_yaw_deg"], "body_yaw_deg"
                        ),
                        self._finite(
                            current["pose"]["body_yaw_deg"], "body_yaw_deg"
                        ),
                    )
                )
                floor = self._finite(
                    baseline["uncertainty"]["yaw_error_95_deg"],
                    "yaw_error_95_deg",
                ) + self._finite(
                    current["uncertainty"]["yaw_error_95_deg"],
                    "yaw_error_95_deg",
                )
            if signal > max(1e-12, floor):
                return index
        return None

    def _is_onset(
        self,
        previous: Mapping[str, Any],
        current: Mapping[str, Any],
        component: str,
    ) -> bool:
        if component == "forward":
            return (
                self._finite(previous["action"]["forward_axis"], "forward_axis")
                <= self._axis_epsilon
                and self._finite(current["action"]["forward_axis"], "forward_axis")
                > self._axis_epsilon
                and abs(self._finite(current["action"]["turn_axis"], "turn_axis"))
                <= self._axis_epsilon
            )
        return (
            abs(self._finite(previous["action"]["turn_axis"], "turn_axis"))
            <= self._axis_epsilon
            and abs(self._finite(current["action"]["turn_axis"], "turn_axis"))
            > self._axis_epsilon
            and abs(
                self._finite(current["action"]["forward_axis"], "forward_axis")
            )
            <= self._axis_epsilon
        )

    def _axis_remains_active(
        self, sample: Mapping[str, Any], component: str
    ) -> bool:
        if component == "forward":
            return (
                self._finite(sample["action"]["forward_axis"], "forward_axis")
                > self._axis_epsilon
                and abs(self._finite(sample["action"]["turn_axis"], "turn_axis"))
                <= self._axis_epsilon
            )
        return (
            abs(self._finite(sample["action"]["turn_axis"], "turn_axis"))
            > self._axis_epsilon
            and abs(
                self._finite(sample["action"]["forward_axis"], "forward_axis")
            )
            <= self._axis_epsilon
        )

    def _pure_forward_axis(
        self, previous: Mapping[str, Any], current: Mapping[str, Any]
    ) -> float | None:
        previous_forward = self._finite(
            previous["action"]["forward_axis"], "forward_axis"
        )
        current_forward = self._finite(
            current["action"]["forward_axis"], "forward_axis"
        )
        if (
            previous_forward <= self._axis_epsilon
            or current_forward <= self._axis_epsilon
            or abs(self._finite(previous["action"]["turn_axis"], "turn_axis"))
            > self._axis_epsilon
            or abs(self._finite(current["action"]["turn_axis"], "turn_axis"))
            > self._axis_epsilon
        ):
            return None
        return (previous_forward + current_forward) / 2.0

    def _pure_turn_axis(
        self, previous: Mapping[str, Any], current: Mapping[str, Any]
    ) -> float | None:
        previous_turn = self._finite(previous["action"]["turn_axis"], "turn_axis")
        current_turn = self._finite(current["action"]["turn_axis"], "turn_axis")
        if (
            abs(previous_turn) <= self._axis_epsilon
            or abs(current_turn) <= self._axis_epsilon
            or previous_turn * current_turn <= 0
            or abs(
                self._finite(previous["action"]["forward_axis"], "forward_axis")
            )
            > self._axis_epsilon
            or abs(self._finite(current["action"]["forward_axis"], "forward_axis"))
            > self._axis_epsilon
        ):
            return None
        return (abs(previous_turn) + abs(current_turn)) / 2.0

    @staticmethod
    def _wrapped_yaw_delta(start_deg: float, end_deg: float) -> float:
        delta = (end_deg - start_deg + 180.0) % 360.0 - 180.0
        if delta == -180.0 and end_deg - start_deg > 0:
            return 180.0
        return delta

    @staticmethod
    def _point_estimate(candidates: Sequence[tuple[float, float]]) -> dict[str, Any]:
        value = float(median(candidate[0] for candidate in candidates))
        uncertainty = max(
            abs(candidate_value - value) + candidate_error
            for candidate_value, candidate_error in candidates
        )
        if not isfinite(value) or value <= 0 or not isfinite(uncertainty):
            raise MotionCalibrationError("Point estimate is not finite and positive")
        return {
            "value": value,
            "uncertainty_95": uncertainty,
            "sample_count": len(candidates),
        }

    @staticmethod
    def _require_strictly_increasing(values: Sequence[float], field: str) -> None:
        for previous, current in zip(values, values[1:]):
            if current <= previous:
                raise MotionCalibrationError(f"{field} must be strictly increasing")

    @staticmethod
    def _finite(value: Any, field: str) -> float:
        if isinstance(value, bool):
            raise MotionCalibrationError(f"{field} must be a finite number")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as error:
            raise MotionCalibrationError(f"{field} must be a finite number") from error
        if not isfinite(parsed):
            raise MotionCalibrationError(f"{field} must be a finite number")
        return parsed

    @staticmethod
    def _require_timestamp(value: str) -> None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError) as error:
            raise MotionCalibrationError(f"Invalid created_at timestamp: {value!r}") from error
        if parsed.tzinfo is None:
            raise MotionCalibrationError("created_at must include a timezone")
