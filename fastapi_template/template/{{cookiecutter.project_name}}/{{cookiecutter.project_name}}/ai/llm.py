from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

Role = Literal["system", "user", "assistant", "tool"]


class Message(BaseModel):
    role: Role = "user"
    content: str | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = {}


class AssistantReply(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = []


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


@runtime_checkable
class ChatModel(Protocol):
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AssistantReply: ...


def get_chat_model(provider: str, *, model: str | None = None) -> ChatModel:
    """
    Resolve a chat model by provider name.

    Scripted doubles belong in ``tests/_fakes.py`` only (gold kill-list).
    Optional ``any_llm`` adapter is used when installed.
    """
    if provider in {"any_llm", "ollama", "openai", "anthropic"}:
        try:
            from {{cookiecutter.project_name}}.ai.providers.any_llm import (
                AnyLLMChatModel,
            )
        except ImportError as exc:
            raise ValueError(
                f"provider {provider!r} needs any-llm-sdk; "
                f"install the LLM extra or use a ScriptedChatModel in tests",
            ) from exc
        return AnyLLMChatModel(provider=provider, model=model)

    raise ValueError(
        f"chat model provider {provider!r} is not configured; "
        f"wire an adapter under ai/providers/ or use tests/_fakes.ScriptedChatModel",
    )
