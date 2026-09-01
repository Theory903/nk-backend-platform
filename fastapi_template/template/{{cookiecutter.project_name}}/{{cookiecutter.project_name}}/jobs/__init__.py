"""
Reliable task enqueueing with retry, circuit breaking, and DLQ support.

Architecture:

    Application
        │
        ▼
    enqueue()
        │
        ├── Circuit breaker
        │
        ├── Broker enqueue
        │
        └── Failure
              │
              ├── retry
              │
              └── DLQ

The default implementations are in-memory for development/testing.

The in-memory DLQ is **not** multi-process durable — it is process-local and
lost on restart. Production should use a shared Redis/SQL-backed DeadLetterQueue
(and a shared CircuitBreaker when required).

For business events, the transactional outbox remains the primary reliability
path; this enqueuer protects broker publish attempts and parks poison/failed
enqueues in the DLQ for replay tooling.
"""

from __future__ import annotations

import logging
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from {{cookiecutter.project_name}}.core.circuit_breaker import CircuitBreaker
from {{cookiecutter.project_name}}.operations.metrics import (
    record_queue_enqueue,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DLQ
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DeadLetterItem:
    """
    A permanently failed task.
    """

    id: str
    task_name: str
    payload: dict[str, Any]
    reason: str

    attempts: int = 0
    created_at: float = field(default_factory=time.time)

    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DeadLetterQueue(Protocol):
    """
    Persistent abstraction for permanently failed jobs.
    """

    async def push(
        self,
        *,
        task_name: str,
        payload: dict[str, Any],
        reason: str,
        attempts: int = 0,
        last_error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        ...

    async def get(
        self,
        item_id: str,
    ) -> DeadLetterItem | None:
        ...

    async def list(
        self,
        *,
        limit: int = 100,
    ) -> list[DeadLetterItem]:
        ...

    async def remove(
        self,
        item_id: str,
    ) -> bool:
        ...


class InMemoryDeadLetterQueue:
    """
    Development/test DLQ.

    Not multi-process durable: items live only in this process memory.
    Production should replace with Redis/PostgreSQL (or similar) shared store.
    """

    def __init__(self) -> None:
        self._items: dict[str, DeadLetterItem] = {}

    async def push(
        self,
        *,
        task_name: str,
        payload: dict[str, Any],
        reason: str,
        attempts: int = 0,
        last_error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        item = DeadLetterItem(
            id=f"dlq_{uuid.uuid4().hex}",
            task_name=task_name,
            payload=dict(payload),
            reason=reason,
            attempts=attempts,
            last_error=last_error,
            metadata=dict(metadata or {}),
        )

        self._items[item.id] = item

        return item.id

    async def get(
        self,
        item_id: str,
    ) -> DeadLetterItem | None:
        return self._items.get(item_id)

    async def list(
        self,
        *,
        limit: int = 100,
    ) -> list[DeadLetterItem]:
        if limit <= 0:
            return []

        items = sorted(
            self._items.values(),
            key=lambda item: item.created_at,
        )

        return items[:limit]

    async def remove(
        self,
        item_id: str,
    ) -> bool:
        return self._items.pop(
            item_id,
            None,
        ) is not None


class RedisDeadLetterQueue:
    """Shared durable DLQ using Redis values and a sorted index."""

    def __init__(self, redis_client: Any, *, prefix: str = "nk:dlq") -> None:
        self._redis = redis_client
        self._prefix = prefix.rstrip(":")

    def _item_key(self, item_id: str) -> str:
        return f"{self._prefix}:item:{item_id}"

    @property
    def _index_key(self) -> str:
        return f"{self._prefix}:index"

    async def push(
        self,
        *,
        task_name: str,
        payload: dict[str, Any],
        reason: str,
        attempts: int = 0,
        last_error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        item = DeadLetterItem(
            id=f"dlq_{uuid.uuid4().hex}",
            task_name=task_name,
            payload=dict(payload),
            reason=reason,
            attempts=attempts,
            last_error=last_error,
            metadata=dict(metadata or {}),
        )
        await self._redis.set(
            self._item_key(item.id),
            json.dumps(asdict(item)),
        )
        await self._redis.zadd(self._index_key, {item.id: item.created_at})
        return item.id

    async def get(self, item_id: str) -> DeadLetterItem | None:
        raw = await self._redis.get(self._item_key(item_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return DeadLetterItem(**json.loads(raw))

    async def list(self, *, limit: int = 100) -> list[DeadLetterItem]:
        if limit <= 0:
            return []
        ids = await self._redis.zrange(self._index_key, 0, limit - 1)
        items: list[DeadLetterItem] = []
        for raw_id in ids:
            item_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else str(raw_id)
            item = await self.get(item_id)
            if item is not None:
                items.append(item)
        return items

    async def remove(self, item_id: str) -> bool:
        removed = bool(await self._redis.delete(self._item_key(item_id)))
        await self._redis.zrem(self._index_key, item_id)
        return removed


# ---------------------------------------------------------------------------
# Broker abstraction
# ---------------------------------------------------------------------------


class TaskBroker(Protocol):
    """
    Minimal broker contract.

    This keeps application code independent from Taskiq.
    """

    def find_task(
        self,
        task_name: str,
    ) -> Any | None:
        ...


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """
    Retry policy for enqueue failures.
    """

    max_attempts: int = 3

    base_delay_s: float = 0.25

    multiplier: float = 2.0

    max_delay_s: float = 10.0

    jitter: bool = True

    def delay(
        self,
        attempt: int,
    ) -> float:
        """
        Calculate exponential backoff.

        attempt is zero-based.
        """
        delay = min(
            self.base_delay_s
            * (self.multiplier ** attempt),
            self.max_delay_s,
        )

        if not self.jitter:
            return delay

        # Simple bounded jitter without adding another dependency.
        import random

        return random.uniform(
            delay * 0.5,
            delay,
        )


# ---------------------------------------------------------------------------
# Enqueue result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    """
    Result of attempting to enqueue a task.
    """

    accepted: bool

    task_id: str | None = None

    attempts: int = 0

    dlq_id: str | None = None

    error: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TaskEnqueuer:
    """
    Reliable task enqueue service.

    Responsibilities:

    - broker lookup
    - circuit breaker protection
    - bounded retries
    - exponential backoff
    - DLQ fallback
    - structured logging

    The broker itself remains responsible for durable task delivery.
    """

    def __init__(
        self,
        *,
        dlq: DeadLetterQueue,
        breaker: CircuitBreaker,
        retry_policy: RetryPolicy | None = None,
        broker_loader: Any | None = None,
    ) -> None:
        self.dlq = dlq
        self.breaker = breaker
        self.retry_policy = retry_policy or RetryPolicy()
        self.broker_loader = broker_loader

    async def _load_broker(self) -> Any:
        """
        Load the configured broker lazily.

        Lazy loading avoids importing Taskiq during unit tests where
        the broker package may not be installed.
        """
        if self.broker_loader is not None:
            result = self.broker_loader()

            if hasattr(result, "__await__"):
                return await result

            return result

        from {{cookiecutter.project_name}}.tkq import broker

        return broker

    def _breaker_allows(self) -> bool:
        """
        Gate on the circuit breaker.

        Supports both ``allow_request()`` (legacy naming) and ``allow()``
        (current CircuitBreaker API). If neither exists, requests proceed.
        """
        if hasattr(self.breaker, "allow_request"):
            return bool(self.breaker.allow_request())

        if hasattr(self.breaker, "allow"):
            return bool(self.breaker.allow())

        return True

    async def _enqueue_once(
        self,
        *,
        task_name: str,
        payload: dict[str, Any],
    ) -> str:
        broker = await self._load_broker()

        task = broker.find_task(task_name)

        if task is None:
            raise LookupError(
                f"task not found: {task_name}"
            )

        result = await task.kiq(payload)

        task_id = str(
            getattr(result, "task_id", "")
            or ""
        )

        if not task_id:
            raise RuntimeError(
                f"broker accepted task '{task_name}' "
                "but returned no task id"
            )

        return task_id

    async def enqueue(
        self,
        task_name: str,
        payload: dict[str, Any],
        *,
        retry_policy: RetryPolicy | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EnqueueResult:
        """
        Enqueue a task with bounded retry and DLQ fallback.
        """
        if not task_name:
            raise ValueError(
                "task_name cannot be empty"
            )

        if not isinstance(payload, dict):
            raise TypeError(
                "payload must be a dictionary"
            )

        policy = (
            retry_policy
            or self.retry_policy
        )

        if policy.max_attempts <= 0:
            raise ValueError(
                "max_attempts must be greater than zero"
            )

        last_error: Exception | None = None

        for attempt in range(
            policy.max_attempts
        ):
            try:
                # -------------------------------------------------------
                # Circuit breaker
                # -------------------------------------------------------

                if not self._breaker_allows():
                    raise RuntimeError(
                        "task broker circuit breaker is open"
                    )

                # -------------------------------------------------------
                # Broker operation
                # -------------------------------------------------------

                task_id = await self._enqueue_once(
                    task_name=task_name,
                    payload=payload,
                )

                if hasattr(
                    self.breaker,
                    "record_success",
                ):
                    self.breaker.record_success()

                record_queue_enqueue(
                    task=task_name,
                    outcome="accepted",
                )
                return EnqueueResult(
                    accepted=True,
                    task_id=task_id,
                    attempts=attempt + 1,
                )

            except Exception as exc:
                last_error = exc

                logger.warning(
                    "task enqueue failed",
                    extra={
                        "task_name": task_name,
                        "attempt": attempt + 1,
                        "max_attempts": policy.max_attempts,
                        "error": str(exc),
                    },
                )
                record_queue_enqueue(
                    task=task_name,
                    outcome="retrying"
                    if attempt + 1 < policy.max_attempts
                    else "failed",
                )

                if hasattr(
                    self.breaker,
                    "record_failure",
                ):
                    self.breaker.record_failure()

                # No more retries.
                if attempt + 1 >= policy.max_attempts:
                    break

                delay = policy.delay(
                    attempt
                )

                import asyncio

                await asyncio.sleep(delay)

        # ----------------------------------------------------------------
        # DLQ fallback
        # ----------------------------------------------------------------

        error_text = (
            str(last_error)
            if last_error is not None
            else "unknown enqueue failure"
        )

        try:
            dlq_id = await self.dlq.push(
                task_name=task_name,
                payload=payload,
                reason="enqueue_failed",
                attempts=policy.max_attempts,
                last_error=error_text,
                metadata=metadata,
            )

        except Exception as dlq_exc:
            # A broken DLQ is serious enough to log loudly.
            logger.exception(
                "failed to write task to DLQ",
                extra={
                    "task_name": task_name,
                    "enqueue_error": error_text,
                    "dlq_error": str(dlq_exc),
                },
            )

            return EnqueueResult(
                accepted=False,
                attempts=policy.max_attempts,
                error=(
                    f"enqueue failed: {error_text}; "
                    f"DLQ write failed: {dlq_exc}"
                ),
            )

        logger.error(
            "task moved to DLQ",
            extra={
                "task_name": task_name,
                "dlq_id": dlq_id,
                "attempts": policy.max_attempts,
                "error": error_text,
            },
        )
        record_queue_enqueue(
            task=task_name,
            outcome="dlq",
        )

        return EnqueueResult(
            accepted=False,
            attempts=policy.max_attempts,
            dlq_id=dlq_id,
            error=error_text,
        )


# ---------------------------------------------------------------------------
# Process-wide defaults
# ---------------------------------------------------------------------------


_default_dlq = InMemoryDeadLetterQueue()

_default_breaker = CircuitBreaker()

_default_enqueuer = TaskEnqueuer(
    dlq=_default_dlq,
    breaker=_default_breaker,
)


def get_dlq() -> DeadLetterQueue:
    """
    Return the configured DLQ.
    """
    return _default_dlq


def get_breaker() -> CircuitBreaker:
    """
    Return the configured circuit breaker.
    """
    return _default_breaker


def get_enqueuer() -> TaskEnqueuer:
    """
    Return the process-wide task enqueuer.
    """
    return _default_enqueuer


# ---------------------------------------------------------------------------
# Compatibility helper
# ---------------------------------------------------------------------------


async def enqueue(
    task_name: str,
    payload: dict[str, Any],
    *,
    retries: int = 3,
) -> str | None:
    """
    Compatibility wrapper.

    Returns the task ID when accepted, otherwise None.

    For new code, prefer TaskEnqueuer.enqueue() so callers can inspect
    attempts, DLQ placement, and errors.
    """
    result = await get_enqueuer().enqueue(
        task_name,
        payload,
        retry_policy=RetryPolicy(
            max_attempts=max(1, retries),
        ),
    )

    return result.task_id


async def replay_dlq(item_ids: list[str] | None = None) -> list[str]:
    """Replay selected (or all currently visible) dead-letter items."""
    items = []
    if item_ids:
        for item_id in item_ids:
            item = await get_dlq().get(item_id)
            if item is not None:
                items.append(item)
    else:
        items = await get_dlq().list()

    replayed: list[str] = []
    for item in items:
        result = await get_enqueuer().enqueue(item.task_name, item.payload)
        if result.accepted:
            await get_dlq().remove(item.id)
            replayed.append(item.id)
    return replayed


def _run_replay_command() -> None:
    import asyncio

    replayed = asyncio.run(replay_dlq(sys.argv[2:] or None))
    print(f"replayed {len(replayed)} dead-letter job(s)")


__all__ = [
    "DeadLetterItem",
    "DeadLetterQueue",
    "EnqueueResult",
    "InMemoryDeadLetterQueue",
    "RedisDeadLetterQueue",
    "RetryPolicy",
    "TaskBroker",
    "TaskEnqueuer",
    "enqueue",
    "get_breaker",
    "get_dlq",
    "get_enqueuer",
    "replay_dlq",
]


if __name__ == "__main__" and len(sys.argv) > 1:
    if sys.argv[1] == "replay":
        _run_replay_command()