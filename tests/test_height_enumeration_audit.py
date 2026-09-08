import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "height_enumeration_audit", ROOT / "tools/audit_height_enumeration.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_extracts_only_complete_nested_function_body():
    assert (
        audit.function_body("before f() { if (x) { y(); } } after", "f()")
        == "{ if (x) { y(); } }"
    )


@pytest.mark.parametrize("text", ["missing", "f() {", "f() { if(x) { y(); }"])
def test_missing_or_truncated_source_cannot_pass_parity(text):
    with pytest.raises(ValueError):
        audit.function_body(text, "f()")


def test_fixture_parity_region_preserves_the_suspect_upper_bound_branch():
    source = (ROOT / "native/height_enumeration_audit/main.cpp").read_text()
    body = audit.function_body(source, "bool AuditMap::FindHeights(")
    assert "if (next == current)" in body
    assert "if (current < tile->m_bounds.getMaximum().Z)" in body
    assert "output.push_back(adtHeight);" in body
