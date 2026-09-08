"""Portable roots for large runtime artifacts and external dependencies."""

from __future__ import annotations

import os
from pathlib import Path


RUNTIME_ROOT_ENV = "PERFECT_ASSASSIN_RUNTIME_ROOT"
DEPENDENCIES_ROOT_ENV = "PERFECT_ASSASSIN_DEPENDENCIES_ROOT"


def _configured_sibling_root(
    repository_root: Path,
    *,
    environment_variable: str,
    sibling_name: str,
) -> Path:
    configured = os.environ.get(environment_variable)
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            raise ValueError(f"{environment_variable} must be an absolute path")
        return candidate
    return repository_root.resolve().parent / sibling_name


def external_runtime_root(repository_root: Path) -> Path:
    """Return the relocatable store for WorldPacks, assets and experience."""

    return _configured_sibling_root(
        repository_root,
        environment_variable=RUNTIME_ROOT_ENV,
        sibling_name="PerfectAssassin-Runtime",
    )


def external_dependencies_root(repository_root: Path) -> Path:
    """Return the relocatable store for native third-party dependencies."""

    return _configured_sibling_root(
        repository_root,
        environment_variable=DEPENDENCIES_ROOT_ENV,
        sibling_name="PerfectAssassin-Dependencies",
    )
