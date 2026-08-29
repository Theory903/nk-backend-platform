"""Optimistic locking for concurrent repository updates.

Optimistic locking prevents lost updates by making the persistence
operation conditional on the version observed by the caller.

The critical operation is atomic:

    UPDATE resource
    SET ..., version = expected_version + 1
    WHERE id = resource_id
      AND version = expected_version

If zero rows are affected, another writer won the race and a
ConcurrencyConflictError is raised.

SQLAlchemy and Mongo repositories should implement the atomic operation
natively; this module provides the shared contract and error semantics.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy.orm import Mapped, mapped_column

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.core.query import FilterClause, SortField
from {{cookiecutter.project_name}}.data.protocols import Repository

M = TypeVar("M")


class ConcurrencyConflictError(Problem):
    """Raised when an optimistic-lock version check fails."""

    def __init__(
        self,
        resource_id: str,
        expected_version: int,
        actual_version: int | None = None,
    ) -> None:
        detail = (
            f"resource '{resource_id}' was modified concurrently; "
            f"expected version {expected_version}"
        )

        if actual_version is not None:
            detail += f", actual version {actual_version}"

        super().__init__(
            title="Concurrent Modification Conflict",
            status_code=409,
            detail=detail,
        )


class VersionedMixin:
    """SQLAlchemy mixin for resources protected by optimistic locking."""

    version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
    )


class VersionedRepository(Protocol[M]):
    """Repository capability required by optimistic locking."""

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> M | None:
        ...


class OptimisticLockRepository(Generic[M]):
    """
    Repository decorator enforcing version-aware updates.

    The wrapped repository MUST implement an atomic expected-version
    update. A read-then-write check is intentionally not performed here,
    because that pattern is vulnerable to races.

    The decorator strips any client ``version`` from the payload.
    The repository owns ``version = expected_version + 1`` in the
    atomic UPDATE.

    Version semantics:

        create -> version 1
        update(v=1) -> version 2
        update(v=2) -> version 3

    A stale update receives HTTP 409 through ConcurrencyConflictError.
    """

    def __init__(self, inner: Repository[M]) -> None:
        self._inner = inner

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> M | None:
        return await self._inner.get(
            item_id,
            include_deleted=include_deleted,
        )

    async def create(self, data: dict[str, Any]) -> M:
        payload = dict(data)

        payload.pop("version", None)

        return await self._inner.create(payload)

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> M | None:
        if expected_version < 1:
            raise ValueError("expected_version must be >= 1")

        payload = dict(data)
        payload.pop("version", None)

        # Repository owns version = expected_version + 1 in the atomic UPDATE.
        # Do not put the next version in the payload.
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
    ) -> bool:
        return await self._inner.delete(
            item_id,
            soft=soft,
        )

    async def restore(self, item_id: str) -> M | None:
        return await self._inner.restore(item_id)

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

    async def bulk_create(
        self,
        items: Sequence[dict[str, Any]],
    ) -> list[M]:
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
                expected_version = int(getattr(current, "version"))
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
        return await self._inner.bulk_delete(
            item_ids,
            soft=soft,
        )


__all__ = [
    "ConcurrencyConflictError",
    "VersionedMixin",
    "VersionedRepository",
    "OptimisticLockRepository",
]
