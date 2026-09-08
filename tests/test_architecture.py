from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "perfect_assassin"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_brain_depends_only_on_python_and_domain(self) -> None:
        imports = set().union(
            *(imported_modules(path) for path in (PACKAGE / "brain").glob("*.py"))
        )
        internal = {name for name in imports if name.startswith("perfect_assassin.")}
        self.assertTrue(
            all(name.startswith("perfect_assassin.domain") for name in internal),
            f"Brain has outward imports: {sorted(internal)}",
        )

    def test_m1_has_no_input_or_process_execution_libraries(self) -> None:
        forbidden_roots = {"ctypes", "keyboard", "mouse", "pyautogui", "pynput", "socket", "subprocess"}
        violations: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            for module in imported_modules(path):
                if module.split(".", 1)[0] in forbidden_roots:
                    violations.append(f"{path.relative_to(ROOT)} -> {module}")
        self.assertEqual(violations, [])

    def test_win32_input_transport_is_external_and_gateway_uses_the_port(self) -> None:
        core_sink = PACKAGE / "execution" / "windows_send_input.py"
        native_backend = (
            ROOT / "integrations" / "windows-input" / "send_input_backend.py"
        )
        gateway = PACKAGE / "execution" / "gateway.py"

        self.assertNotIn("ctypes", imported_modules(core_sink))
        self.assertIn("ctypes", imported_modules(native_backend))
        self.assertNotIn(
            "perfect_assassin.execution.gateway", imported_modules(native_backend)
        )
        self.assertIn("perfect_assassin.execution.ports", imported_modules(gateway))


if __name__ == "__main__":
    unittest.main()
