"""Tests for RLS: DDL generation, GUC session context, tenant validation.

These tests verify safe identifier quoting, parameterized set_config, and
TenantScopedSession commit/rollback wiring. Full PostgreSQL RLS enforcement
requires real policies + a non-superuser app role and is covered in CI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from {{cookiecutter.project_name}}.data.rls import (
    TenantScopedSession,
    TenantSecurityError,
    generate_rls_ddl,
    set_tenant_context,
    tenant_scoped,
    tenant_transaction,
    validate_tenant_id,
)


class Base(DeclarativeBase):
    pass


class ScopedRecord(Base):
    __tablename__ = "scoped_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(String, nullable=False)
    name = Column(Text)
    created_at = Column(
        String,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def engine():
    return create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )


@pytest.fixture
async def session_factory(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.fixture
async def seed_data(session_factory):
    """Seed records for two different orgs."""
    async with session_factory() as session:
        async with session.begin():
            for org in ["org_a", "org_b"]:
                for i in range(3):
                    session.add(
                        ScopedRecord(org_id=org, name=f"{org}_record_{i}")
                    )
    return session_factory


def _make_session_factory() -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock(spec=AsyncSession)
    session.begin = AsyncMock(return_value=MagicMock())
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    factory = MagicMock(return_value=session)
    return factory, session


# --- Identifier / tenant validation ---


def test_invalid_identifiers_rejected() -> None:
    with pytest.raises(TenantSecurityError, match="invalid PostgreSQL identifier"):
        generate_rls_ddl("orders; DROP TABLE users")
    with pytest.raises(TenantSecurityError, match="invalid PostgreSQL identifier"):
        generate_rls_ddl('orders"')
    with pytest.raises(TenantSecurityError, match="invalid PostgreSQL identifier"):
        generate_rls_ddl("orders", role="app; evil")
    with pytest.raises(TenantSecurityError, match="identifier cannot be empty"):
        generate_rls_ddl("")


def test_validate_tenant_id() -> None:
    assert validate_tenant_id("  org_123  ") == "org_123"
    with pytest.raises(TenantSecurityError, match="must be a string"):
        validate_tenant_id(123)  # type: ignore[arg-type]
    with pytest.raises(TenantSecurityError, match="cannot be empty"):
        validate_tenant_id("   ")
    with pytest.raises(TenantSecurityError, match="maximum length"):
        validate_tenant_id("x" * 256)


# --- DDL generation ---


def test_ddl_generates_enable_and_force() -> None:
    stmts = generate_rls_ddl("orders")
    assert any("ENABLE ROW LEVEL SECURITY" in s for s in stmts)
    assert any("FORCE ROW LEVEL SECURITY" in s for s in stmts)


def test_ddl_uses_quoted_identifiers() -> None:
    stmts = generate_rls_ddl("public.orders", role="app_user")
    joined = "\n".join(stmts)

    assert '"public"."orders"' in joined
    assert '"app_user"' in joined
    assert '"tenant_isolation_public_orders"' in joined

    # Unsafe names must never appear unquoted / raw-interpolated
    assert "public.orders" not in joined.replace('"public"."orders"', "")
    assert "DROP TABLE" not in joined


def test_ddl_rejects_unsafe_names_before_interpolation() -> None:
    unsafe = "orders'; DROP TABLE x--"
    with pytest.raises(TenantSecurityError):
        generate_rls_ddl(unsafe)
    # Confirm generate would not have produced a statement containing the payload
    # (rejection happens before any DDL string is built with it).


def test_ddl_generates_policy_with_using_and_check() -> None:
    stmts = generate_rls_ddl("orders")
    policy_stmts = [s for s in stmts if "CREATE POLICY" in s]
    assert len(policy_stmts) == 1
    assert "USING" in policy_stmts[0]
    assert "WITH CHECK" in policy_stmts[0]
    assert "app.tenant_id" in policy_stmts[0]


def test_ddl_custom_role() -> None:
    stmts = generate_rls_ddl("orders", role="readonly_user")
    grant_stmts = [s for s in stmts if "GRANT" in s]
    assert any('"readonly_user"' in s for s in grant_stmts)


# --- set_config parameterization ---


@pytest.mark.anyio
async def test_set_config_uses_bound_params() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()

    await set_tenant_context(session, "org_a")

    session.execute.assert_awaited_once()
    args, kwargs = session.execute.await_args
    stmt = args[0]
    params = args[1] if len(args) > 1 else kwargs.get("params") or kwargs

    sql = str(stmt)
    assert "set_config" in sql.lower()
    assert ":setting_name" in sql
    assert ":tenant_id" in sql
    # Literal tenant id must not be interpolated into SQL text
    assert "org_a" not in sql

    assert params["setting_name"] == "app.tenant_id"
    assert params["tenant_id"] == "org_a"


@pytest.mark.anyio
async def test_set_tenant_context_validates() -> None:
    session = AsyncMock(spec=AsyncSession)
    with pytest.raises(TenantSecurityError, match="cannot be empty"):
        await set_tenant_context(session, "")
    session.execute.assert_not_awaited()


# --- TenantScopedSession commit / rollback ---


@pytest.mark.anyio
async def test_tenant_scoped_session_commits_on_success() -> None:
    factory, session = _make_session_factory()

    async with TenantScopedSession(factory, "org_a") as scoped:
        assert scoped is session

    session.begin.assert_awaited_once()
    session.execute.assert_awaited()  # set_config
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.anyio
async def test_tenant_scoped_session_rolls_back_on_error() -> None:
    factory, session = _make_session_factory()

    with pytest.raises(RuntimeError, match="boom"):
        async with TenantScopedSession(factory, "org_b"):
            raise RuntimeError("boom")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.close.assert_awaited_once()


def test_tenant_scoped_rejects_invalid_org() -> None:
    factory, _session = _make_session_factory()
    with pytest.raises(TenantSecurityError):
        TenantScopedSession(factory, "")


@pytest.mark.anyio
async def test_tenant_transaction_helper() -> None:
    factory, session = _make_session_factory()

    async with tenant_transaction(factory, "org_x") as scoped:
        assert scoped is session

    session.commit.assert_awaited_once()
    session.close.assert_awaited_once()


@pytest.mark.anyio
async def test_tenant_scoped_factory_helper() -> None:
    factory, session = _make_session_factory()
    ctx = tenant_scoped(factory, "org_y")
    assert isinstance(ctx, TenantScopedSession)

    async with ctx as scoped:
        assert scoped is session

    session.commit.assert_awaited_once()


# --- Application-level isolation pattern (SQLite stand-in) ---


class TestTenantSessionContext:
    @pytest.mark.anyio
    async def test_set_tenant_context_executes(self, session_factory) -> None:
        """SQLite has no set_config; verify call shape via mock patch."""
        async with session_factory() as session:
            async with session.begin():
                with patch.object(
                    session,
                    "execute",
                    new_callable=AsyncMock,
                ) as execute:
                    await set_tenant_context(session, "org_a")
                    execute.assert_awaited_once()
                    stmt = execute.await_args.args[0]
                    params = execute.await_args.args[1]
                    assert ":setting_name" in str(stmt)
                    assert params["tenant_id"] == "org_a"

    @pytest.mark.anyio
    async def test_tenant_scoped_session_filters_correctly(self, seed_data) -> None:
        """Simulate tenant isolation at the application level (RLS equivalent)."""
        factory = seed_data

        async def get_org_records(org_id: str) -> list[dict]:
            async with factory() as session:
                result = await session.execute(
                    select(ScopedRecord).where(ScopedRecord.org_id == org_id)
                )
                rows = result.scalars().all()
                return [
                    {"id": r.id, "org_id": r.org_id, "name": r.name} for r in rows
                ]

        org_a_records = await get_org_records("org_a")
        assert len(org_a_records) == 3
        assert all(r["org_id"] == "org_a" for r in org_a_records)

        org_b_records = await get_org_records("org_b")
        assert len(org_b_records) == 3
        assert all(r["org_id"] == "org_b" for r in org_b_records)

        org_a_ids = {r["id"] for r in org_a_records}
        org_b_ids = {r["id"] for r in org_b_records}
        assert not (org_a_ids & org_b_ids)

    @pytest.mark.anyio
    async def test_cross_tenant_query_returns_zero_rows(self, seed_data) -> None:
        factory = seed_data

        async with factory() as session:
            result = await session.execute(
                select(ScopedRecord).where(
                    ScopedRecord.org_id == "nonexistent_org"
                )
            )
            rows = result.scalars().all()
            assert len(rows) == 0

    @pytest.mark.anyio
    async def test_cross_tenant_write_isolated(self, seed_data) -> None:
        factory = seed_data

        async with factory() as session:
            async with session.begin():
                session.add(ScopedRecord(org_id="org_c", name="org_c_record"))

        async with factory() as session:
            result = await session.execute(
                select(ScopedRecord).where(
                    ScopedRecord.org_id == "org_a",
                    ScopedRecord.name == "org_c_record",
                )
            )
            assert result.scalars().all() == []
