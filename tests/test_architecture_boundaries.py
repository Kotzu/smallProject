from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "perfect_assassin"


def _imports_below(directory: Path) -> list[tuple[Path, str]]:
    imports: list[tuple[Path, str]] = []
    for path in sorted(directory.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend((path, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append((path, node.module))
    return imports


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_brain_does_not_import_outward_implementations(self) -> None:
        forbidden = (
            "perfect_assassin.adapter",
            "perfect_assassin.application",
            "perfect_assassin.execution",
            "perfect_assassin.journal",
            "perfect_assassin.lab",
            "perfect_assassin.observer",
            "perfect_assassin.replay",
        )
        violations = [
            (str(path.relative_to(ROOT)), module)
            for path, module in _imports_below(PACKAGE / "brain")
            if module.startswith(forbidden)
        ]
        self.assertEqual(violations, [])

    def test_domain_and_movement_do_not_import_execution(self) -> None:
        violations = [
            (str(path.relative_to(ROOT)), module)
            for directory in (PACKAGE / "domain", PACKAGE / "movement")
            for path, module in _imports_below(directory)
            if module.startswith("perfect_assassin.execution")
        ]
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
