"""Tests for async password lifecycle (policy, throttle, reset, history)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from {{cookiecutter.project_name}}.core.state import (
    InMemoryCounterStore,
    InMemoryExpiringStore,
)
from {{cookiecutter.project_name}}.identity.password_lifecycle import (
    LoginThrottleConfig,
    LoginThrottler,
    PasswordHistory,
    PasswordLifecycleService,
    PasswordPolicyConfig,
    PasswordResetConfig,
    PasswordResetService,
    make_password_hasher,
    validate_password,
)

SECRET = "pw-lifecycle-test-secret"
STRONG = "C0rr3ct-H0rs3-Batt3ry!"
STRONG_ALT = "An0ther-Str0ng-P@ss!"


@pytest.fixture
def counters() -> InMemoryCounterStore:
    return InMemoryCounterStore()


@pytest.fixture
def used_tokens() -> InMemoryExpiringStore:
    return InMemoryExpiringStore()


@pytest.fixture
def reset_svc(
    used_tokens: InMemoryExpiringStore,
) -> PasswordResetService:
    return PasswordResetService(
        SECRET,
        used_tokens,
        config=PasswordResetConfig(ttl_s=300),
    )


@pytest.fixture
def lifecycle(
    reset_svc: PasswordResetService,
) -> PasswordLifecycleService:
    policy = PasswordPolicyConfig()
    return PasswordLifecycleService(
        hasher=make_password_hasher(policy),
        history=PasswordHistory(max_history=2),
        reset_service=reset_svc,
        policy=policy,
    )


# --- Policy ---


def test_policy_rejects_weak() -> None:
    errors = validate_password("password123")
    assert errors
    assert any(
        "forbidden pattern" in e or "uppercase" in e
        for e in errors
    )


def test_policy_accepts_strong() -> None:
    assert validate_password(STRONG) == []


def test_hasher_rejects_weak() -> None:
    hasher = make_password_hasher()
    with pytest.raises(ValueError, match="forbidden|uppercase|minimum"):
        hasher("password123")


def test_hasher_hashes_strong() -> None:
    hashed = make_password_hasher()(STRONG)
    assert hashed.startswith("scrypt$")


# --- Reset tokens ---


@pytest.mark.anyio
async def test_reset_create_verify_replay(
    reset_svc: PasswordResetService,
) -> None:
    token = reset_svc.create_reset_token("user_1")
    assert await reset_svc.verify_reset_token(token) == "user_1"
    assert await reset_svc.verify_reset_token(token) is None


@pytest.mark.anyio
async def test_reset_tampered_fails(
    reset_svc: PasswordResetService,
) -> None:
    token = reset_svc.create_reset_token("user_1")
    parts = token.rsplit(".", 1)
    tampered = f"{parts[0]}.{'0' * 64}"
    assert await reset_svc.verify_reset_token(tampered) is None


@pytest.mark.anyio
async def test_reset_expired_fails(
    used_tokens: InMemoryExpiringStore,
) -> None:
    svc = PasswordResetService(
        SECRET,
        used_tokens,
        config=PasswordResetConfig(ttl_s=10),
    )
    with patch(
        "{{cookiecutter.project_name}}.identity.password_lifecycle.time.time",
        return_value=1_000_000.0,
    ):
        token = svc.create_reset_token("user_exp")

    # Exact expiry boundary: time == expires → invalid
    with patch(
        "{{cookiecutter.project_name}}.identity.password_lifecycle.time.time",
        return_value=1_000_010.0,
    ):
        assert await svc.verify_reset_token(token) is None


@pytest.mark.anyio
async def test_reset_user_id_special_chars(
    reset_svc: PasswordResetService,
) -> None:
    user_id = "org:user.with/dots+plus@ex.com"
    token = reset_svc.create_reset_token(user_id)
    assert await reset_svc.verify_reset_token(token) == user_id


@pytest.mark.anyio
async def test_facade_consume_reset(
    lifecycle: PasswordLifecycleService,
) -> None:
    token = lifecycle.create_reset_token("facade-user")
    assert await lifecycle.consume_reset_token(token) == "facade-user"
    assert await lifecycle.consume_reset_token(token) is None


# --- Throttler ---


@pytest.mark.anyio
async def test_throttler_failure_count_and_lockout(
    counters: InMemoryCounterStore,
) -> None:
    throttle = LoginThrottler(
        counters,
        config=LoginThrottleConfig(max_failures=3),
    )
    ident = "user@x.com"
    for _ in range(3):
        await throttle.record_failure(ident)

    allowed, delay = await throttle.check_allowed(ident)
    assert allowed is False
    assert delay > 0


@pytest.mark.anyio
async def test_throttler_success_clears(
    counters: InMemoryCounterStore,
) -> None:
    throttle = LoginThrottler(
        counters,
        config=LoginThrottleConfig(max_failures=5),
    )
    ident = "user@y.com"
    await throttle.record_failure(ident)
    await throttle.record_failure(ident)
    await throttle.record_success(ident)

    allowed, delay = await throttle.check_allowed(ident)
    assert allowed is True
    assert delay == 0.0


# --- History / set_password ---


def test_history_reuse_detection() -> None:
    hist = PasswordHistory(max_history=2)
    hasher = make_password_hasher()
    old_hash = hasher(STRONG)
    hist.record("u1", old_hash)
    assert hist.is_reused("u1", STRONG) is True
    assert hist.is_reused("u1", STRONG_ALT) is False


def test_set_password_rejects_reuse(
    lifecycle: PasswordLifecycleService,
) -> None:
    lifecycle.set_password("u1", STRONG)
    with pytest.raises(ValueError, match="recently used"):
        lifecycle.set_password("u1", STRONG)

    hashed = lifecycle.set_password("u1", STRONG_ALT)
    assert hashed.startswith("scrypt$")
    assert lifecycle.verify_password(STRONG_ALT, hashed) is True
