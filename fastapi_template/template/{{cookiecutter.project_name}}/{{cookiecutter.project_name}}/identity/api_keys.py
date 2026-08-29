"""
API key storage primitive (sync, in-memory).

Security properties:

    - Plaintext keys are returned only during creation.
    - Only SHA-256 digests are stored.
    - Key verification uses constant-time comparison.
    - Keys can be revoked.
    - Metadata never contains the plaintext secret.
    - API keys are identified by a stable key_id.
    - Designed to be replaced by Redis/SQL persistence through DI.

Layering (do not conflate with api_key_lifecycle):

    ApiKeyLifecycleService  (policy — production path)
            │
       ApiKeyRepository     (Protocol in api_key_lifecycle)
            │
       ApiKeyStore          (this module: sync in-memory / unit tests)

This module owns ``api_keys.ApiKeyRecord`` (digest, sync). Lifecycle owns a
separate ``api_key_lifecycle.ApiKeyRecord`` (secret_hash, environment,
rotation, IP allowlist, async repository). Field shapes do not map cleanly;
callers must import from the module they intend. Production should wire
Lifecycle + SQL; this store remains for unit tests and simple DI.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "ApiKeyRecord",
    "ApiKeyStore",
]


@dataclass(slots=True)
class ApiKeyRecord:
    """Metadata associated with an API key (store primitive)."""

    key_id: str
    name: str
    digest: str

    prefix: str = "nk"

    owner_id: str | None = None
    org_id: str | None = None

    scopes: frozenset[str] = field(
        default_factory=lambda: frozenset({"read"}),
    )

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )

    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    last_used_at: datetime | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return (
            self.expires_at is not None
            and datetime.now(UTC) >= self.expires_at
        )

    @property
    def is_active(self) -> bool:
        return not self.is_revoked and not self.is_expired

    def has_scope(self, scope: str) -> bool:
        """
        Check exact and hierarchical scopes.

        Examples:

            read
            users.read
            users.*
            *
        """

        if "*" in self.scopes:
            return True

        if scope in self.scopes:
            return True

        parts = scope.split(".")

        for index in range(len(parts), 0, -1):
            wildcard = ".".join(parts[:index]) + ".*"

            if wildcard in self.scopes:
                return True

        return False


class ApiKeyStore:
    """
    In-memory API-key store.

    Verify path: parse key_id → load record → digest → constant-time compare
    → reject revoked/expired.

    Production policy/persistence should use ApiKeyLifecycleService + a SQL
    ApiKeyRepository. This class preserves a sync contract for tests / simple DI.
    """

    def __init__(self) -> None:
        self._keys_by_id: dict[str, ApiKeyRecord] = {}
        self._ids_by_digest: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        *,
        prefix: str = "nk",
        owner_id: str | None = None,
        org_id: str | None = None,
        scopes: set[str] | frozenset[str] | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, ApiKeyRecord]:
        """
        Generate a new API key.

        Returns:

            (plaintext_key, metadata)

        The plaintext key must be shown/stored by the caller immediately.
        It cannot be recovered from this store later.
        """

        if not name or not name.strip():
            raise ValueError("API key name is required")

        if not prefix:
            raise ValueError("API key prefix is required")

        key_id = secrets.token_hex(8)
        secret = secrets.token_urlsafe(32)

        plaintext = f"{prefix}_{key_id}_{secret}"

        digest = self._digest(plaintext)

        now = datetime.now(UTC)

        record = ApiKeyRecord(
            key_id=key_id,
            name=name.strip(),
            digest=digest,
            prefix=prefix,
            owner_id=owner_id,
            org_id=org_id,
            scopes=frozenset(scopes or {"read"}),
            created_at=now,
            expires_at=expires_at,
            metadata=dict(metadata or {}),
        )

        self._keys_by_id[key_id] = record
        self._ids_by_digest[digest] = key_id

        return plaintext, record

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(
        self,
        raw_key: str,
        *,
        client_ip: str | None = None,
    ) -> ApiKeyRecord | None:
        """
        Verify an API key.

        Returns metadata only.

        Returns None when:

            - malformed
            - unknown
            - revoked
            - expired
            - secret mismatch (constant-time)

        ``client_ip`` is accepted for DI compatibility with auth deps; this
        primitive does not enforce IP allowlists. Use ApiKeyLifecycleService
        for production IP / scope policy.
        """

        del client_ip  # unused — IP policy lives in api_key_lifecycle

        if not isinstance(raw_key, str) or not raw_key:
            return None

        parsed = self._parse(raw_key)

        if parsed is None:
            return None

        key_id, _secret = parsed

        record = self._keys_by_id.get(key_id)

        if record is None:
            return None

        if not record.is_active:
            return None

        supplied_digest = self._digest(raw_key)

        if not self._constant_time_equal(
            supplied_digest,
            record.digest,
        ):
            return None

        record.last_used_at = datetime.now(UTC)

        return record

    # ------------------------------------------------------------------
    # Revocation
    # ------------------------------------------------------------------

    def revoke(
        self,
        raw_key: str,
    ) -> bool:
        """
        Revoke an API key using its plaintext value.
        """

        if not isinstance(raw_key, str) or not raw_key:
            return False

        parsed = self._parse(raw_key)

        if parsed is None:
            return False

        key_id, _secret = parsed

        return self.revoke_by_id(key_id)

    def revoke_by_id(
        self,
        key_id: str,
    ) -> bool:
        """
        Revoke an API key by stable key identifier.
        """

        record = self._keys_by_id.get(key_id)

        if record is None or record.is_revoked:
            return False

        record.revoked_at = datetime.now(UTC)

        return True

    def revoke_all_for_owner(
        self,
        owner_id: str,
    ) -> int:
        """
        Revoke every active API key belonging to an owner.

        Used by account suspension/deactivation cascades.
        """

        count = 0
        now = datetime.now(UTC)

        for record in self._keys_by_id.values():
            if (
                record.owner_id == owner_id
                and record.revoked_at is None
            ):
                record.revoked_at = now
                count += 1

        return count

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(
        self,
        key_id: str,
    ) -> ApiKeyRecord | None:
        return self._keys_by_id.get(key_id)

    def list_names(
        self,
        *,
        owner_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[str]:
        records = self.list(
            owner_id=owner_id,
            include_revoked=include_revoked,
        )

        return [record.name for record in records]

    def list(
        self,
        *,
        owner_id: str | None = None,
        org_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[ApiKeyRecord]:
        result: list[ApiKeyRecord] = []

        for record in self._keys_by_id.values():
            if owner_id is not None and record.owner_id != owner_id:
                continue

            if org_id is not None and record.org_id != org_id:
                continue

            if not include_revoked and record.is_revoked:
                continue

            result.append(record)

        return result

    def has(
        self,
        raw_key: str,
    ) -> bool:
        return self.verify(raw_key) is not None

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    def has_scope(
        self,
        raw_key: str,
        scope: str,
    ) -> bool:
        record = self.verify(raw_key)

        if record is None:
            return False

        return record.has_scope(scope)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(
            value.encode("utf-8"),
        ).hexdigest()

    @staticmethod
    def _constant_time_equal(
        a: str,
        b: str,
    ) -> bool:
        """Constant-time digest comparison."""

        return hmac.compare_digest(a, b)

    @staticmethod
    def _parse(
        raw_key: str,
    ) -> tuple[str, str] | None:
        """
        Parse:

            prefix_keyid_secret
        """

        parts = raw_key.split("_", 2)

        if len(parts) != 3:
            return None

        prefix, key_id, secret = parts

        if not prefix or not key_id or not secret:
            return None

        return key_id, secret
