"""Security primitives for request identity, password hashing and tokens.

Design goals:
- cryptographically secure request IDs
- safe secret masking
- constant-time comparisons
- memory-hard password hashing with scrypt
- authenticated, expiring tokens
- strict token validation
- no accidental secret disclosure

These helpers are intentionally dependency-light and use Python's standard
library.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Final

from fastapi import Request


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PASSWORD_SALT_BYTES: Final[int] = 16
PASSWORD_HASH_BYTES: Final[int] = 32

SCRYPT_N: Final[int] = 2**14
SCRYPT_R: Final[int] = 8
SCRYPT_P: Final[int] = 1

TOKEN_VERSION: Final[int] = 1
DEFAULT_TOKEN_TTL_S: Final[int] = 3600
MAX_TOKEN_TTL_S: Final[int] = 7 * 24 * 60 * 60

MAX_REQUEST_ID_LENGTH: Final[int] = 128
MAX_TOKEN_LENGTH: Final[int] = 8192


class SecurityError(ValueError):
    """Base security primitive error."""


class InvalidPasswordHash(SecurityError):
    """Stored password hash is malformed."""


class InvalidToken(SecurityError):
    """Token is malformed or invalid."""


# ---------------------------------------------------------------------------
# Request identity
# ---------------------------------------------------------------------------


def new_request_id() -> str:
    """Generate a cryptographically random request identifier."""

    return uuid.uuid4().hex


def get_request_id(
    request: Request,
) -> str:
    """
    Resolve the request ID.

    Existing IDs are accepted only after basic normalization. Applications
    that expose request IDs externally should consider generating their own
    ID rather than blindly trusting an incoming header.
    """

    header = request.headers.get(
        "x-request-id"
    )

    if header:
        value = header.strip()

        if (
            value
            and len(value) <= MAX_REQUEST_ID_LENGTH
        ):
            return value

    existing = getattr(
        request.state,
        "request_id",
        None,
    )

    if isinstance(existing, str) and existing:
        return existing

    return new_request_id()


# ---------------------------------------------------------------------------
# Secret handling
# ---------------------------------------------------------------------------


def mask_secret(
    value: str,
    *,
    visible: int = 4,
) -> str:
    """Mask a secret for logs or diagnostics."""

    if visible < 0:
        raise ValueError(
            "visible cannot be negative"
        )

    if not value:
        return ""

    if visible == 0:
        return "*" * len(value)

    if len(value) <= visible:
        return "*" * len(value)

    return (
        value[:visible]
        + "*" * (
            len(value) - visible
        )
    )


def constant_time_compare(
    a: str,
    b: str,
) -> bool:
    """Compare two strings without timing-based equality shortcuts."""

    return hmac.compare_digest(
        a.encode("utf-8"),
        b.encode("utf-8"),
    )


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScryptParameters:
    """Parameters used to derive a password hash."""

    n: int = SCRYPT_N
    r: int = SCRYPT_R
    p: int = SCRYPT_P
    dklen: int = PASSWORD_HASH_BYTES


def hash_password(
    password: str,
    *,
    salt: bytes | None = None,
    parameters: ScryptParameters | None = None,
) -> str:
    """
    Hash a password using scrypt.

    Format:

        scrypt$v=1$n=16384$r=8$p=1$<salt_hex>$<hash_hex>

    Parameters are embedded so future parameter upgrades do not require
    guessing which configuration produced an existing password hash.
    """

    if not isinstance(password, str):
        raise TypeError(
            "password must be a string"
        )

    if not password:
        raise ValueError(
            "password must not be empty"
        )

    params = (
        parameters
        or ScryptParameters()
    )

    _validate_scrypt_parameters(
        params
    )

    salt = (
        salt
        if salt is not None
        else secrets.token_bytes(
            PASSWORD_SALT_BYTES
        )
    )

    if len(salt) < 16:
        raise ValueError(
            "password salt must contain at least 16 bytes"
        )

    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=params.n,
        r=params.r,
        p=params.p,
        dklen=params.dklen,
    )

    return (
        f"scrypt$v={1}"
        f"$n={params.n}"
        f"$r={params.r}"
        f"$p={params.p}"
        f"${salt.hex()}"
        f"${derived.hex()}"
    )


def verify_password(
    password: str,
    stored: str,
) -> bool:
    """
    Verify a password against a stored scrypt hash.

    Invalid/malformed hashes return False rather than leaking parsing details.
    """

    try:
        algorithm, version, n, r, p, salt_hex, hash_hex = (
            stored.split("$")
        )

        if algorithm != "scrypt":
            return False

        if version != "v=1":
            return False

        n_value = _parse_parameter(
            n,
            "n",
        )
        r_value = _parse_parameter(
            r,
            "r",
        )
        p_value = _parse_parameter(
            p,
            "p",
        )

        salt = bytes.fromhex(
            salt_hex
        )
        expected = bytes.fromhex(
            hash_hex
        )

        parameters = ScryptParameters(
            n=n_value,
            r=r_value,
            p=p_value,
            dklen=len(expected),
        )

        _validate_scrypt_parameters(
            parameters
        )

        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n_value,
            r=r_value,
            p=p_value,
            dklen=len(expected),
        )

        return hmac.compare_digest(
            derived,
            expected,
        )

    except (
        AttributeError,
        TypeError,
        ValueError,
        UnicodeError,
    ):
        return False


def _parse_parameter(
    value: str,
    expected_name: str,
) -> int:
    name, separator, raw = value.partition("=")

    if (
        not separator
        or name != expected_name
    ):
        raise ValueError(
            f"invalid scrypt parameter: {expected_name}"
        )

    parsed = int(raw)

    if parsed <= 0:
        raise ValueError(
            f"invalid scrypt parameter: {expected_name}"
        )

    return parsed


def _validate_scrypt_parameters(
    parameters: ScryptParameters,
) -> None:
    if parameters.n <= 1 or (
        parameters.n
        & (parameters.n - 1)
    ):
        raise ValueError(
            "scrypt n must be a power of two greater than one"
        )

    if parameters.r <= 0:
        raise ValueError(
            "scrypt r must be greater than zero"
        )

    if parameters.p <= 0:
        raise ValueError(
            "scrypt p must be greater than zero"
        )

    if parameters.dklen <= 0:
        raise ValueError(
            "scrypt dklen must be greater than zero"
        )


# ---------------------------------------------------------------------------
# Signed tokens
# ---------------------------------------------------------------------------


def create_token(
    payload: str,
    secret: str,
    *,
    ttl_s: int = DEFAULT_TOKEN_TTL_S,
) -> str:
    """
    Create an authenticated, expiring opaque token.

    The payload is signed with HMAC-SHA256.

    Token format:

        base64url(payload).base64url(signature)
    """

    if not payload:
        raise ValueError(
            "token payload must not be empty"
        )

    if not secret:
        raise ValueError(
            "token secret must not be empty"
        )

    if ttl_s <= 0:
        raise ValueError(
            "ttl_s must be greater than zero"
        )

    if ttl_s > MAX_TOKEN_TTL_S:
        raise ValueError(
            f"ttl_s cannot exceed {MAX_TOKEN_TTL_S} seconds"
        )

    now = int(time.time())

    claims = {
        "v": TOKEN_VERSION,
        "sub": payload,
        "iat": now,
        "exp": now + ttl_s,
        "jti": secrets.token_urlsafe(16),
    }

    body = _encode_json(
        claims
    )

    signature = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()

    return (
        _b64encode(body)
        + "."
        + _b64encode(signature)
    )


def validate_token(
    token: str,
    secret: str,
) -> str | None:
    """
    Validate a signed token and return its subject.

    Returns None for any invalid, expired or malformed token.
    """

    try:
        if (
            not token
            or len(token) > MAX_TOKEN_LENGTH
            or not secret
        ):
            return None

        body_part, signature_part = token.split(
            ".",
            1,
        )

        body = _b64decode(
            body_part
        )
        supplied_signature = _b64decode(
            signature_part
        )

        expected_signature = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()

        if not hmac.compare_digest(
            supplied_signature,
            expected_signature,
        ):
            return None

        data = json.loads(
            body.decode("utf-8")
        )

        if not isinstance(data, dict):
            return None

        if data.get("v") != TOKEN_VERSION:
            return None

        subject = data.get("sub")
        issued_at = data.get("iat")
        expires_at = data.get("exp")

        if not isinstance(
            subject,
            str,
        ) or not subject:
            return None

        if not isinstance(
            issued_at,
            int,
        ):
            return None

        if not isinstance(
            expires_at,
            int,
        ):
            return None

        now = int(time.time())

        if issued_at > now:
            return None

        if expires_at <= now:
            return None

        return subject

    except (
        UnicodeDecodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return None


# ---------------------------------------------------------------------------
# Internal encoding
# ---------------------------------------------------------------------------


def _encode_json(
    value: dict[str, object],
) -> bytes:
    return json.dumps(
        value,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")


def _b64encode(
    value: bytes,
) -> str:
    return (
        base64.urlsafe_b64encode(
            value
        )
        .rstrip(b"=")
        .decode("ascii")
    )


def _b64decode(
    value: str,
) -> bytes:
    if not value:
        raise ValueError(
            "empty base64 value"
        )

    encoded = value.encode("ascii")

    encoded += b"=" * (
        (-len(encoded)) % 4
    )

    return base64.b64decode(
        encoded,
        altchars=b"-_",
        validate=True,
    )


__all__ = [
    "DEFAULT_TOKEN_TTL_S",
    "InvalidPasswordHash",
    "InvalidToken",
    "MAX_TOKEN_TTL_S",
    "ScryptParameters",
    "SecurityError",
    "constant_time_compare",
    "create_token",
    "get_request_id",
    "hash_password",
    "mask_secret",
    "new_request_id",
    "validate_token",
    "verify_password",
]