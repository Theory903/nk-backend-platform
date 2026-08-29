"""Email verification with throttling and single-use tokens.

Tokens are signed with HMAC-SHA256 and contain:

    email
    expiry
    nonce

The plaintext token is safe to place in an email link because it contains
no password or other secret.

Resend cooldown and consumed-token state are backed by shared
``ExpiringStore`` (in-memory for tests / Redis in production).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Final

from {{cookiecutter.project_name}}.core.state import (
    ExpiringStore,
    InMemoryExpiringStore,
)


TOKEN_SEPARATOR: Final[str] = ":"
USED_TOKEN_PREFIX: Final[str] = "email-verification:used:"
RESEND_PREFIX: Final[str] = "email-verification:resend:"


class EmailVerificationService:
    """
    Create and verify short-lived, single-use email verification tokens.

    Security properties:

    - HMAC-SHA256 signatures prevent token tampering.
    - Cryptographically random nonces prevent token prediction.
    - Expiry limits token lifetime.
    - Consumed tokens cannot be reused (atomic ``set_if_absent``).
    - Resend cooldown prevents email spam (atomic ``set_if_absent``).
    - Shared stores allow multiple application instances to coordinate.
    """

    def __init__(
        self,
        secret: str,
        *,
        ttl_s: int = 86_400,
        resend_cooldown_s: int = 60,
        used_store: ExpiringStore | None = None,
        resend_store: ExpiringStore | None = None,
    ) -> None:
        if not secret:
            raise ValueError(
                "email verification secret must not be empty"
            )

        if ttl_s <= 0:
            raise ValueError(
                "ttl_s must be greater than zero"
            )

        if resend_cooldown_s < 0:
            raise ValueError(
                "resend_cooldown_s cannot be negative"
            )

        self._secret = secret.encode("utf-8")
        self.ttl_s = ttl_s
        self.resend_cooldown_s = resend_cooldown_s

        self._used_store = used_store or InMemoryExpiringStore()
        self._resend_store = resend_store or InMemoryExpiringStore()

    # ------------------------------------------------------------------
    # Token primitives
    # ------------------------------------------------------------------

    def _sign(self, payload: str) -> str:
        return hmac.new(
            self._secret,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _build_token(
        self,
        *,
        email: str,
        expires: int,
        nonce: str,
    ) -> str:
        payload = (
            f"{email}"
            f"{TOKEN_SEPARATOR}{expires}"
            f"{TOKEN_SEPARATOR}{nonce}"
        )

        signature = self._sign(payload)

        return (
            f"{payload}"
            f"{TOKEN_SEPARATOR}{signature}"
        )

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    async def create_verification_token(
        self,
        email: str,
    ) -> str:
        """
        Create a verification token.

        Raises ValueError when resend cooldown is active.
        """

        normalized_email = self._normalize_email(email)

        if not normalized_email:
            raise ValueError(
                "email is required"
            )

        if self.resend_cooldown_s > 0:
            resend_key = (
                f"{RESEND_PREFIX}"
                f"{self._hash_identifier(normalized_email)}"
            )

            inserted = await self._resend_store.set_if_absent(
                resend_key,
                True,
                ttl_s=float(self.resend_cooldown_s),
            )

            if not inserted:
                raise ValueError(
                    f"resend cooldown active "
                    f"({self.resend_cooldown_s}s)"
                )

        now = int(time.time())
        expires = now + self.ttl_s
        nonce = secrets.token_urlsafe(24)

        return self._build_token(
            email=normalized_email,
            expires=expires,
            nonce=nonce,
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    async def verify_token(
        self,
        token: str,
    ) -> str | None:
        """
        Validate and consume a verification token.

        Returns the normalized email on success, otherwise None.

        Consumption occurs only after signature and expiry validation,
        via atomic ``set_if_absent`` so concurrent consumers cannot
        both succeed.
        """

        parsed = self._parse_token(token)

        if parsed is None:
            return None

        email, expires, nonce, signature = parsed

        payload = (
            f"{email}"
            f"{TOKEN_SEPARATOR}{expires}"
            f"{TOKEN_SEPARATOR}{nonce}"
        )

        expected_signature = self._sign(payload)

        if not hmac.compare_digest(
            signature,
            expected_signature,
        ):
            return None

        now = int(time.time())

        if now >= expires:
            return None

        token_hash = self._hash_identifier(token)
        used_key = f"{USED_TOKEN_PREFIX}{token_hash}"

        remaining_ttl = max(1, expires - now)

        inserted = await self._used_store.set_if_absent(
            used_key,
            True,
            ttl_s=float(remaining_ttl),
        )

        if not inserted:
            return None

        return email

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_token(
        token: str,
    ) -> tuple[str, int, str, str] | None:
        if not token or not isinstance(token, str):
            return None

        try:
            email, expires_raw, nonce, signature = token.split(
                TOKEN_SEPARATOR,
                3,
            )

            expires = int(expires_raw)

        except (ValueError, TypeError):
            return None

        if not email or not nonce or not signature:
            return None

        return (
            email,
            expires,
            nonce,
            signature,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _hash_identifier(value: str) -> str:
        """
        Hash identifiers before using them as store keys.

        This prevents raw email addresses/tokens from becoming visible
        in Redis keys, metrics, logs, etc.
        """

        return hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()


__all__ = [
    "EmailVerificationService",
    "RESEND_PREFIX",
    "TOKEN_SEPARATOR",
    "USED_TOKEN_PREFIX",
]
