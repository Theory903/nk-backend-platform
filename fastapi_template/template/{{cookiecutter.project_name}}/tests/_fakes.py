"""Test-only doubles. Never import from application code (gold kill-list)."""

from __future__ import annotations

import hashlib
import struct
from typing import Any

from {{cookiecutter.project_name}}.ai.llm import AssistantReply, Message, ToolSpec


class ScriptedChatModel:
    """
    Deterministic chat model for unit tests; replays replies in order and
    records every prompt it received.
    """

    def __init__(self, replies: list[AssistantReply] | None = None) -> None:
        self._replies = list(replies or [])
        self.requests: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AssistantReply:
        self.requests.append(list(messages))
        if not self._replies:
            raise AssertionError("ScriptedChatModel ran out of scripted replies")
        return self._replies.pop(0)


# Backward-compatible alias used by older tests
FakeChatModel = ScriptedChatModel


class ScriptedEmbeddingProvider:
    dimensions = 8

    def embed(self, text: str) -> list[float]:
        seed = sum(ord(ch) for ch in text) or 1
        return [
            ((seed * (index + 3)) % 100 - 50) / 50 for index in range(self.dimensions)
        ]


class FakeEmbeddingProvider:
    """Stable hash-derived vectors for tests only (not a production provider)."""

    dimensions = 32

    def embed(self, text: str) -> list[float]:
        digest = hashlib.blake2b(text.encode(), digest_size=64).digest()
        words = struct.unpack(f"{self.dimensions}H", digest)
        scale = float(max(words))
        return [((value / scale) * 2.0 - 1.0) if scale else 0.0 for value in words]


def any_llm_installed() -> bool:
    try:
        import any_llm  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def fastembed_installed() -> bool:
    try:
        import fastembed  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True
