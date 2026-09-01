"""Instrumented ChatModel wrapper for GenAI spans and metrics (P19)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.llm import AssistantReply, ChatModel, Message, ToolSpec
from {{cookiecutter.project_name}}.observability.genai.metrics import record_completion_latency
from {{cookiecutter.project_name}}.observability.genai.spans import genai_chat_span, set_chat_span_usage


class InstrumentedChatModel:
    """Wrap a ChatModel with OTel GenAI spans and latency/cost metrics."""

    def __init__(
        self,
        inner: ChatModel,
        *,
        capability: str = "chat",
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self._inner = inner
        self._capability = capability
        self._provider = provider
        self._model = model
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
        identity = getattr(self._inner, "last_identity", None) or self._last_identity
        system = self._provider or (identity[0] if identity else "unknown")
        model_name = self._model or (identity[1] if identity else "unknown")

        with genai_chat_span(
            system=system,
            model=model_name,
            capability=self._capability,
        ) as span_state:
            reply = await self._inner.complete(messages, tools)
            identity = getattr(self._inner, "last_identity", None)
            if identity:
                self._last_identity = identity
                system, model_name = identity

            input_tokens = max(1, sum(len(m.content or "") for m in messages) // 4)
            output_tokens = max(1, len(reply.content or "") // 4)
            set_chat_span_usage(
                span_state,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason="tool_calls" if reply.tool_calls else "stop",
            )
            record_completion_latency(
                provider=system,
                model=model_name,
                capability=self._capability,
                duration_s=float(span_state.get("duration_s") or 0.0),
            )
            return reply

    @property
    def last_identity(self) -> tuple[str, str] | None:
        return self._last_identity


__all__ = ["InstrumentedChatModel"]
