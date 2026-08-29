"""Prompt render cache abstraction."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol

from {{cookiecutter.project_name}}.ai.prompts.models import PromptTemplate, RenderedPrompt


class PromptCache(Protocol):
    async def get(self, key: str) -> RenderedPrompt | None:
        ...

    async def set(self, key: str, value: RenderedPrompt, ttl: int) -> None:
        ...


def cache_key(
    name: str,
    version: int,
    variant: str | None,
    values: dict[str, Any],
) -> str:
    """Stable cache key over prompt identity + canonical variables."""
    canonical = json.dumps(
        {
            "name": name,
            "version": version,
            "variant": variant,
            "values": values,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def may_cache(prompt: PromptTemplate) -> bool:
    """Refuse caching when any variable is secret or PII."""
    return not any(v.secret or v.pii for v in prompt.variables)


class MemoryPromptCache:
    """Process-local TTL cache. Prefer Redis in production; never store secrets."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, RenderedPrompt]] = {}

    async def get(self, key: str) -> RenderedPrompt | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: RenderedPrompt, ttl: int) -> None:
        # Defense in depth: refuse entries whose metadata marks secrets.
        if value.metadata.get("contains_secrets"):
            return
        self._store[key] = (time.monotonic() + max(ttl, 0), value)
