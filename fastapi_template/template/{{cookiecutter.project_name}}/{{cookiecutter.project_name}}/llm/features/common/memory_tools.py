"""Memory helpers for memory_chat feature pack."""

from __future__ import annotations

from {{cookiecutter.project_name}}.agents.memory import MemoryStore
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext


def _store(ctx: FeatureContext) -> MemoryStore:
    if ctx.memory_store is None:
        raise RuntimeError("memory store not configured")
    return ctx.memory_store


def remember_fact(ctx: FeatureContext, *, user_id: str, fact: str) -> str:
    store = _store(ctx)
    store.remember(user_id, fact)
    return f"remembered: {fact[:500]}"


def recall_facts(
    ctx: FeatureContext,
    *,
    user_id: str,
    query: str | None = None,
    limit: int = 5,
) -> list[str]:
    return _store(ctx).recall(user_id, query=query, limit=limit)


def format_memory_context(facts: list[str]) -> str:
    if not facts:
        return ""
    lines = ["Known facts about the user:"]
    lines.extend(f"- {fact}" for fact in facts)
    return "\n".join(lines)


__all__ = ["format_memory_context", "recall_facts", "remember_fact"]
