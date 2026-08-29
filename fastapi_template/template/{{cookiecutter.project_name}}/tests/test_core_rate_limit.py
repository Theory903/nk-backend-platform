"""Tests for TokenBucket + RedisRateLimiter primitives."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from {{cookiecutter.project_name}}.core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)
from {{cookiecutter.project_name}}.core.rate_limit import (
    RateLimitError,
    RateLimitResult,
    RedisRateLimiter,
    TokenBucket,
)


def test_token_bucket_allows_within_capacity() -> None:
    bucket = TokenBucket(capacity=2, refill_per_sec=10.0)
    assert bucket.allow("user:1") is True
    assert bucket.allow("user:1") is True
    assert bucket.allow("user:1") is False


def test_token_bucket_isolated_per_key() -> None:
    bucket = TokenBucket(capacity=1, refill_per_sec=10.0)
    assert bucket.allow("a") is True
    assert bucket.allow("b") is True
    assert bucket.allow("a") is False


def test_token_bucket_refill_restores_tokens() -> None:
    clock = {"now": 1000.0}
    bucket = TokenBucket(
        capacity=2,
        refill_per_sec=1.0,
        clock=lambda: clock["now"],
    )

    assert bucket.allow("user") is True
    assert bucket.allow("user") is True
    denied = bucket.check("user")
    assert denied.allowed is False
    assert denied.retry_after_s == pytest.approx(1.0)

    clock["now"] = 1001.0
    allowed = bucket.check("user")
    assert allowed.allowed is True
    assert allowed.remaining == 0


def test_token_bucket_deny_includes_retry_after() -> None:
    bucket = TokenBucket(
        capacity=1,
        refill_per_sec=2.0,
        clock=lambda: 1000.0,
    )
    assert bucket.check("k").allowed is True
    result = bucket.check("k")
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after_s == pytest.approx(0.5)


def test_token_bucket_cleanup_removes_idle() -> None:
    clock = {"now": 0.0}
    bucket = TokenBucket(
        capacity=1,
        refill_per_sec=1.0,
        idle_ttl_s=10.0,
        clock=lambda: clock["now"],
    )
    assert bucket.allow("stale") is True
    assert bucket.bucket_count == 1

    clock["now"] = 10.0
    removed = bucket.cleanup()
    assert removed == 1
    assert bucket.bucket_count == 0


def test_token_bucket_empty_key_raises() -> None:
    bucket = TokenBucket(capacity=1, refill_per_sec=1.0)
    with pytest.raises(RateLimitError, match="empty"):
        bucket.check("")


def test_token_bucket_tokens_greater_than_capacity() -> None:
    bucket = TokenBucket(capacity=5, refill_per_sec=1.0)
    result = bucket.check("k", tokens=10)
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after_s == pytest.approx(5.0)


def test_token_bucket_allow_helper_matches_check() -> None:
    bucket = TokenBucket(capacity=1, refill_per_sec=10.0)
    assert bucket.allow("x") is True
    assert bucket.allow("x") is False
    assert bucket.check("x").allowed is False


def test_token_bucket_reset_clears_bucket() -> None:
    bucket = TokenBucket(capacity=1, refill_per_sec=10.0)
    assert bucket.allow("r") is True
    assert bucket.allow("r") is False
    bucket.reset("r")
    assert bucket.allow("r") is True


def test_token_bucket_invalid_config() -> None:
    with pytest.raises(RateLimitError):
        TokenBucket(capacity=0, refill_per_sec=1.0)
    with pytest.raises(RateLimitError):
        TokenBucket(capacity=1, refill_per_sec=0.0)
    with pytest.raises(RateLimitError):
        TokenBucket(capacity=1, refill_per_sec=1.0, idle_ttl_s=0.0)


def test_token_bucket_rejects_non_positive_tokens() -> None:
    bucket = TokenBucket(capacity=1, refill_per_sec=1.0)
    with pytest.raises(RateLimitError, match="tokens"):
        bucket.check("k", tokens=0)


@pytest.mark.anyio
async def test_redis_rate_limiter_mocked_lua_path() -> None:
    redis = MagicMock()
    redis.eval = AsyncMock(return_value=[1, 9, 0.0])
    redis.delete = AsyncMock(return_value=1)

    limiter = RedisRateLimiter(
        redis,
        capacity=10,
        refill_per_sec=5.0,
        key_prefix="rl:",
        clock=lambda: 1234.5,
    )

    result = await limiter.check("user:1", tokens=1)
    assert isinstance(result, RateLimitResult)
    assert result.allowed is True
    assert result.remaining == 9
    assert result.retry_after_s == 0.0

    redis.eval.assert_awaited_once()
    args = redis.eval.await_args.args
    assert args[0] == RedisRateLimiter.SCRIPT
    assert args[1] == 1
    assert args[2] == "rl:user:1"
    assert args[3] == 10
    assert args[4] == 5.0
    assert args[5] == 1
    assert args[6] == 1234.5
    assert args[7] == 3_600_000

    denied_client = MagicMock()
    denied_client.eval = AsyncMock(return_value=[0, 0, 0.4])
    denied = RedisRateLimiter(
        denied_client,
        capacity=10,
        refill_per_sec=5.0,
    )
    denied_result = await denied.check("user:2")
    assert denied_result.allowed is False
    assert denied_result.retry_after_s == pytest.approx(0.4)

    await limiter.reset("user:1")
    redis.delete.assert_awaited_once_with("rl:user:1")
    assert await limiter.cleanup() == 0


@pytest.mark.anyio
async def test_redis_rate_limiter_tokens_over_capacity_skips_eval() -> None:
    redis = MagicMock()
    redis.eval = AsyncMock()
    limiter = RedisRateLimiter(
        redis,
        capacity=3,
        refill_per_sec=1.0,
    )
    result = await limiter.check("k", tokens=10)
    assert result.allowed is False
    assert result.retry_after_s == pytest.approx(7.0)
    redis.eval.assert_not_called()


@pytest.mark.anyio
async def test_redis_rate_limiter_empty_key_raises() -> None:
    limiter = RedisRateLimiter(
        MagicMock(),
        capacity=1,
        refill_per_sec=1.0,
    )
    with pytest.raises(RateLimitError, match="empty"):
        await limiter.check("")


def test_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_s=60.0)
    assert breaker.allow() is True
    breaker.record_failure()
    st_one: CircuitState = breaker.state
    assert st_one == CircuitState.CLOSED
    breaker.record_failure()
    st_two: CircuitState = breaker.state
    assert st_two == CircuitState.OPEN
    assert breaker.allow() is False


def test_breaker_resets_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_s=60.0)
    breaker.record_failure()
    breaker.record_failure()
    st_open: CircuitState = breaker.state
    assert st_open == CircuitState.OPEN
    breaker.record_success()
    st_closed: CircuitState = breaker.state
    assert st_closed == CircuitState.CLOSED
    assert breaker.allow() is True
