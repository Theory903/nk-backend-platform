"""Production SQLAlchemy async repository implementing the Repository protocol."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.core.pagination import parse_cursor
from {{cookiecutter.project_name}}.core.query import (
    FilterClause,
    FilterOp,
    SortDirection,
    SortField,
)
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.persistence import RecordRow
from {{cookiecutter.project_name}}.data.models import Record
from {{cookiecutter.project_name}}.data.optimistic_lock import (
    ConcurrencyConflictError,
)


class SqlalchemyRepository:
    """
    Async SQLAlchemy repository.

    Responsibilities:
      - persistence only
      - SQL-side filtering/search/sorting
      - stable cursor pagination
      - optimistic concurrency
      - soft/hard deletion
      - bulk operations

    Transaction ownership remains with the caller.
    This repository flushes but never commits.
    """

    model: ClassVar[type[RecordRow]] = RecordRow

    cursor_sort_field: ClassVar[str] = "created_at"

    searchable_fields: ClassVar[tuple[str, ...]] = ("name",)

    filterable_fields: ClassVar[frozenset[str]] = frozenset(
        {
            "id",
            "name",
            "created_at",
            "deleted_at",
            "version",
            "org_id",
        }
    )

    sortable_fields: ClassVar[frozenset[str]] = frozenset(
        {
            "id",
            "name",
            "created_at",
            "deleted_at",
            "version",
        }
    )

    writable_fields: ClassVar[frozenset[str]] = frozenset(
        {
            "name",
            "org_id",
        }
    )

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Single entity operations
    # ------------------------------------------------------------------

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> BaseModel | None:
        stmt = select(self.model).where(self.model.id == item_id)

        if not include_deleted:
            stmt = stmt.where(self.model.deleted_at.is_(None))

        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()

        return row.to_domain() if row is not None else None

    async def create(
        self,
        data: dict[str, Any],
    ) -> BaseModel:
        clean_data = self._validate_write_data(data)

        record = Record.model_validate(clean_data)

        row = self.model.from_domain(record)

        self.session.add(row)
        await self.session.flush()

        return row.to_domain()

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> BaseModel | None:
        # Client version is never trusted; repo owns the increment.
        write_data = dict(data)
        write_data.pop("version", None)
        clean_data = self._validate_write_data(write_data)

        conditions = [
            self.model.id == item_id,
            self.model.deleted_at.is_(None),
            self.model.version == expected_version,
        ]

        values = dict(clean_data)
        # Atomic optimistic lock: SET version = expected + 1 WHERE version = expected.
        values["version"] = expected_version + 1

        stmt = (
            update(self.model)
            .where(and_(*conditions))
            .values(**values)
            .returning(self.model)
        )

        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            await self._raise_concurrency_if_needed(
                item_id,
                expected_version,
            )
            return None

        await self.session.flush()

        return row.to_domain()

    async def delete(
        self,
        item_id: str,
        *,
        soft: bool = True,
        expected_version: int | None = None,
    ) -> bool:
        if soft:
            conditions = [
                self.model.id == item_id,
                self.model.deleted_at.is_(None),
            ]

            if expected_version is not None:
                conditions.append(
                    self.model.version == expected_version,
                )

            stmt = (
                update(self.model)
                .where(and_(*conditions))
                .values(
                    deleted_at=utcnow(),
                    version=self.model.version + 1,
                )
            )

            result = await self.session.execute(stmt)

            if result.rowcount == 0 and expected_version is not None:
                await self._raise_concurrency_if_needed(
                    item_id,
                    expected_version,
                )

            await self.session.flush()
            return bool(result.rowcount)

        conditions = [self.model.id == item_id]

        if expected_version is not None:
            conditions.append(
                self.model.version == expected_version,
            )

        stmt = delete(self.model).where(and_(*conditions))

        result = await self.session.execute(stmt)

        if result.rowcount == 0 and expected_version is not None:
            await self._raise_concurrency_if_needed(
                item_id,
                expected_version,
            )

        await self.session.flush()
        return bool(result.rowcount)

    async def restore(
        self,
        item_id: str,
        *,
        expected_version: int | None = None,
    ) -> BaseModel | None:
        conditions = [
            self.model.id == item_id,
            self.model.deleted_at.is_not(None),
        ]

        if expected_version is not None:
            conditions.append(
                self.model.version == expected_version,
            )

        stmt = (
            update(self.model)
            .where(and_(*conditions))
            .values(
                deleted_at=None,
                version=self.model.version + 1,
            )
            .returning(self.model)
        )

        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            if expected_version is not None:
                await self._raise_concurrency_if_needed(
                    item_id,
                    expected_version,
                )
            return None

        await self.session.flush()

        return row.to_domain()

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    async def list(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        filters: Sequence[FilterClause] | None = None,
        sort: Sequence[SortField] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> list[BaseModel]:
        if limit <= 0:
            return []

        stmt = select(self.model)

        if not include_deleted:
            stmt = stmt.where(
                self.model.deleted_at.is_(None),
            )

        stmt = self._apply_filters(stmt, filters)
        stmt = self._apply_search(stmt, search)
        stmt = self._apply_cursor(stmt, cursor)
        stmt = self._apply_sort(stmt, sort)

        # Fetch one extra row so callers can construct next_cursor.
        stmt = stmt.limit(limit + 1)

        result = await self.session.execute(stmt)

        rows = list(result.scalars().all())

        return [
            row.to_domain()
            for row in rows[:limit]
        ]

    async def count(
        self,
        *,
        filters: Sequence[FilterClause] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        stmt = select(
            func.count(),
        ).select_from(self.model)

        if not include_deleted:
            stmt = stmt.where(
                self.model.deleted_at.is_(None),
            )

        stmt = self._apply_filters(stmt, filters)
        stmt = self._apply_search(stmt, search)

        result = await self.session.execute(stmt)

        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    async def bulk_create(
        self,
        items: Sequence[dict[str, Any]],
    ) -> list[BaseModel]:
        if not items:
            return []

        rows: list[RecordRow] = []

        for data in items:
            clean_data = self._validate_write_data(dict(data))
            record = Record.model_validate(clean_data)
            rows.append(self.model.from_domain(record))

        self.session.add_all(rows)
        await self.session.flush()

        return [
            row.to_domain()
            for row in rows
        ]

    async def bulk_update(
        self,
        updates: Sequence[tuple[str, dict[str, Any]]],
    ) -> list[BaseModel]:
        """Update many rows; each payload may carry ``version`` as expected.

        Future: typed ``UpdateOperation`` with mandatory expected_version.
        """
        results: list[BaseModel] = []

        for item_id, data in updates:
            payload = dict(data)
            raw_version = payload.pop("version", None)
            if raw_version is None:
                current = await self.get(item_id)
                if current is None:
                    continue
                expected_version = int(current.version)
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
        if not item_ids:
            return 0

        unique_ids = list(dict.fromkeys(item_ids))

        if soft:
            stmt = (
                update(self.model)
                .where(
                    self.model.id.in_(unique_ids),
                    self.model.deleted_at.is_(None),
                )
                .values(
                    deleted_at=utcnow(),
                    version=self.model.version + 1,
                )
            )
        else:
            stmt = delete(self.model).where(
                self.model.id.in_(unique_ids),
            )

        result = await self.session.execute(stmt)

        await self.session.flush()

        return int(result.rowcount or 0)

    # ------------------------------------------------------------------
    # SQL query construction
    # ------------------------------------------------------------------

    def _column(self, field_name: str) -> Any:
        if field_name not in self.filterable_fields | self.sortable_fields:
            raise ValueError(
                f"field '{field_name}' is not allowed",
            )

        column = getattr(self.model, field_name, None)

        if column is None:
            raise ValueError(
                f"field '{field_name}' does not exist",
            )

        return column

    def _apply_filters(
        self,
        stmt: Any,
        filters: Sequence[FilterClause] | None,
    ) -> Any:
        if not filters:
            return stmt

        for clause in filters:
            if clause.field not in self.filterable_fields:
                raise ValueError(
                    f"filter field '{clause.field}' is not allowed",
                )

            column = self._column(clause.field)

            if clause.op is FilterOp.EQ:
                stmt = stmt.where(column == clause.value)

            elif clause.op is FilterOp.NEQ:
                stmt = stmt.where(column != clause.value)

            elif clause.op is FilterOp.IN:
                values = clause.value or []

                if not isinstance(values, (list, tuple, set, frozenset)):
                    raise ValueError(
                        f"IN filter for '{clause.field}' requires a sequence",
                    )

                stmt = stmt.where(column.in_(values))

            elif clause.op is FilterOp.GT:
                stmt = stmt.where(column > clause.value)

            elif clause.op is FilterOp.GTE:
                stmt = stmt.where(column >= clause.value)

            elif clause.op is FilterOp.LT:
                stmt = stmt.where(column < clause.value)

            elif clause.op is FilterOp.LTE:
                stmt = stmt.where(column <= clause.value)

            elif clause.op is FilterOp.CONTAINS:
                stmt = stmt.where(
                    column.contains(str(clause.value)),
                )

            else:
                raise ValueError(
                    f"unsupported filter operation: {clause.op}",
                )

        return stmt

    def _apply_search(
        self,
        stmt: Any,
        search: str | None,
    ) -> Any:
        if not search:
            return stmt

        search = search.strip()

        if not search:
            return stmt

        clauses = [
            self._column(field_name).contains(search)
            for field_name in self.searchable_fields
        ]

        if clauses:
            stmt = stmt.where(or_(*clauses))

        return stmt

    def _apply_cursor(
        self,
        stmt: Any,
        cursor: str | None,
    ) -> Any:
        if not cursor:
            return stmt

        token = parse_cursor(cursor)

        sort_field = self.cursor_sort_field

        if sort_field not in self.sortable_fields:
            raise ValueError(
                f"cursor sort field '{sort_field}' is not allowed",
            )

        sort_column = self._column(sort_field)

        stmt = stmt.where(
            or_(
                sort_column > token.sort_value,
                and_(
                    sort_column == token.sort_value,
                    self.model.id > token.last_id,
                ),
            ),
        )

        return stmt

    def _apply_sort(
        self,
        stmt: Any,
        sort: Sequence[SortField] | None,
    ) -> Any:
        if not sort:
            column = self._column(self.cursor_sort_field)

            return stmt.order_by(
                column.asc(),
                self.model.id.asc(),
            )

        order_by = []

        for item in sort:
            if item.field not in self.sortable_fields:
                raise ValueError(
                    f"sort field '{item.field}' is not allowed",
                )

            column = self._column(item.field)

            if item.direction is SortDirection.DESC:
                order_by.append(column.desc())
            else:
                order_by.append(column.asc())

        # Deterministic tie-breaker.
        order_by.append(self.model.id.asc())

        return stmt.order_by(*order_by)

    # ------------------------------------------------------------------
    # Validation / concurrency
    # ------------------------------------------------------------------

    def _validate_write_data(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        unknown = set(data) - self.writable_fields

        if unknown:
            raise ValueError(
                f"fields are not writable: {sorted(unknown)}",
            )

        return {
            key: value
            for key, value in data.items()
            if key in self.writable_fields
        }

    async def _raise_concurrency_if_needed(
        self,
        item_id: str,
        expected_version: int,
    ) -> None:
        current = await self.session.get(
            self.model,
            item_id,
        )

        if current is not None and current.deleted_at is None:
            raise ConcurrencyConflictError(
                item_id,
                expected_version,
                actual_version=int(current.version),
            )


__all__ = [
    "SqlalchemyRepository",
]