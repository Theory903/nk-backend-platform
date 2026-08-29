import pytest

{%- if cookiecutter.orm == "sqlalchemy" %}
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from {{cookiecutter.project_name}}.core.events import EventEnvelope
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.outbox import (
    OutboxRelay,
    OutboxRow,
    cleanup_published,
    record_event,
)
from {{cookiecutter.project_name}}.db.meta import meta
{%- elif cookiecutter.orm == "beanie" %}
from {{cookiecutter.project_name}}.core.events import EventEnvelope
from {{cookiecutter.project_name}}.data.adapters.mongo.outbox import (
    OutboxDocument,
    OutboxRelay,
    record_event,
)
{%- endif %}


{%- if cookiecutter.orm == "sqlalchemy" %}
def make_session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)

    async def create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(meta.create_all)

    return engine, create_tables


@pytest.fixture
async def published():
    seen: list[dict] = []

    async def sink(payload: dict) -> None:
        seen.append(payload)

    engine, create_tables = make_session_factory()
    await create_tables()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield OutboxRelay(maker, publish=sink), seen, maker
    finally:
        await engine.dispose()

{%- elif cookiecutter.orm == "beanie" %}
@pytest.fixture(autouse=True)
async def clean_outbox():
    await OutboxDocument.find_all().delete()
    yield
    await OutboxDocument.find_all().delete()


@pytest.fixture
async def published():
    seen: list[dict] = []

    async def sink(payload: dict) -> None:
        seen.append(payload)

    relay = OutboxRelay(publish=sink)
    yield relay, seen

{%- endif %}


async def test_relay_publishes_pending_and_marks_done(published) -> None:
{%- if cookiecutter.orm == "sqlalchemy" %}
    relay, seen, maker = published
    async with maker() as session:
        await record_event(session, EventEnvelope(type="e1", source="/t", data={"n": 1}))
        await record_event(session, EventEnvelope(type="e2", source="/t", data={"n": 2}))
        await session.commit()
{%- elif cookiecutter.orm == "beanie" %}
    relay, seen = published
    await record_event(EventEnvelope(type="e1", source="/t", data={"n": 1}))
    await record_event(EventEnvelope(type="e2", source="/t", data={"n": 2}))
{%- endif %}

    handled = await relay.poll_once()
    assert handled == 2
    assert {item["type"] for item in seen} == {"e1", "e2"}

    again = await relay.poll_once()
    assert again == 0
    assert len(seen) == 2


async def test_unpublished_events_survive_relay_restart(published) -> None:
{%- if cookiecutter.orm == "sqlalchemy" %}
    relay, seen, maker = published
    async with maker() as session:
        await record_event(session, EventEnvelope(type="keep", source="/t", data={}))
        await session.commit()

    async def replay(payload: dict) -> None:
        seen.append(payload)

    fresh_relay = OutboxRelay(maker, publish=replay)
{%- elif cookiecutter.orm == "beanie" %}
    relay, seen = published
    await record_event(EventEnvelope(type="keep", source="/t", data={}))

    async def replay(payload: dict) -> None:
        seen.append(payload)

    fresh_relay = OutboxRelay(publish=replay)
{%- endif %}

    handled = await fresh_relay.poll_once()
    assert handled == 1
    assert seen[0]["type"] == "keep"


{%- if cookiecutter.orm == "sqlalchemy" %}
async def test_mid_batch_publish_failure_returns_zero(published) -> None:
    """Rolled-back published_at updates must not inflate the success count."""

    _relay, _seen, maker = published

    async with maker() as session:
        await record_event(session, EventEnvelope(type="ok", source="/t", data={"n": 1}))
        await record_event(session, EventEnvelope(type="boom", source="/t", data={"n": 2}))
        await session.commit()

    async def flaky(payload: dict) -> None:
        if payload["type"] == "boom":
            raise RuntimeError("broker unavailable")

    relay = OutboxRelay(maker, publish=flaky, batch_size=10)
    handled = await relay.poll_once()
    assert handled == 0

    async with maker() as session:
        pending = (
            await session.execute(
                select(OutboxRow).where(OutboxRow.published_at.is_(None))
            )
        ).scalars().all()
    assert len(pending) == 2


async def test_cleanup_removes_only_published(published) -> None:
    from datetime import timedelta

    _relay, _seen, maker = published
    async with maker() as session:
        await record_event(session, EventEnvelope(type="aged-out", source="/t", data={}))
        await record_event(session, EventEnvelope(type="fresh", source="/t", data={}))
        rows = (
            (await session.execute(select(OutboxRow).order_by(OutboxRow.created_at)))
            .scalars()
            .all()
        )
        rows[0].published_at = utcnow() - timedelta(days=8)
        rows[1].published_at = utcnow()
        await session.commit()

    removed = await cleanup_published(maker, older_than_days=7)

    assert removed == 1
    async with maker() as session:
        remaining = (
            (await session.execute(select(OutboxRow.type))).scalars().fetchall()
        )
    assert remaining == ["fresh"]
{%- endif %}
