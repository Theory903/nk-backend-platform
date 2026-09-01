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
import ipaddress
import json
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
    ip_allowlist: tuple[str, ...] = ()

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
        ip_allowlist: tuple[str, ...] | None = None,
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
            ip_allowlist=tuple(ip_allowlist or ()),
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

        If an IP allowlist is configured, the client address must belong to at
        least one configured network.
        """

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

        if record.ip_allowlist and not self._ip_allowed(
            client_ip,
            record.ip_allowlist,
        ):
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
        *,
        client_ip: str | None = None,
    ) -> bool:
        return self.verify(raw_key, client_ip=client_ip) is not None

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    def has_scope(
        self,
        raw_key: str,
        scope: str,
        *,
        client_ip: str | None = None,
    ) -> bool:
        record = self.verify(raw_key, client_ip=client_ip)

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
    def _ip_allowed(
        client_ip: str | None,
        allowlist: tuple[str, ...],
    ) -> bool:
        """Return whether a client address matches the configured networks."""
        if not client_ip:
            return False

        try:
            address = ipaddress.ip_address(client_ip)
            return any(
                address in ipaddress.ip_network(network, strict=False)
                for network in allowlist
            )
        except ValueError:
            return False

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


class RedisApiKeyStore(ApiKeyStore):
    """Redis-backed API-key store with the same sync authentication contract."""

    def __init__(self, redis_client: Any, *, prefix: str = "nk:api-key") -> None:
        super().__init__()
        self._redis = redis_client
        self._prefix = prefix.rstrip(":")

    def _record_key(self, key_id: str) -> str:
        return f"{self._prefix}:{key_id}"

    def _index_key(self) -> str:
        return f"{self._prefix}:index"

    def create(self, *args: Any, **kwargs: Any) -> tuple[str, ApiKeyRecord]:
        raw_key, record = super().create(*args, **kwargs)
        self._persist(record)
        self._redis.sadd(self._index_key(), record.key_id)
        return raw_key, record

    def verify(
        self,
        raw_key: str,
        *,
        client_ip: str | None = None,
    ) -> ApiKeyRecord | None:
        if not isinstance(raw_key, str) or not raw_key:
            return None
        parsed = self._parse(raw_key)
        if parsed is None:
            return None
        key_id, _secret = parsed
        record = self.get(key_id)
        if record is None or not record.is_active:
            return None
        if record.ip_allowlist and not self._ip_allowed(
            client_ip,
            record.ip_allowlist,
        ):
            return None
        if not self._constant_time_equal(
            self._digest(raw_key),
            record.digest,
        ):
            return None
        record.last_used_at = datetime.now(UTC)
        self._persist(record)
        return record

    def get(self, key_id: str) -> ApiKeyRecord | None:
        raw = self._redis.get(self._record_key(key_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return self._decode(json.loads(raw))

    def list(
        self,
        *,
        owner_id: str | None = None,
        org_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[ApiKeyRecord]:
        result: list[ApiKeyRecord] = []
        for raw_key_id in self._redis.smembers(self._index_key()):
            key_id = (
                raw_key_id.decode("utf-8")
                if isinstance(raw_key_id, bytes)
                else str(raw_key_id)
            )
            record = self.get(key_id)
            if record is None:
                continue
            if owner_id is not None and record.owner_id != owner_id:
                continue
            if org_id is not None and record.org_id != org_id:
                continue
            if not include_revoked and record.is_revoked:
                continue
            result.append(record)
        return result

    def revoke_by_id(self, key_id: str) -> bool:
        record = self.get(key_id)
        if record is None or record.is_revoked:
            return False
        record.revoked_at = datetime.now(UTC)
        self._persist(record)
        return True

    def revoke_all_for_owner(self, owner_id: str) -> int:
        count = 0
        for record in self.list(owner_id=owner_id):
            if self.revoke_by_id(record.key_id):
                count += 1
        return count

    def _persist(self, record: ApiKeyRecord) -> None:
        self._redis.set(
            self._record_key(record.key_id),
            json.dumps(self._encode(record)),
        )

    @staticmethod
    def _encode(record: ApiKeyRecord) -> dict[str, Any]:
        return {
            "key_id": record.key_id,
            "name": record.name,
            "digest": record.digest,
            "prefix": record.prefix,
            "owner_id": record.owner_id,
            "org_id": record.org_id,
            "scopes": sorted(record.scopes),
            "ip_allowlist": list(record.ip_allowlist),
            "created_at": record.created_at.isoformat(),
            "expires_at": (
                record.expires_at.isoformat()
                if record.expires_at is not None
                else None
            ),
            "revoked_at": (
                record.revoked_at.isoformat()
                if record.revoked_at is not None
                else None
            ),
            "last_used_at": (
                record.last_used_at.isoformat()
                if record.last_used_at is not None
                else None
            ),
            "metadata": record.metadata,
        }

    @staticmethod
    def _decode(data: dict[str, Any]) -> ApiKeyRecord:
        def parse_date(value: str | None) -> datetime | None:
            return datetime.fromisoformat(value) if value else None

        created_at = parse_date(data.get("created_at")) or datetime.now(UTC)
        return ApiKeyRecord(
            key_id=str(data["key_id"]),
            name=str(data["name"]),
            digest=str(data["digest"]),
            prefix=str(data.get("prefix", "nk")),
            owner_id=data.get("owner_id"),
            org_id=data.get("org_id"),
            scopes=frozenset(data.get("scopes") or ()),
            ip_allowlist=tuple(data.get("ip_allowlist") or ()),
            created_at=created_at,
            expires_at=parse_date(data.get("expires_at")),
            revoked_at=parse_date(data.get("revoked_at")),
            last_used_at=parse_date(data.get("last_used_at")),
            metadata=dict(data.get("metadata") or {}),
        )
