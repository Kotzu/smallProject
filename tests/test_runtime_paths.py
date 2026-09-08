from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from perfect_assassin.runtime_paths import (
    DEPENDENCIES_ROOT_ENV,
    RUNTIME_ROOT_ENV,
    external_dependencies_root,
    external_runtime_root,
)


class RuntimePathTests(unittest.TestCase):
    def test_default_roots_are_repository_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "PerfectAssassin-Workspace"
            with patch.dict(
                os.environ,
                {RUNTIME_ROOT_ENV: "", DEPENDENCIES_ROOT_ENV: ""},
                clear=False,
            ):
                self.assertEqual(
                    external_runtime_root(repository),
                    repository.resolve().parent / "PerfectAssassin-Runtime",
                )
                self.assertEqual(
                    external_dependencies_root(repository),
                    repository.resolve().parent / "PerfectAssassin-Dependencies",
                )

    def test_absolute_environment_override_is_supported(self) -> None:
        repository = Path("C:/workspace/PerfectAssassin-Workspace")
        configured = Path("D:/PredatorRuntime")
        with patch.dict(os.environ, {RUNTIME_ROOT_ENV: str(configured)}):
            self.assertEqual(external_runtime_root(repository), configured)

    def test_relative_environment_override_fails_closed(self) -> None:
        with patch.dict(os.environ, {RUNTIME_ROOT_ENV: "relative/runtime"}):
            with self.assertRaisesRegex(ValueError, "absolute path"):
                external_runtime_root(Path("C:/workspace/project"))


if __name__ == "__main__":
    unittest.main()
