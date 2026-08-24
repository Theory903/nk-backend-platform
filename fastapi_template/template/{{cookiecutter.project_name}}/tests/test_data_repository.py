import pytest

from {{cookiecutter.project_name}}.data.models import Record

{%- if cookiecutter.orm == "sqlalchemy" %}
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.repository import (
    SqlalchemyRepository,
)
from {{cookiecutter.project_name}}.db.meta import meta
from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.persistence import RecordRow

{%- elif cookiecutter.orm == "beanie" %}
from {{cookiecutter.project_name}}.data.adapters.mongo.documents import RecordDocument
from {{cookiecutter.project_name}}.data.adapters.mongo.repository import BeanieRepository

{%- endif %}


{%- if cookiecutter.orm == "sqlalchemy" %}
@pytest.fixture
async def repository():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(meta.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    session = maker()
    try:
        yield SqlalchemyRepository(session)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()

{%- elif cookiecutter.orm == "beanie" %}
@pytest.fixture(autouse=True)
async def clean_records():
    await RecordDocument.find_all().delete()
    yield
    await RecordDocument.find_all().delete()


@pytest.fixture
async def repository():
    yield BeanieRepository()

{%- endif %}


async def test_create_and_get_roundtrip(repository) -> None:
    created = await repository.create(Record(name="alpha"))
    fetched = await repository.get(created.id)

    assert fetched is not None
    assert fetched.name == "alpha"
    assert fetched.id == created.id


async def test_get_missing_returns_none(repository) -> None:
    assert await repository.get("nope") is None


async def test_list_paginates_in_order(repository) -> None:
    names = ["a", "b", "c"]
    for name in names:
        await repository.create(Record(name=name))

    page = await repository.list(limit=2, offset=1)

    assert [item.name for item in page] == ["b", "c"]


async def test_count_reflects_creates_and_deletes(repository) -> None:
    first = await repository.create(Record(name="x"))
    await repository.create(Record(name="y"))
    assert await repository.count() == 2

    await repository.delete(first.id)

    assert await repository.count() == 1


async def test_update_replaces_existing(repository) -> None:
    created = await repository.create(Record(name="before"))

    updated = await repository.update(Record(id=created.id, name="after"))

    assert updated.name == "after"
    fetched = await repository.get(created.id)
    assert fetched.name == "after"


async def test_update_missing_raises_key_error(repository) -> None:
    with pytest.raises(KeyError):
        await repository.update(Record(id="ghost", name="?"))


async def test_delete_returns_true_then_false(repository) -> None:
    created = await repository.create(Record(name="doomed"))

    assert await repository.delete(created.id) is True
    assert await repository.delete(created.id) is False
    assert await repository.get(created.id) is None


{%- if cookiecutter.orm == "sqlalchemy" %}
async def test_unit_of_work_commit_persists() -> None:
    from sqlalchemy import select

    from {{cookiecutter.project_name}}.core.time import utcnow
    from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.persistence import (
        RecordRow,
    )
    from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.unit_of_work import (
        SqlalchemyUnitOfWork,
    )

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(meta.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with SqlalchemyUnitOfWork(maker) as unit_of_work:
        unit_of_work.session.add(
            RecordRow(id="rec_keep", name="kept", created_at=utcnow()),
        )
        await unit_of_work.commit()

    reader = maker()
    rows = (await reader.execute(select(RecordRow))).scalars().fetchall()
    await reader.close()
    await engine.dispose()

    assert [row.id for row in rows] == ["rec_keep"]


async def test_unit_of_work_rollback_discards() -> None:
    from sqlalchemy import select

    from {{cookiecutter.project_name}}.core.time import utcnow
    from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.persistence import (
        RecordRow,
    )
    from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.unit_of_work import (
        SqlalchemyUnitOfWork,
    )

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(meta.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with SqlalchemyUnitOfWork(maker) as unit_of_work:
        unit_of_work.session.add(
            RecordRow(id="rec_gone", name="dropped", created_at=utcnow()),
        )
        await unit_of_work.rollback()

    reader = maker()
    rows = (await reader.execute(select(RecordRow))).scalars().fetchall()
    await reader.close()
    await engine.dispose()

    assert rows == []
{%- endif %}
