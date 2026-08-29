"""TOTP multi-factor authentication (RFC 6238).

Stdlib-only HMAC-SHA1 TOTP generation and verification.

Defaults:

    Algorithm: SHA-1
    Period:    30 seconds
    Digits:    6
    Window:    ±1 period

Production notes:

- Encrypt TOTP secrets at rest; never log them.
- Prefer WebAuthn / passkeys for phishing-resistant MFA when available.
- This module is crypto only — it does **not** persist MFA enrollment state.
  Enrollment, factor binding, and recovery codes belong in a separate store.

Replay rejection (``TotpReplayGuard``) is optional and uses ``ExpiringStore``;
pure ``totp`` / ``verify_totp`` stay free of I/O and persistence.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import struct
import time
from typing import Final
from urllib.parse import quote

from {{cookiecutter.project_name}}.core.state import (
    ExpiringStore,
    InMemoryExpiringStore,
)

DEFAULT_PERIOD = 30
DEFAULT_DIGITS = 6
DEFAULT_WINDOW = 1
DEFAULT_SECRET_BYTES = 20

MIN_DIGITS = 6
MAX_DIGITS = 8
MAX_VERIFY_WINDOW = 10

REPLAY_KEY_PREFIX: Final[str] = "mfa:totp-replay:"

__all__ = [
    "DEFAULT_PERIOD",
    "DEFAULT_DIGITS",
    "DEFAULT_WINDOW",
    "DEFAULT_SECRET_BYTES",
    "MIN_DIGITS",
    "MAX_DIGITS",
    "REPLAY_KEY_PREFIX",
    "TotpReplayGuard",
    "generate_secret",
    "totp",
    "totp_timestep",
    "verify_totp",
    "provisioning_uri",
]


# ---------------------------------------------------------------------------
# Secret generation
# ---------------------------------------------------------------------------


def generate_secret(
    length: int = DEFAULT_SECRET_BYTES,
) -> str:
    """
    Generate a cryptographically random Base32 TOTP secret.

    ``length`` is measured in raw bytes before Base32 encoding.
    20 bytes provides 160 bits of entropy (RFC 4226 recommendation).
    """

    if length < 16:
        raise ValueError(
            "TOTP secret must contain at least 16 random bytes"
        )

    return (
        base64.b32encode(secrets.token_bytes(length))
        .decode("ascii")
        .rstrip("=")
    )


# ---------------------------------------------------------------------------
# Secret decoding
# ---------------------------------------------------------------------------


def _decode_secret(secret: str) -> bytes:
    """
    Decode a Base32 TOTP secret.

    Whitespace is ignored and lowercase input is accepted.
    """

    if not isinstance(secret, str):
        raise ValueError("TOTP secret must be a string")

    normalized = "".join(secret.split()).upper()

    if not normalized:
        raise ValueError("TOTP secret must not be empty")

    # Base32 length must be padded to a multiple of 8.
    padding = "=" * ((8 - len(normalized) % 8) % 8)

    try:
        key = base64.b32decode(
            normalized + padding,
            casefold=True,
        )
    except (binascii.Error, ValueError):
        raise ValueError("invalid Base32 TOTP secret") from None

    if len(key) < 16:
        raise ValueError("TOTP secret is too short")

    return key


# ---------------------------------------------------------------------------
# TOTP generation
# ---------------------------------------------------------------------------


def _validate_parameters(
    *,
    period: int,
    digits: int,
) -> None:
    if period <= 0:
        raise ValueError("period must be greater than zero")

    if digits < MIN_DIGITS or digits > MAX_DIGITS:
        raise ValueError(
            f"digits must be between {MIN_DIGITS} and {MAX_DIGITS}"
        )


def totp_timestep(
    at_time: int | float | None = None,
    *,
    period: int = DEFAULT_PERIOD,
) -> int:
    """Return the RFC 6238 counter ``T = floor(unix_time / period)``."""

    if period <= 0:
        raise ValueError("period must be greater than zero")

    timestamp = time.time() if at_time is None else at_time

    if timestamp < 0:
        raise ValueError("at_time cannot be negative")

    return int(timestamp // period)


def totp(
    secret: str,
    *,
    period: int = DEFAULT_PERIOD,
    digits: int = DEFAULT_DIGITS,
    at_time: int | float | None = None,
) -> str:
    """
    Generate a TOTP code.

    RFC 6238 uses::

        T = floor((current_time - T0) / X)

    with T0 = 0 and X = 30 seconds by default.
    """

    _validate_parameters(period=period, digits=digits)

    key = _decode_secret(secret)
    counter = totp_timestep(at_time, period=period)
    message = struct.pack(">Q", counter)

    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary_code = (
        struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    )
    otp = binary_code % (10**digits)

    return str(otp).zfill(digits)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_totp(
    secret: str,
    code: str,
    *,
    period: int = DEFAULT_PERIOD,
    digits: int = DEFAULT_DIGITS,
    window: int = DEFAULT_WINDOW,
    at_time: int | float | None = None,
) -> bool:
    """
    Verify a TOTP code.

    ``window=1`` accepts the previous, current, and next periods.

    Returns False for malformed secrets/codes rather than exposing
    parsing details to callers. Uses ``secrets.compare_digest``.
    """

    try:
        _validate_parameters(period=period, digits=digits)

        if window < 0 or window > MAX_VERIFY_WINDOW:
            return False

        if not isinstance(code, str):
            return False

        normalized_code = code.strip()

        if len(normalized_code) != digits or not normalized_code.isdigit():
            return False

        timestamp = time.time() if at_time is None else at_time

        if timestamp < 0:
            return False

        current_counter = int(timestamp // period)

        for offset in range(-window, window + 1):
            candidate = totp(
                secret,
                period=period,
                digits=digits,
                at_time=(current_counter + offset) * period,
            )

            if secrets.compare_digest(candidate, normalized_code):
                return True

        return False

    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Provisioning URI
# ---------------------------------------------------------------------------


def provisioning_uri(
    secret: str,
    account: str,
    *,
    issuer: str = "NK",
    algorithm: str = "SHA1",
    digits: int = DEFAULT_DIGITS,
    period: int = DEFAULT_PERIOD,
) -> str:
    """
    Generate a standard ``otpauth://`` provisioning URI.

    Compatible with common authenticator applications.
    """

    _validate_parameters(period=period, digits=digits)

    if not account.strip():
        raise ValueError("account must not be empty")

    if not issuer.strip():
        raise ValueError("issuer must not be empty")

    algorithm = algorithm.upper()

    if algorithm != "SHA1":
        raise ValueError("this implementation supports SHA1 only")

    # Validate the secret before producing the URI.
    _decode_secret(secret)

    encoded_issuer = quote(issuer, safe="")
    encoded_account = quote(account, safe="")
    label = f"{encoded_issuer}:{encoded_account}"

    return (
        f"otpauth://totp/{label}"
        f"?secret={quote(secret.upper(), safe='')}"
        f"&issuer={encoded_issuer}"
        f"&algorithm={algorithm}"
        f"&digits={digits}"
        f"&period={period}"
    )


# ---------------------------------------------------------------------------
# Replay guard (I/O; separate from pure crypto)
# ---------------------------------------------------------------------------


class TotpReplayGuard:
    """
    Reject reuse of the same TOTP timestep for a given factor.

    Backed by ``ExpiringStore.set_if_absent`` so the first successful claim
    wins. Keep this out of ``totp`` / ``verify_totp`` so the crypto path
    stays stdlib-clean and side-effect free.
    """

    def __init__(
        self,
        store: ExpiringStore[str] | None = None,
        *,
        ttl_s: float | None = None,
        period: int = DEFAULT_PERIOD,
        window: int = DEFAULT_WINDOW,
    ) -> None:
        if period <= 0:
            raise ValueError("period must be greater than zero")

        if window < 0:
            raise ValueError("window cannot be negative")

        # Cover the full acceptance window so a code cannot be replayed
        # while verify_totp would still accept it.
        default_ttl = float(period * (2 * window + 1))

        if ttl_s is not None and ttl_s <= 0:
            raise ValueError("ttl_s must be greater than zero")

        self._store: ExpiringStore[str] = store or InMemoryExpiringStore()
        self._ttl_s = default_ttl if ttl_s is None else float(ttl_s)

    @staticmethod
    def replay_key(
        user_id: str,
        factor_id: str,
        timestep: int,
    ) -> str:
        return f"{REPLAY_KEY_PREFIX}{user_id}:{factor_id}:{timestep}"

    async def claim(
        self,
        user_id: str,
        factor_id: str,
        timestep: int,
        *,
        ttl_s: float | None = None,
    ) -> bool:
        """
        Atomically claim a ``(user_id, factor_id, timestep)`` tuple.

        Returns True when newly claimed; False on replay (already used).
        """

        if not user_id or not factor_id:
            raise ValueError("user_id and factor_id must not be empty")

        effective_ttl = self._ttl_s if ttl_s is None else float(ttl_s)

        if effective_ttl <= 0:
            raise ValueError("ttl_s must be greater than zero")

        return await self._store.set_if_absent(
            self.replay_key(user_id, factor_id, timestep),
            "1",
            ttl_s=effective_ttl,
        )
