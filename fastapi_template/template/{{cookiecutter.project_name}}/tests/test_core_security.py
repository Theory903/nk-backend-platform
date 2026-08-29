"""Tests for core security primitives (request IDs, scrypt, opaque tokens)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.requests import Request

from {{cookiecutter.project_name}}.core.security import (
    MAX_REQUEST_ID_LENGTH,
    ScryptParameters,
    constant_time_compare,
    create_token,
    get_request_id,
    hash_password,
    mask_secret,
    new_request_id,
    validate_token,
    verify_password,
)


def _make_request(
    *,
    headers: dict[str, str] | None = None,
    request_id: str | None = None,
) -> Request:
    header_items = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": header_items,
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = Request(scope)
    if request_id is not None:
        request.state.request_id = request_id
    return request


# --- Request identity ---


def test_request_id_unique() -> None:
    a = new_request_id()
    b = new_request_id()
    assert a != b
    assert len(a) == 32
    assert a.isalnum()


def test_get_request_id_from_header() -> None:
    request = _make_request(headers={"x-request-id": "  abc-123  "})
    assert get_request_id(request) == "abc-123"


def test_get_request_id_rejects_oversized_header() -> None:
    oversized = "x" * (MAX_REQUEST_ID_LENGTH + 1)
    request = _make_request(headers={"x-request-id": oversized})
    rid = get_request_id(request)
    assert rid != oversized
    assert len(rid) == 32


def test_get_request_id_rejects_blank_header() -> None:
    request = _make_request(headers={"x-request-id": "   "})
    rid = get_request_id(request)
    assert rid
    assert len(rid) == 32


def test_get_request_id_uses_state_fallback() -> None:
    request = _make_request(request_id="from-state")
    assert get_request_id(request) == "from-state"


def test_get_request_id_header_max_bound_accepted() -> None:
    exact = "y" * MAX_REQUEST_ID_LENGTH
    request = _make_request(headers={"x-request-id": exact})
    assert get_request_id(request) == exact


# --- Secret masking ---


def test_mask_secret() -> None:
    secret = "sk-abcdef123456"
    assert mask_secret(secret) == secret[:4] + "*" * (len(secret) - 4)
    assert mask_secret("ab") == "**"
    assert mask_secret("") == ""
    assert mask_secret("secret", visible=0) == "******"
    assert mask_secret("abcdef", visible=2) == "ab****"


def test_mask_secret_rejects_negative_visible() -> None:
    with pytest.raises(ValueError, match="visible"):
        mask_secret("secret", visible=-1)


# --- Constant-time compare ---


def test_constant_time_compare() -> None:
    assert constant_time_compare("secret", "secret") is True
    assert constant_time_compare("secret", "other") is False
    assert constant_time_compare("", "") is True
    assert constant_time_compare("a", "ab") is False


# --- Password hashing ---


def test_hash_verify_roundtrip() -> None:
    stored = hash_password("hunter2!")
    assert stored.startswith("scrypt$v=1$")
    assert verify_password("hunter2!", stored) is True
    assert verify_password("wrong", stored) is False


def test_hash_password_unique_salts() -> None:
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    assert verify_password("same", a) is True
    assert verify_password("same", b) is True


def test_hash_password_embeds_parameters() -> None:
    params = ScryptParameters(n=2**10, r=8, p=1, dklen=32)
    stored = hash_password("pw", parameters=params)
    assert "$n=1024$" in stored
    assert "$r=8$" in stored
    assert "$p=1$" in stored
    assert verify_password("pw", stored) is True


def test_verify_malformed_hash_returns_false() -> None:
    assert verify_password("x", "not-a-hash") is False
    assert verify_password("x", "") is False
    assert verify_password("x", "bcrypt$v=1$n=1$r=1$p=1$aa$bb") is False
    assert verify_password("x", "scrypt$v=2$n=16384$r=8$p=1$aa$bb") is False
    assert verify_password("x", "scrypt$v=1$broken") is False


def test_hash_password_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        hash_password("")


# --- Opaque tokens ---


def test_token_create_and_validate() -> None:
    token = create_token("user_abc", secret="s3cret", ttl_s=300)
    assert token.count(".") == 1
    assert validate_token(token, "s3cret") == "user_abc"
    assert validate_token(token, secret="s3cret") == "user_abc"


def test_token_wrong_secret_rejected() -> None:
    token = create_token("user_abc", "right", ttl_s=300)
    assert validate_token(token, "wrong") is None


def test_token_tampered_rejected() -> None:
    token = create_token("user_abc", "s3cret", ttl_s=300)
    body, sig = token.split(".", 1)
    flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
    assert validate_token(f"{body}.{flipped}", "s3cret") is None
    assert validate_token(f"AAAA.{sig}", "s3cret") is None


def test_token_expired() -> None:
    with patch(
        "{{cookiecutter.project_name}}.core.security.time.time",
        return_value=1_000_000,
    ):
        token = create_token("u", "k", ttl_s=60)
    with patch(
        "{{cookiecutter.project_name}}.core.security.time.time",
        return_value=1_000_061,
    ):
        assert validate_token(token, "k") is None


def test_token_not_yet_valid_iat() -> None:
    with patch(
        "{{cookiecutter.project_name}}.core.security.time.time",
        return_value=1_000_000,
    ):
        token = create_token("u", "k", ttl_s=60)
    with patch(
        "{{cookiecutter.project_name}}.core.security.time.time",
        return_value=999_999,
    ):
        assert validate_token(token, "k") is None


def test_token_rejects_bad_ttl() -> None:
    with pytest.raises(ValueError, match="ttl_s"):
        create_token("u", "k", ttl_s=-1)
    with pytest.raises(ValueError, match="ttl_s"):
        create_token("u", "k", ttl_s=0)


def test_token_rejects_empty_payload_or_secret() -> None:
    with pytest.raises(ValueError, match="payload"):
        create_token("", "k")
    with pytest.raises(ValueError, match="secret"):
        create_token("u", "")


def test_validate_token_malformed() -> None:
    assert validate_token("", "k") is None
    assert validate_token("no-dot", "k") is None
    assert validate_token("a.b", "") is None
    assert validate_token("not.base64!!!", "k") is None
