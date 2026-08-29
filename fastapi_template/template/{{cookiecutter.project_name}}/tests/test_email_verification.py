"""Tests for async EmailVerificationService (HMAC tokens + ExpiringStore)."""

from __future__ import annotations

import hashlib
import time
from unittest.mock import patch

import pytest

from {{cookiecutter.project_name}}.core.state import InMemoryExpiringStore
from {{cookiecutter.project_name}}.identity.email_verification import (
    RESEND_PREFIX,
    USED_TOKEN_PREFIX,
    EmailVerificationService,
)


SECRET = "ev-test-secret"


@pytest.fixture
def used_store() -> InMemoryExpiringStore:
    return InMemoryExpiringStore()


@pytest.fixture
def resend_store() -> InMemoryExpiringStore:
    return InMemoryExpiringStore()


@pytest.fixture
def svc(
    used_store: InMemoryExpiringStore,
    resend_store: InMemoryExpiringStore,
) -> EmailVerificationService:
    return EmailVerificationService(
        SECRET,
        ttl_s=300,
        resend_cooldown_s=60,
        used_store=used_store,
        resend_store=resend_store,
    )


@pytest.mark.anyio
async def test_create_and_verify_success(
    svc: EmailVerificationService,
) -> None:
    token = await svc.create_verification_token("Verify@Example.COM")
    email = await svc.verify_token(token)
    assert email == "verify@example.com"


@pytest.mark.anyio
async def test_replay_fails_single_use(
    svc: EmailVerificationService,
) -> None:
    token = await svc.create_verification_token("once@x.com")
    assert await svc.verify_token(token) == "once@x.com"
    assert await svc.verify_token(token) is None


@pytest.mark.anyio
async def test_tampered_signature_fails(
    svc: EmailVerificationService,
) -> None:
    token = await svc.create_verification_token("t@x.com")
    parts = token.rsplit(":", 1)
    assert len(parts) == 2
    tampered = f"{parts[0]}:{'0' * 64}"
    assert await svc.verify_token(tampered) is None


@pytest.mark.anyio
async def test_expired_token_fails(
    used_store: InMemoryExpiringStore,
    resend_store: InMemoryExpiringStore,
) -> None:
    svc = EmailVerificationService(
        SECRET,
        ttl_s=1,
        resend_cooldown_s=0,
        used_store=used_store,
        resend_store=resend_store,
    )
    with patch(
        "{{cookiecutter.project_name}}.identity.email_verification.time.time",
        return_value=1_000_000,
    ):
        token = await svc.create_verification_token("exp@x.com")

    with patch(
        "{{cookiecutter.project_name}}.identity.email_verification.time.time",
        return_value=1_000_002,
    ):
        assert await svc.verify_token(token) is None


@pytest.mark.anyio
async def test_resend_cooldown(
    svc: EmailVerificationService,
) -> None:
    await svc.create_verification_token("r@x.com")
    with pytest.raises(ValueError, match="cooldown"):
        await svc.create_verification_token("r@x.com")


@pytest.mark.anyio
async def test_hashed_keys_no_raw_email(
    used_store: InMemoryExpiringStore,
    resend_store: InMemoryExpiringStore,
    svc: EmailVerificationService,
) -> None:
    email = "hashed-keys@example.com"
    token = await svc.create_verification_token(email)
    await svc.verify_token(token)

    email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    resend_keys = list(resend_store._data.keys())
    used_keys = list(used_store._data.keys())

    assert resend_keys == [f"{RESEND_PREFIX}{email_hash}"]
    assert used_keys == [f"{USED_TOKEN_PREFIX}{token_hash}"]

    joined = " ".join(resend_keys + used_keys)
    assert email not in joined
    assert "hashed-keys" not in joined
    assert token not in joined


def test_empty_secret_rejected() -> None:
    with pytest.raises(ValueError, match="secret"):
        EmailVerificationService("")


def test_invalid_ttl_rejected() -> None:
    with pytest.raises(ValueError, match="ttl_s"):
        EmailVerificationService(SECRET, ttl_s=0)
    with pytest.raises(ValueError, match="ttl_s"):
        EmailVerificationService(SECRET, ttl_s=-5)


def test_negative_resend_cooldown_rejected() -> None:
    with pytest.raises(ValueError, match="resend_cooldown"):
        EmailVerificationService(SECRET, resend_cooldown_s=-1)


@pytest.mark.anyio
async def test_empty_email_rejected(
    svc: EmailVerificationService,
) -> None:
    with pytest.raises(ValueError, match="email"):
        await svc.create_verification_token("   ")


@pytest.mark.anyio
async def test_malformed_token_returns_none(
    svc: EmailVerificationService,
) -> None:
    assert await svc.verify_token("") is None
    assert await svc.verify_token("not-a-token") is None
    assert await svc.verify_token("a:b") is None


@pytest.mark.anyio
async def test_expiry_boundary_now_equals_expires(
    used_store: InMemoryExpiringStore,
    resend_store: InMemoryExpiringStore,
) -> None:
    """``now >= expires`` must reject (exact equality)."""
    svc = EmailVerificationService(
        SECRET,
        ttl_s=10,
        resend_cooldown_s=0,
        used_store=used_store,
        resend_store=resend_store,
    )
    now = int(time.time())
    with patch(
        "{{cookiecutter.project_name}}.identity.email_verification.time.time",
        return_value=now,
    ):
        token = await svc.create_verification_token("boundary@x.com")

    # Force clock to exactly the expiry timestamp embedded in the token.
    expires = int(token.split(":")[1])
    with patch(
        "{{cookiecutter.project_name}}.identity.email_verification.time.time",
        return_value=expires,
    ):
        assert await svc.verify_token(token) is None
