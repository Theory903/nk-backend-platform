"""Unit tests for identity JWT encode/decode primitives."""

from __future__ import annotations

import base64
import json
import time

import pytest

from {{cookiecutter.project_name}}.identity.jwt import (
    create_access_token,
    decode_hs256,
    decode_rs256,
    encode_hs256,
    encode_rs256,
)

SECRET = "test-secret-key-32bytes-minimum!!"
OTHER_SECRET = "other-secret-key-32bytes-min!!!"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _tamper_payload(token: str) -> str:
    header_b64, payload_b64, sig_b64 = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    payload["sub"] = "attacker"
    new_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    return f"{header_b64}.{new_payload}.{sig_b64}"


def _force_alg(token: str, alg: str) -> str:
    header_b64, payload_b64, sig_b64 = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
    header["alg"] = alg
    new_header = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    return f"{new_header}.{payload_b64}.{sig_b64}"


# --- HS256 ---


def test_hs256_roundtrip() -> None:
    now = int(time.time())
    claims = {"sub": "user-1", "iat": now, "exp": now + 3600}
    token = encode_hs256(claims, SECRET)
    decoded = decode_hs256(token, SECRET)
    assert decoded is not None
    assert decoded["sub"] == "user-1"
    assert decoded["exp"] == claims["exp"]


def test_hs256_wrong_secret_returns_none() -> None:
    token = encode_hs256({"sub": "u", "exp": int(time.time()) + 60}, SECRET)
    assert decode_hs256(token, OTHER_SECRET) is None


def test_hs256_tampered_payload_returns_none() -> None:
    token = encode_hs256({"sub": "u", "exp": int(time.time()) + 60}, SECRET)
    assert decode_hs256(_tamper_payload(token), SECRET) is None


def test_hs256_rejects_alg_none() -> None:
    token = encode_hs256({"sub": "u", "exp": int(time.time()) + 60}, SECRET)
    assert decode_hs256(_force_alg(token, "none"), SECRET) is None
    assert decode_hs256(_force_alg(token, "None"), SECRET) is None


def test_hs256_rejects_unexpected_alg() -> None:
    token = encode_hs256({"sub": "u", "exp": int(time.time()) + 60}, SECRET)
    assert decode_hs256(_force_alg(token, "RS256"), SECRET) is None
    assert decode_hs256(_force_alg(token, "HS384"), SECRET) is None


def test_hs256_expired_returns_none() -> None:
    token = encode_hs256({"sub": "u", "exp": 1}, SECRET)
    assert decode_hs256(token, SECRET) is None


def test_hs256_missing_exp_when_verify_exp() -> None:
    token = encode_hs256({"sub": "u"}, SECRET)
    assert decode_hs256(token, SECRET, verify_exp=True) is None
    assert decode_hs256(token, SECRET, verify_exp=False) is not None


def test_hs256_nbf_future_returns_none() -> None:
    now = int(time.time())
    token = encode_hs256(
        {"sub": "u", "exp": now + 3600, "nbf": now + 10_000},
        SECRET,
    )
    assert decode_hs256(token, SECRET, leeway_s=0) is None


def test_hs256_iat_future_returns_none() -> None:
    now = int(time.time())
    token = encode_hs256(
        {"sub": "u", "exp": now + 3600, "iat": now + 10_000},
        SECRET,
    )
    assert decode_hs256(token, SECRET, leeway_s=0) is None


def test_hs256_issuer_mismatch() -> None:
    now = int(time.time())
    token = encode_hs256(
        {"sub": "u", "exp": now + 60, "iss": "issuer-a"},
        SECRET,
    )
    assert decode_hs256(token, SECRET, issuer="issuer-a") is not None
    assert decode_hs256(token, SECRET, issuer="issuer-b") is None


def test_hs256_audience_mismatch() -> None:
    now = int(time.time())
    token = encode_hs256(
        {"sub": "u", "exp": now + 60, "aud": "api"},
        SECRET,
    )
    assert decode_hs256(token, SECRET, audience="api") is not None
    assert decode_hs256(token, SECRET, audience="other") is None


def test_hs256_audience_list() -> None:
    now = int(time.time())
    token = encode_hs256(
        {"sub": "u", "exp": now + 60, "aud": ["api", "admin"]},
        SECRET,
    )
    assert decode_hs256(token, SECRET, audience="admin") is not None
    assert decode_hs256(token, SECRET, audience="missing") is None


def test_hs256_kid_in_header() -> None:
    now = int(time.time())
    token = encode_hs256(
        {"sub": "u", "exp": now + 60},
        SECRET,
        kid="key-1",
    )
    header_b64 = token.split(".")[0]
    header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
    assert header["kid"] == "key-1"
    assert header["alg"] == "HS256"
    assert decode_hs256(token, SECRET) is not None


def test_hs256_deterministic_json() -> None:
    claims = {"z": 1, "a": 2, "exp": int(time.time()) + 60}
    t1 = encode_hs256(claims, SECRET)
    t2 = encode_hs256({"a": 2, "z": 1, "exp": claims["exp"]}, SECRET)
    assert t1 == t2


# --- create_access_token ---


def test_create_access_token_claims() -> None:
    before = int(time.time())
    token = create_access_token(
        "user-42",
        SECRET,
        ttl_s=300,
        issuer="nk",
        audience="api",
        scopes=["read", "write"],
        token_id="jti-1",
        not_before_s=0,
        kid="k1",
        extra_claims={"org_id": "org-9"},
    )
    after = int(time.time())
    payload = decode_hs256(
        token,
        SECRET,
        issuer="nk",
        audience="api",
    )
    assert payload is not None
    assert payload["sub"] == "user-42"
    assert payload["iss"] == "nk"
    assert payload["aud"] == "api"
    assert payload["scope"] == "read write"
    assert payload["jti"] == "jti-1"
    assert payload["org_id"] == "org-9"
    assert payload["nbf"] == payload["iat"]
    assert before <= payload["iat"] <= after
    assert payload["exp"] == payload["iat"] + 300

    header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
    assert header["kid"] == "k1"


def test_create_access_token_ttl_non_positive_raises() -> None:
    with pytest.raises(ValueError, match="ttl_s"):
        create_access_token("u", SECRET, ttl_s=0)
    with pytest.raises(ValueError, match="ttl_s"):
        create_access_token("u", SECRET, ttl_s=-1)


def test_create_access_token_empty_subject_raises() -> None:
    with pytest.raises(ValueError, match="subject"):
        create_access_token("", SECRET)


# --- RS256 ---


def _ephemeral_rsa_pem() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def test_rs256_roundtrip() -> None:
    private_pem, public_pem = _ephemeral_rsa_pem()
    now = int(time.time())
    claims = {"sub": "rsa-user", "iat": now, "exp": now + 600}
    token = encode_rs256(claims, private_pem, kid="rsa-1")
    decoded = decode_rs256(token, public_pem)
    assert decoded is not None
    assert decoded["sub"] == "rsa-user"

    header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
    assert header["alg"] == "RS256"
    assert header["kid"] == "rsa-1"


def test_rs256_rejects_hs256_alg() -> None:
    private_pem, public_pem = _ephemeral_rsa_pem()
    now = int(time.time())
    # HS256 token must not verify under RS256 decoder
    hs_token = encode_hs256({"sub": "u", "exp": now + 60}, SECRET)
    assert decode_rs256(hs_token, public_pem) is None

    # Forced alg=none on an RS256 token
    rs_token = encode_rs256({"sub": "u", "exp": now + 60}, private_pem)
    assert decode_rs256(_force_alg(rs_token, "none"), public_pem) is None
    assert decode_rs256(_force_alg(rs_token, "HS256"), public_pem) is None


def test_rs256_wrong_key_returns_none() -> None:
    private_a, _ = _ephemeral_rsa_pem()
    _, public_b = _ephemeral_rsa_pem()
    now = int(time.time())
    token = encode_rs256({"sub": "u", "exp": now + 60}, private_a)
    assert decode_rs256(token, public_b) is None


def test_malformed_token_returns_none() -> None:
    assert decode_hs256("", SECRET) is None
    assert decode_hs256("a.b", SECRET) is None
    assert decode_hs256("a.b.c.d", SECRET) is None
    assert decode_hs256("not-a-jwt", SECRET) is None
