from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final


class GuardrailViolation(PermissionError):
    """Raised when a tool violates the configured guardrail policy."""


InputHook = Callable[[str], str]
OutputHook = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class Guardrails:
    """
    Static tool allow/deny policy plus optional I/O rewrite hooks.

    Evaluation order for tools:
    1. Explicit deny always wins.
    2. If an allow-list exists, the tool must be present in it.
    3. Otherwise the tool is allowed.

    An empty allow-set means no tools are allowed.
    """

    allow: frozenset[str] | None = None
    deny: frozenset[str] = frozenset()
    input_hooks: tuple[InputHook, ...] = ()
    output_hooks: tuple[OutputHook, ...] = ()

    def __init__(
        self,
        allow: set[str] | frozenset[str] | None = None,
        deny: set[str] | frozenset[str] | None = None,
        input_hooks: list[InputHook] | tuple[InputHook, ...] | None = None,
        output_hooks: list[OutputHook] | tuple[OutputHook, ...] | None = None,
    ) -> None:
        object.__setattr__(
            self,
            "allow",
            None if allow is None else frozenset(allow),
        )
        object.__setattr__(
            self,
            "deny",
            frozenset(deny or ()),
        )
        object.__setattr__(
            self,
            "input_hooks",
            tuple(input_hooks or ()),
        )
        object.__setattr__(
            self,
            "output_hooks",
            tuple(output_hooks or ()),
        )

        overlap = self.allow & self.deny if self.allow is not None else set()

        if overlap:
            raise ValueError(
                "tools cannot be both allowed and denied: "
                + ", ".join(sorted(overlap))
            )

    def check_input(self, text: str) -> str:
        """Run input hooks in order; each may rewrite the text."""
        for hook in self.input_hooks:
            text = hook(text)
        return text

    def check_output(self, text: str) -> str:
        """Run output hooks; a hook returning None leaves text unchanged."""
        for hook in self.output_hooks:
            rewritten = hook(text)
            if rewritten is not None:
                text = rewritten
        return text

    def check(self, name: str) -> str | None:
        """
        Return a denial reason, or None when the tool is permitted.
        """
        name = name.strip()

        if not name:
            return "DENIED: tool name cannot be empty"

        if name in self.deny:
            return f"DENIED: tool '{name}' is not allowed"

        if self.allow is not None and name not in self.allow:
            return f"DENIED: tool '{name}' is not in the allowed set"

        return None

    def check_tool(self, name: str) -> str | None:
        """Alias for :meth:`check` used by 3-layer guardrail tests."""
        return self.check(name)

    def is_allowed(self, name: str) -> bool:
        """Return whether a tool is allowed."""
        return self.check(name) is None

    def require(self, name: str) -> None:
        """
        Enforce the policy.

        Raises:
            GuardrailViolation: when the tool is denied.
        """
        reason = self.check(name)

        if reason is not None:
            raise GuardrailViolation(reason)

    def with_allow(
        self,
        *names: str,
    ) -> Guardrails:
        """Return a new policy with additional allowed tools."""
        current = set(self.allow or ())
        current.update(names)

        return Guardrails(
            allow=current,
            deny=set(self.deny),
            input_hooks=list(self.input_hooks),
            output_hooks=list(self.output_hooks),
        )

    def with_deny(
        self,
        *names: str,
    ) -> Guardrails:
        """Return a new policy with additional denied tools."""
        current = set(self.deny)
        current.update(names)

        return Guardrails(
            allow=set(self.allow) if self.allow is not None else None,
            deny=current,
            input_hooks=list(self.input_hooks),
            output_hooks=list(self.output_hooks),
        )


__all__ = [
    "GuardrailViolation",
    "Guardrails",
]
