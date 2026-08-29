"""Template variable extraction."""

from __future__ import annotations

import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from {{cookiecutter.project_name}}.ai.prompts.models import PromptMessage

_FORMATTER = string.Formatter()


def _base_field_name(field_name: str | None) -> str | None:
    """
    Extract the root variable name from a format field.

    Examples:
      user          → user
      user.name     → user
      user[name]    → user
      user!r        → user
      user.name!s   → user
    """
    if not field_name:
        return None
    # Strip conversion/format already handled by Formatter.parse;
    # field_name may still contain . or [].
    name = field_name
    for sep in (".", "["):
        if sep in name:
            name = name.split(sep, 1)[0]
    name = name.strip()
    return name or None


def extract_variables_from_text(template: str) -> set[str]:
    """Extract top-level placeholder names via string.Formatter.parse."""
    names: set[str] = set()
    for _literal, field_name, _format_spec, _conversion in _FORMATTER.parse(template):
        base = _base_field_name(field_name)
        if base is not None:
            names.add(base)
    return names


def extract_variables(messages: tuple[PromptMessage, ...] | list[PromptMessage]) -> set[str]:
    """Extract placeholder names across all messages."""
    names: set[str] = set()
    for message in messages:
        names |= extract_variables_from_text(message.content)
    return names
