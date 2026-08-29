"""Tests for soft-delete: exclusion, restore, hard-delete, no over-fetch."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

import pytest

from {{cookiecutter.project_name}}.core.query import FilterClause, SortDirection, SortField
from {{cookiecutter.project_name}}.data.query_runtime import apply_cursor, apply_filters, apply_sort
from {{cookiecutter.project_name}}.data.soft_delete import (
    NotDeletedError,
    SoftDeleteMixin,
    SoftDeleteRepository,
)


@dataclass
class FakeRecord:
    id: str
    name: str
    deleted_at: datetime | None = None
    version: int = 1


class SoftDeleteEntity(SoftDeleteMixin):
    """Minimal mixin host for property tests."""

    def __init__(self, deleted_at: datetime | None = None) -> None:
        self.deleted_at = deleted_at


class FakeInnerRepo:
    """In-memory fake implementing the Repository protocol."""

    def __init__(self) -> None:
        self._store: dict[str, FakeRecord] = {}
        self._next_id = 0
        self.list_calls: list[dict[str, Any]] = []
        self.count_calls: list[dict[str, Any]] = []

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> Any:
        item = self._store.get(item_id)
        if item is None:
            return None
        if not include_deleted and item.deleted_at is not None:
            return None
        return replace(item)

    async def create(self, data: dict[str, Any]) -> FakeRecord:
        self._next_id += 1
        item = FakeRecord(
            id=f"rec_{self._next_id}",
            name=str(data.get("name", "")),
            deleted_at=data.get("deleted_at"),
            version=int(data.get("version", 1)),
        )
        self._store[item.id] = item
        return replace(item)

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> FakeRecord | None:
        item = self._store.get(item_id)
        if item is None:
            return None
        if item.version != expected_version:
            return None
        updated = replace(item)
        for key, value in data.items():
            if hasattr(updated, key):
                setattr(updated, key, value)
        updated.version = expected_version + 1
        self._store[item_id] = updated
        return replace(updated)

    async def delete(self, item_id: str, *, soft: bool = True) -> bool:
        if soft:
            item = self._store.get(item_id)
            if item is None or item.deleted_at is not None:
                return False
            self._store[item_id] = replace(item, deleted_at=datetime.now(timezone.utc))
            return True
        return self._store.pop(item_id, None) is not None

    async def restore(self, item_id: str) -> FakeRecord | None:
        item = self._store.get(item_id)
        if item is None or item.deleted_at is None:
            return None
        restored = replace(item, deleted_at=None)
        self._store[item_id] = restored
        return replace(restored)

    async def list(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        filters: Sequence[FilterClause] | None = None,
        sort: Sequence[SortField] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> list[FakeRecord]:
        self.list_calls.append(
            {
                "limit": limit,
                "cursor": cursor,
                "filters": filters,
                "sort": sort,
                "search": search,
                "include_deleted": include_deleted,
            }
        )
        items = [replace(v) for v in self._store.values()]
        if not include_deleted:
            items = [i for i in items if i.deleted_at is None]
        items = apply_filters(items, filters)
        items = apply_sort(items, sort)
        cursor_direction = sort[0].direction if sort else SortDirection.ASC
        cursor_sort_field = sort[0].field if sort else "id"
        items = apply_cursor(
            items,
            cursor,
            sort_field=cursor_sort_field,
            direction=cursor_direction,
        )
        return items[:limit]

    async def count(
        self,
        *,
        filters: Sequence[FilterClause] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        self.count_calls.append(
            {
                "filters": filters,
                "search": search,
                "include_deleted": include_deleted,
            }
        )
        return len(
            await self.list(
                limit=10_000,
                filters=filters,
                search=search,
                include_deleted=include_deleted,
            )
        )

    async def bulk_create(self, items: Sequence[dict[str, Any]]) -> list[FakeRecord]:
        return [await self.create(dict(item)) for item in items]

    async def bulk_update(
        self,
        updates: Sequence[tuple[str, dict[str, Any]]],
    ) -> list[FakeRecord]:
        results: list[FakeRecord] = []
        for item_id, data in updates:
            item = self._store.get(item_id)
            if item is None:
                continue
            updated = await self.update(
                item_id,
                dict(data),
                expected_version=item.version,
            )
            if updated is not None:
                results.append(updated)
        return results

    async def bulk_delete(self, item_ids: Sequence[str], *, soft: bool = True) -> int:
        count = 0
        for item_id in item_ids:
            if await self.delete(item_id, soft=soft):
                count += 1
        return count


@pytest.fixture
def repo():
    inner = FakeInnerRepo()
    return SoftDeleteRepository(inner), inner


@pytest.fixture
async def seeded(repo):
    sd_repo, _ = repo
    await sd_repo.create({"name": "alpha"})
    await sd_repo.create({"name": "beta"})
    await sd_repo.create({"name": "gamma"})
    return sd_repo


class TestSoftDeleteMixin:
    def test_is_deleted_and_is_active(self) -> None:
        active = SoftDeleteEntity()
        assert active.is_active is True
        assert active.is_deleted is False

        deleted = SoftDeleteEntity(deleted_at=datetime.now(timezone.utc))
        assert deleted.is_deleted is True
        assert deleted.is_active is False

    def test_soft_delete_sets_utcnow(self) -> None:
        entity = SoftDeleteEntity()
        entity.soft_delete()
        assert entity.deleted_at is not None
        assert entity.is_deleted is True

    def test_restore_clears_deleted_at(self) -> None:
        entity = SoftDeleteEntity(deleted_at=datetime.now(timezone.utc))
        entity.restore()
        assert entity.deleted_at is None
        assert entity.is_active is True


class TestSoftDeleteExclusion:
    @pytest.mark.anyio
    async def test_soft_deleted_excluded_from_list(self, seeded) -> None:
        sd_repo = seeded
        await sd_repo.delete("rec_2", expected_version=1)
        items = await sd_repo.list(limit=50)
        names = [i.name for i in items]
        assert "beta" not in names
        assert "alpha" in names and "gamma" in names

    @pytest.mark.anyio
    async def test_soft_deleted_excluded_from_get(self, seeded) -> None:
        sd_repo = seeded
        await sd_repo.delete("rec_1", expected_version=1)
        assert await sd_repo.get("rec_1") is None

    @pytest.mark.anyio
    async def test_include_deleted_flag_returns_them(self, seeded) -> None:
        sd_repo = seeded
        await sd_repo.delete("rec_1", expected_version=1)
        item = await sd_repo.get("rec_1", include_deleted=True)
        assert item is not None
        assert item.deleted_at is not None


class TestNoOverFetch:
    @pytest.mark.anyio
    async def test_list_delegates_limit_and_include_deleted(self, repo) -> None:
        sd_repo, inner = repo
        await sd_repo.create({"name": "a"})
        await sd_repo.list(limit=7, include_deleted=True)

        assert len(inner.list_calls) == 1
        call = inner.list_calls[0]
        assert call["limit"] == 7
        assert call["include_deleted"] is True
        # Must not inflate limit for Python-side filtering.
        assert call["limit"] != 7 * 5

    @pytest.mark.anyio
    async def test_count_delegates_include_deleted(self, repo) -> None:
        sd_repo, inner = repo
        await sd_repo.create({"name": "a"})
        await sd_repo.count(include_deleted=False)

        assert len(inner.count_calls) == 1
        assert inner.count_calls[0]["include_deleted"] is False


class TestCreateAndUpdate:
    @pytest.mark.anyio
    async def test_create_clears_deleted_at(self, repo) -> None:
        sd_repo, _ = repo
        created = await sd_repo.create(
            {
                "name": "ghost",
                "deleted_at": datetime.now(timezone.utc),
            }
        )
        assert created.deleted_at is None

    @pytest.mark.anyio
    async def test_update_strips_deleted_at(self, repo) -> None:
        sd_repo, inner = repo
        created = await sd_repo.create({"name": "alive"})
        stamp = datetime.now(timezone.utc)

        updated = await sd_repo.update(
            created.id,
            {"name": "renamed", "deleted_at": stamp},
            expected_version=1,
        )

        assert updated is not None
        assert updated.name == "renamed"
        assert updated.deleted_at is None
        assert inner._store[created.id].deleted_at is None


class TestRestore:
    @pytest.mark.anyio
    async def test_restore_makes_visible_again(self, seeded) -> None:
        sd_repo = seeded
        await sd_repo.delete("rec_3", expected_version=1)
        assert await sd_repo.get("rec_3") is None
        restored = await sd_repo.restore("rec_3", expected_version=2)
        assert restored is not None
        item = await sd_repo.get("rec_3")
        assert item is not None
        assert item.deleted_at is None

    @pytest.mark.anyio
    async def test_restore_nonexistent_returns_none(self, repo) -> None:
        sd_repo, _ = repo
        assert await sd_repo.restore("nonexistent", expected_version=1) is None

    @pytest.mark.anyio
    async def test_restore_active_raises_not_deleted(self, seeded) -> None:
        sd_repo = seeded
        with pytest.raises(NotDeletedError):
            await sd_repo.restore("rec_1", expected_version=1)


class TestHardDelete:
    @pytest.mark.anyio
    async def test_hard_delete_permanently_removes(self, seeded) -> None:
        sd_repo = seeded
        ok = await sd_repo.hard_delete("rec_1")
        assert ok is True
        assert await sd_repo.get("rec_1", include_deleted=True) is None


class TestSoftDeleteProperties:
    def test_is_deleted_true_when_set(self) -> None:
        r = FakeRecord(
            id="x",
            name="test",
            deleted_at=datetime.now(timezone.utc),
        )
        assert r.deleted_at is not None

    @pytest.mark.anyio
    async def test_double_delete_is_noop(self, seeded) -> None:
        sd_repo = seeded
        await sd_repo.delete("rec_1", expected_version=1)
        result = await sd_repo.delete("rec_1", expected_version=2)
        assert result is False
