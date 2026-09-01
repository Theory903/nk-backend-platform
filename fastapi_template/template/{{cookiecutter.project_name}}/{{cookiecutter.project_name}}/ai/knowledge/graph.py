"""GraphRAG adapter boundary with a deterministic local implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class GraphFact:
    subject: str
    predicate: str
    object: str
    source_chunk_id: str


class GraphRetriever(Protocol):
    async def related(self, subject: str, *, limit: int = 10) -> list[GraphFact]:
        """Return facts related to a subject."""


class InMemoryGraphRetriever:
    """Reference implementation for tests and local exploration."""

    def __init__(self, facts: list[GraphFact] | None = None) -> None:
        self._facts = list(facts or [])

    def add(self, fact: GraphFact) -> None:
        self._facts.append(fact)

    async def related(self, subject: str, *, limit: int = 10) -> list[GraphFact]:
        if limit <= 0:
            return []
        return [
            fact
            for fact in self._facts
            if fact.subject.casefold() == subject.casefold()
            or fact.object.casefold() == subject.casefold()
        ][:limit]


__all__ = ["GraphFact", "GraphRetriever", "InMemoryGraphRetriever"]
