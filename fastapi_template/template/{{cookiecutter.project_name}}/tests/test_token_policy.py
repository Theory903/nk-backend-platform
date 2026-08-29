"""Tests for identity.token_policy (PyJWT policy layer)."""

from __future__ import annotations

import base64
import json
import time

import jwt as pyjwt
import pytest

from {{cookiecutter.project_name}}.identity.token_policy import (
    ALLOWED_ALGORITHMS,
    TokenPolicy,
    create_token,
    validate_token,
)

SECRET = "x" * 64


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _force_alg(token: str, alg: str) -> str:
    header_b64, payload_b64, sig_b64 = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
    header["alg"] = alg
    new_header = _b64url(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    )
    return f"{new_header}.{payload_b64}.{sig_b64}"


def _strip_claim(token: str, claim: str) -> str:
    """Re-sign after removing a claim (HS256)."""
    header_b64, payload_b64, _ = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    payload.pop(claim, None)
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def test_allowed_algorithms() -> None:
    assert ALLOWED_ALGORITHMS == frozenset({"HS256", "RS256", "ES256"})


def test_create_validate_roundtrip_hs256() -> None:
    policy = TokenPolicy(
        expected_issuer="https://auth.example",
        expected_audiences=frozenset({"api"}),
    )
    token = create_token(
        "user-1",
        SECRET,
        expires_in_s=300,
        issuer="https://auth.example",
        audiences=["api"],
        extra_claims={"org_id": "org-9"},
        policy=policy,
    )
    result = validate_token(token, SECRET, policy=policy)
    assert result.valid is True
    assert result.error is None
    assert result.claims["sub"] == "user-1"
    assert result.claims["org_id"] == "org-9"
    assert isinstance(result.claims["jti"], str) and result.claims["jti"]


def test_rejects_alg_none() -> None:
    policy = TokenPolicy()
    token = create_token("u", SECRET, expires_in_s=60)
    forced = _force_alg(token, "none")
    result = validate_token(forced, SECRET, policy=policy)
    assert result.valid is False
    assert result.error is not None
    assert "algorithm" in result.error.lower() or "not allowed" in result.error


def test_rejects_alg_hs512() -> None:
    policy = TokenPolicy()
    # Legitimate HS512 token must still be rejected by policy allowlist.
    now = int(time.time())
    token = pyjwt.encode(
        {"sub": "u", "iat": now, "exp": now + 60, "jti": "j1"},
        SECRET,
        algorithm="HS512",
    )
    result = validate_token(token, SECRET, policy=policy)
    assert result.valid is False
    assert "HS512" in (result.error or "")


def test_rejects_expired() -> None:
    policy = TokenPolicy(clock_skew_s=0)
    token = create_token("u", SECRET, expires_in_s=1)
    time.sleep(1.1)
    result = validate_token(token, SECRET, policy=policy)
    assert result.valid is False
    assert result.error == "token expired"


def test_rejects_wrong_issuer() -> None:
    policy = TokenPolicy(expected_issuer="https://auth.a")
    token = create_token(
        "u",
        SECRET,
        expires_in_s=60,
        issuer="https://auth.b",
    )
    result = validate_token(token, SECRET, policy=policy)
    assert result.valid is False
    assert result.error == "wrong issuer"


def test_rejects_wrong_audience() -> None:
    policy = TokenPolicy(expected_audiences=frozenset({"api"}))
    token = create_token(
        "u",
        SECRET,
        expires_in_s=60,
        audiences=["other"],
    )
    result = validate_token(token, SECRET, policy=policy)
    assert result.valid is False
    assert result.error == "wrong audience"


def test_rejects_missing_sub() -> None:
    policy = TokenPolicy()
    now = int(time.time())
    token = pyjwt.encode(
        {"iat": now, "exp": now + 60, "jti": "j1"},
        SECRET,
        algorithm="HS256",
    )
    result = validate_token(token, SECRET, policy=policy)
    assert result.valid is False
    assert result.error is not None


def test_rejects_missing_jti() -> None:
    policy = TokenPolicy()
    token = create_token("u", SECRET, expires_in_s=60)
    token = _strip_claim(token, "jti")
    result = validate_token(token, SECRET, policy=policy)
    assert result.valid is False
    assert result.error is not None
    assert "jti" in result.error.lower() or "missing" in result.error.lower()


def test_rejects_token_too_old() -> None:
    policy = TokenPolicy(max_token_age_s=60, clock_skew_s=0)
    now = int(time.time())
    token = pyjwt.encode(
        {
            "sub": "u",
            "iat": now - 120,
            "exp": now + 3600,
            "jti": "old-jti",
        },
        SECRET,
        algorithm="HS256",
    )
    result = validate_token(token, SECRET, policy=policy)
    assert result.valid is False
    assert result.error == "token too old"


def test_create_token_rejects_reserved_extra_claims() -> None:
    with pytest.raises(ValueError, match="reserved"):
        create_token(
            "u",
            SECRET,
            extra_claims={"sub": "attacker"},
        )
    with pytest.raises(ValueError, match="reserved"):
        create_token("u", SECRET, extra_claims={"jti": "fixed"})
    with pytest.raises(ValueError, match="reserved"):
        create_token("u", SECRET, extra_claims={"iat": 1})
    with pytest.raises(ValueError, match="reserved"):
        create_token("u", SECRET, extra_claims={"exp": 1})


def test_create_token_rejects_disallowed_algorithm() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        create_token("u", SECRET, algorithm="HS512")
    with pytest.raises(ValueError, match="not allowed"):
        create_token("u", SECRET, algorithm="none")


def test_create_token_policy_restricts_algorithm() -> None:
    policy = TokenPolicy(algorithms=frozenset({"RS256"}))
    with pytest.raises(ValueError, match="policy"):
        create_token("u", SECRET, algorithm="HS256", policy=policy)


def test_leeway_accepts_slight_clock_skew() -> None:
    """Slightly future iat within clock_skew_s remains valid (leeway is decode kwarg)."""
    policy = TokenPolicy(clock_skew_s=30)
    now = int(time.time())
    # iat 10s in the future — within 30s leeway.
    token = pyjwt.encode(
        {
            "sub": "u",
            "iat": now + 10,
            "exp": now + 3600,
            "jti": "skew-jti",
        },
        SECRET,
        algorithm="HS256",
    )
    result = validate_token(token, SECRET, policy=policy)
    assert result.valid is True, result.error


def test_policy_rejects_unsupported_algorithms_at_init() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        TokenPolicy(algorithms=frozenset({"HS512"}))


def test_empty_token_and_key_fail_closed() -> None:
    policy = TokenPolicy()
    assert validate_token("", SECRET, policy=policy).valid is False
    assert validate_token("a.b.c", "", policy=policy).valid is False
    assert validate_token("not-a-jwt", SECRET, policy=policy).valid is False
