"""Typed variable validation for prompt rendering."""

from __future__ import annotations

from typing import Any

from {{cookiecutter.project_name}}.ai.prompts.exceptions import PromptRenderError
from {{cookiecutter.project_name}}.ai.prompts.models import PromptTemplate, PromptVariable

_TYPE_CHECKS: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "float": (int, float),
    "boolean": bool,
    "list[string]": list,
    "dict": dict,
    "any": object,
}


def _check_type(variable: PromptVariable, value: Any) -> None:
    expected = _TYPE_CHECKS.get(variable.type, object)
    if variable.type == "any":
        return
    if variable.type == "list[string]":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise PromptRenderError(
                f"{variable.name!r} expected list[string], got {type(value).__name__}"
            )
        return
    if variable.type == "float" and isinstance(value, bool):
        # bool is a subclass of int — reject for numeric slots.
        raise PromptRenderError(
            f"{variable.name!r} expected float, got bool"
        )
    if variable.type == "integer" and isinstance(value, bool):
        raise PromptRenderError(
            f"{variable.name!r} expected integer, got bool"
        )
    if not isinstance(value, expected):
        label = (
            expected.__name__
            if isinstance(expected, type)
            else " | ".join(t.__name__ for t in expected)
        )
        raise PromptRenderError(
            f"{variable.name!r} expected {label}, got {type(value).__name__}"
        )


def validate_variables(
    prompt: PromptTemplate,
    values: dict[str, Any],
    *,
    allow_extra: bool = False,
) -> dict[str, Any]:
    """
    Validate and normalize render inputs.

    Applies defaults for missing optional variables.
    Raises PromptRenderError on missing/unknown/type mismatches.
    """
    declared = {v.name: v for v in prompt.variables}
    normalized = dict(values)

    for name, variable in declared.items():
        if name not in normalized and variable.default is not None:
            normalized[name] = variable.default

    # Declared vars without a value/default cannot be rendered.
    missing = [
        name
        for name, variable in declared.items()
        if name not in normalized and variable.default is None
    ]
    if missing:
        raise PromptRenderError(
            f"'{prompt.name}' missing required variables: {sorted(missing)}"
        )

    if not allow_extra:
        unknown = set(normalized) - set(declared)
        if unknown and declared:
            raise PromptRenderError(
                f"'{prompt.name}' unknown variables: {sorted(unknown)}"
            )

    for name, value in normalized.items():
        variable = declared.get(name)
        if variable is None:
            continue
        _check_type(variable, value)

    return normalized


def redact_for_logging(
    prompt: PromptTemplate,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Strip secret/PII/non-loggable variables before observability export."""
    declared = {v.name: v for v in prompt.variables}
    safe: dict[str, Any] = {}
    for name, value in values.items():
        variable = declared.get(name)
        if variable is None:
            continue
        if variable.secret or variable.pii or not variable.log:
            safe[name] = "***"
        else:
            safe[name] = value
    return safe
