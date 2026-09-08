"""Compatibility launcher for the unified Movement Engine Control Center."""

from __future__ import annotations

from run_movement_engine_client import MovementEngineClient


def run() -> None:
    """Preserve old shortcuts without maintaining a second control surface."""

    MovementEngineClient().run()


if __name__ == "__main__":
    run()
