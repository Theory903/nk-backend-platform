"""Production-grade rate limiting primitives.

Provides:
    - Thread-safe in-memory token bucket
    - Atomic consume/refill semantics
    - Retry-after calculation
    - Bucket cleanup
    - Backend interface ready for Redis
    - No shared mutable state across unrelated buckets

For distributed deployments, use a Redis-backed implementation. The
in-memory backend is intentionally limited to a single process.
"""

from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Final


DEFAULT_CAPACITY: Final[int] = 100
DEFAULT_REFILL_PER_SEC: Final[float] = 10.0


class RateLimitError(ValueError):
    """Base rate-limit configuration error."""


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """Result of a rate-limit decision."""

    allowed: bool
    remaining: int
    retry_after_s: float = 0.0


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter(ABC):
    """Backend-independent rate limiter contract.

    Sync methods describe the in-process ``TokenBucket`` API.
    ``RedisRateLimiter`` intentionally implements the same operations as
    ``async`` methods (dual API) for redis-py asyncio clients — call sites
    must ``await`` Redis backends. Runtime ABC registration only checks
    method names; type checkers may flag the sync/async mismatch.
    """

    @abstractmethod
    def check(
        self,
        key: str,
        *,
        tokens: int = 1,
    ) -> RateLimitResult:
        """Consume tokens and return the decision."""

    @abstractmethod
    def reset(
        self,
        key: str,
    ) -> None:
        """Remove a bucket."""

    @abstractmethod
    def cleanup(self) -> int:
        """Remove stale buckets."""


class TokenBucket(RateLimiter):
    """
    Thread-safe single-process token bucket.

    Example:

        limiter = TokenBucket(
            capacity=100,
            refill_per_sec=10,
        )

        result = limiter.check("user:123")

        if not result.allowed:
            # Retry after result.retry_after_s
            ...

    ``capacity`` is the maximum burst size.

    ``refill_per_sec`` controls sustained throughput.
    """

    def __init__(
        self,
        *,
        capacity: int,
        refill_per_sec: float,
        idle_ttl_s: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity <= 0:
            raise RateLimitError(
                "capacity must be greater than zero"
            )

        if refill_per_sec <= 0:
            raise RateLimitError(
                "refill_per_sec must be greater than zero"
            )

        if idle_ttl_s <= 0:
            raise RateLimitError(
                "idle_ttl_s must be greater than zero"
            )

        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.idle_ttl_s = idle_ttl_s
        self._clock = clock

        self._buckets: dict[str, _Bucket] = {}
        self._lock = RLock()

    def check(
        self,
        key: str,
        *,
        tokens: int = 1,
    ) -> RateLimitResult:
        """Atomically refill and consume tokens."""

        if not key:
            raise RateLimitError(
                "rate-limit key must not be empty"
            )

        if tokens <= 0:
            raise RateLimitError(
                "tokens must be greater than zero"
            )

        if tokens > self.capacity:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_s=(
                    tokens - self.capacity
                ) / self.refill_per_sec,
            )

        now = self._clock()

        with self._lock:
            bucket = self._buckets.get(key)

            if bucket is None:
                bucket = _Bucket(
                    tokens=float(self.capacity),
                    updated_at=now,
                )
                self._buckets[key] = bucket

            elapsed = max(
                0.0,
                now - bucket.updated_at,
            )

            bucket.tokens = min(
                float(self.capacity),
                bucket.tokens
                + elapsed * self.refill_per_sec,
            )

            bucket.updated_at = now

            if bucket.tokens >= tokens:
                bucket.tokens -= tokens

                return RateLimitResult(
                    allowed=True,
                    remaining=max(
                        0,
                        math.floor(bucket.tokens),
                    ),
                )

            deficit = (
                tokens - bucket.tokens
            )

            retry_after = (
                deficit
                / self.refill_per_sec
            )

            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_s=retry_after,
            )

    def allow(
        self,
        key: str,
        *,
        tokens: int = 1,
    ) -> bool:
        """Compatibility helper returning only the decision."""

        return self.check(
            key,
            tokens=tokens,
        ).allowed

    def reset(
        self,
        key: str,
    ) -> None:
        """Reset one rate-limit bucket."""

        with self._lock:
            self._buckets.pop(
                key,
                None,
            )

    def cleanup(self) -> int:
        """Remove buckets idle beyond ``idle_ttl_s``."""

        now = self._clock()
        removed = 0

        with self._lock:
            stale_keys = [
                key
                for key, bucket in self._buckets.items()
                if now - bucket.updated_at
                >= self.idle_ttl_s
            ]

            for key in stale_keys:
                self._buckets.pop(
                    key,
                    None,
                )
                removed += 1

        return removed

    @property
    def bucket_count(self) -> int:
        """Number of active buckets."""

        with self._lock:
            return len(self._buckets)


class RedisRateLimiter(RateLimiter):
    """
    Redis-backed token bucket.

    The state transition is performed atomically with a Lua script,
    allowing multiple API workers/replicas to share one limiter.

    Requires an async Redis client such as redis-py asyncio.
    Methods are ``async`` (dual API vs sync ``RateLimiter`` ABC) — always
    ``await`` ``check`` / ``reset`` / ``cleanup``.
    """

    SCRIPT: Final[str] = """
    local key = KEYS[1]

    local capacity = tonumber(ARGV[1])
    local refill = tonumber(ARGV[2])
    local requested = tonumber(ARGV[3])
    local now = tonumber(ARGV[4])
    local ttl_ms = tonumber(ARGV[5])

    local data = redis.call("HMGET", key, "tokens", "updated")

    local tokens = tonumber(data[1])
    local updated = tonumber(data[2])

    if tokens == nil then
        tokens = capacity
        updated = now
    end

    local elapsed = math.max(0, now - updated)

    tokens = math.min(
        capacity,
        tokens + (elapsed * refill)
    )

    local allowed = 0
    local retry_after = 0

    if tokens >= requested then
        tokens = tokens - requested
        allowed = 1
    else
        retry_after = (requested - tokens) / refill
    end

    redis.call(
        "HSET",
        key,
        "tokens",
        tokens,
        "updated",
        now
    )

    redis.call(
        "PEXPIRE",
        key,
        ttl_ms
    )

    return {
        allowed,
        math.floor(tokens),
        retry_after
    }
    """

    def __init__(
        self,
        redis_client,
        *,
        key_prefix: str = "ratelimit:",
        capacity: int,
        refill_per_sec: float,
        idle_ttl_s: float = 3600.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if capacity <= 0:
            raise RateLimitError(
                "capacity must be greater than zero"
            )

        if refill_per_sec <= 0:
            raise RateLimitError(
                "refill_per_sec must be greater than zero"
            )

        if idle_ttl_s <= 0:
            raise RateLimitError(
                "idle_ttl_s must be greater than zero"
            )

        self._redis = redis_client
        self._prefix = key_prefix
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.idle_ttl_s = idle_ttl_s
        self._clock = clock

    def _key(
        self,
        key: str,
    ) -> str:
        return f"{self._prefix}{key}"

    async def check(
        self,
        key: str,
        *,
        tokens: int = 1,
    ) -> RateLimitResult:
        """Atomically check and consume tokens in Redis."""

        if not key:
            raise RateLimitError(
                "rate-limit key must not be empty"
            )

        if tokens <= 0:
            raise RateLimitError(
                "tokens must be greater than zero"
            )

        if tokens > self.capacity:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_s=(
                    tokens - self.capacity
                ) / self.refill_per_sec,
            )

        result = await self._redis.eval(
            self.SCRIPT,
            1,
            self._key(key),
            self.capacity,
            self.refill_per_sec,
            tokens,
            self._clock(),
            max(
                1,
                int(self.idle_ttl_s * 1000),
            ),
        )

        return RateLimitResult(
            allowed=bool(result[0]),
            remaining=int(result[1]),
            retry_after_s=float(result[2]),
        )

    async def reset(
        self,
        key: str,
    ) -> None:
        """Remove one Redis rate-limit bucket."""

        await self._redis.delete(
            self._key(key)
        )

    async def cleanup(self) -> int:
        """
        Redis cleanup is handled by key expiration.

        Returns zero because Redis expires idle buckets automatically.
        """

        return 0


__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_REFILL_PER_SEC",
    "RateLimitError",
    "RateLimitResult",
    "RateLimiter",
    "RedisRateLimiter",
    "TokenBucket",
]