"""Tests for identity AuthRateLimiter (multi-dimensional, atomic reservation)."""

from __future__ import annotations

import time

import pytest

from {{cookiecutter.project_name}}.identity.auth_rate_limit import (
    AuthRateLimiter,
    RateLimitResult,
)


def test_endpoint_bucket_limits_when_capacity_one() -> None:
    limiter = AuthRateLimiter(
        ip_capacity=100,
        account_capacity=100,
        endpoint_capacity=1,
        endpoint_window_s=300.0,
    )

    first = limiter.check(endpoint="login")
    second = limiter.check(endpoint="login")

    assert first.allowed is True
    assert second.allowed is False
    assert second.bucket == "endpoint"
    assert second.retry_after_s > 0


def test_account_rejection_does_not_consume_ip_token() -> None:
    """Atomic reservation: reject without draining sibling buckets."""
    limiter = AuthRateLimiter(
        ip_capacity=1,
        ip_window_s=300.0,
        account_capacity=1,
        account_window_s=300.0,
        endpoint_capacity=100,
    )

    # Exhaust the account bucket without touching IP.
    allowed, _ = limiter.check(account_id="acct_1")
    assert allowed is True

    # Combined check: account rejects; IP must not be consumed.
    rejected = limiter.check(ip_address="203.0.113.10", account_id="acct_1")
    assert rejected.allowed is False
    assert rejected.bucket == "account"

    # IP-only check still has its single token.
    ip_only = limiter.check(ip_address="203.0.113.10")
    assert ip_only.allowed is True


def test_progressive_backoff_grows_then_clears_on_success() -> None:
    limiter = AuthRateLimiter(
        progressive_backoff_base_s=1.0,
        backoff_multiplier=2.0,
        max_backoff_s=60.0,
    )

    assert limiter.get_backoff(account_id="u1") == 0.0

    limiter.record_failure(account_id="u1")
    assert limiter.get_backoff(account_id="u1") == pytest.approx(1.0)

    limiter.record_failure(account_id="u1")
    assert limiter.get_backoff(account_id="u1") == pytest.approx(2.0)

    limiter.record_failure(account_id="u1")
    assert limiter.get_backoff(account_id="u1") == pytest.approx(4.0)

    limiter.record_success(account_id="u1")
    assert limiter.get_backoff(account_id="u1") == 0.0


def test_cleanup_removes_idle_buckets() -> None:
    limiter = AuthRateLimiter(ip_capacity=5, account_capacity=5, endpoint_capacity=5)

    assert limiter.check(ip_address="10.0.0.1").allowed is True
    assert limiter.check(account_id="idle_acct").allowed is True
    assert limiter.check(endpoint="token").allowed is True

    # Force all buckets into the idle past.
    past = time.monotonic() - 10_000.0
    for buckets in (
        limiter._ip_buckets,
        limiter._account_buckets,
        limiter._endpoint_buckets,
    ):
        for state in buckets.values():
            state.updated_at = past

    removed = limiter.cleanup(max_idle_s=60.0)
    assert removed == 3
    assert limiter._ip_buckets == {}
    assert limiter._account_buckets == {}
    assert limiter._endpoint_buckets == {}


def test_rate_limit_result_unpacking() -> None:
    limiter = AuthRateLimiter(ip_capacity=1)
    result = limiter.check(ip_address="1.2.3.4")

    assert isinstance(result, RateLimitResult)
    allowed, retry_after = result
    assert allowed is True
    assert retry_after == 0.0

    denied = limiter.check(ip_address="1.2.3.4")
    allowed2, retry_after2 = denied
    assert allowed2 is False
    assert retry_after2 > 0


def test_invalid_config_raises() -> None:
    with pytest.raises(ValueError, match="ip_capacity"):
        AuthRateLimiter(ip_capacity=0)

    with pytest.raises(ValueError, match="account_window_s"):
        AuthRateLimiter(account_window_s=-1.0)

    with pytest.raises(ValueError, match="backoff_multiplier"):
        AuthRateLimiter(backoff_multiplier=0.5)

    with pytest.raises(ValueError, match="max_idle_s"):
        AuthRateLimiter().cleanup(max_idle_s=0)
