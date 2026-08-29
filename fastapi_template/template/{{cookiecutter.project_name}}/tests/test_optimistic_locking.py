"""Tests for optimistic locking: version checks, concurrent conflicts, ETag semantics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

import pytest

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.core.query import FilterClause, SortDirection, SortField
from {{cookiecutter.project_name}}.data.optimistic_lock import (
    ConcurrencyConflictError,
    OptimisticLockRepository,
)
from {{cookiecutter.project_name}}.data.query_runtime import apply_cursor, apply_filters, apply_sort


@dataclass
class FakeRecord:
    id: str = ""
    name: str = ""
    version: int | None = None


class FakeInnerRepo:
    """In-memory store simulating an atomic version-conditional UPDATE."""

    def __init__(self) -> None:
        self._store: dict[str, FakeRecord] = {}
        self._next_id = 0
        self.last_update_kwargs: dict[str, Any] | None = None

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> FakeRecord | None:
        item = self._store.get(item_id)
        if item is None:
            return None
        return replace(item)

    async def create(self, data: dict[str, Any]) -> FakeRecord:
        self._next_id += 1
        item = FakeRecord(
            id=f"rec_{self._next_id}",
            name=str(data.get("name", "")),
            version=int(data.get("version", 1)),
        )
        self._store[item.id] = replace(item)
        return replace(item)

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> FakeRecord | None:
        self.last_update_kwargs = {
            "item_id": item_id,
            "data": dict(data),
            "expected_version": expected_version,
        }
        item = self._store.get(item_id)
        if item is None:
            return None

        # Simulate atomic WHERE version = expected_version.
        if item.version != expected_version:
            raise ConcurrencyConflictError(
                item_id,
                expected_version,
                actual_version=int(item.version) if item.version is not None else None,
            )
        updated = replace(item)
        for key, value in data.items():
            if hasattr(updated, key) and key != "version":
                setattr(updated, key, value)
        updated.version = expected_version + 1
        self._store[item_id] = updated
        return replace(updated)

    async def delete(self, item_id: str, *, soft: bool = True) -> bool:
        return self._store.pop(item_id, None) is not None

    async def restore(self, item_id: str) -> FakeRecord | None:
        return await self.get(item_id)

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
        items = [replace(v) for v in self._store.values()]
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
        return len(await self.list(limit=10_000, filters=filters, search=search))

    async def bulk_create(self, items: Sequence[dict[str, Any]]) -> list[FakeRecord]:
        return [await self.create(dict(item)) for item in items]

    async def bulk_update(
        self,
        updates: Sequence[tuple[str, dict[str, Any]]],
    ) -> list[FakeRecord]:
        results: list[FakeRecord] = []
        for item_id, data in updates:
            payload = dict(data)
            raw_version = payload.pop("version", None)
            if raw_version is None:
                current = self._store.get(item_id)
                if current is None:
                    continue
                expected_version = int(current.version or 1)
            else:
                expected_version = int(raw_version)
            updated = await self.update(
                item_id,
                payload,
                expected_version=expected_version,
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
    return OptimisticLockRepository(inner), inner


@pytest.fixture
async def seeded(repo):
    ol_repo, _ = repo
    await ol_repo.create({"name": "original"})
    return ol_repo


class TestOptimisticLocking:
    @pytest.mark.anyio
    async def test_create_assigns_version_1(self, repo) -> None:
        ol_repo, _ = repo
        created = await ol_repo.create({"name": "new"})
        assert created.version == 1

    @pytest.mark.anyio
    async def test_update_with_matching_version_succeeds(self, seeded) -> None:
        current = await seeded.get("rec_1")
        updated = await seeded.update(
            "rec_1",
            {"name": "updated"},
            expected_version=current.version,
        )
        assert updated is not None
        assert updated.version == 2

    @pytest.mark.anyio
    async def test_update_with_expected_version_kwarg(self, seeded) -> None:
        updated = await seeded.update(
            "rec_1",
            {"name": "via-kwarg"},
            expected_version=1,
        )
        assert updated is not None
        assert updated.version == 2

    @pytest.mark.anyio
    async def test_update_with_stale_version_raises(self, seeded) -> None:
        await seeded.update("rec_1", {"name": "client-a-edit"}, expected_version=1)
        with pytest.raises(ConcurrencyConflictError):
            await seeded.update("rec_1", {"name": "client-b-edit"}, expected_version=1)

    @pytest.mark.anyio
    async def test_conflict_error_is_problem_409(self, seeded) -> None:
        await seeded.update("rec_1", {"name": "someone-else-wrote"}, expected_version=1)
        with pytest.raises(Problem) as exc_info:
            await seeded.update("rec_1", {"name": "stale-write"}, expected_version=1)
        assert exc_info.value.status_code == 409
        assert (
            "modified" in (exc_info.value.detail or "").lower()
            or "conflict" in (exc_info.value.title or "").lower()
        )

    @pytest.mark.anyio
    async def test_after_conflict_fresh_read_then_update_succeeds(self, seeded) -> None:
        await seeded.update("rec_1", {"name": "fresh-write"}, expected_version=1)
        with pytest.raises(ConcurrencyConflictError):
            await seeded.update("rec_1", {"name": "stale"}, expected_version=1)
        latest = await seeded.get("rec_1")
        result = await seeded.update(
            "rec_1",
            {"name": "resolved-write"},
            expected_version=latest.version,
        )
        assert result is not None
        assert result.version == 3

    @pytest.mark.anyio
    async def test_missing_expected_version_is_type_error(self, repo) -> None:
        ol_repo, _ = repo
        created = await ol_repo.create({"name": "plain"})
        with pytest.raises(TypeError):
            await ol_repo.update(created.id, {"name": "no-version-field"})  # type: ignore[call-arg]

    @pytest.mark.anyio
    async def test_decorator_does_not_pre_read(self, repo) -> None:
        """Decorator must not read-then-write; only forward expected_version."""
        ol_repo, inner = repo
        created = await ol_repo.create({"name": "x"})
        original_get = inner.get
        calls: list[str] = []

        async def tracking_get(*args: Any, **kwargs: Any) -> FakeRecord | None:
            calls.append("get")
            return await original_get(*args, **kwargs)

        inner.get = tracking_get  # type: ignore[method-assign]
        await ol_repo.update(created.id, {"name": "y"}, expected_version=1)
        assert calls == []
        assert inner.last_update_kwargs is not None
        assert inner.last_update_kwargs["expected_version"] == 1
        assert "version" not in inner.last_update_kwargs["data"]


class TestETagSemantics:
    @pytest.mark.anyio
    async def test_etag_equals_version(self, seeded) -> None:
        item = await seeded.get("rec_1")
        etag = f'"{item.version}"'
        assert etag == '"1"'

    @pytest.mark.anyio
    async def test_if_match_wrong_version_is_conflict(self, seeded) -> None:
        with pytest.raises(ConcurrencyConflictError) as exc_info:
            await seeded.update("rec_1", {"name": "x"}, expected_version=99)
        err = exc_info.value
        assert err.status_code == 409
        assert "expected version 99" in (err.detail or "")
