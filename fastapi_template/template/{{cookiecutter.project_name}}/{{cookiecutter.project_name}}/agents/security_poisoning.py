"""Tool poisoning detection for MCP and feature-pack tools (P18)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolPoisonInspection:
    allowed: bool
    reasons: tuple[str, ...] = ()


class ToolPoisoningDefense:
    """Detect instruction injection hidden in tool metadata."""

    _PATTERNS = (
        (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I), "instruction override in tool"),
        (re.compile(r"system\s+prompt", re.I), "system prompt reference in tool"),
        (re.compile(r"<\s*script", re.I), "script tag in tool metadata"),
        (re.compile(r"run\s+shell\s+command", re.I), "shell escalation hint in tool"),
    )

    def inspect(
        self,
        *,
        name: str,
        description: str,
        parameters: dict | None = None,
    ) -> ToolPoisonInspection:
        blob = " ".join(
            part
            for part in (
                name,
                description,
                str(parameters or {}),
            )
            if part
        )
        reasons = tuple(
            reason
            for pattern, reason in self._PATTERNS
            if pattern.search(blob)
        )
        return ToolPoisonInspection(allowed=not reasons, reasons=reasons)


__all__ = ["ToolPoisonInspection", "ToolPoisoningDefense"]
