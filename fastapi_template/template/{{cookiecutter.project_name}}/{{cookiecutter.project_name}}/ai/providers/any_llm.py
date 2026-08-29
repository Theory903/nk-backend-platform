"""Optional any-llm backed ChatModel (real path; no scripted fakes)."""

from __future__ import annotations

from typing import Any

from {{cookiecutter.project_name}}.ai.llm import (
    AssistantReply,
    Message,
    ToolCall,
    ToolSpec,
)


class AnyLLMChatModel:
    """Thin adapter over ``any_llm.acompletion`` when the package is installed."""

    def __init__(self, provider: str = "ollama", model: str | None = None) -> None:
        self.provider = provider
        self.model = model or "llama3.2"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AssistantReply:
        try:
            from any_llm import acompletion
        except ImportError as exc:
            raise RuntimeError(
                "any-llm-sdk is not installed; add the LLM dependency group",
            ) from exc

        payload: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content or ""} for m in messages
        ]
        kwargs: dict[str, Any] = {
            "model": f"{self.provider}/{self.model}",
            "messages": payload,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        response = await acompletion(**kwargs)
        choice = response.choices[0].message
        tool_calls: list[ToolCall] = []
        for call in getattr(choice, "tool_calls", None) or []:
            import json

            args = call.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(
                ToolCall(
                    id=getattr(call, "id", call.function.name),
                    name=call.function.name,
                    arguments=args or {},
                ),
            )
        return AssistantReply(content=choice.content, tool_calls=tool_calls)
