"""Provider-neutral moderation gate for model inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ModerationDecision:
    allowed: bool
    categories: tuple[str, ...] = ()
    reason: str | None = None


class ModerationProvider(Protocol):
    async def check(self, text: str) -> ModerationDecision:
        """Classify text before it reaches a model or user."""


class KeywordModeration:
    """Deterministic baseline policy; replace with a provider adapter."""

    def __init__(self, blocked_terms: set[str] | None = None) -> None:
        self._blocked = {term.casefold() for term in (blocked_terms or set())}

    async def check(self, text: str) -> ModerationDecision:
        hits = tuple(sorted(term for term in self._blocked if term in text.casefold()))
        return ModerationDecision(
            allowed=not hits,
            categories=("blocked_term",) if hits else (),
            reason="moderation policy matched a blocked term" if hits else None,
        )


__all__ = ["KeywordModeration", "ModerationDecision", "ModerationProvider"]
