"""Production distributed locking.

Backends:
    - InMemoryLockBackend: single-process development/testing
    - RedisLockBackend: distributed production locking

Redis semantics:
    SET key token NX PX ttl
    + ownership-checked Lua release

The lock is a lease. A holder must finish before the TTL expires.
Do not use this primitive for correctness-critical transactions that
can safely exceed the lease duration.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import secrets
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import RLock
from typing import Any, Final

logger = logging.getLogger(__name__)

DEFAULT_TTL_S: Final[float] = 30.0
DEFAULT_LOCK_TTL_S: Final[float] = DEFAULT_TTL_S
DEFAULT_WAIT_S: Final[float] = 0.0
DEFAULT_POLL_INTERVAL_S: Final[float] = 0.1
DEFAULT_REDIS_URL: Final[str] = "redis://localhost:6379/0"
LOCK_PREFIX: Final[str] = "lock:"


class LockError(RuntimeError):
    """Base distributed-lock error."""


class InvalidLockConfiguration(LockError):
    """Invalid lock configuration."""


class LockBackend(ABC):
    """Backend contract for lease-based distributed locks."""

    @abstractmethod
    async def acquire(
        self,
        key: str,
        *,
        ttl_s: float,
    ) -> str | None:
        """Acquire a lease and return its ownership token."""

    @abstractmethod
    async def release(
        self,
        key: str,
        *,
        owner_token: str,
    ) -> bool:
        """Release only if the caller still owns the lease."""

    async def close(self) -> None:
        """Release backend resources if necessary."""


@dataclass(frozen=True, slots=True)
class _MemoryLease:
    owner_token: str
    expires_at: float


class InMemoryLockBackend(LockBackend):
    """
    Single-process lock backend.

    Thread-safe for multiple event-loop threads, but not distributed.
    """

    def __init__(
        self,
        *,
        clock: Any = time.monotonic,
    ) -> None:
        self._clock = clock
        self._leases: dict[str, _MemoryLease] = {}
        self._lock = RLock()

    async def acquire(
        self,
        key: str,
        *,
        ttl_s: float,
    ) -> str | None:
        now = self._clock()

        with self._lock:
            existing = self._leases.get(key)

            if (
                existing is not None
                and existing.expires_at > now
            ):
                return None

            token = secrets.token_urlsafe(32)

            self._leases[key] = _MemoryLease(
                owner_token=token,
                expires_at=now + ttl_s,
            )

            return token

    async def release(
        self,
        key: str,
        *,
        owner_token: str,
    ) -> bool:
        with self._lock:
            existing = self._leases.get(key)

            if existing is None:
                return False

            if existing.owner_token != owner_token:
                return False

            del self._leases[key]

            return True

    async def close(self) -> None:
        with self._lock:
            self._leases.clear()


class RedisLockBackend(LockBackend):
    """
    Redis-backed distributed lock.

    Acquisition uses Redis atomic SET NX PX.

    Release uses a Lua compare-and-delete script so a stale owner can
    never delete a newer owner's lease.
    """

    RELEASE_SCRIPT: Final[str] = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    end
    return 0
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        key_prefix: str = LOCK_PREFIX,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix

    def _key(
        self,
        key: str,
    ) -> str:
        return f"{self._key_prefix}{key}"

    async def acquire(
        self,
        key: str,
        *,
        ttl_s: float,
    ) -> str | None:
        token = secrets.token_urlsafe(32)

        result = await self._redis.set(
            self._key(key),
            token,
            nx=True,
            px=max(
                1,
                int(ttl_s * 1000),
            ),
        )

        return token if result else None

    async def release(
        self,
        key: str,
        *,
        owner_token: str,
    ) -> bool:
        result = await self._redis.eval(
            self.RELEASE_SCRIPT,
            1,
            self._key(key),
            owner_token,
        )

        return bool(result)

    async def close(self) -> None:
        close = getattr(
            self._redis,
            "aclose",
            None,
        )

        if close is not None:
            result = close()

            if inspect.isawaitable(result):
                await result
            return

        close = getattr(
            self._redis,
            "close",
            None,
        )

        if close is not None:
            result = close()

            if inspect.isawaitable(result):
                await result


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------


def _validate(
    key: str,
    ttl_s: float,
    wait_s: float,
    poll_interval_s: float,
) -> None:
    if not isinstance(key, str) or not key.strip():
        raise InvalidLockConfiguration(
            "lock key must not be empty"
        )

    if ttl_s <= 0:
        raise InvalidLockConfiguration(
            "ttl_s must be greater than zero"
        )

    if wait_s < 0:
        raise InvalidLockConfiguration(
            "wait_s cannot be negative"
        )

    if poll_interval_s <= 0:
        raise InvalidLockConfiguration(
            "poll_interval_s must be greater than zero"
        )


# ----------------------------------------------------------------------
# Lock context manager
# ----------------------------------------------------------------------


@asynccontextmanager
async def distributed_lock(
    key: str,
    *,
    ttl_s: float = DEFAULT_TTL_S,
    wait_s: float = DEFAULT_WAIT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    backend: LockBackend | str = "memory",
    redis_url: str | None = None,
) -> AsyncGenerator[bool, None]:
    """
    Acquire a lease and yield whether it was acquired.

    Example:

        async with distributed_lock(
            "cache-rebuild",
            backend="redis",
            redis_url=settings.redis_url,
        ) as acquired:
            if not acquired:
                return

            await rebuild_cache()
    """

    _validate(
        key,
        ttl_s,
        wait_s,
        poll_interval_s,
    )

    if isinstance(backend, LockBackend):
        lock_backend = backend

    elif backend == "memory":
        lock_backend = _memory_backend

    elif backend == "redis":
        lock_backend = get_lock_backend(
            backend="redis",
            redis_url=redis_url,
        )

    else:
        raise InvalidLockConfiguration(
            f"unsupported lock backend: {backend!r}"
        )

    deadline = time.monotonic() + wait_s
    owner_token: str | None = None

    while True:
        owner_token = await lock_backend.acquire(
            key,
            ttl_s=ttl_s,
        )

        if owner_token is not None:
            break

        if wait_s == 0:
            break

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            break

        await asyncio.sleep(
            min(
                poll_interval_s,
                remaining,
            )
        )

    acquired = owner_token is not None

    try:
        yield acquired
    finally:
        if acquired and owner_token is not None:
            released = await lock_backend.release(
                key,
                owner_token=owner_token,
            )

            if not released:
                # The lease may have expired. This is deliberately a
                # warning rather than an exception during context exit.
                logger.warning(
                    "distributed lock lease was no longer owned: key=%s",
                    key,
                )


# ----------------------------------------------------------------------
# Backend factory
# ----------------------------------------------------------------------


_memory_backend = InMemoryLockBackend()

_redis_backend: RedisLockBackend | None = None
_redis_backend_url: str | None = None
_backend_lock = RLock()


def get_lock_backend(
    *,
    backend: str = "memory",
    redis_url: str | None = None,
) -> LockBackend:
    """Return the configured lock backend."""

    if backend == "memory":
        return _memory_backend

    if backend != "redis":
        raise InvalidLockConfiguration(
            f"unsupported lock backend: {backend!r}"
        )

    url = redis_url or DEFAULT_REDIS_URL

    global _redis_backend
    global _redis_backend_url

    with _backend_lock:
        if (
            _redis_backend is None
            or _redis_backend_url != url
        ):
            from {{cookiecutter.project_name}}.stores.redis_store import (
                create_redis_client,
            )

            _redis_backend = RedisLockBackend(
                create_redis_client(url)
            )

            _redis_backend_url = url

        return _redis_backend


async def close_lock_backends() -> None:
    """Close configured backend clients during application shutdown."""

    global _redis_backend
    global _redis_backend_url

    if _redis_backend is not None:
        await _redis_backend.close()

        _redis_backend = None
        _redis_backend_url = None


__all__ = [
    "DEFAULT_LOCK_TTL_S",
    "DEFAULT_POLL_INTERVAL_S",
    "DEFAULT_TTL_S",
    "DEFAULT_WAIT_S",
    "InMemoryLockBackend",
    "InvalidLockConfiguration",
    "LockBackend",
    "LockError",
    "RedisLockBackend",
    "close_lock_backends",
    "distributed_lock",
    "get_lock_backend",
]