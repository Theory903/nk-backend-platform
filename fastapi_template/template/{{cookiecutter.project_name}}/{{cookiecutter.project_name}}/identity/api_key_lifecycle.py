"""
Production-oriented API key lifecycle.

Properties:

    - plaintext key is returned exactly once at creation/rotation
    - only a cryptographic digest is persisted
    - key lookup uses a public key identifier
    - expiration and revocation are enforced centrally
    - hierarchical scopes are supported
    - CIDR-based IP restrictions are supported
    - rotation creates a new key and revokes the old one
    - account/org ownership is explicit
    - lifecycle operations are repository-backed
    - authentication never returns the plaintext secret
    - last-used timestamps may be asynchronously persisted

Recommended storage model:

    api_keys
    ─────────────────────────────────────────────
    key_id              PRIMARY KEY
    secret_hash         UNIQUE
    name
    owner_id
    org_id
    environment
    scopes
    created_at
    expires_at
    revoked_at
    revoked_reason
    last_used_at
    rotated_from
    metadata

Recommended indexes:

    UNIQUE(secret_hash)
    INDEX(owner_id)
    INDEX(org_id)
    INDEX(expires_at)
    INDEX(revoked_at)

The database should additionally enforce tenant ownership rules.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.core.identifiers import new_id


# Format: nk_{env}_{key_id}_{secret}
# key_id comes from new_id("key") → "key_<32 hex>" (contains an underscore).
_PLAINTEXT_KEY_RE: Final[re.Pattern[str]] = re.compile(
    r"^nk_(live|test)_(key_[A-Za-z0-9]+)_(.+)$",
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ApiKeyError(Problem):
    """Base API-key error."""


class ApiKeyNotFoundError(ApiKeyError):
    def __init__(self) -> None:
        super().__init__(
            title="API Key Not Found",
            status_code=404,
            detail="API key was not found",
        )


class ApiKeyInvalidError(ApiKeyError):
    def __init__(self) -> None:
        super().__init__(
            title="Invalid API Key",
            status_code=401,
            detail="API key is invalid or inactive",
            headers={"WWW-Authenticate": "ApiKey"},
        )


class ApiKeyAlreadyRevokedError(ApiKeyError):
    def __init__(self) -> None:
        super().__init__(
            title="API Key Already Revoked",
            status_code=409,
            detail="API key has already been revoked",
        )


class ApiKeyScopeError(ApiKeyError):
    def __init__(self, scope: str) -> None:
        super().__init__(
            title="Insufficient API Key Scope",
            status_code=403,
            detail=f"API key does not grant scope '{scope}'",
        )


class ApiKeyIpRestrictedError(ApiKeyError):
    def __init__(self) -> None:
        super().__init__(
            title="IP Address Not Allowed",
            status_code=403,
            detail="request IP is not allowed for this API key",
        )


class ApiKeyOwnershipError(ApiKeyError):
    def __init__(self) -> None:
        super().__init__(
            title="API Key Ownership Error",
            status_code=403,
            detail="API key does not belong to the requested owner",
        )


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    """
    Safe representation of an API key.

    IMPORTANT:
        plaintext secret is deliberately absent.
    """

    key_id: str
    name: str
    secret_hash: str

    owner_id: str
    org_id: str | None = None

    environment: str = "live"

    scopes: frozenset[str] = frozenset()

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )

    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_reason: str | None = None

    last_used_at: datetime | None = None

    rotated_from: str | None = None

    ip_allowlist: tuple[str, ...] = ()

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    @property
    def prefix(self) -> str:
        return f"nk_{self.environment}"

    @property
    def is_expired(self) -> bool:
        return (
            self.expires_at is not None
            and datetime.now(UTC) >= self.expires_at
        )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_active(self) -> bool:
        return not self.is_revoked and not self.is_expired

    def has_scope(self, required: str) -> bool:
        """
        Hierarchical scope matching.

        Examples:

            crm.read
            crm.*
            *
        """

        if "*" in self.scopes:
            return True

        if required in self.scopes:
            return True

        parts = required.split(".")

        for index in range(len(parts), 0, -1):
            wildcard = ".".join(parts[:index]) + ".*"

            if wildcard in self.scopes:
                return True

        return False


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class ApiKeyRepository(Protocol):
    """
    Persistence boundary.

    Implement with SQLAlchemy, Mongo, etc.

    A UNIQUE constraint on secret_hash is strongly recommended.
    """

    async def get_by_id(
        self,
        key_id: str,
    ) -> ApiKeyRecord | None:
        ...

    async def get_by_hash(
        self,
        secret_hash: str,
    ) -> ApiKeyRecord | None:
        ...

    async def create(
        self,
        record: ApiKeyRecord,
    ) -> ApiKeyRecord:
        ...

    async def revoke(
        self,
        key_id: str,
        *,
        reason: str | None = None,
    ) -> bool:
        ...

    async def list_for_owner(
        self,
        owner_id: str,
        *,
        org_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[ApiKeyRecord]:
        ...

    async def revoke_all_for_owner(
        self,
        owner_id: str,
        *,
        reason: str | None = None,
    ) -> int:
        ...

    async def update_last_used(
        self,
        key_id: str,
        *,
        used_at: datetime,
    ) -> None:
        ...


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ApiKeyLifecycleService:
    """
    Complete API-key lifecycle.

    The service owns policy.
    The repository owns persistence.
    """

    def __init__(
        self,
        repository: ApiKeyRepository,
        *,
        can_authenticate: Callable[[str], Awaitable[bool]] | None = None,
    ) -> None:
        self._repository = repository
        self._can_authenticate = can_authenticate

    async def create(
        self,
        name: str,
        *,
        owner_id: str,
        org_id: str | None = None,
        scopes: set[str] | frozenset[str] | None = None,
        expires_in_s: int | None = None,
        ip_allowlist: Sequence[str] | None = None,
        metadata: dict[str, Any] | None = None,
        environment: str = "live",
        rotated_from: str | None = None,
    ) -> tuple[str, ApiKeyRecord]:
        """
        Create an API key.

        Returns:

            plaintext_key
            safe ApiKeyRecord

        The plaintext key must be shown to the caller exactly once.
        """

        self._validate_environment(environment)

        if not owner_id:
            raise ValueError("owner_id is required")

        if expires_in_s is not None and expires_in_s <= 0:
            raise ValueError(
                "expires_in_s must be greater than zero",
            )

        networks = self._normalize_ip_allowlist(
            ip_allowlist or (),
        )

        key_id = new_id("key")

        secret = secrets.token_urlsafe(32)

        plaintext = (
            f"nk_{environment}_{key_id}_{secret}"
        )

        secret_hash = self._hash_secret(
            plaintext,
        )

        now = datetime.now(UTC)

        expires_at = (
            datetime.fromtimestamp(
                now.timestamp() + expires_in_s,
                tz=UTC,
            )
            if expires_in_s is not None
            else None
        )

        record = ApiKeyRecord(
            key_id=key_id,
            name=name.strip(),
            secret_hash=secret_hash,
            owner_id=owner_id,
            org_id=org_id,
            environment=environment,
            scopes=frozenset(
                scopes or {"read"},
            ),
            created_at=now,
            expires_at=expires_at,
            rotated_from=rotated_from,
            ip_allowlist=tuple(networks),
            metadata=dict(metadata or {}),
        )

        created = await self._repository.create(
            record,
        )

        return plaintext, created

    async def authenticate(
        self,
        plaintext: str,
        *,
        client_ip: str | None = None,
        required_scope: str | None = None,
    ) -> ApiKeyRecord:
        """
        Authenticate an API key.

        This is the central enforcement point.
        """

        key_id, secret = self._parse_key(
            plaintext,
        )

        if not key_id or not secret:
            raise ApiKeyInvalidError()

        record = await self._repository.get_by_id(
            key_id,
        )

        if record is None:
            raise ApiKeyInvalidError()

        expected_hash = self._hash_secret(
            plaintext,
        )

        if not hmac.compare_digest(
            expected_hash,
            record.secret_hash,
        ):
            raise ApiKeyInvalidError()

        if not record.is_active:
            raise ApiKeyInvalidError()

        if self._can_authenticate is not None:
            if not await self._can_authenticate(record.owner_id):
                raise ApiKeyInvalidError()

        if client_ip is not None:
            if not self._ip_allowed(
                client_ip,
                record.ip_allowlist,
            ):
                raise ApiKeyIpRestrictedError()

        if required_scope is not None:
            if not record.has_scope(
                required_scope,
            ):
                raise ApiKeyScopeError(
                    required_scope,
                )

        # last_used_at should ideally be buffered rather than
        # synchronously persisted on every request.
        now = datetime.now(UTC)

        await self._repository.update_last_used(
            record.key_id,
            used_at=now,
        )

        return record

    async def revoke(
        self,
        key_id: str,
        *,
        reason: str | None = None,
    ) -> bool:
        record = await self._repository.get_by_id(
            key_id,
        )

        if record is None:
            raise ApiKeyNotFoundError()

        if record.is_revoked:
            raise ApiKeyAlreadyRevokedError()

        return await self._repository.revoke(
            key_id,
            reason=reason,
        )

    async def rotate(
        self,
        plaintext: str,
        *,
        grace_period_s: int = 0,
    ) -> tuple[str, ApiKeyRecord] | None:
        """
        Rotate a key.

        Default behavior:

            old key -> immediately revoked
            new key -> active

        grace_period_s may be used when a migration window is needed.

        NOTE:
            A grace period requires an explicit scheduled revocation
            mechanism. This implementation only performs immediate
            revocation.
        """

        if grace_period_s != 0:
            raise ValueError(
                "grace-period rotation requires scheduled revocation",
            )

        old = await self.authenticate(
            plaintext,
        )

        new_plaintext, new_record = await self.create(
            old.name,
            owner_id=old.owner_id,
            org_id=old.org_id,
            scopes=set(old.scopes),
            expires_in_s=self._remaining_ttl(
                old.expires_at,
            ),
            ip_allowlist=old.ip_allowlist,
            metadata={
                **old.metadata,
                "rotated_from": old.key_id,
            },
            environment=old.environment,
            rotated_from=old.key_id,
        )

        await self._repository.revoke(
            old.key_id,
            reason="rotated",
        )

        return new_plaintext, new_record

    async def revoke_all_for_owner(
        self,
        owner_id: str,
        *,
        reason: str = "account_deactivated",
    ) -> int:
        """
        Used by account lifecycle cascades.
        """

        return await self._repository.revoke_all_for_owner(
            owner_id,
            reason=reason,
        )

    async def list_for_owner(
        self,
        owner_id: str,
        *,
        org_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[ApiKeyRecord]:
        return await self._repository.list_for_owner(
            owner_id,
            org_id=org_id,
            include_revoked=include_revoked,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_secret(
        plaintext: str,
    ) -> str:
        """
        Deterministic SHA-256 digest for indexed lookup.

        Because the API-key secret has high entropy, a cryptographic
        digest is appropriate here. Do not use this pattern for
        human passwords.
        """

        return hashlib.sha256(
            plaintext.encode("utf-8"),
        ).hexdigest()

    @staticmethod
    def _parse_key(
        plaintext: str,
    ) -> tuple[str, str]:
        """
        Parse:

            nk_live_key_<hex>_<secret>

        key_id from new_id("key") contains an underscore (key_<hex>),
        so a fixed split("_", 3) would truncate key_id to "key".
        """

        match = _PLAINTEXT_KEY_RE.fullmatch(plaintext)

        if match is None:
            return "", ""

        key_id = match.group(2)
        secret = match.group(3)

        if not key_id or not secret:
            return "", ""

        return key_id, secret

    @staticmethod
    def _normalize_ip_allowlist(
        values: Sequence[str],
    ) -> list[str]:
        normalized: list[str] = []

        for value in values:
            network = ipaddress.ip_network(
                value.strip(),
                strict=False,
            )

            normalized.append(
                str(network),
            )

        return normalized

    @staticmethod
    def _ip_allowed(
        client_ip: str,
        allowlist: Sequence[str],
    ) -> bool:
        if not allowlist:
            return True

        try:
            address = ipaddress.ip_address(
                client_ip,
            )
        except ValueError:
            return False

        for network_value in allowlist:
            try:
                network = ipaddress.ip_network(
                    network_value,
                    strict=False,
                )
            except ValueError:
                continue

            if address in network:
                return True

        return False

    @staticmethod
    def _remaining_ttl(
        expires_at: datetime | None,
    ) -> int | None:
        if expires_at is None:
            return None

        remaining = (
            expires_at - datetime.now(UTC)
        ).total_seconds()

        if remaining <= 0:
            return None

        return max(1, int(remaining))

    @staticmethod
    def _validate_environment(
        environment: str,
    ) -> None:
        if environment not in {
            "live",
            "test",
        }:
            raise ValueError(
                "environment must be 'live' or 'test'",
            )


__all__ = [
    "ApiKeyAlreadyRevokedError",
    "ApiKeyError",
    "ApiKeyInvalidError",
    "ApiKeyIpRestrictedError",
    "ApiKeyLifecycleService",
    "ApiKeyNotFoundError",
    "ApiKeyOwnershipError",
    "ApiKeyRecord",
    "ApiKeyRepository",
    "ApiKeyScopeError",
]
