"""Client-neutral observations consumed by the standalone movement core."""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

from perfect_assassin.movement.dynamic_avoidance import ScreenEntityObservation
from perfect_assassin.movement.risk_aware_route_policy import TravelCapability


@runtime_checkable
class MovementObservationPort(Protocol):
    """Minimal live/replay observation boundary for movement execution.

    The core deliberately knows nothing about DXGI, addon pixels, a server,
    process memory, input injection, or a particular WoW client.  A concrete
    adapter may provide observations only through this contract.
    """

    def open(self) -> None:
        """Acquire the adapter resources required for observation."""

    def close(self) -> None:
        """Release adapter resources; implementations must be idempotent."""

    def next_observation(self) -> Mapping[str, object]:
        """Return one fresh, validated observation or fail closed."""

    @property
    def latest_facing_source(self) -> str:
        """Describe the provenance of the most recent facing value."""

    @property
    def latest_travel_capability(self) -> TravelCapability | None:
        """Return visible travel capability without fabricating state."""

    @property
    def latest_dynamic_observations(
        self,
    ) -> tuple[ScreenEntityObservation, ...]:
        """Return bounded dynamic-entity observations for the latest frame."""

    @property
    def latest_dynamic_detection_error(self) -> str | None:
        """Return the latest non-fatal dynamic-detection diagnostic."""
