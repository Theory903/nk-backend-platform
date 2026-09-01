"""Defense-in-depth prompt, tool, and output security policies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from {{cookiecutter.project_name}}.platform.contracts import (
    PolicyDecision,
    Scope,
    ToolDescriptor,
    ToolInvocation,
)


class SecurityRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class PromptInspection:
    """Result of input inspection before model context construction."""

    allowed: bool
    risk: SecurityRisk
    reasons: tuple[str, ...] = ()
    sanitized: str = ""


class PromptInjectionDefense:
    """Detect common instruction-boundary attacks without claiming perfection."""

    _PATTERNS = (
        (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I), "instruction override"),
        (re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.I), "system prompt extraction"),
        (re.compile(r"developer\s+message|hidden\s+instructions", re.I), "boundary probing"),
    )

    def inspect(self, text: str) -> PromptInspection:
        reasons = tuple(
            reason
            for pattern, reason in self._PATTERNS
            if pattern.search(text)
        )
        risk = SecurityRisk.HIGH if reasons else SecurityRisk.LOW
        return PromptInspection(
            allowed=not reasons,
            risk=risk,
            reasons=reasons,
            sanitized=text.strip(),
        )


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """Authorization policy evaluated after identity and tenant checks."""

    allowed_tools: frozenset[str] | None = None
    denied_tools: frozenset[str] = frozenset()
    high_risk_requires_approval: bool = True

    def authorize(
        self,
        scope: Scope,
        descriptor: ToolDescriptor,
    ) -> PolicyDecision:
        if not scope.organization_id:
            return PolicyDecision(allowed=False, reason="organization is required")
        if descriptor.name in self.denied_tools:
            return PolicyDecision(allowed=False, reason="tool is denied by policy")
        if self.allowed_tools is not None and descriptor.name not in self.allowed_tools:
            return PolicyDecision(allowed=False, reason="tool is not in allow-list")
        requires_approval = descriptor.requires_approval or (
            self.high_risk_requires_approval and descriptor.risk.value == "high"
        )
        return PolicyDecision(
            allowed=True,
            requires_approval=requires_approval,
        )


@dataclass
class SecurityPipeline:
    """Composed model-input, tool, and output enforcement boundary."""

    prompt_defense: PromptInjectionDefense = field(
        default_factory=PromptInjectionDefense,
    )
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)

    def inspect_prompt(self, text: str) -> PromptInspection:
        return self.prompt_defense.inspect(text)

    def authorize_tool(
        self,
        invocation: ToolInvocation,
    ) -> PolicyDecision:
        return self.tool_policy.authorize(invocation.scope, invocation.descriptor)

    @staticmethod
    def validate_output(text: str, *, max_chars: int = 100_000) -> str:
        if len(text) > max_chars:
            raise ValueError("model output exceeds configured size limit")
        return text


__all__ = [
    "PromptInjectionDefense",
    "PromptInspection",
    "SecurityPipeline",
    "SecurityRisk",
    "ToolPolicy",
]
