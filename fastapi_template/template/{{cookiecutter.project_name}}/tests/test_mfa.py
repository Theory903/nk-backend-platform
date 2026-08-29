"""RFC 6238 TOTP + optional TotpReplayGuard tests."""

from __future__ import annotations

import base64
import re

import pytest

from {{cookiecutter.project_name}}.core.state import InMemoryExpiringStore
from {{cookiecutter.project_name}}.identity.mfa import (
    DEFAULT_DIGITS,
    DEFAULT_PERIOD,
    REPLAY_KEY_PREFIX,
    TotpReplayGuard,
    generate_secret,
    provisioning_uri,
    totp,
    totp_timestep,
    verify_totp,
)

# Fixed unix time for deterministic roundtrips (well inside int range).
FIXED_AT = 1_700_000_000


def test_generate_secret_base32_and_entropy() -> None:
    secret = generate_secret()
    assert secret.isupper() or secret.isalnum()
    assert "=" not in secret
    # ≥16 bytes of entropy after Base32 decode.
    padding = "=" * ((8 - len(secret) % 8) % 8)
    raw = base64.b32decode(secret + padding, casefold=True)
    assert len(raw) >= 16


def test_generate_secret_rejects_short_length() -> None:
    with pytest.raises(ValueError, match="at least 16"):
        generate_secret(15)


def test_totp_verify_roundtrip_fixed_time() -> None:
    secret = generate_secret()
    code = totp(secret, at_time=FIXED_AT)
    assert len(code) == DEFAULT_DIGITS
    assert code.isdigit()
    assert verify_totp(secret, code, at_time=FIXED_AT) is True


def test_wrong_code_fails() -> None:
    secret = generate_secret()
    assert verify_totp(secret, "000000", at_time=FIXED_AT) is False
    good = totp(secret, at_time=FIXED_AT)
    # Flip last digit.
    bad = good[:-1] + ("0" if good[-1] != "0" else "1")
    assert verify_totp(secret, bad, at_time=FIXED_AT) is False


def test_window_accepts_adjacent_period() -> None:
    secret = generate_secret()
    prev = totp(secret, at_time=FIXED_AT - DEFAULT_PERIOD)
    nxt = totp(secret, at_time=FIXED_AT + DEFAULT_PERIOD)
    assert verify_totp(secret, prev, at_time=FIXED_AT, window=1) is True
    assert verify_totp(secret, nxt, at_time=FIXED_AT, window=1) is True
    assert verify_totp(secret, prev, at_time=FIXED_AT, window=0) is False


@pytest.mark.parametrize(
    "code",
    [
        "",
        "12345",
        "1234567",
        "abcdef",
        "12 3456",
        "12345a",
    ],
)
def test_malformed_code_returns_false(code: str) -> None:
    secret = generate_secret()
    assert verify_totp(secret, code, at_time=FIXED_AT) is False


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "NOT!!!BASE32",
        "SHORT",  # decodes to <16 bytes
        "ABCDEFGH",  # 5 bytes
    ],
)
def test_invalid_secret_verify_returns_false(secret: str) -> None:
    assert verify_totp(secret, "123456", at_time=FIXED_AT) is False


def test_period_digits_validation() -> None:
    secret = generate_secret()

    with pytest.raises(ValueError, match="period"):
        totp(secret, period=0, at_time=FIXED_AT)

    with pytest.raises(ValueError, match="digits"):
        totp(secret, digits=5, at_time=FIXED_AT)

    with pytest.raises(ValueError, match="digits"):
        totp(secret, digits=9, at_time=FIXED_AT)

    assert verify_totp(secret, "123456", period=0, at_time=FIXED_AT) is False
    assert verify_totp(secret, "12345", digits=5, at_time=FIXED_AT) is False


def test_provisioning_uri_shape() -> None:
    secret = generate_secret()
    uri = provisioning_uri(
        secret,
        "user@example.com",
        issuer="My App",
        digits=6,
        period=30,
    )

    assert uri.startswith("otpauth://totp/")
    assert "My%20App:user%40example.com" in uri or "My%20App:" in uri
    assert f"secret={secret.upper()}" in uri
    assert "issuer=My%20App" in uri
    assert "algorithm=SHA1" in uri
    assert "digits=6" in uri
    assert "period=30" in uri
    assert re.match(r"^otpauth://totp/.+\?.+$", uri)


def test_totp_timestep_helper() -> None:
    assert totp_timestep(FIXED_AT, period=30) == FIXED_AT // 30
    with pytest.raises(ValueError):
        totp_timestep(FIXED_AT, period=0)


@pytest.mark.anyio
async def test_replay_guard_rejects_same_timestep() -> None:
    store = InMemoryExpiringStore[str]()
    guard = TotpReplayGuard(store, period=30, window=1)
    secret = generate_secret()
    code = totp(secret, at_time=FIXED_AT)
    assert verify_totp(secret, code, at_time=FIXED_AT) is True

    step = totp_timestep(FIXED_AT)
    assert await guard.claim("user-1", "factor-a", step) is True
    assert await guard.claim("user-1", "factor-a", step) is False
    # Different factor or user is independent.
    assert await guard.claim("user-1", "factor-b", step) is True
    assert await guard.claim("user-2", "factor-a", step) is True

    key = TotpReplayGuard.replay_key("user-1", "factor-a", step)
    assert key.startswith(REPLAY_KEY_PREFIX)
    assert await store.exists(key) is True
