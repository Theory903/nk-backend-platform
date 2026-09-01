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

try:
    from {{cookiecutter.project_name}}.agents.security_loader import SecurityManifest
except ImportError:
    SecurityManifest = None  # type: ignore[misc,assignment]


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
    pii_redactor: Any | None = None
    tool_poisoning: Any | None = None
    manifest: Any | None = None

    def __post_init__(self) -> None:
        if self.pii_redactor is None:
            from {{cookiecutter.project_name}}.agents.security_pii import PIIRedactor

            self.pii_redactor = PIIRedactor()
        if self.tool_poisoning is None:
            from {{cookiecutter.project_name}}.agents.security_poisoning import (
                ToolPoisoningDefense,
            )

            self.tool_poisoning = ToolPoisoningDefense()
        if self.manifest is None:
            from {{cookiecutter.project_name}}.agents.security_loader import (
                load_security_manifest,
            )

            self.manifest = load_security_manifest()

    def inspect_prompt(self, text: str) -> PromptInspection:
        inspection = self.prompt_defense.inspect(text)
        if (
            inspection.allowed
            and getattr(self.manifest, "redact_pii_in_context", True)
            and self.pii_redactor is not None
        ):
            sanitized = self.pii_redactor.redact(inspection.sanitized)
            return PromptInspection(
                allowed=True,
                risk=inspection.risk,
                reasons=inspection.reasons,
                sanitized=sanitized,
            )
        return inspection

    def inspect_tool_poisoning(
        self,
        descriptor: ToolDescriptor,
        *,
        input_schema: dict | None = None,
    ) -> PolicyDecision | None:
        if not getattr(self.manifest, "scan_tool_poisoning", True):
            return None
        if self.tool_poisoning is None:
            return None
        poison = self.tool_poisoning.inspect(
            name=descriptor.name,
            description=descriptor.description,
            parameters=input_schema,
        )
        if not poison.allowed:
            return PolicyDecision(
                allowed=False,
                reason=f"tool poisoning detected: {', '.join(poison.reasons)}",
            )
        return None

    def authorize_tool(
        self,
        invocation: ToolInvocation,
    ) -> PolicyDecision:
        denial = self.inspect_tool_poisoning(
            invocation.descriptor,
            input_schema=invocation.descriptor.input_schema,
        )
        if denial is not None:
            return denial
        return self.tool_policy.authorize(invocation.scope, invocation.descriptor)

    def finalize_output(self, text: str, *, max_chars: int = 100_000) -> str:
        if len(text) > max_chars:
            raise ValueError("model output exceeds configured size limit")
        if getattr(self.manifest, "redact_pii_in_output", True) and self.pii_redactor:
            return self.pii_redactor.redact(text)
        return text

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
