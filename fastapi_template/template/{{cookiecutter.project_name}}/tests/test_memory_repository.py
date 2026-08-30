"""Contract checks for the generated development repository."""

import pytest

from {{cookiecutter.project_name}}.core.pagination import make_cursor
from {{cookiecutter.project_name}}.core.query import SortDirection, SortField
from {{cookiecutter.project_name}}.data.adapters.memory.repository import (
    InMemoryRepository,
)
from {{cookiecutter.project_name}}.data.models import Record
from {{cookiecutter.project_name}}.data.optimistic_lock import (
    ConcurrencyConflictError,
)


@pytest.mark.anyio
async def test_memory_repository_crud_and_soft_delete() -> None:
    repository = InMemoryRepository(Record)

    with pytest.raises(ValueError, match="server-assigned"):
        await repository.create({"id": "client_id", "name": "invalid"})

    created = await repository.create({"name": "first"})
    assert created.id is not None
    assert created.version == 1

    updated = await repository.update(
        str(created.id),
        {"name": "updated"},
        expected_version=1,
    )
    assert updated is not None
    assert updated.name == "updated"
    assert updated.version == 2

    with pytest.raises(ConcurrencyConflictError):
        await repository.update(
            str(created.id),
            {"name": "stale"},
            expected_version=1,
        )

    assert await repository.delete(str(created.id)) is True
    assert await repository.get(str(created.id)) is None
    assert await repository.restore(str(created.id)) is not None
    assert await repository.get(str(created.id)) is not None


@pytest.mark.anyio
async def test_memory_repository_scopes_records_by_organization() -> None:
    repository = InMemoryRepository(Record)
    tenant_a = repository.scoped("org_a")
    tenant_b = repository.scoped("org_b")

    created = await tenant_a.create({"name": "private"})
    assert await tenant_a.get(str(created.id)) is not None
    assert await tenant_b.get(str(created.id)) is None
    assert await tenant_b.list(limit=10) == []


@pytest.mark.anyio
async def test_memory_repository_scopes_records_by_principal() -> None:
    repository = InMemoryRepository(Record)
    principal_a = repository.scoped(None, scope_id="user:alice")
    principal_b = repository.scoped(None, scope_id="user:bob")

    created = await principal_a.create({"name": "private"})

    assert created.org_id is None
    assert await principal_a.get(str(created.id)) is not None
    assert await principal_b.get(str(created.id)) is None


@pytest.mark.anyio
async def test_memory_repository_cursor_handles_descending_ids() -> None:
    repository = InMemoryRepository(Record)
    await repository.bulk_create(
        [{"name": "one"}, {"name": "two"}, {"name": "three"}],
    )
    descending = [SortField("id", SortDirection.DESC)]

    first_page = await repository.list(limit=1, sort=descending)
    cursor = make_cursor(str(first_page[0].id), str(first_page[0].id))
    remaining = await repository.list(
        limit=10,
        cursor=cursor,
        sort=descending,
    )

    assert len(remaining) == 2
