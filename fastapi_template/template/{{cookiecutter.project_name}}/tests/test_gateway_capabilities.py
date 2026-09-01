"""Tests for capability-based model gateway (P2)."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.ai.gateway.capabilities import resolve_capability
from {{cookiecutter.project_name}}.ai.gateway.router import ModelRouter, Route
from {{cookiecutter.project_name}}.ai.gateway.semantic_cache import (
    InMemoryCompletionCache,
    _message_fingerprint,
    configure_completion_cache,
)
from {{cookiecutter.project_name}}.ai.llm import AssistantReply, Message
from {{cookiecutter.project_name}}.ai.usage import get_tracker


class _ScriptedModel:
    def __init__(self) -> None:
        self.calls = 0
        self.last_identity = ("scripted", "demo")

    async def complete(self, messages, tools):  # noqa: ANN001
        self.calls += 1
        return AssistantReply(content=f"ok:{len(messages)}")


@pytest.mark.asyncio
async def test_semantic_cache_exact_hit() -> None:
    cache = InMemoryCompletionCache()
    configure_completion_cache(cache)
    model = _ScriptedModel()
    from {{cookiecutter.project_name}}.ai.gateway.semantic_cache import CachedChatModel

    wrapped = CachedChatModel(model, cache, embedder=None, capability="chat")
    messages = [Message(role="user", content="hello")]
    first = await wrapped.complete(messages, [])
    second = await wrapped.complete(messages, [])
    assert first.content == "ok:1"
    assert second.content == "ok:1"
    assert model.calls == 1
    configure_completion_cache(None)


def test_resolve_capability_aliases() -> None:
    aliases = {"default": "chat", "fast": "fast"}
    assert resolve_capability("default", aliases) == "chat"
    assert resolve_capability("reasoning", aliases) == "reasoning"


def test_capabilities_manifest_loads() -> None:
    from {{cookiecutter.project_name}}.ai.gateway.capabilities import load_capability_routes

    routes, aliases = load_capability_routes()
    assert "chat" in routes
    assert aliases["default"] == "chat"


def test_budget_tracker_records_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    get_tracker().reset()
    router = ModelRouter(
        routes={"chat": Route(provider="ollama", model="llama3.2")},
        task_aliases={"default": "chat"},
    )
    assert router.for_capability("chat").provider == "ollama"
    assert _message_fingerprint([Message(role="user", content="x")], [])
