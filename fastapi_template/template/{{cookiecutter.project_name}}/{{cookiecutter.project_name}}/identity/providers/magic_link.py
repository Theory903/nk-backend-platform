"""Passwordless email authentication using signed, single-use tokens.

Semantics:

- Token contains email + expiry + random nonce.
- Token is authenticated with HMAC-SHA256.
- Expired tokens are rejected.
- Tokens are single-use via ``MagicLinkStore.consume``.
- Token consumption is atomic when backed by a shared store.
- In-memory storage is suitable only for single-process development/tests.

Production multi-worker deployments should use ``RedisMagicLinkStore``
(or another shared atomic store) for consumption.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from threading import RLock
from typing import Any

__all__ = [
    "ExpiredMagicLink",
    "InMemoryMagicLinkStore",
    "InvalidMagicLink",
    "MagicLinkError",
    "MagicLinkPayload",
    "MagicLinkProvider",
    "MagicLinkStore",
    "RedisMagicLinkStore",
    "UsedMagicLink",
]


class MagicLinkError(ValueError):
    """Base magic-link error."""


class InvalidMagicLink(MagicLinkError):
    """Raised when a token is malformed or cryptographically invalid."""


class ExpiredMagicLink(MagicLinkError):
    """Raised when a token has expired."""


class UsedMagicLink(MagicLinkError):
    """Raised when a token has already been consumed."""


@dataclass(frozen=True, slots=True)
class MagicLinkPayload:
    email: str
    expires_at: int
    nonce: str


class MagicLinkStore(ABC):
    """Shared storage contract for single-use token consumption."""

    @abstractmethod
    async def consume(
        self,
        token_id: str,
        *,
        ttl_s: int,
    ) -> bool:
        """Atomically consume a token. True only for the first caller."""
        ...


class InMemoryMagicLinkStore(MagicLinkStore):
    """Single-process implementation for development and tests.

    Thread-safe within one process via ``RLock``. Not suitable for
    multi-worker / multi-process production deployments.
    """

    def __init__(self) -> None:
        self._used: dict[str, float] = {}
        self._lock = RLock()

    async def consume(
        self,
        token_id: str,
        *,
        ttl_s: int,
    ) -> bool:
        now = time.time()

        with self._lock:
            expires_at = self._used.get(token_id)

            if expires_at is not None:
                if expires_at > now:
                    return False

                del self._used[token_id]

            self._used[token_id] = now + ttl_s
            return True

    def cleanup(self) -> None:
        """Remove expired consumption records."""
        now = time.time()

        with self._lock:
            expired = [
                token_id
                for token_id, expires_at in self._used.items()
                if expires_at <= now
            ]

            for token_id in expired:
                del self._used[token_id]


class RedisMagicLinkStore(MagicLinkStore):
    """Multi-worker consumption via Redis ``SET key value NX EX ttl``.

    First successful SET wins; subsequent callers get False.
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        key_prefix: str = "magic_link:used:",
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix

    def _key(self, token_id: str) -> str:
        return f"{self._key_prefix}{token_id}"

    async def consume(
        self,
        token_id: str,
        *,
        ttl_s: int,
    ) -> bool:
        result = await self._redis.set(
            self._key(token_id),
            "1",
            nx=True,
            ex=max(1, int(ttl_s)),
        )
        return bool(result)


class MagicLinkProvider:
    """
    Passwordless email authentication provider.

    Token format:

        version.<urlsafe-b64-payload>.signature

    The payload is base64url-encoded (email/expires/nonce newline-separated)
    so email addresses cannot corrupt token parsing via delimiters.
    """

    VERSION = "v1"

    def __init__(
        self,
        secret: str,
        *,
        ttl_s: int = 600,
        store: MagicLinkStore | None = None,
    ) -> None:
        if not secret:
            raise ValueError("magic-link secret cannot be empty")

        if ttl_s <= 0:
            raise ValueError("ttl_s must be greater than zero")

        self._secret = secret.encode("utf-8")
        self._ttl_s = ttl_s
        self._store = store or InMemoryMagicLinkStore()

    def create_link_token(
        self,
        email: str,
    ) -> str:
        """Create a signed passwordless-login token."""
        normalized_email = self._normalize_email(email)

        expires_at = int(time.time()) + self._ttl_s
        nonce = secrets.token_urlsafe(24)

        payload = MagicLinkPayload(
            email=normalized_email,
            expires_at=expires_at,
            nonce=nonce,
        )

        unsigned = self._encode_payload(payload)
        signature = self._sign(unsigned)

        return f"{unsigned}.{signature}"

    async def verify(
        self,
        token: str,
    ) -> str | None:
        """
        Verify and consume a magic-link token.

        Returns the normalized email on success.
        Returns None for invalid, expired, or already-used tokens.
        Does not issue sessions or access tokens — callers own that.
        """
        try:
            payload = self._decode_and_verify(token)

            if payload.expires_at < int(time.time()):
                return None

            token_id = self._token_id(payload)

            consumed = await self._store.consume(
                token_id,
                ttl_s=self._ttl_s,
            )

            if not consumed:
                return None

            return payload.email

        except (ValueError, TypeError):
            return None

    def _encode_payload(
        self,
        payload: MagicLinkPayload,
    ) -> str:
        """Encode payload with URL-safe base64 (no colon-delimited email)."""
        raw = (
            f"{payload.email}\n"
            f"{payload.expires_at}\n"
            f"{payload.nonce}"
        ).encode("utf-8")

        encoded = base64.urlsafe_b64encode(raw).decode("ascii")

        return f"{self.VERSION}.{encoded}"

    def _decode_and_verify(
        self,
        token: str,
    ) -> MagicLinkPayload:
        try:
            unsigned, signature = token.rsplit(".", 1)

            expected_signature = self._sign(unsigned)

            if not hmac.compare_digest(
                signature,
                expected_signature,
            ):
                raise InvalidMagicLink("invalid signature")

            version, encoded = unsigned.split(".", 1)

            if version != self.VERSION:
                raise InvalidMagicLink("unsupported token version")

            raw = base64.urlsafe_b64decode(
                encoded.encode("ascii")
            ).decode("utf-8")

            email, expires_str, nonce = raw.split("\n", 2)

            expires_at = int(expires_str)

            if not email or not nonce:
                raise InvalidMagicLink("invalid payload")

            return MagicLinkPayload(
                email=self._normalize_email(email),
                expires_at=expires_at,
                nonce=nonce,
            )

        except (
            ValueError,
            TypeError,
            UnicodeDecodeError,
        ) as exc:
            raise InvalidMagicLink("malformed token") from exc

    def _sign(
        self,
        value: str,
    ) -> str:
        return hmac.new(
            self._secret,
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _normalize_email(
        email: str,
    ) -> str:
        normalized = email.strip().casefold()

        if not normalized or "@" not in normalized:
            raise ValueError("invalid email")

        return normalized

    @staticmethod
    def _token_id(
        payload: MagicLinkPayload,
    ) -> str:
        """
        Stable identifier for consumption tracking.

        The full signed token does not need to be stored.
        """
        value = (
            f"{payload.email}:"
            f"{payload.expires_at}:"
            f"{payload.nonce}"
        )

        return hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()
