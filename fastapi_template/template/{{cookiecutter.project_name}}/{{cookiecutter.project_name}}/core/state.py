"""
Universal mutable-state primitives.

The application depends only on these interfaces.

Backends:

    InMemory*  -> development/tests
    Redis*     -> production

Design goals:

- async-first
- TTL support
- atomic operations where Redis supports them
- explicit namespacing
- no raw Redis access from business modules
- easy dependency injection
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class StateStoreError(RuntimeError):
    """Base error for state-store failures."""


class StateBackendUnavailable(StateStoreError):
    """Raised when the backing state system cannot be reached."""


class ExpiringStore(ABC, Generic[T]):
    """
    Key/value state where every value may have a TTL.

    Typical uses:

    - sessions
    - OAuth state
    - magic links
    - idempotency responses
    - temporary authentication challenges
    - cached authorization state
    """

    @abstractmethod
    async def set(
        self,
        key: str,
        value: T,
        *,
        ttl_s: float,
    ) -> None:
        ...

    @abstractmethod
    async def get(
        self,
        key: str,
    ) -> T | None:
        ...

    @abstractmethod
    async def delete(
        self,
        key: str,
    ) -> bool:
        ...

    @abstractmethod
    async def exists(
        self,
        key: str,
    ) -> bool:
        ...

    @abstractmethod
    async def set_if_absent(
        self,
        key: str,
        value: T,
        *,
        ttl_s: float,
    ) -> bool:
        """
        Atomically set only when the key does not exist.

        Returns True when inserted.
        """
        ...

    @abstractmethod
    async def expire(
        self,
        key: str,
        *,
        ttl_s: float,
    ) -> bool:
        ...

    @abstractmethod
    async def ttl(
        self,
        key: str,
    ) -> float | None:
        ...


class SetStore(ABC):
    """
    Set primitive.

    Typical uses:

    - revoked tokens
    - group membership
    - active sessions
    - feature cohorts
    - tenant membership
    """

    @abstractmethod
    async def add(
        self,
        key: str,
        member: str,
    ) -> bool:
        ...

    @abstractmethod
    async def remove(
        self,
        key: str,
        member: str,
    ) -> bool:
        ...

    @abstractmethod
    async def contains(
        self,
        key: str,
        member: str,
    ) -> bool:
        ...

    @abstractmethod
    async def members(
        self,
        key: str,
    ) -> set[str]:
        ...

    @abstractmethod
    async def clear(
        self,
        key: str,
    ) -> bool:
        ...


class CounterStore(ABC):
    """
    Atomic integer counters.

    Typical uses:

    - rate limiting
    - login attempts
    - request counts
    - quotas
    - metrics
    """

    @abstractmethod
    async def increment(
        self,
        key: str,
        amount: int = 1,
        *,
        ttl_s: float | None = None,
    ) -> int:
        ...

    @abstractmethod
    async def get_value(
        self,
        key: str,
    ) -> int:
        ...

    @abstractmethod
    async def delete(
        self,
        key: str,
    ) -> bool:
        ...


class InMemoryExpiringStore(ExpiringStore[T]):
    """
    Async-safe in-memory implementation.

    Intended for:

    - local development
    - unit tests
    - single-process execution

    Not suitable for multiple workers.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[T, float]] = {}
        self._lock = asyncio.Lock()

    async def set(
        self,
        key: str,
        value: T,
        *,
        ttl_s: float,
    ) -> None:
        if ttl_s <= 0:
            await self.delete(key)
            return

        async with self._lock:
            self._data[key] = (
                value,
                time.monotonic() + ttl_s,
            )

    async def get(
        self,
        key: str,
    ) -> T | None:
        async with self._lock:
            entry = self._data.get(key)

            if entry is None:
                return None

            value, expires_at = entry

            if time.monotonic() >= expires_at:
                self._data.pop(key, None)
                return None

            return value

    async def delete(
        self,
        key: str,
    ) -> bool:
        async with self._lock:
            return self._data.pop(key, None) is not None

    async def exists(
        self,
        key: str,
    ) -> bool:
        return await self.get(key) is not None

    async def set_if_absent(
        self,
        key: str,
        value: T,
        *,
        ttl_s: float,
    ) -> bool:
        if ttl_s <= 0:
            return False

        async with self._lock:
            entry = self._data.get(key)

            if entry is not None:
                _, expires_at = entry

                if time.monotonic() < expires_at:
                    return False

                self._data.pop(key, None)

            self._data[key] = (
                value,
                time.monotonic() + ttl_s,
            )

            return True

    async def expire(
        self,
        key: str,
        *,
        ttl_s: float,
    ) -> bool:
        async with self._lock:
            entry = self._data.get(key)

            if entry is None:
                return False

            value, _ = entry

            self._data[key] = (
                value,
                time.monotonic() + ttl_s,
            )

            return True

    async def ttl(
        self,
        key: str,
    ) -> float | None:
        async with self._lock:
            entry = self._data.get(key)

            if entry is None:
                return None

            _, expires_at = entry

            remaining = expires_at - time.monotonic()

            if remaining <= 0:
                self._data.pop(key, None)
                return None

            return remaining


class InMemorySetStore(SetStore):
    """Async-safe single-process set store."""

    def __init__(self) -> None:
        self._sets: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    async def add(
        self,
        key: str,
        member: str,
    ) -> bool:
        async with self._lock:
            bucket = self._sets.setdefault(key, set())

            before = len(bucket)
            bucket.add(member)

            return len(bucket) != before

    async def remove(
        self,
        key: str,
        member: str,
    ) -> bool:
        async with self._lock:
            bucket = self._sets.get(key)

            if not bucket or member not in bucket:
                return False

            bucket.remove(member)

            if not bucket:
                self._sets.pop(key, None)

            return True

    async def contains(
        self,
        key: str,
        member: str,
    ) -> bool:
        async with self._lock:
            return member in self._sets.get(key, set())

    async def members(
        self,
        key: str,
    ) -> set[str]:
        async with self._lock:
            return set(
                self._sets.get(key, set()),
            )

    async def clear(
        self,
        key: str,
    ) -> bool:
        async with self._lock:
            return self._sets.pop(key, None) is not None


class InMemoryCounterStore(CounterStore):
    """Async-safe single-process atomic counters."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._expires: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def increment(
        self,
        key: str,
        amount: int = 1,
        *,
        ttl_s: float | None = None,
    ) -> int:
        async with self._lock:
            self._cleanup_expired(key)

            value = (
                self._counters.get(key, 0)
                + amount
            )

            self._counters[key] = value

            if ttl_s is not None and ttl_s > 0:
                self._expires[key] = (
                    time.monotonic() + ttl_s
                )

            return value

    async def get_value(
        self,
        key: str,
    ) -> int:
        async with self._lock:
            self._cleanup_expired(key)
            return self._counters.get(key, 0)

    async def delete(
        self,
        key: str,
    ) -> bool:
        async with self._lock:
            existed = key in self._counters

            self._counters.pop(key, None)
            self._expires.pop(key, None)

            return existed

    def _cleanup_expired(
        self,
        key: str,
    ) -> None:
        expires_at = self._expires.get(key)

        if (
            expires_at is not None
            and time.monotonic() >= expires_at
        ):
            self._counters.pop(key, None)
            self._expires.pop(key, None)


@dataclass(frozen=True, slots=True)
class StateNamespace:
    """
    Generates predictable platform-wide keys.

    Example:

        ns = StateNamespace("auth")

        ns.key("oauth", state)

        -> nk:auth:oauth:<state>
    """

    prefix: str = "nk"

    def key(
        self,
        namespace: str,
        identifier: str,
    ) -> str:
        return (
            f"{self.prefix}:"
            f"{namespace}:"
            f"{identifier}"
        )

    def scoped(
        self,
        namespace: str,
        *,
        org_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        parts = [self.prefix, namespace]

        if org_id:
            parts.append(f"org:{org_id}")

        if user_id:
            parts.append(f"user:{user_id}")

        return ":".join(parts)


class RedisExpiringStore(ExpiringStore[Any]):
    """
    Redis implementation.

    Requires an async Redis client implementing:

        get
        set
        delete
        exists
        expire
        ttl

    Compatible with redis-py asyncio clients. Values are JSON-encoded;
    ``get`` accepts both ``str`` and ``bytes`` so the shared app pool
    (``decode_responses=False``) works without a second pool.
    """

    def __init__(
        self,
        redis_client: Any,
    ) -> None:
        self._redis = redis_client

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_s: float,
    ) -> None:
        payload = json.dumps(value)

        await self._redis.set(
            key,
            payload,
            ex=max(1, int(ttl_s)),
        )

    async def get(
        self,
        key: str,
    ) -> Any | None:
        value = await self._redis.get(key)

        if value is None:
            return None

        if isinstance(value, bytes):
            value = value.decode()

        return json.loads(value)

    async def delete(
        self,
        key: str,
    ) -> bool:
        return bool(
            await self._redis.delete(key),
        )

    async def exists(
        self,
        key: str,
    ) -> bool:
        return bool(
            await self._redis.exists(key),
        )

    async def set_if_absent(
        self,
        key: str,
        value: Any,
        *,
        ttl_s: float,
    ) -> bool:
        payload = json.dumps(value)

        result = await self._redis.set(
            key,
            payload,
            nx=True,
            ex=max(1, int(ttl_s)),
        )

        return bool(result)

    async def expire(
        self,
        key: str,
        *,
        ttl_s: float,
    ) -> bool:
        return bool(
            await self._redis.expire(
                key,
                max(1, int(ttl_s)),
            ),
        )

    async def ttl(
        self,
        key: str,
    ) -> float | None:
        result = await self._redis.ttl(key)

        if result < 0:
            return None

        return float(result)


class RedisSetStore(SetStore):
    """Redis-backed set primitive."""

    def __init__(
        self,
        redis_client: Any,
    ) -> None:
        self._redis = redis_client

    async def add(
        self,
        key: str,
        member: str,
    ) -> bool:
        return bool(
            await self._redis.sadd(
                key,
                member,
            ),
        )

    async def remove(
        self,
        key: str,
        member: str,
    ) -> bool:
        return bool(
            await self._redis.srem(
                key,
                member,
            ),
        )

    async def contains(
        self,
        key: str,
        member: str,
    ) -> bool:
        return bool(
            await self._redis.sismember(
                key,
                member,
            ),
        )

    async def members(
        self,
        key: str,
    ) -> set[str]:
        values = await self._redis.smembers(key)

        return {
            value.decode()
            if isinstance(value, bytes)
            else str(value)
            for value in values
        }

    async def clear(
        self,
        key: str,
    ) -> bool:
        return bool(
            await self._redis.delete(key),
        )


class RedisCounterStore(CounterStore):
    """Redis-backed atomic counter."""

    _INCREMENT_SCRIPT = """
    local value = redis.call("INCRBY", KEYS[1], ARGV[1])

    if ARGV[2] ~= "0" and value == tonumber(ARGV[1]) then
        redis.call("EXPIRE", KEYS[1], ARGV[2])
    end

    return value
    """

    def __init__(
        self,
        redis_client: Any,
    ) -> None:
        self._redis = redis_client

    async def increment(
        self,
        key: str,
        amount: int = 1,
        *,
        ttl_s: float | None = None,
    ) -> int:
        ttl = (
            max(1, int(ttl_s))
            if ttl_s is not None
            else 0
        )

        value = await self._redis.eval(
            self._INCREMENT_SCRIPT,
            1,
            key,
            amount,
            ttl,
        )

        return int(value)

    async def get_value(
        self,
        key: str,
    ) -> int:
        value = await self._redis.get(key)

        if value is None:
            return 0

        return int(value)

    async def delete(
        self,
        key: str,
    ) -> bool:
        return bool(
            await self._redis.delete(key),
        )


@dataclass(frozen=True, slots=True)
class StateStores:
    expiring: ExpiringStore[Any]
    sets: SetStore
    counters: CounterStore
    namespace: StateNamespace


def create_state_stores(
    *,
    backend: str = "memory",
    redis_client: Any | None = None,
    prefix: str = "nk",
) -> StateStores:
    """
    Construct the platform state subsystem (canonical factory).

    backend:
        memory | redis

    For ``backend="redis"``, pass an already-constructed async Redis
    client. Production path (shared pool from lifespan; pool uses
    ``decode_responses=False``, and Redis* stores accept bytes)::

        Redis(connection_pool=app.state.redis_pool)

    Do not pass a redis URL here — client construction belongs to the
    application (or to ``stores.redis_store.create_redis_client`` for
    locks/legacy only).
    """

    namespace = StateNamespace(
        prefix=prefix,
    )

    if backend == "redis":
        if redis_client is None:
            raise ValueError(
                "redis_client is required for redis backend",
            )

        return StateStores(
            expiring=RedisExpiringStore(
                redis_client,
            ),
            sets=RedisSetStore(
                redis_client,
            ),
            counters=RedisCounterStore(
                redis_client,
            ),
            namespace=namespace,
        )

    if backend == "memory":
        return StateStores(
            expiring=InMemoryExpiringStore(),
            sets=InMemorySetStore(),
            counters=InMemoryCounterStore(),
            namespace=namespace,
        )

    raise ValueError(
        f"unsupported state backend: {backend}",
    )


__all__ = [
    "CounterStore",
    "ExpiringStore",
    "InMemoryCounterStore",
    "InMemoryExpiringStore",
    "InMemorySetStore",
    "RedisCounterStore",
    "RedisExpiringStore",
    "RedisSetStore",
    "SetStore",
    "StateBackendUnavailable",
    "StateNamespace",
    "StateStoreError",
    "StateStores",
    "create_state_stores",
]
