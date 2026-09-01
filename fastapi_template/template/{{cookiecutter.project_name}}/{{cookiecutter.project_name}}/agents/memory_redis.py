"""Redis-backed episodic / conversation / working memory (P1).

Uses a synchronous redis-py client so agent tools keep the same sync API as
``MemoryStore``. Application lifespan creates the client from ``settings.redis_url``.
"""

from __future__ import annotations

import json
from typing import Any

from {{cookiecutter.project_name}}.agents.memory import (
    MemoryConfig,
    MemoryItem,
    _copy_item,
    _lexical_score,
    _require_id,
    _validate_limit,
)


class RedisMemoryStore:
    """Durable memory store backed by Redis lists."""

    __slots__ = ("_client", "_prefix", "_config")

    def __init__(
        self,
        client: Any,
        *,
        prefix: str = "nk:memory",
        config: MemoryConfig | None = None,
    ) -> None:
        self._client = client
        self._prefix = prefix.rstrip(":")
        self._config = config or MemoryConfig()

    def _key(self, tier: str, entity_id: str) -> str:
        return f"{self._prefix}:{tier}:{entity_id}"

    def _append_limited(self, key: str, payload: str, *, max_items: int) -> None:
        pipe = self._client.pipeline()
        pipe.rpush(key, payload)
        pipe.ltrim(key, -max_items, -1)
        pipe.execute()

    def push_working(self, run_id: str, item: MemoryItem) -> None:
        run_id = _require_id(run_id, "run_id")
        item = _copy_item(item)
        self._append_limited(
            self._key("working", run_id),
            json.dumps(item),
            max_items=self._config.max_working_items,
        )

    def get_working(self, run_id: str) -> list[MemoryItem]:
        run_id = _require_id(run_id, "run_id")
        raw = self._client.lrange(self._key("working", run_id), 0, -1)
        return [json.loads(entry) for entry in raw]

    def clear_working(self, run_id: str) -> None:
        run_id = _require_id(run_id, "run_id")
        self._client.delete(self._key("working", run_id))

    def push_conversation(self, thread_id: str, item: MemoryItem) -> None:
        thread_id = _require_id(thread_id, "thread_id")
        item = _copy_item(item)
        self._append_limited(
            self._key("conversation", thread_id),
            json.dumps(item),
            max_items=self._config.max_conversation_items,
        )

    def get_conversation(self, thread_id: str, limit: int = 50) -> list[MemoryItem]:
        thread_id = _require_id(thread_id, "thread_id")
        limit = _validate_limit(limit)
        raw = self._client.lrange(self._key("conversation", thread_id), -limit, -1)
        return [json.loads(entry) for entry in raw]

    def clear_conversation(self, thread_id: str) -> None:
        thread_id = _require_id(thread_id, "thread_id")
        self._client.delete(self._key("conversation", thread_id))

    def remember(self, user_id: str, fact: str) -> None:
        user_id = _require_id(user_id, "user_id")
        fact = fact.strip()
        if not fact:
            raise ValueError("fact cannot be empty")
        key = self._key("episodic", user_id)
        existing = self._client.lrange(key, 0, -1)
        if fact in existing:
            return
        self._append_limited(key, fact, max_items=self._config.max_episodic_items)

    def recall(
        self,
        user_id: str,
        query: str | None = None,
        limit: int = 5,
    ) -> list[str]:
        user_id = _require_id(user_id, "user_id")
        limit = _validate_limit(limit)
        items = list(self._client.lrange(self._key("episodic", user_id), 0, -1))
        if not query:
            return items[-limit:]
        query_norm = query.strip().casefold()
        if not query_norm:
            return items[-limit:]
        scored = sorted(
            enumerate(items),
            key=lambda pair: (_lexical_score(pair[1], query_norm), pair[0]),
            reverse=True,
        )
        return [
            fact
            for _, fact in scored[:limit]
            if _lexical_score(fact, query_norm) > 0
        ]

    def forget(self, user_id: str, fact: str) -> bool:
        user_id = _require_id(user_id, "user_id")
        fact = fact.strip()
        key = self._key("episodic", user_id)
        removed = self._client.lrem(key, 1, fact)
        return removed > 0

    def clear_user(self, user_id: str) -> None:
        user_id = _require_id(user_id, "user_id")
        self._client.delete(self._key("episodic", user_id))


__all__ = ["RedisMemoryStore"]
