import pytest

from {{cookiecutter.project_name}}.data.models import Record

{%- if cookiecutter.orm == "sqlalchemy" %}
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.repository import (
    SqlalchemyRepository,
)
from {{cookiecutter.project_name}}.db.meta import meta

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
    created = await repository.create({"name": "alpha"})
    fetched = await repository.get(created.id)

    assert fetched is not None
    assert fetched.name == "alpha"
    assert fetched.id == created.id


async def test_get_missing_returns_none(repository) -> None:
    assert await repository.get("nope") is None


async def test_list_cursor_paginates_in_order(repository) -> None:
    names = ["a", "b", "c"]
    created = []
    for name in names:
        created.append(await repository.create({"name": name}))

    page = await repository.list(limit=2)
    assert len(page) == 2

    cursor = None
    # Build cursor from last item of first page using created_at+id via service helper pattern
    from {{cookiecutter.project_name}}.core.pagination import make_cursor

    last = page[-1]
    cursor = make_cursor(str(last.created_at), str(last.id))
    page2 = await repository.list(limit=2, cursor=cursor)
    assert len(page2) >= 1
    assert page2[0].id not in {p.id for p in page}


async def test_count_reflects_creates_and_deletes(repository) -> None:
    first = await repository.create({"name": "x"})
    await repository.create({"name": "y"})
    assert await repository.count() == 2

    await repository.delete(first.id, soft=False)

    assert await repository.count() == 1


async def test_update_replaces_existing(repository) -> None:
    created = await repository.create({"name": "before"})

    updated = await repository.update(
        created.id,
        {"name": "after"},
        expected_version=created.version,
    )

    assert updated is not None
    assert updated.name == "after"
    fetched = await repository.get(created.id)
    assert fetched.name == "after"


async def test_update_missing_returns_none(repository) -> None:
    assert (
        await repository.update("ghost", {"name": "?"}, expected_version=1) is None
    )


async def test_soft_delete_and_restore(repository) -> None:
    created = await repository.create({"name": "doomed"})

    assert await repository.delete(created.id, soft=True) is True
    assert await repository.get(created.id) is None
    restored = await repository.restore(created.id)
    assert restored is not None
    assert restored.deleted_at is None
    assert await repository.get(created.id) is not None


async def test_delete_returns_true_then_false(repository) -> None:
    created = await repository.create({"name": "doomed"})

    assert await repository.delete(created.id, soft=False) is True
    assert await repository.delete(created.id, soft=False) is False
    assert await repository.get(created.id) is None


async def test_bulk_create_and_delete(repository) -> None:
    created = await repository.bulk_create(
        [{"name": "b1"}, {"name": "b2"}, {"name": "b3"}]
    )
    assert len(created) == 3
    deleted = await repository.bulk_delete([c.id for c in created], soft=False)
    assert deleted == 3
    assert await repository.count() == 0


{%- if cookiecutter.orm == "sqlalchemy" %}
async def test_writable_allow_list_rejects_unknown_fields(repository) -> None:
    with pytest.raises(ValueError, match="not writable"):
        await repository.create({"name": "ok", "version": 99})


async def test_filterable_allow_list_rejects_unknown_fields(repository) -> None:
    from {{cookiecutter.project_name}}.core.query import FilterClause, FilterOp

    await repository.create({"name": "alpha"})
    with pytest.raises(ValueError, match="not allowed"):
        await repository.list(
            limit=10,
            filters=[FilterClause(field="secret", op=FilterOp.EQ, value="x")],
        )


async def test_sortable_allow_list_rejects_unknown_fields(repository) -> None:
    from {{cookiecutter.project_name}}.core.query import SortDirection, SortField

    await repository.create({"name": "alpha"})
    with pytest.raises(ValueError, match="not allowed"):
        await repository.list(
            limit=10,
            sort=[SortField(field="secret", direction=SortDirection.ASC)],
        )


async def test_update_concurrency_conflict(repository) -> None:
    from {{cookiecutter.project_name}}.data.optimistic_lock import (
        ConcurrencyConflictError,
    )

    created = await repository.create({"name": "v1"})
    assert created.version == 1

    updated = await repository.update(
        created.id,
        {"name": "v2"},
        expected_version=1,
    )
    assert updated is not None
    assert updated.version == 2

    with pytest.raises(ConcurrencyConflictError):
        await repository.update(
            created.id,
            {"name": "stale"},
            expected_version=1,
        )


async def test_delete_concurrency_conflict(repository) -> None:
    from {{cookiecutter.project_name}}.data.optimistic_lock import (
        ConcurrencyConflictError,
    )

    created = await repository.create({"name": "doomed"})
    await repository.update(created.id, {"name": "touched"}, expected_version=1)

    with pytest.raises(ConcurrencyConflictError):
        await repository.delete(created.id, soft=True, expected_version=1)


async def test_count_is_uncapped_sql(repository) -> None:
    """count() uses SQL COUNT — no Python 10_000 materialization cap."""
    batch = [{"name": f"n{i:04d}"} for i in range(25)]
    await repository.bulk_create(batch)
    assert await repository.count() == 25


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
            RecordRow(id="rec_keep", name="kept", created_at=utcnow(), version=1),
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
            RecordRow(id="rec_gone", name="dropped", created_at=utcnow(), version=1),
        )
        await unit_of_work.rollback()

    reader = maker()
    rows = (await reader.execute(select(RecordRow))).scalars().fetchall()
    await reader.close()
    await engine.dispose()

    assert rows == []


async def test_record_row_from_domain_preserves_id() -> None:
    """Updates must not mint a new id when converting from domain."""
    from {{cookiecutter.project_name}}.core.time import utcnow
    from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.persistence import (
        RecordRow,
    )

    created_at = utcnow()
    record = Record(
        id="rec_alpha",
        name="alpha",
        created_at=created_at,
        deleted_at=None,
        version=3,
        org_id="org_1",
    )

    row = RecordRow.from_domain(record)

    assert row.id == "rec_alpha"
    assert row.name == "alpha"
    assert row.created_at == created_at
    assert row.deleted_at is None
    assert row.version == 3
    assert row.org_id == "org_1"

    domain = row.to_domain()
    assert domain.id == "rec_alpha"
    assert domain.name == "alpha"
    assert domain.created_at == created_at
    assert domain.deleted_at is None
    assert domain.version == 3
    assert domain.org_id == "org_1"


async def test_record_row_from_domain_defaults_when_optional_unset() -> None:
    from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.persistence import (
        RecordRow,
    )

    record = Record(name="beta")

    row = RecordRow.from_domain(record)

    assert row.id is not None
    assert row.id.startswith("rec_")
    assert row.name == "beta"
    assert row.created_at is not None
    assert row.deleted_at is None
    assert row.version == 1
    assert row.org_id is None
{%- endif %}

{%- if cookiecutter.orm == "beanie" %}
async def test_record_document_from_domain_preserves_id() -> None:
    """Updates must not mint a new Mongo _id when converting from domain."""
    from bson import ObjectId

    from {{cookiecutter.project_name}}.core.time import utcnow

    oid = str(ObjectId())
    created_at = utcnow()
    record = Record(
        id=oid,
        name="alpha",
        created_at=created_at,
        deleted_at=None,
        version=3,
        org_id="org_1",
    )

    document = RecordDocument.from_domain(record)

    assert str(document.id) == oid
    assert document.name == "alpha"
    assert document.created_at == created_at
    assert document.deleted_at is None
    assert document.version == 3
    assert document.org_id == "org_1"

    domain = document.to_domain()
    assert domain.id == oid
    assert domain.name == "alpha"
    assert domain.created_at == created_at
    assert domain.deleted_at is None
    assert domain.version == 3
    assert domain.org_id == "org_1"


async def test_record_document_from_domain_defaults_when_optional_unset() -> None:
    record = Record(name="beta")

    document = RecordDocument.from_domain(record)

    assert document.name == "beta"
    assert document.created_at is not None
    assert document.deleted_at is None
    assert document.version == 1
    assert document.org_id is None
{%- endif %}
