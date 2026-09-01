"""Apply and revert configuration mutations (P26)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from {{cookiecutter.project_name}}.research.experiments.contracts import MutationSpec


def apply_mutation(base: dict[str, Any], mutation: MutationSpec) -> dict[str, Any]:
    """Return a copied config with mutation changes applied."""
    updated = deepcopy(base)
    for key, value in mutation.changes.items():
        if key == "system_prompt_suffix" and isinstance(value, str):
            current = str(updated.get("system_prompt", ""))
            updated["system_prompt"] = f"{current}{value}".strip()
        elif key == "runtime_mode" and isinstance(value, str):
            updated["runtime_mode"] = value
        elif key == "capability" and isinstance(value, str):
            updated["capability"] = value
        else:
            updated[key] = value
    return updated


def revert_mutation(base: dict[str, Any], _mutation: MutationSpec) -> dict[str, Any]:
    """Revert by restoring the baseline configuration snapshot."""
    return deepcopy(base)


__all__ = ["apply_mutation", "revert_mutation"]
