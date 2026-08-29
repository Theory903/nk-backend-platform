"""Tests for emit() one-liner: outbox write, relay, backlog count."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from {{cookiecutter.project_name}}.core.event_emitter import (
    EventEmitError,
    count_pending,
    emit,
)


@pytest.fixture
async def db():
    from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.outbox import OutboxRow  # noqa: F401
    from {{cookiecutter.project_name}}.db.meta import meta

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(meta.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


class TestEmit:
    @pytest.mark.asyncio
    async def test_emit_writes_outbox_row(self, db) -> None:
        from sqlalchemy import select

        from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.outbox import OutboxRow

        async with db() as session:
            async with session.begin():
                envelope = await emit(
                    "order.created",
                    "/orders",
                    {"id": "ord_1"},
                    session=session,
                )
            assert envelope.id  # auto-generated ID
            assert envelope.type == "order.created"

            # Verify the outbox row exists and is unpublished
            result = await session.execute(select(OutboxRow))
            rows = result.scalars().all()
            assert len(rows) == 1
            assert rows[0].published_at is None

    @pytest.mark.asyncio
    async def test_emit_multiple_events_same_session(self, db) -> None:
        from sqlalchemy import select

        from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.outbox import OutboxRow

        async with db() as session:
            async with session.begin():
                await emit("a.created", "/a", {"id": "1"}, session=session)
                await emit("b.updated", "/b", {"id": "2"}, session=session)
                await emit("c.deleted", "/c", {"id": "3"}, session=session)

        async with db() as session:
            result = await session.execute(select(OutboxRow).order_by(OutboxRow.type))
            rows = result.scalars().all()
            assert len(rows) == 3
            types = [r.type for r in rows]
            assert types == ["a.created", "b.updated", "c.deleted"]

    @pytest.mark.asyncio
    async def test_emit_requires_active_transaction(self, db) -> None:
        async with db() as session:
            with pytest.raises(EventEmitError, match="active database transaction"):
                await emit(
                    "order.created",
                    "/orders",
                    {"id": "ord_1"},
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_emit_rejects_empty_event_type(self, db) -> None:
        async with db() as session:
            async with session.begin():
                with pytest.raises(ValueError, match="event_type"):
                    await emit("  ", "/orders", {}, session=session)

    @pytest.mark.asyncio
    async def test_emit_rejects_empty_source(self, db) -> None:
        async with db() as session:
            async with session.begin():
                with pytest.raises(ValueError, match="source"):
                    await emit("order.created", "   ", {}, session=session)


class TestBacklogCount:
    @pytest.mark.asyncio
    async def test_count_pending_returns_unpublished(self, db) -> None:
        from sqlalchemy import select

        from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.outbox import OutboxRow

        async with db() as session:
            async with session.begin():
                await emit("evt.one", "/one", {}, session=session)
                await emit("evt.two", "/two", {}, session=session)

            pending = await count_pending(session)
            assert pending == 2

            # count_pending() may autobegin; commit before starting a new txn
            await session.commit()

            async with session.begin():
                result = await session.execute(
                    select(OutboxRow).where(OutboxRow.type == "evt.one")
                )
                row = result.scalars().first()
                row.published_at = row.created_at  # mark published

            pending_after = await count_pending(session)
            assert pending_after == 1


class TestRelayIntegration:
    @pytest.mark.asyncio
    async def test_relay_publishes_emitted_events(self, db) -> None:
        from sqlalchemy import select

        from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.outbox import (
            OutboxRelay,
            OutboxRow,
        )

        published: list[dict] = []

        async def sink(payload: dict) -> None:
            published.append(payload)

        async with db() as session:
            async with session.begin():
                await emit(
                    "relay.test",
                    "/test",
                    {"key": "value"},
                    session=session,
                )

        # Relay picks it up
        relay = OutboxRelay(db, publish=sink, batch_size=10)
        handled = await relay.poll_once()
        assert handled >= 1
        assert len(published) == 1
        assert published[0]["type"] == "relay.test"

        # Verify marked as published (no loss on restart)
        async with db() as session:
            result = await session.execute(
                select(OutboxRow).where(OutboxRow.published_at.isnot(None))
            )
            assert len(result.scalars().all()) == 1
