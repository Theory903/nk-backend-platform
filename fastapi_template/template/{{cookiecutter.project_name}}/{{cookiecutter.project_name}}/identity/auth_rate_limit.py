"""
Auth-specific multi-dimensional rate limiting.

Limits authentication attempts across:

    1. IP address
    2. Account / principal
    3. Endpoint

A request is allowed only when every applicable bucket has capacity.

The implementation uses token buckets rather than fixed windows, which
avoids the boundary burst problem of fixed-window counters.

This module is intentionally separate from ``core.rate_limit.TokenBucket``,
which is for generic application throttling.

Production deployments should replace this in-memory implementation with
an atomic Redis-backed limiter (Lua script that checks-and-consumes all
applicable buckets in one round-trip) while preserving the public API.
Do not invent a RedisAuthRateLimiter in the same change as the in-memory API.

Example:

    limiter = AuthRateLimiter()

    allowed, retry_after = limiter.check(
        ip_address="203.0.113.10",
        account_id="usr_123",
        endpoint="login",
    )

    if not allowed:
        raise Problem(
            title="Too Many Requests",
            status_code=429,
            headers={
                "Retry-After": str(int(retry_after)),
            },
        )

    # After authentication:
    limiter.record_success(
        ip_address="203.0.113.10",
        account_id="usr_123",
    )

    # After a failed authentication:
    limiter.record_failure(
        ip_address="203.0.113.10",
        account_id="usr_123",
    )
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

__all__ = [
    "AuthRateLimiter",
    "BucketState",
    "RateLimitResult",
]


@dataclass(slots=True)
class BucketState:
    """
    Mutable token-bucket state.

    tokens:
        Current number of available tokens.

    updated_at:
        Monotonic timestamp of the last refill calculation.
    """

    tokens: float
    updated_at: float


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """
    Result of a rate-limit check.

    allowed:
        Whether the request may proceed.

    retry_after_s:
        Minimum suggested delay before retrying.

    bucket:
        Bucket responsible for rejection, when applicable.
    """

    allowed: bool
    retry_after_s: float = 0.0
    bucket: str | None = None

    def __iter__(self):
        """
        Preserve compatibility with:

            allowed, retry_after = limiter.check(...)
        """

        yield self.allowed
        yield self.retry_after_s


class AuthRateLimiter:
    """
    Multi-bucket authentication rate limiter.

    Three independent dimensions are supported:

        IP
        account
        endpoint

    Every applicable bucket must allow the request.

    Important:

    Bucket reservation is performed atomically from the caller's
    perspective: tokens are consumed only after ALL applicable buckets
    have capacity. This prevents a rejected account request from also
    consuming an IP token.
    """

    def __init__(
        self,
        *,
        ip_capacity: int = 20,
        ip_window_s: float = 300.0,
        account_capacity: int = 10,
        account_window_s: float = 300.0,
        endpoint_capacity: int = 100,
        endpoint_window_s: float = 300.0,
        progressive_backoff_base_s: float = 1.0,
        backoff_multiplier: float = 2.0,
        max_backoff_s: float = 60.0,
    ) -> None:
        self._validate_configuration(
            ip_capacity=ip_capacity,
            ip_window_s=ip_window_s,
            account_capacity=account_capacity,
            account_window_s=account_window_s,
            endpoint_capacity=endpoint_capacity,
            endpoint_window_s=endpoint_window_s,
            progressive_backoff_base_s=progressive_backoff_base_s,
            backoff_multiplier=backoff_multiplier,
            max_backoff_s=max_backoff_s,
        )

        self.ip_capacity = ip_capacity
        self.ip_window_s = ip_window_s

        self.account_capacity = account_capacity
        self.account_window_s = account_window_s

        self.endpoint_capacity = endpoint_capacity
        self.endpoint_window_s = endpoint_window_s

        self.backoff_base_s = progressive_backoff_base_s
        self.backoff_multiplier = backoff_multiplier
        self.max_backoff_s = max_backoff_s

        self._ip_buckets: dict[str, BucketState] = {}
        self._account_buckets: dict[str, BucketState] = {}
        self._endpoint_buckets: dict[str, BucketState] = {}

        # Authentication failures are intentionally independent from
        # request-rate bucket state.
        self._failure_counts: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        *,
        ip_address: str = "",
        account_id: str = "",
        endpoint: str = "",
    ) -> RateLimitResult:
        """
        Check whether an authentication request is allowed.

        The request is checked against every supplied dimension.

        Returns:

            RateLimitResult(
                allowed=True,
                retry_after_s=0,
            )

        or:

            RateLimitResult(
                allowed=False,
                retry_after_s=...,
                bucket="ip" | "account" | "endpoint",
            )

        No bucket consumes a token unless all applicable buckets can
        accept the request.
        """

        now = time.monotonic()

        candidates: list[
            tuple[
                str,
                dict[str, BucketState],
                str,
                int,
                float,
            ]
        ] = []

        if ip_address:
            candidates.append(
                (
                    "ip",
                    self._ip_buckets,
                    f"ip:{ip_address}",
                    self.ip_capacity,
                    self.ip_window_s,
                )
            )

        if account_id:
            candidates.append(
                (
                    "account",
                    self._account_buckets,
                    f"acct:{account_id}",
                    self.account_capacity,
                    self.account_window_s,
                )
            )

        if endpoint:
            candidates.append(
                (
                    "endpoint",
                    self._endpoint_buckets,
                    f"endpoint:{endpoint}",
                    self.endpoint_capacity,
                    self.endpoint_window_s,
                )
            )

        # First calculate availability for every bucket.
        checks: list[
            tuple[
                str,
                dict[str, BucketState],
                str,
                BucketState,
            ]
        ] = []

        rejection: tuple[str, float] | None = None

        for bucket_name, buckets, key, capacity, window in candidates:
            state = self._state_for(
                buckets,
                key,
                capacity,
                window,
                now,
            )

            retry_after = self._retry_after(
                state,
                capacity=capacity,
                window=window,
            )

            checks.append(
                (
                    bucket_name,
                    buckets,
                    key,
                    state,
                )
            )

            if state.tokens < 1.0:
                if rejection is None or retry_after > rejection[1]:
                    rejection = (
                        bucket_name,
                        retry_after,
                    )

        # Do not consume tokens when one of the dimensions rejects
        # the request.
        if rejection is not None:
            bucket_name, retry_after = rejection

            return RateLimitResult(
                allowed=False,
                retry_after_s=retry_after,
                bucket=bucket_name,
            )

        # All buckets passed. Consume exactly one token from each.
        for _bucket_name, _buckets, _key, state in checks:
            state.tokens -= 1.0

        return RateLimitResult(
            allowed=True,
            retry_after_s=0.0,
            bucket=None,
        )

    def record_success(
        self,
        *,
        ip_address: str = "",
        account_id: str = "",
    ) -> None:
        """
        Clear progressive authentication-failure backoff.

        This does not reset request-rate buckets.
        """

        if ip_address:
            self._failure_counts.pop(
                self._failure_key("ip", ip_address),
                None,
            )

        if account_id:
            self._failure_counts.pop(
                self._failure_key("account", account_id),
                None,
            )

    def record_failure(
        self,
        *,
        ip_address: str = "",
        account_id: str = "",
    ) -> None:
        """
        Record a failed authentication attempt.

        Failure counts are independent per IP and account.
        """

        if ip_address:
            self._increment_failure(
                self._failure_key("ip", ip_address),
            )

        if account_id:
            self._increment_failure(
                self._failure_key("account", account_id),
            )

    def get_backoff(
        self,
        *,
        ip_address: str = "",
        account_id: str = "",
    ) -> float:
        """
        Return the strongest progressive backoff currently applicable.

        The value is capped by max_backoff_s.
        """

        delays: list[float] = []

        if ip_address:
            delays.append(
                self._backoff_for(
                    self._failure_key("ip", ip_address),
                )
            )

        if account_id:
            delays.append(
                self._backoff_for(
                    self._failure_key("account", account_id),
                )
            )

        return max(delays, default=0.0)

    def clear(
        self,
        *,
        ip_address: str | None = None,
        account_id: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        """
        Remove bucket state.

        Primarily useful for tests and administrative resets.
        """

        if ip_address is not None:
            self._ip_buckets.pop(
                f"ip:{ip_address}",
                None,
            )

        if account_id is not None:
            self._account_buckets.pop(
                f"acct:{account_id}",
                None,
            )

        if endpoint is not None:
            self._endpoint_buckets.pop(
                f"endpoint:{endpoint}",
                None,
            )

    def cleanup(
        self,
        *,
        max_idle_s: float = 3600.0,
    ) -> int:
        """
        Remove idle bucket state.

        Important for long-running processes where attacker-controlled
        identifiers could otherwise grow dictionaries indefinitely.

        Returns the number of removed bucket entries.
        """

        if max_idle_s <= 0:
            raise ValueError("max_idle_s must be greater than zero")

        now = time.monotonic()
        removed = 0

        for buckets in (
            self._ip_buckets,
            self._account_buckets,
            self._endpoint_buckets,
        ):
            stale_keys = [
                key
                for key, state in buckets.items()
                if now - state.updated_at > max_idle_s
            ]

            for key in stale_keys:
                buckets.pop(key, None)
                removed += 1

        return removed

    # ------------------------------------------------------------------
    # Bucket implementation
    # ------------------------------------------------------------------

    @staticmethod
    def _state_for(
        buckets: dict[str, BucketState],
        key: str,
        capacity: int,
        window_s: float,
        now: float,
    ) -> BucketState:
        state = buckets.get(key)

        if state is None:
            state = BucketState(
                tokens=float(capacity),
                updated_at=now,
            )
            buckets[key] = state
            return state

        elapsed = max(0.0, now - state.updated_at)

        if elapsed > 0:
            refill_rate = capacity / window_s

            state.tokens = min(
                float(capacity),
                state.tokens + elapsed * refill_rate,
            )

            state.updated_at = now

        return state

    @staticmethod
    def _retry_after(
        state: BucketState,
        *,
        capacity: int,
        window: float,
    ) -> float:
        if state.tokens >= 1.0:
            return 0.0

        refill_rate = capacity / window

        if refill_rate <= 0:
            return window

        missing = 1.0 - state.tokens

        return max(
            0.0,
            missing / refill_rate,
        )

    # ------------------------------------------------------------------
    # Progressive backoff
    # ------------------------------------------------------------------

    def _increment_failure(
        self,
        key: str,
    ) -> None:
        self._failure_counts[key] = (
            self._failure_counts.get(key, 0) + 1
        )

    def _backoff_for(
        self,
        key: str,
    ) -> float:
        failures = self._failure_counts.get(key, 0)

        if failures <= 0:
            return 0.0

        delay = self.backoff_base_s * (
            self.backoff_multiplier ** (failures - 1)
        )

        return min(
            self.max_backoff_s,
            delay,
        )

    @staticmethod
    def _failure_key(
        dimension: str,
        value: str,
    ) -> str:
        return f"{dimension}:{value}"

    # ------------------------------------------------------------------
    # Configuration validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_configuration(
        *,
        ip_capacity: int,
        ip_window_s: float,
        account_capacity: int,
        account_window_s: float,
        endpoint_capacity: int,
        endpoint_window_s: float,
        progressive_backoff_base_s: float,
        backoff_multiplier: float,
        max_backoff_s: float,
    ) -> None:
        capacities = {
            "ip_capacity": ip_capacity,
            "account_capacity": account_capacity,
            "endpoint_capacity": endpoint_capacity,
        }

        for name, value in capacities.items():
            if value <= 0:
                raise ValueError(
                    f"{name} must be greater than zero",
                )

        windows = {
            "ip_window_s": ip_window_s,
            "account_window_s": account_window_s,
            "endpoint_window_s": endpoint_window_s,
        }

        for name, value in windows.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(
                    f"{name} must be a finite value greater than zero",
                )

        if (
            not math.isfinite(progressive_backoff_base_s)
            or progressive_backoff_base_s < 0
        ):
            raise ValueError(
                "progressive_backoff_base_s must be finite and non-negative",
            )

        if (
            not math.isfinite(backoff_multiplier)
            or backoff_multiplier < 1
        ):
            raise ValueError(
                "backoff_multiplier must be finite and >= 1",
            )

        if (
            not math.isfinite(max_backoff_s)
            or max_backoff_s < 0
        ):
            raise ValueError(
                "max_backoff_s must be finite and non-negative",
            )