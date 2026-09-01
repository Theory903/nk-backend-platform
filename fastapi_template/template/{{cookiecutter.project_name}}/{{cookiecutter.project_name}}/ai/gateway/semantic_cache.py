"""Exact + lightweight semantic completion cache for the model gateway (P2)."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from {{cookiecutter.project_name}}.ai.llm import AssistantReply, ChatModel, Message, ToolSpec, ToolCall
from {{cookiecutter.project_name}}.settings import settings


def _message_fingerprint(messages: list[Message], tools: list[ToolSpec]) -> str:
    payload = {
        "messages": [
            {"role": m.role, "content": m.content, "tool_call_id": m.tool_call_id}
            for m in messages
        ],
        "tools": [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _last_user_text(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content:
            return message.content.strip()
    return ""


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass(slots=True)
class _SemanticEntry:
    fingerprint: str
    embedding: list[float]
    reply: AssistantReply
    expires_at: float


class CompletionCache(Protocol):
    async def get_exact(self, fingerprint: str) -> AssistantReply | None: ...

    async def put_exact(
        self,
        fingerprint: str,
        reply: AssistantReply,
        *,
        ttl_seconds: int,
    ) -> None: ...

    async def get_semantic(
        self,
        embedding: list[float],
        *,
        threshold: float,
    ) -> AssistantReply | None: ...

    async def put_semantic(
        self,
        fingerprint: str,
        embedding: list[float],
        reply: AssistantReply,
        *,
        ttl_seconds: int,
    ) -> None: ...


class InMemoryCompletionCache:
    """Dev/test completion cache with optional semantic tier."""

    def __init__(self, *, max_semantic_entries: int = 128) -> None:
        self._exact: dict[str, tuple[AssistantReply, float]] = {}
        self._semantic: list[_SemanticEntry] = []
        self._max_semantic_entries = max_semantic_entries

    async def get_exact(self, fingerprint: str) -> AssistantReply | None:
        row = self._exact.get(fingerprint)
        if row is None:
            return None
        reply, expires_at = row
        if expires_at < time.time():
            self._exact.pop(fingerprint, None)
            return None
        return reply

    async def put_exact(
        self,
        fingerprint: str,
        reply: AssistantReply,
        *,
        ttl_seconds: int,
    ) -> None:
        self._exact[fingerprint] = (reply, time.time() + ttl_seconds)

    async def get_semantic(
        self,
        embedding: list[float],
        *,
        threshold: float,
    ) -> AssistantReply | None:
        now = time.time()
        best: tuple[float, AssistantReply] | None = None
        kept: list[_SemanticEntry] = []
        for entry in self._semantic:
            if entry.expires_at < now:
                continue
            kept.append(entry)
            score = _cosine(embedding, entry.embedding)
            if score >= threshold and (best is None or score > best[0]):
                best = (score, entry.reply)
        self._semantic = kept[-self._max_semantic_entries :]
        return best[1] if best else None

    async def put_semantic(
        self,
        fingerprint: str,
        embedding: list[float],
        reply: AssistantReply,
        *,
        ttl_seconds: int,
    ) -> None:
        self._semantic.append(
            _SemanticEntry(
                fingerprint=fingerprint,
                embedding=embedding,
                reply=reply,
                expires_at=time.time() + ttl_seconds,
            ),
        )
        if len(self._semantic) > self._max_semantic_entries:
            self._semantic = self._semantic[-self._max_semantic_entries :]


class RedisCompletionCache:
    """Shared exact cache; semantic tier stays in-process for now."""

    def __init__(self, redis_client: Any, *, prefix: str = "nk:llm:cache") -> None:
        self._redis = redis_client
        self._prefix = prefix.rstrip(":")
        self._semantic = InMemoryCompletionCache()

    def _exact_key(self, fingerprint: str) -> str:
        return f"{self._prefix}:exact:{fingerprint}"

    async def get_exact(self, fingerprint: str) -> AssistantReply | None:
        raw = await self._redis.get(self._exact_key(fingerprint))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return AssistantReply(
            content=data.get("content"),
            tool_calls=[ToolCall(**call) for call in data.get("tool_calls", [])],
        )

    async def put_exact(
        self,
        fingerprint: str,
        reply: AssistantReply,
        *,
        ttl_seconds: int,
    ) -> None:
        payload = json.dumps(
            {
                "content": reply.content,
                "tool_calls": [call.model_dump() for call in reply.tool_calls],
            },
        )
        await self._redis.set(self._exact_key(fingerprint), payload, ex=ttl_seconds)

    async def get_semantic(
        self,
        embedding: list[float],
        *,
        threshold: float,
    ) -> AssistantReply | None:
        return await self._semantic.get_semantic(embedding, threshold=threshold)

    async def put_semantic(
        self,
        fingerprint: str,
        embedding: list[float],
        reply: AssistantReply,
        *,
        ttl_seconds: int,
    ) -> None:
        await self._semantic.put_semantic(
            fingerprint,
            embedding,
            reply,
            ttl_seconds=ttl_seconds,
        )


class CachedChatModel:
    """Cache tool-free completions by exact hash and semantic similarity."""

    def __init__(
        self,
        inner: ChatModel,
        cache: CompletionCache,
        *,
        embedder: Any | None = None,
        capability: str = "chat",
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._embedder = embedder
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
        if tools:
            reply = await self._inner.complete(messages, tools)
            identity = getattr(self._inner, "last_identity", None)
            if identity:
                self._last_identity = identity
            return reply

        if not getattr(settings, "llm_semantic_cache_enabled", True):
            reply = await self._inner.complete(messages, tools)
            identity = getattr(self._inner, "last_identity", None)
            if identity:
                self._last_identity = identity
            return reply

        ttl = int(getattr(settings, "llm_semantic_cache_ttl_s", 3600))
        threshold = float(getattr(settings, "llm_semantic_cache_threshold", 0.92))
        fingerprint = _message_fingerprint(messages, tools)

        cached = await self._cache.get_exact(fingerprint)
        if cached is not None:
            return cached

        user_text = _last_user_text(messages)
        if user_text and self._embedder is not None:
            embedding = self._embedder.embed(user_text)
            semantic = await self._cache.get_semantic(embedding, threshold=threshold)
            if semantic is not None:
                return semantic

        reply = await self._inner.complete(messages, tools)
        identity = getattr(self._inner, "last_identity", None)
        if identity:
            self._last_identity = identity

        await self._cache.put_exact(fingerprint, reply, ttl_seconds=ttl)
        if user_text and self._embedder is not None:
            embedding = self._embedder.embed(user_text)
            await self._cache.put_semantic(
                fingerprint,
                embedding,
                reply,
                ttl_seconds=ttl,
            )
        return reply

    @property
    def last_identity(self) -> tuple[str, str] | None:
        return self._last_identity


_completion_cache: CompletionCache | None = None
_embedder: Any | None = None


def get_completion_cache() -> CompletionCache | None:
    return _completion_cache


def get_semantic_embedder() -> Any | None:
    return _embedder


def configure_completion_cache(
    cache: CompletionCache | None,
    *,
    embedder: Any | None = None,
) -> None:
    global _completion_cache, _embedder
    _completion_cache = cache
    _embedder = embedder


__all__ = [
    "CachedChatModel",
    "CompletionCache",
    "InMemoryCompletionCache",
    "RedisCompletionCache",
    "configure_completion_cache",
    "get_completion_cache",
    "get_semantic_embedder",
]
