from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class GearPolicyError(ValueError):
    """Raised when an advisory result crosses the legitimate-availability boundary."""


class GearAvailabilityPolicy:
    """Validates advisory output against client-observed item availability."""

    selectable_states = frozenset(
        {"observed_equipped", "observed_bag", "observed_reward_option"}
    )

    def validate_recommendation(
        self,
        request: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        if request.get("analysis_id") != result.get("analysis_id"):
            raise GearPolicyError("Gear result does not match its request")

        recommended = result.get("recommended_item_ref")
        if recommended is None:
            return

        candidates = {
            candidate.get("item_ref"): candidate.get("availability")
            for candidate in request.get("candidates", [])
        }
        if recommended not in candidates:
            raise GearPolicyError("Recommended item is absent from the legitimate snapshot")

        availability = candidates[recommended]
        if availability not in self.selectable_states:
            raise GearPolicyError(
                f"Recommended item is not selectable: availability={availability}"
            )
