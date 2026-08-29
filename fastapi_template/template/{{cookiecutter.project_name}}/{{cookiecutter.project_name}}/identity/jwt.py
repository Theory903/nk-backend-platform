"""JWT encode/decode primitives (HS256 / RS256, optional kid).

Supported algorithms:

    HS256
    RS256

For production access-token issuance and policy-gated validation
(allowlist, max age, structured errors), use ``identity.token_policy``
(``create_token`` / ``validate_token`` + ``TokenPolicy``). This module
stays as low-level primitives used by kid-aware helpers and key rotation.

Security properties:

    - Explicit algorithm allow-list.
    - Deterministic JSON serialization.
    - Constant-time HS256 signature comparison.
    - Required/optional temporal claim validation.
    - Issuer and audience validation.
    - JWT ID support.
    - Clock-skew leeway.
    - RSA key type validation.
    - Optional ``kid`` for key rotation.

This module intentionally does not implement JWE/encryption.
JWTs produced here are signed, not encrypted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Any

ALGORITHM_HS256 = "HS256"
ALGORITHM_RS256 = "RS256"
JWT_TYPE = "JWT"

DEFAULT_LEEWAY_S = 30


# ---------------------------------------------------------------------------
# Base64URL
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    """Encode bytes using unpadded Base64URL."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Decode unpadded Base64URL."""
    if not data:
        raise ValueError("empty base64url value")

    if len(data) % 4:
        data += "=" * (4 - len(data) % 4)

    return base64.urlsafe_b64decode(data.encode("ascii"))


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _json_encode(value: Mapping[str, Any]) -> str:
    """
    Serialize JWT JSON deterministically.

    Compact output avoids insignificant whitespace and sorted keys make
    signatures reproducible for equivalent dictionaries.
    """
    return json.dumps(
        value,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )


def _encode_segment(value: Mapping[str, Any]) -> str:
    return _b64url_encode(
        _json_encode(value).encode("utf-8"),
    )


def _decode_json_segment(segment: str) -> dict[str, Any]:
    value = json.loads(
        _b64url_decode(segment).decode("utf-8"),
    )

    if not isinstance(value, dict):
        raise ValueError("JWT segment must contain a JSON object")

    return value


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


def _validate_temporal_claims(
    payload: Mapping[str, Any],
    *,
    verify_exp: bool,
    verify_nbf: bool,
    verify_iat: bool,
    leeway_s: int,
) -> None:
    now = time.time()

    exp = payload.get("exp")

    if verify_exp:
        if exp is None:
            raise ValueError("missing exp claim")

        if not isinstance(exp, (int, float)):
            raise ValueError("exp must be numeric")

        if now >= float(exp) + leeway_s:
            raise ValueError("token expired")

    elif exp is not None and not isinstance(exp, (int, float)):
        raise ValueError("exp must be numeric")

    nbf = payload.get("nbf")

    if verify_nbf and nbf is not None:
        if not isinstance(nbf, (int, float)):
            raise ValueError("nbf must be numeric")

        if now + leeway_s < float(nbf):
            raise ValueError("token is not active yet")

    iat = payload.get("iat")

    if verify_iat and iat is not None:
        if not isinstance(iat, (int, float)):
            raise ValueError("iat must be numeric")

        if float(iat) > now + leeway_s:
            raise ValueError("iat is in the future")


def _validate_identity_claims(
    payload: Mapping[str, Any],
    *,
    issuer: str | None,
    audience: str | None,
) -> None:
    if issuer is not None:
        if payload.get("iss") != issuer:
            raise ValueError("invalid issuer")

    if audience is not None:
        actual = payload.get("aud")

        if isinstance(actual, str):
            audiences = {actual}
        elif isinstance(actual, list):
            audiences = {
                value
                for value in actual
                if isinstance(value, str)
            }
        else:
            audiences = set()

        if audience not in audiences:
            raise ValueError("invalid audience")


# ---------------------------------------------------------------------------
# HS256
# ---------------------------------------------------------------------------


def encode_hs256(
    payload: dict[str, Any],
    secret: str,
    *,
    kid: str | None = None,
) -> str:
    """
    Encode a JWT using HMAC-SHA256.

    ``secret`` must be supplied explicitly. No fallback secret is used.
    """

    if not secret:
        raise ValueError("JWT signing secret must not be empty")

    header: dict[str, Any] = {
        "alg": ALGORITHM_HS256,
        "typ": JWT_TYPE,
    }

    if kid:
        header["kid"] = kid

    encoded_header = _encode_segment(header)
    encoded_payload = _encode_segment(payload)

    signing_input = (
        f"{encoded_header}.{encoded_payload}"
    ).encode("ascii")

    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    return (
        f"{encoded_header}."
        f"{encoded_payload}."
        f"{_b64url_encode(signature)}"
    )


def decode_hs256(
    token: str,
    secret: str,
    *,
    verify_exp: bool = True,
    verify_nbf: bool = True,
    verify_iat: bool = True,
    issuer: str | None = None,
    audience: str | None = None,
    leeway_s: int = DEFAULT_LEEWAY_S,
) -> dict[str, Any] | None:
    """
    Decode and verify an HS256 JWT.

    Returns the payload when valid, otherwise None.
    """

    if not secret:
        return None

    try:
        header_b64, payload_b64, signature_b64 = _split_token(token)

        header = _decode_json_segment(header_b64)

        # Never trust the caller's requested algorithm.
        if header.get("alg") != ALGORITHM_HS256:
            return None

        if header.get("typ") not in (None, JWT_TYPE):
            return None

        expected = hmac.new(
            secret.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode("ascii"),
            hashlib.sha256,
        ).digest()

        actual = _b64url_decode(signature_b64)

        if not hmac.compare_digest(actual, expected):
            return None

        payload = _decode_json_segment(payload_b64)

        _validate_temporal_claims(
            payload,
            verify_exp=verify_exp,
            verify_nbf=verify_nbf,
            verify_iat=verify_iat,
            leeway_s=leeway_s,
        )

        _validate_identity_claims(
            payload,
            issuer=issuer,
            audience=audience,
        )

        return payload

    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# RS256
# ---------------------------------------------------------------------------


def encode_rs256(
    payload: dict[str, Any],
    private_key_pem: str,
    *,
    kid: str | None = None,
) -> str:
    """
    Encode a JWT using an RSA private key.

    Requires ``cryptography``.
    """

    if not private_key_pem:
        raise ValueError("private key must not be empty")

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    header: dict[str, Any] = {
        "alg": ALGORITHM_RS256,
        "typ": JWT_TYPE,
    }

    if kid:
        header["kid"] = kid

    encoded_header = _encode_segment(header)
    encoded_payload = _encode_segment(payload)

    key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
    )

    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError(
            "RS256 requires an RSA private key"
        )

    signing_input = (
        f"{encoded_header}.{encoded_payload}"
    ).encode("ascii")

    signature = key.sign(
        signing_input,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    return (
        f"{encoded_header}."
        f"{encoded_payload}."
        f"{_b64url_encode(signature)}"
    )


def decode_rs256(
    token: str,
    public_key_pem: str,
    *,
    verify_exp: bool = True,
    verify_nbf: bool = True,
    verify_iat: bool = True,
    issuer: str | None = None,
    audience: str | None = None,
    leeway_s: int = DEFAULT_LEEWAY_S,
) -> dict[str, Any] | None:
    """
    Decode and verify an RS256 JWT.

    Requires ``cryptography``.
    """

    if not public_key_pem:
        return None

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import (
            padding,
            rsa,
        )

        header_b64, payload_b64, signature_b64 = _split_token(token)

        header = _decode_json_segment(header_b64)

        if header.get("alg") != ALGORITHM_RS256:
            return None

        if header.get("typ") not in (None, JWT_TYPE):
            return None

        key = serialization.load_pem_public_key(
            public_key_pem.encode("utf-8"),
        )

        if not isinstance(key, rsa.RSAPublicKey):
            return None

        key.verify(
            _b64url_decode(signature_b64),
            f"{header_b64}.{payload_b64}".encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        payload = _decode_json_segment(payload_b64)

        _validate_temporal_claims(
            payload,
            verify_exp=verify_exp,
            verify_nbf=verify_nbf,
            verify_iat=verify_iat,
            leeway_s=leeway_s,
        )

        _validate_identity_claims(
            payload,
            issuer=issuer,
            audience=audience,
        )

        return payload

    except (
        ValueError,
        TypeError,
        UnicodeError,
        json.JSONDecodeError,
        InvalidSignature,
    ):
        return None


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _split_token(token: str) -> tuple[str, str, str]:
    if not token or not isinstance(token, str):
        raise ValueError("empty JWT")

    parts = token.split(".")

    if len(parts) != 3:
        raise ValueError("malformed JWT")

    if any(not part for part in parts):
        raise ValueError("malformed JWT")

    return parts[0], parts[1], parts[2]


def create_access_token(
    subject: str,
    secret: str,
    *,
    ttl_s: int = 3600,
    issuer: str | None = None,
    audience: str | None = None,
    scopes: list[str] | None = None,
    token_id: str | None = None,
    not_before_s: int | None = None,
    kid: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a short-lived HS256 access token.

    Standard claims:

        sub
        iat
        exp
        nbf
        iss
        aud
        jti
        scope
    """

    if not subject:
        raise ValueError("subject must not be empty")

    if not secret:
        raise ValueError("JWT secret must not be empty")

    if ttl_s <= 0:
        raise ValueError("ttl_s must be greater than zero")

    now = int(time.time())

    claims: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + ttl_s,
    }

    if not_before_s is not None:
        claims["nbf"] = now + not_before_s

    if issuer:
        claims["iss"] = issuer

    if audience:
        claims["aud"] = audience

    if scopes:
        claims["scope"] = " ".join(scopes)

    if token_id:
        claims["jti"] = token_id

    if extra_claims:
        # Deliberately applied last so callers can add custom claims.
        # Security-sensitive standard claims should not normally be
        # overridden by application code.
        claims.update(extra_claims)

    return encode_hs256(
        claims,
        secret,
        kid=kid,
    )


__all__ = [
    "ALGORITHM_HS256",
    "ALGORITHM_RS256",
    "DEFAULT_LEEWAY_S",
    "JWT_TYPE",
    "create_access_token",
    "decode_hs256",
    "decode_rs256",
    "encode_hs256",
    "encode_rs256",
]