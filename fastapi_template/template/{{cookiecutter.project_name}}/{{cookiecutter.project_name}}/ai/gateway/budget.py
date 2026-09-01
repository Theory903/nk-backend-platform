"""Budget enforcement wrapper for chat models (P2)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.llm import AssistantReply, ChatModel, Message, ToolSpec
from {{cookiecutter.project_name}}.ai.usage import get_tracker
from {{cookiecutter.project_name}}.settings import settings


def _estimate_cost(messages: list[Message], reply: AssistantReply) -> float:
    """Rough USD estimate when providers do not return usage metadata."""
    prompt_chars = sum(len(message.content or "") for message in messages)
    completion_chars = len(reply.content or "")
    # Heuristic for local/dev; cloud adapters should record real usage later.
    return (prompt_chars + completion_chars) / 100_000


class BudgetEnforcingChatModel:
    """Reject completions when the process budget is exhausted."""

    def __init__(self, inner: ChatModel, *, capability: str = "chat") -> None:
        self._inner = inner
        self._capability = capability
        self._last_identity: tuple[str, str] | None = getattr(
            inner,
            "last_identity",
            None,
        )

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AssistantReply:
        budget = getattr(settings, "llm_cost_budget_usd", None)
        if budget is not None:
            spent = sum(record.cost_usd for record in get_tracker().all().values())
            if spent >= budget:
                raise RuntimeError(
                    f"LLM budget exhausted ({spent:.4f} >= {budget:.4f} USD)",
                )
        reply = await self._inner.complete(messages, tools)
        identity = getattr(self._inner, "last_identity", None)
        if identity:
            self._last_identity = identity
        provider = identity[0] if identity else f"capability:{self._capability}"
        get_tracker().record(
            provider,
            prompt_tokens=max(1, sum(len(m.content or "") for m in messages) // 4),
            completion_tokens=max(1, len(reply.content or "") // 4),
            cost=_estimate_cost(messages, reply),
        )
        if budget is not None:
            spent = sum(record.cost_usd for record in get_tracker().all().values())
            if spent > budget:
                raise RuntimeError(
                    f"LLM budget exceeded after completion ({spent:.4f} > {budget:.4f} USD)",
                )
        return reply

    @property
    def last_identity(self) -> tuple[str, str] | None:
        return self._last_identity


__all__ = ["BudgetEnforcingChatModel"]
