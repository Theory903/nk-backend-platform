"""Soft-delete mixin and repository wrapper.

Add SoftDeleteMixin to a SQLAlchemy model to get a `deleted_at` column.
Wrap any Repository with SoftDeleteRepository to automatically exclude
soft-deleted records from list/get, with opt-in restore and hard-delete.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.core.query import FilterClause, SortField
from {{cookiecutter.project_name}}.data.protocols import Repository

M = TypeVar("M")


class NotDeletedError(Problem):
    """Raised when restore is attempted on a record that is not soft-deleted."""

    def __init__(self, resource_id: str) -> None:
        super().__init__(
            title="Not Deleted",
            status_code=409,
            detail=f"resource '{resource_id}' is not soft-deleted",
        )


class SoftDeleteMixin:
    """SQLAlchemy mixin adding a nullable deleted_at column."""

    deleted_at: Any  # Mapped[datetime | None] — typed by the concrete model

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None

    def soft_delete(self) -> None:
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        self.deleted_at = None


class SoftDeleteRepository(Generic[M]):
    """Wraps any Repository to exclude soft-deleted records by default."""

    def __init__(
        self,
        inner: Repository[M],
        *,
        deleted_field: str = "deleted_at",
        search_fields: Sequence[str] = ("name",),
        cursor_sort_field: str = "id",
    ) -> None:
        self._inner = inner
        self._field = deleted_field
        self._search_fields = tuple(search_fields)
        self._cursor_sort_field = cursor_sort_field

    def _is_deleted(self, item: M) -> bool:
        return getattr(item, self._field, None) is not None

    def _version_of(self, item: M) -> int:
        return int(getattr(item, "version", 1) or 1)

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> M | None:
        item = await self._inner.get(item_id, include_deleted=True)
        if item is None:
            return None
        if not include_deleted and self._is_deleted(item):
            return None
        return item

    async def create(self, data: dict[str, Any]) -> M:
        payload = dict(data)
        payload[self._field] = None
        return await self._inner.create(payload)

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> M | None:
        existing = await self.get(item_id)
        if existing is None:
            return None
        payload = dict(data)
        # Callers must not resurrect/soft-delete via update payload.
        payload.pop(self._field, None)
        return await self._inner.update(
            item_id,
            payload,
            expected_version=expected_version,
        )

    async def delete(
        self,
        item_id: str,
        *,
        soft: bool = True,
        expected_version: int | None = None,
    ) -> bool:
        if not soft:
            return await self._inner.delete(item_id, soft=False)

        item = await self.get(item_id)
        if item is None or self._is_deleted(item):
            return False

        version = (
            expected_version
            if expected_version is not None
            else self._version_of(item)
        )
        payload = {self._field: datetime.now(timezone.utc)}
        updated = await self._inner.update(
            item_id,
            payload,
            expected_version=version,
        )
        return updated is not None

    async def restore(
        self,
        item_id: str,
        *,
        expected_version: int | None = None,
    ) -> M | None:
        item = await self._inner.get(item_id, include_deleted=True)
        if item is None:
            return None
        if not self._is_deleted(item):
            raise NotDeletedError(item_id)

        version = (
            expected_version
            if expected_version is not None
            else self._version_of(item)
        )
        return await self._inner.update(
            item_id,
            {self._field: None},
            expected_version=version,
        )

    async def hard_delete(self, item_id: str) -> bool:
        """Permanently remove the row. Irreversible."""
        return await self._inner.delete(item_id, soft=False)

    async def list(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        filters: Sequence[FilterClause] | None = None,
        sort: Sequence[SortField] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> list[M]:
        return await self._inner.list(
            limit=limit,
            cursor=cursor,
            filters=filters,
            sort=sort,
            search=search,
            include_deleted=include_deleted,
        )

    async def count(
        self,
        *,
        filters: Sequence[FilterClause] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        return await self._inner.count(
            filters=filters,
            search=search,
            include_deleted=include_deleted,
        )

    async def bulk_create(self, items: Sequence[dict[str, Any]]) -> list[M]:
        return [
            await self.create(dict(item))
            for item in items
        ]

    async def bulk_update(
        self,
        updates: Sequence[tuple[str, dict[str, Any]]],
    ) -> list[M]:
        """Update many rows; payload ``version`` is treated as expected.

        Future: typed ``UpdateOperation`` with mandatory expected_version.
        """
        results: list[M] = []
        for item_id, data in updates:
            payload = dict(data)
            raw_version = payload.pop("version", None)
            if raw_version is None:
                current = await self.get(item_id)
                if current is None:
                    continue
                expected_version = self._version_of(current)
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

    async def bulk_delete(
        self,
        item_ids: Sequence[str],
        *,
        soft: bool = True,
    ) -> int:
        count = 0
        for item_id in item_ids:
            if await self.delete(item_id, soft=soft):
                count += 1
        return count


__all__ = [
    "NotDeletedError",
    "SoftDeleteMixin",
    "SoftDeleteRepository",
]
