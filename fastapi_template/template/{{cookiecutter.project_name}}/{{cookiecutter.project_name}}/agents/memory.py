"""NK tiered memory abstraction.

Memory tiers:
- working: per-run ephemeral state
- conversation: per-thread conversational state
- episodic: durable user-level facts

The in-memory implementation is suitable for development and tests.
Production persistence should be provided through an adapter, such as
LangGraph Store, Redis, MongoDB, PostgreSQL, or a vector store.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from threading import RLock
from typing import Any, Protocol


MemoryItem = dict[str, Any]


class MemoryBackend(Protocol):
    """Backend contract for persistent memory implementations."""

    def push_working(
        self,
        run_id: str,
        item: MemoryItem,
    ) -> None:
        ...

    def get_working(
        self,
        run_id: str,
    ) -> list[MemoryItem]:
        ...

    def push_conversation(
        self,
        thread_id: str,
        item: MemoryItem,
    ) -> None:
        ...

    def get_conversation(
        self,
        thread_id: str,
        limit: int = 50,
    ) -> list[MemoryItem]:
        ...

    def remember(
        self,
        user_id: str,
        fact: str,
    ) -> None:
        ...

    def recall(
        self,
        user_id: str,
        query: str | None = None,
        limit: int = 5,
    ) -> list[str]:
        ...


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    """Limits applied by the default in-memory backend."""

    max_working_items: int = 1_000
    max_conversation_items: int = 10_000
    max_episodic_items: int = 10_000

    def __post_init__(self) -> None:
        if self.max_working_items < 1:
            raise ValueError(
                "max_working_items must be >= 1"
            )

        if self.max_conversation_items < 1:
            raise ValueError(
                "max_conversation_items must be >= 1"
            )

        if self.max_episodic_items < 1:
            raise ValueError(
                "max_episodic_items must be >= 1"
            )


class MemoryStore:
    """
    Thread-safe development memory store.

    This class defines the NK memory contract. Persistent implementations
    should satisfy the same interface.

    Memory ownership:
        working      -> run_id
        conversation -> thread_id
        episodic     -> user_id
    """

    __slots__ = (
        "_working",
        "_conversation",
        "_episodic",
        "_lock",
        "_config",
    )

    def __init__(
        self,
        *,
        config: MemoryConfig | None = None,
    ) -> None:
        self._working: dict[
            str,
            list[MemoryItem],
        ] = defaultdict(list)

        self._conversation: dict[
            str,
            list[MemoryItem],
        ] = defaultdict(list)

        self._episodic: dict[
            str,
            list[str],
        ] = defaultdict(list)

        self._lock = RLock()
        self._config = config or MemoryConfig()

    # ------------------------------------------------------------------
    # Working memory
    # ------------------------------------------------------------------

    def push_working(
        self,
        run_id: str,
        item: MemoryItem,
    ) -> None:
        run_id = _require_id(
            run_id,
            "run_id",
        )

        item = _copy_item(item)

        with self._lock:
            items = self._working[run_id]
            items.append(item)

            if len(items) > self._config.max_working_items:
                del items[
                    : len(items)
                    - self._config.max_working_items
                ]

    def get_working(
        self,
        run_id: str,
    ) -> list[MemoryItem]:
        run_id = _require_id(
            run_id,
            "run_id",
        )

        with self._lock:
            return [
                _copy_item(item)
                for item in self._working.get(run_id, ())
            ]

    def clear_working(
        self,
        run_id: str,
    ) -> None:
        run_id = _require_id(
            run_id,
            "run_id",
        )

        with self._lock:
            self._working.pop(run_id, None)

    # ------------------------------------------------------------------
    # Conversation memory
    # ------------------------------------------------------------------

    def push_conversation(
        self,
        thread_id: str,
        item: MemoryItem,
    ) -> None:
        thread_id = _require_id(
            thread_id,
            "thread_id",
        )

        item = _copy_item(item)

        with self._lock:
            items = self._conversation[thread_id]
            items.append(item)

            if len(items) > self._config.max_conversation_items:
                del items[
                    : len(items)
                    - self._config.max_conversation_items
                ]

    def get_conversation(
        self,
        thread_id: str,
        limit: int = 50,
    ) -> list[MemoryItem]:
        thread_id = _require_id(
            thread_id,
            "thread_id",
        )

        limit = _validate_limit(limit)

        with self._lock:
            return [
                _copy_item(item)
                for item in self._conversation.get(
                    thread_id,
                    (),
                )[-limit:]
            ]

    def clear_conversation(
        self,
        thread_id: str,
    ) -> None:
        thread_id = _require_id(
            thread_id,
            "thread_id",
        )

        with self._lock:
            self._conversation.pop(
                thread_id,
                None,
            )

    # ------------------------------------------------------------------
    # Episodic memory
    # ------------------------------------------------------------------

    def remember(
        self,
        user_id: str,
        fact: str,
    ) -> None:
        user_id = _require_id(
            user_id,
            "user_id",
        )

        fact = fact.strip()

        if not fact:
            raise ValueError(
                "fact cannot be empty"
            )

        with self._lock:
            items = self._episodic[user_id]

            # Avoid storing exact duplicate facts.
            if fact in items:
                return

            items.append(fact)

            if len(items) > self._config.max_episodic_items:
                del items[
                    : len(items)
                    - self._config.max_episodic_items
                ]

    def recall(
        self,
        user_id: str,
        query: str | None = None,
        limit: int = 5,
    ) -> list[str]:
        user_id = _require_id(
            user_id,
            "user_id",
        )

        limit = _validate_limit(limit)

        with self._lock:
            items = list(
                self._episodic.get(
                    user_id,
                    (),
                )
            )

        if not query:
            return items[-limit:]

        query = query.strip().casefold()

        if not query:
            return items[-limit:]

        # Simple lexical matching for the development backend.
        # Production semantic retrieval belongs in the backend adapter.
        scored = sorted(
            enumerate(items),
            key=lambda pair: (
                _lexical_score(
                    pair[1],
                    query,
                ),
                pair[0],
            ),
            reverse=True,
        )

        return [
            fact
            for _, fact in scored[:limit]
            if _lexical_score(fact, query) > 0
        ]

    def forget(
        self,
        user_id: str,
        fact: str,
    ) -> bool:
        """Remove an exact episodic fact."""
        user_id = _require_id(
            user_id,
            "user_id",
        )

        fact = fact.strip()

        with self._lock:
            items = self._episodic.get(user_id)

            if not items or fact not in items:
                return False

            items.remove(fact)
            return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def clear_user(
        self,
        user_id: str,
    ) -> None:
        """Clear all user-scoped episodic memory."""
        user_id = _require_id(
            user_id,
            "user_id",
        )

        with self._lock:
            self._episodic.pop(
                user_id,
                None,
            )


def _require_id(
    value: str,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        raise ValueError(
            f"{field_name} cannot be empty"
        )

    return value


def _validate_limit(limit: int) -> int:
    if limit < 1:
        raise ValueError(
            "limit must be >= 1"
        )

    return limit


def _copy_item(
    item: MemoryItem,
) -> MemoryItem:
    if not isinstance(item, dict):
        raise TypeError(
            "memory item must be a dict"
        )

    return dict(item)


def _lexical_score(
    fact: str,
    query: str,
) -> int:
    """
    Lightweight development scoring.

    Production semantic search should be implemented by the persistent
    memory backend rather than inside MemoryStore.
    """
    fact_normalized = fact.casefold()

    if query in fact_normalized:
        return 2

    query_terms = {
        term
        for term in query.split()
        if term
    }

    fact_terms = set(
        fact_normalized.split()
    )

    return len(
        query_terms & fact_terms
    )


__all__ = [
    "MemoryBackend",
    "MemoryConfig",
    "MemoryItem",
    "MemoryStore",
]