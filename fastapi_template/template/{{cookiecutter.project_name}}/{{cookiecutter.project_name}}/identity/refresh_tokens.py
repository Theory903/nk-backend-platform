"""Refresh-token rotation with family-based reuse detection.

Security properties:

- Refresh tokens are random opaque values.
- Only SHA-256 token hashes are stored.
- Tokens are single-use.
- Every rotation creates a new token in the same family.
- Reuse of a consumed token revokes the entire family.
- Family revocation supports global logout.
- Rotation is designed around an atomic storage operation.

The in-memory implementation is suitable for development/tests only
(single-process). Production should provide an atomic Redis/database
implementation (e.g. Redis Lua consume-then-issue).
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "RefreshTokenRecord",
    "RefreshTokenManager",
]


@dataclass
class RefreshTokenRecord:
    token_hash: str
    user_id: str
    family_id: str

    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    used: bool = False
    revoked: bool = False

    replaced_by: str | None = None


class RefreshTokenManager:
    """
    Refresh-token family manager.

    Token lifecycle:

        issued
           ↓
        active
           ↓
        consumed
           ↓
        replaced

    Reuse of a consumed/revoked token causes family revocation.

    Thread safety: a process-local ``threading.RLock`` serializes
    issue/rotate/revoke/purge. This does **not** protect across
    processes or hosts — production needs Redis/DB atomicity.
    """

    def __init__(self, *, ttl_s: int = 604800) -> None:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be greater than zero")

        self.ttl_s = ttl_s
        self._lock = threading.RLock()
        self._tokens: dict[str, RefreshTokenRecord] = {}
        self._families_revoked: set[str] = set()

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _new_token() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def _new_family_id() -> str:
        return secrets.token_hex(16)

    def issue(self, user_id: str) -> str:
        """
        Issue the initial refresh token.

        Creates a new token family.
        """
        if not user_id:
            raise ValueError("user_id must not be empty")

        with self._lock:
            return self._issue_in_family(
                user_id=user_id,
                family_id=self._new_family_id(),
            )

    def _issue_in_family(self, *, user_id: str, family_id: str) -> str:
        raw = self._new_token()
        now = time.time()
        record = RefreshTokenRecord(
            token_hash=self._hash(raw),
            user_id=user_id,
            family_id=family_id,
            created_at=now,
            expires_at=now + self.ttl_s,
        )
        self._tokens[record.token_hash] = record
        return raw

    def rotate(
        self,
        raw_token: str,
    ) -> tuple[str, dict[str, Any]] | None:
        """
        Atomically consume an old token and issue its replacement.

        Returns:

            (new_refresh_token, metadata)

        Returns None for an invalid token.

        Reuse of a previously consumed/revoked token revokes its
        entire family and returns None.
        """
        with self._lock:
            token_hash = self._hash(raw_token)
            record = self._tokens.get(token_hash)

            if record is None:
                return None

            if record.family_id in self._families_revoked:
                return None

            now = time.time()

            if record.revoked:
                self._revoke_family(record.family_id)
                return None

            if record.used:
                # Refresh-token reuse detection.
                self._revoke_family(record.family_id)
                return None

            if now >= record.expires_at:
                record.revoked = True
                return None

            # Consume the old token BEFORE issuing the replacement.
            record.used = True

            new_token = self._issue_in_family(
                user_id=record.user_id,
                family_id=record.family_id,
            )
            record.replaced_by = self._hash(new_token)

            return new_token, {
                "user_id": record.user_id,
                "family_id": record.family_id,
            }

    def validate(self, raw_token: str) -> dict[str, Any] | None:
        """
        Validate without rotating.

        IMPORTANT:
        This method does not consume the token.

        For a real refresh endpoint, use rotate() instead.
        """
        with self._lock:
            token_hash = self._hash(raw_token)
            record = self._tokens.get(token_hash)

            if record is None:
                return None

            if record.family_id in self._families_revoked:
                return None

            if record.revoked or record.used:
                return None

            if time.time() >= record.expires_at:
                return None

            return {
                "user_id": record.user_id,
                "family_id": record.family_id,
            }

    def revoke(self, raw_token: str) -> bool:
        """Revoke one refresh token."""
        with self._lock:
            token_hash = self._hash(raw_token)
            record = self._tokens.get(token_hash)

            if record is None:
                return False

            if record.revoked:
                return False

            record.revoked = True
            return True

    def revoke_family(self, family_id: str) -> None:
        """Revoke every token belonging to a family."""
        with self._lock:
            self._revoke_family(family_id)

    def _revoke_family(self, family_id: str) -> None:
        self._families_revoked.add(family_id)
        for record in self._tokens.values():
            if record.family_id == family_id:
                record.revoked = True

    def revoke_all_for_user(self, user_id: str) -> int:
        """
        Revoke every refresh-token family belonging to a user.

        Used for global logout, password reset, account suspension,
        account deactivation, etc.
        """
        with self._lock:
            families: set[str] = set()
            for record in self._tokens.values():
                if record.user_id == user_id:
                    families.add(record.family_id)

            for family_id in families:
                self._revoke_family(family_id)

            return len(families)

    def family_for_token(self, raw_token: str) -> str | None:
        """Return the token family without changing state."""
        with self._lock:
            record = self._tokens.get(self._hash(raw_token))
            if record is None:
                return None
            return record.family_id

    def purge_expired(self) -> int:
        """
        Remove expired token records.

        Production implementations should perform this as a background
        cleanup job with database/Redis TTLs where possible.
        """
        with self._lock:
            now = time.time()
            expired = [
                token_hash
                for token_hash, record in self._tokens.items()
                if record.expires_at <= now
            ]
            for token_hash in expired:
                del self._tokens[token_hash]
            return len(expired)
