from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import jsonschema_rs
from jsonschema import Draft202012Validator


class ContractValidationError(ValueError):
    """Raised when data does not satisfy a versioned contract."""


class ContractValidator:
    def __init__(self, schema_path: Path) -> None:
        self.schema_path = schema_path
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self._validator = jsonschema_rs.Draft202012Validator(
            schema,
            validate_formats=True,
            ignore_unknown_formats=True,
        )

    def validate(self, value: Any) -> None:
        non_finite_path = _first_non_finite_path(value)
        if non_finite_path is not None:
            raise ContractValidationError(
                f"{self.schema_path.name}: {non_finite_path}: "
                "non-finite numbers are not valid JSON"
            )
        try:
            self._validator.validate(value)
        except jsonschema_rs.ValidationError as error:
            path = str(error.instance_path).strip("/") or "<root>"
            raise ContractValidationError(
                f"{self.schema_path.name}: {path}: {error.message}"
            ) from error


def _first_non_finite_path(value: Any, path: str = "<root>") -> str | None:
    if isinstance(value, float) and not math.isfinite(value):
        return path
    if isinstance(value, dict):
        for key, child in value.items():
            result = _first_non_finite_path(
                child,
                str(key) if path == "<root>" else f"{path}.{key}",
            )
            if result is not None:
                return result
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            result = _first_non_finite_path(child, f"{path}[{index}]")
            if result is not None:
                return result
    return None
