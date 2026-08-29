"""PostgreSQL Row-Level Security tenant isolation.

Provides:

- Safe RLS DDL generation
- FORCE RLS
- tenant_id transaction-local GUC
- INSERT/UPDATE isolation through WITH CHECK
- SELECT/UPDATE/DELETE isolation through USING
- schema-qualified identifiers
- idempotent policy creation
- tenant context validation
- async transaction-scoped tenant sessions

The database remains the final security boundary. Application-level
tenant filters are defense-in-depth, not a replacement for RLS.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = [
    "TenantSecurityError",
    "TenantScopedSession",
    "clear_tenant_context",
    "generate_rls_ddl",
    "get_tenant_context",
    "require_tenant_context",
    "set_tenant_context",
    "tenant_scoped",
    "tenant_transaction",
    "validate_tenant_id",
]

_TENANT_GUC = "app.tenant_id"
_POLICY_PREFIX = "tenant_isolation"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TenantSecurityError(ValueError):
    """Raised when tenant context or RLS configuration is invalid."""


def _quote_identifier(identifier: str) -> str:
    """Safely quote a PostgreSQL identifier."""
    if not identifier:
        raise TenantSecurityError("identifier cannot be empty")

    parts = identifier.split(".")

    if any(not _IDENTIFIER_RE.fullmatch(part) for part in parts):
        raise TenantSecurityError(
            f"invalid PostgreSQL identifier: {identifier!r}"
        )

    return ".".join(f'"{part}"' for part in parts)


def _policy_name(table_name: str) -> str:
    """Create a deterministic policy name."""
    raw = table_name.replace(".", "_")

    if not _IDENTIFIER_RE.fullmatch(raw):
        raise TenantSecurityError(
            f"invalid table name: {table_name!r}"
        )

    return f"{_POLICY_PREFIX}_{raw}"


def generate_rls_ddl(
    table_name: str,
    *,
    role: str = "app_user",
) -> list[str]:
    """
    Generate PostgreSQL RLS migration statements.

    The target table must contain:

        org_id TEXT NOT NULL

    The policy enforces:

        SELECT  -> tenant rows only
        INSERT  -> tenant rows only
        UPDATE  -> old and new rows must belong to tenant
        DELETE  -> tenant rows only
    """
    table = _quote_identifier(table_name)
    quoted_role = _quote_identifier(role)
    policy = _quote_identifier(_policy_name(table_name))

    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        (
            f"DROP POLICY IF EXISTS {policy} ON {table}"
        ),
        (
            f"""
            CREATE POLICY {policy}
            ON {table}
            TO {quoted_role}
            USING (
                org_id = current_setting('{_TENANT_GUC}', true)
            )
            WITH CHECK (
                org_id = current_setting('{_TENANT_GUC}', true)
            )
            """.strip()
        ),
        (
            f"GRANT SELECT, INSERT, UPDATE, DELETE "
            f"ON {table} TO {quoted_role}"
        ),
    ]


def validate_tenant_id(org_id: str) -> str:
    """
    Validate and normalize a tenant identifier before putting it into
    the PostgreSQL session context.
    """
    if not isinstance(org_id, str):
        raise TenantSecurityError("tenant id must be a string")

    value = org_id.strip()

    if not value:
        raise TenantSecurityError("tenant id cannot be empty")

    if len(value) > 255:
        raise TenantSecurityError(
            "tenant id exceeds maximum length of 255 characters"
        )

    return value


async def set_tenant_context(
    session: AsyncSession,
    org_id: str,
) -> None:
    """
    Set the tenant context for the current transaction.

    `SET LOCAL` semantics are achieved through set_config(..., true),
    so the value disappears automatically at transaction end.
    """
    tenant_id = validate_tenant_id(org_id)

    await session.execute(
        text(
            "SELECT set_config(:setting_name, :tenant_id, true)"
        ),
        {
            "setting_name": _TENANT_GUC,
            "tenant_id": tenant_id,
        },
    )


async def get_tenant_context(
    session: AsyncSession,
) -> str | None:
    """Return the current transaction-local tenant context."""
    result = await session.execute(
        text(
            "SELECT current_setting(:setting_name, true)"
        ),
        {
            "setting_name": _TENANT_GUC,
        },
    )

    value = result.scalar_one_or_none()

    if not value:
        return None

    return str(value)


async def require_tenant_context(
    session: AsyncSession,
) -> str:
    """Return the active tenant or fail closed."""
    tenant_id = await get_tenant_context(session)

    if not tenant_id:
        raise TenantSecurityError(
            "tenant context is not configured for this transaction"
        )

    return tenant_id


async def clear_tenant_context(
    session: AsyncSession,
) -> None:
    """
    Explicitly clear the tenant context.

    Normally unnecessary because the context is transaction-local.
    """
    await session.execute(
        text(
            "SELECT set_config(:setting_name, '', true)"
        ),
        {
            "setting_name": _TENANT_GUC,
        },
    )


@dataclass
class TenantScopedSession:
    """
    Transaction-scoped PostgreSQL session with mandatory tenant context.

    Example:

        async with tenant_scoped(factory, "org_123") as session:
            result = await session.execute(...)
    """

    session_factory: async_sessionmaker[AsyncSession]
    org_id: str

    def __post_init__(self) -> None:
        self.org_id = validate_tenant_id(self.org_id)
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        session = self.session_factory()

        try:
            await session.begin()
            await set_tenant_context(session, self.org_id)

            self._session = session

            return session

        except BaseException:
            await session.close()
            raise

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        session = self._session

        if session is None:
            return

        try:
            if exc_type is not None:
                await session.rollback()
            else:
                await session.commit()
        finally:
            await session.close()
            self._session = None


def tenant_scoped(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> TenantScopedSession:
    """Create a tenant-scoped transaction."""
    return TenantScopedSession(
        session_factory=session_factory,
        org_id=org_id,
    )


@asynccontextmanager
async def tenant_transaction(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """
    Convenience transaction context.

    Guarantees:

        session created
        → transaction started
        → tenant context installed
        → application work
        → commit/rollback
        → connection returned
    """
    async with tenant_scoped(
        session_factory,
        org_id,
    ) as session:
        yield session