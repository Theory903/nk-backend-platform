"""Universal persistence contracts for SQL and document adapters.

Application services depend on these contracts rather than concrete
database implementations.

Adapters may use SQLAlchemy, Mongo/Beanie, or another persistence engine,
but they must preserve the same domain semantics.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, runtime_checkable

from {{cookiecutter.project_name}}.core.query import FilterClause, SortField

ModelT = TypeVar("ModelT")


@runtime_checkable
class Repository(Protocol[ModelT]):
    """
    Storage-independent repository contract.

    Implementations must preserve:

        - domain model semantics
        - soft-delete semantics
        - cursor pagination
        - filtering/sorting/search
        - optimistic locking
        - bulk operation semantics
        - caller-owned transactions

    Repositories must never commit application transactions.
    """

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> ModelT | None:
        """Return a record by id, or None when it does not exist."""
        ...

    async def list(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        filters: Sequence[FilterClause] | None = None,
        sort: Sequence[SortField] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> list[ModelT]:
        """Return a bounded page of matching records."""
        ...

    async def count(
        self,
        *,
        filters: Sequence[FilterClause] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        """Return the number of matching records."""
        ...

    async def create(
        self,
        data: dict[str, Any],
    ) -> ModelT:
        """
        Persist a new record.

        Implementations must establish the initial version.
        """
        ...

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> ModelT | None:
        """
        Atomically update a record using optimistic locking.

        The persistence adapter MUST perform the equivalent of:

            WHERE id = item_id
              AND version = expected_version

        and atomically advance the version.

        A stale version must raise ConcurrencyConflictError.

        Returns None when the record does not exist.
        """
        ...

    async def delete(
        self,
        item_id: str,
        *,
        soft: bool = True,
    ) -> bool:
        """
        Delete a record.

        soft=True marks the record deleted.
        soft=False permanently removes it.
        """
        ...

    async def restore(
        self,
        item_id: str,
    ) -> ModelT | None:
        """Restore a soft-deleted record."""
        ...

    async def bulk_create(
        self,
        items: Sequence[dict[str, Any]],
    ) -> list[ModelT]:
        """Create multiple records."""
        ...

    async def bulk_update(
        self,
        updates: Sequence[tuple[str, dict[str, Any]]],
    ) -> list[ModelT]:
        """
        Update multiple records.

        Each update must carry its expected version in the payload or
        through the adapter's version-aware contract.

        Future: typed ``UpdateOperation`` with mandatory expected_version.
        """
        ...

    async def bulk_delete(
        self,
        item_ids: Sequence[str],
        *,
        soft: bool = True,
    ) -> int:
        """Delete multiple records and return the successful count."""
        ...


@runtime_checkable
class UnitOfWork(Protocol):
    """
    Application transaction boundary.

    The Unit of Work owns transaction lifecycle.

    Repository implementations perform reads/writes and flushes;
    application services decide when the transaction commits.

    Concrete adapters may expose engine-specific handles (e.g. a session)
    on the implementation; those must not appear on this protocol.
    """

    @property
    def is_active(self) -> bool:
        """Whether the transaction is currently active."""
        ...

    @property
    def is_committed(self) -> bool:
        """Whether the transaction has successfully committed."""
        ...

    async def __aenter__(self) -> UnitOfWork:
        """Open the unit of work and begin its transaction."""
        ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        tb: object,
    ) -> None:
        """Rollback unfinished work and release resources."""
        ...

    async def commit(self) -> None:
        """Commit the current transaction."""
        ...

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        ...


__all__ = [
    "Repository",
    "UnitOfWork",
]
