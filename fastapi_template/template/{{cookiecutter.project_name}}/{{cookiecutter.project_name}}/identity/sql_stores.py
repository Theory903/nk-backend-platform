"""SQL-backed authentication stores.

The stores intentionally use SQLAlchemy Core so they remain independent from
the generated application's business models and can be initialized before
request handling begins.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    JSON,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine

from {{cookiecutter.project_name}}.identity.api_keys import (
    ApiKeyRecord,
    ApiKeyStore,
)
from {{cookiecutter.project_name}}.identity.session import (
    Session,
    SessionStatus,
    SessionRevocationReason,
    SessionStore,
)
from {{cookiecutter.project_name}}.identity.tenant_context import Membership

metadata = MetaData()

auth_sessions = Table(
    "auth_session",
    metadata,
    Column("session_id", String(128), primary_key=True),
    Column("principal_id", String(255), nullable=False, index=True),
    Column("data", JSON, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("last_activity", Float, nullable=False),
    Column("expires_at", Float, nullable=False, index=True),
    Column("idle_expires_at", Float, nullable=False),
    Column("status", String(32), nullable=False),
    Column("rotated_from", String(128), nullable=True),
    Column("rotated_to", String(128), nullable=True),
    Column("revoked_at", Float, nullable=True),
    Column("revoked_reason", String(64), nullable=True),
    Column("user_agent", String(1024), nullable=False),
    Column("ip_address", String(128), nullable=False),
    Column("device_id", String(128), nullable=False),
)

auth_api_keys = Table(
    "auth_api_key",
    metadata,
    Column("key_id", String(128), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("digest", String(128), nullable=False, unique=True),
    Column("prefix", String(32), nullable=False),
    Column("owner_id", String(255), nullable=True, index=True),
    Column("org_id", String(255), nullable=True, index=True),
    Column("scopes", JSON, nullable=False),
    Column("ip_allowlist", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("last_used_at", DateTime(timezone=True), nullable=True),
    Column("metadata", JSON, nullable=False),
)

auth_memberships = Table(
    "auth_membership",
    metadata,
    Column("user_id", String(255), primary_key=True),
    Column("org_id", String(255), primary_key=True),
    Column("roles", JSON, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
)


def create_auth_engine(database_url: str) -> Engine:
    """Create the synchronous engine required by sync auth dependencies."""
    normalized = database_url
    normalized = normalized.replace("+asyncpg", "+psycopg2")
    normalized = normalized.replace("+aiosqlite", "")
    normalized = normalized.replace("+aiomysql", "+mysqldb")
    return create_engine(normalized, pool_pre_ping=True)


class SqlAlchemyApiKeyStore(ApiKeyStore):
    """Persist API-key digests and metadata in the application database."""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self._engine = engine

    def create(self, *args: Any, **kwargs: Any) -> tuple[str, ApiKeyRecord]:
        raw_key, record = super().create(*args, **kwargs)
        with self._engine.begin() as connection:
            connection.execute(
                insert(auth_api_keys).values(**self._encode(record)),
            )
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
        if not self._constant_time_equal(self._digest(raw_key), record.digest):
            return None
        last_used = datetime.now(UTC)
        with self._engine.begin() as connection:
            connection.execute(
                update(auth_api_keys)
                .where(auth_api_keys.c.key_id == key_id)
                .values(last_used_at=last_used),
            )
        record.last_used_at = last_used
        return record

    def get(self, key_id: str) -> ApiKeyRecord | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(auth_api_keys).where(auth_api_keys.c.key_id == key_id),
            ).mappings().first()
        return self._decode(dict(row)) if row else None

    def list(
        self,
        *,
        owner_id: str | None = None,
        org_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[ApiKeyRecord]:
        statement = select(auth_api_keys)
        if owner_id is not None:
            statement = statement.where(auth_api_keys.c.owner_id == owner_id)
        if org_id is not None:
            statement = statement.where(auth_api_keys.c.org_id == org_id)
        if not include_revoked:
            statement = statement.where(auth_api_keys.c.revoked_at.is_(None))
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [self._decode(dict(row)) for row in rows]

    def revoke_by_id(self, key_id: str) -> bool:
        record = self.get(key_id)
        if record is None or record.is_revoked:
            return False
        with self._engine.begin() as connection:
            connection.execute(
                update(auth_api_keys)
                .where(auth_api_keys.c.key_id == key_id)
                .values(revoked_at=datetime.now(UTC)),
            )
        return True

    def revoke_all_for_owner(self, owner_id: str) -> int:
        records = self.list(owner_id=owner_id)
        return sum(self.revoke_by_id(record.key_id) for record in records)

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
            "created_at": record.created_at,
            "expires_at": record.expires_at,
            "revoked_at": record.revoked_at,
            "last_used_at": record.last_used_at,
            "metadata": record.metadata,
        }

    @staticmethod
    def _decode(data: dict[str, Any]) -> ApiKeyRecord:
        return ApiKeyRecord(
            key_id=str(data["key_id"]),
            name=str(data["name"]),
            digest=str(data["digest"]),
            prefix=str(data.get("prefix", "nk")),
            owner_id=data.get("owner_id"),
            org_id=data.get("org_id"),
            scopes=frozenset(data.get("scopes") or ()),
            ip_allowlist=tuple(data.get("ip_allowlist") or ()),
            created_at=data.get("created_at") or datetime.now(UTC),
            expires_at=data.get("expires_at"),
            revoked_at=data.get("revoked_at"),
            last_used_at=data.get("last_used_at"),
            metadata=dict(data.get("metadata") or {}),
        )


class SqlAlchemySessionStore(SessionStore):
    """Persist opaque sessions in SQL for multi-instance deployments."""

    def __init__(self, engine: Engine, *, secret: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if not secret:
            raise ValueError("session digest secret is required")
        self._engine = engine
        self._secret = secret.encode("utf-8")

    def _digest(self, session_id: str) -> str:
        return hmac.new(
            self._secret,
            session_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _lookup_digest(self, session_id: str) -> str:
        # A digest is an internal storage key, never an accepted bearer
        # credential. Always hash values supplied at the API boundary.
        return self._digest(session_id)

    def create(
        self,
        principal_id: str,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        session_id = super().create(principal_id, data, **kwargs)
        session = super().get_session(session_id, touch=False)
        if session is not None:
            self._persist(session)
            self._enforce_durable_limit(principal_id)
        return session_id

    def get_session(self, session_id: str, *, touch: bool = True) -> Session | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(auth_sessions).where(
                    auth_sessions.c.session_id == self._lookup_digest(session_id),
                ),
            ).mappings().first()
        if not row:
            return None
        session = self._decode(
            dict(row),
            session_id=session_id,
        )
        now = time.time()
        if (
            not session.is_active
            or now >= session.expires_at
            or now >= session.idle_expires_at
        ):
            with self._engine.begin() as connection:
                connection.execute(
                    update(auth_sessions)
                    .where(
                        auth_sessions.c.session_id == self._lookup_digest(session_id),
                        auth_sessions.c.status == SessionStatus.ACTIVE.value,
                    )
                    .values(
                        status=SessionStatus.REVOKED.value,
                        revoked_at=now,
                        revoked_reason=SessionRevocationReason.EXPIRED.value,
                    ),
                )
            return None
        if touch:
            session.last_activity = now
            if self.idle_timeout_s is not None:
                session.idle_expires_at = min(
                    now + self.idle_timeout_s,
                    session.expires_at,
                )
            self._persist(session)
        return session

    def revoke(
        self,
        session_id: str,
        *,
        reason: SessionRevocationReason = SessionRevocationReason.LOGOUT,
    ) -> bool:
        session = self.get_session(session_id, touch=False)
        if session is None or not session.is_active:
            return False
        self._revoke(session, reason)
        self._persist(session)
        return True

    def rotate(
        self,
        session_id: str,
        *,
        user_agent: str = "",
        ip_address: str = "",
    ) -> str | None:
        digest = self._lookup_digest(session_id)
        with self._engine.begin() as connection:
            if self._engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "SELECT pg_advisory_xact_lock("
                        "hashtextextended(:session_digest, 0))",
                    ),
                    {"session_digest": digest},
                )
            row = connection.execute(
                select(auth_sessions)
                .where(auth_sessions.c.session_id == digest)
                .with_for_update(),
            ).mappings().first()
            if not row:
                return None
            old = self._decode(dict(row), session_id=session_id)
            if not old.is_active or time.time() >= old.expires_at:
                return None
            now = time.time()
            new_session_id = secrets.token_urlsafe(32)
            idle_expiry = (
                now + self.idle_timeout_s
                if self.idle_timeout_s is not None
                else old.expires_at
            )
            new_session = Session(
                session_id=new_session_id,
                principal_id=old.principal_id,
                data=dict(old.data),
                created_at=now,
                last_activity=now,
                expires_at=old.expires_at,
                idle_expires_at=min(idle_expiry, old.expires_at),
                rotated_from=digest,
                user_agent=user_agent or old.user_agent,
                ip_address=ip_address or old.ip_address,
                device_id=old.device_id,
            )
            old.rotated_to = self._lookup_digest(new_session_id)
            self._revoke(
                old,
                SessionRevocationReason.ROTATED,
                status=SessionStatus.ROTATED,
            )
            connection.execute(
                update(auth_sessions)
                .where(auth_sessions.c.session_id == digest)
                .values(**self._encode(old)),
            )
            connection.execute(
                insert(auth_sessions).values(**self._encode(new_session)),
            )
        return new_session_id

    def revoke_all_for_principal(
        self,
        principal_id: str,
        *,
        except_session: str | None = None,
        reason: SessionRevocationReason = SessionRevocationReason.ACCOUNT_DISABLED,
    ) -> int:
        statement = update(auth_sessions).where(
            auth_sessions.c.principal_id == principal_id,
            auth_sessions.c.status == SessionStatus.ACTIVE.value,
        )
        if except_session is not None:
            statement = statement.where(
                auth_sessions.c.session_id != self._lookup_digest(
                    except_session,
                ),
            )
        now = time.time()
        with self._engine.begin() as connection:
            result = connection.execute(
                statement.values(
                    status=SessionStatus.REVOKED.value,
                    revoked_at=now,
                    revoked_reason=reason.value,
                ),
            )
        return int(result.rowcount or 0)

    def list_for_principal(
        self,
        principal_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[Session]:
        statement = select(auth_sessions).where(
            auth_sessions.c.principal_id == principal_id,
        )
        if not include_inactive:
            statement = statement.where(
                auth_sessions.c.status == SessionStatus.ACTIVE.value,
            )
            now = time.time()
            statement = statement.where(
                auth_sessions.c.expires_at > now,
                auth_sessions.c.idle_expires_at > now,
            )
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            self._decode(
                dict(row),
                # Stored digests are not public session identifiers.
                session_id="",
            )
            for row in rows
        ]

    def _enforce_durable_limit(self, principal_id: str) -> None:
        with self._engine.begin() as connection:
            rows = connection.execute(
                select(auth_sessions)
                .where(
                    auth_sessions.c.principal_id == principal_id,
                    auth_sessions.c.status == SessionStatus.ACTIVE.value,
                )
                .order_by(
                    auth_sessions.c.last_activity,
                    auth_sessions.c.session_id,
                )
                .with_for_update(),
            ).mappings().all()
            for row in rows[: max(0, len(rows) - self.max_concurrent)]:
                connection.execute(
                    update(auth_sessions)
                    .where(auth_sessions.c.session_id == row["session_id"])
                    .values(
                        status=SessionStatus.REVOKED.value,
                        revoked_at=time.time(),
                        revoked_reason=SessionRevocationReason.CONCURRENT_LIMIT.value,
                    ),
                )

    def update_data(self, session_id: str, updates: dict[str, Any]) -> bool:
        session = self.get_session(session_id, touch=False)
        if session is None:
            return False
        session.data.update(updates)
        self._persist(session)
        return True

    def delete_data(self, session_id: str, *keys: str) -> bool:
        session = self.get_session(session_id, touch=False)
        if session is None:
            return False
        for key in keys:
            session.data.pop(key, None)
        self._persist(session)
        return True

    def _persist(self, session: Session) -> None:
        values = self._encode(session)
        with self._engine.begin() as connection:
            statement = update(auth_sessions).where(
                auth_sessions.c.session_id == self._lookup_digest(
                    session.session_id,
                ),
            )
            if session.is_active:
                # A stale read must never restore a row revoked or rotated
                # by another request.
                statement = statement.where(
                    auth_sessions.c.status == SessionStatus.ACTIVE.value,
                )
            connection.execute(statement.values(**values))
            if connection.execute(
                select(auth_sessions.c.session_id).where(
                    auth_sessions.c.session_id == self._lookup_digest(
                        session.session_id,
                    ),
                ),
            ).first() is None:
                connection.execute(insert(auth_sessions).values(**values))

    def _encode(self, session: Session) -> dict[str, Any]:
        return {
            "session_id": self._lookup_digest(session.session_id),
            "principal_id": session.principal_id,
            "data": json.loads(json.dumps(session.data)),
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "expires_at": session.expires_at,
            "idle_expires_at": session.idle_expires_at,
            "status": session.status.value,
            "rotated_from": session.rotated_from,
            "rotated_to": session.rotated_to,
            "revoked_at": session.revoked_at,
            "revoked_reason": (
                session.revoked_reason.value
                if session.revoked_reason
                else None
            ),
            "user_agent": session.user_agent,
            "ip_address": session.ip_address,
            "device_id": session.device_id,
        }

    @staticmethod
    def _decode(
        data: dict[str, Any],
        *,
        session_id: str,
    ) -> Session:
        return Session(
            session_id=session_id,
            principal_id=str(data["principal_id"]),
            data=dict(data.get("data") or {}),
            created_at=float(data.get("created_at", time.time())),
            last_activity=float(data.get("last_activity", time.time())),
            expires_at=float(data["expires_at"]),
            idle_expires_at=float(data["idle_expires_at"]),
            status=SessionStatus(str(data.get("status", "active"))),
            rotated_from=data.get("rotated_from"),
            rotated_to=data.get("rotated_to"),
            revoked_at=data.get("revoked_at"),
            revoked_reason=(
                SessionRevocationReason(str(data["revoked_reason"]))
                if data.get("revoked_reason")
                else None
            ),
            user_agent=str(data.get("user_agent", "")),
            ip_address=str(data.get("ip_address", "")),
            device_id=str(data.get("device_id", "")),
        )


class SqlAlchemyMembershipResolver:
    """Database-backed tenant membership resolver."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def get_membership(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> Membership | None:
        return await asyncio.to_thread(
            self._get_membership_sync,
            user_id=user_id,
            org_id=org_id,
        )

    def _get_membership_sync(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> Membership | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(auth_memberships).where(
                    auth_memberships.c.user_id == user_id,
                    auth_memberships.c.org_id == org_id,
                ),
            ).mappings().first()
        if not row or not row["active"]:
            return None
        return Membership(
            user_id=user_id,
            org_id=org_id,
            roles=frozenset(row.get("roles") or ()),
            active=True,
        )


__all__ = [
    "SqlAlchemyMembershipResolver",
    "SqlAlchemyApiKeyStore",
    "SqlAlchemySessionStore",
    "create_auth_engine",
]
