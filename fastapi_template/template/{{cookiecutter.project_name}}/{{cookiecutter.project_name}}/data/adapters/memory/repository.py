"""In-memory Repository implementation for generated CRUD modules.

This adapter is intentionally development-only. Production applications should
replace it with the configured SQLAlchemy or document repository without
changing the generated service or router contract.
"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Generic, TypeVar

from {{cookiecutter.project_name}}.core.identifiers import new_id
from {{cookiecutter.project_name}}.core.pagination import parse_cursor
from {{cookiecutter.project_name}}.core.query import (
    FilterClause,
    FilterOp,
    SortDirection,
    SortField,
)
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.optimistic_lock import (
    ConcurrencyConflictError,
)

ModelT = TypeVar("ModelT")


class InMemoryRepository(Generic[ModelT]):
    """Small async repository used by generated modules before DB wiring."""

    def __init__(
        self,
        model: type[ModelT],
        *,
        id_prefix: str = "res",
        _items: dict[str, ModelT] | None = None,
        _lock: asyncio.Lock | None = None,
        _org_id: str | None = None,
        _scope_id: str | None = None,
        _scopes: dict[str, str] | None = None,
        search_fields: Sequence[str] | None = None,
    ) -> None:
        self.model = model
        self.id_prefix = id_prefix
        self._items = _items if _items is not None else {}
        self._lock = _lock or asyncio.Lock()
        self._org_id = _org_id
        self._scope_id = _scope_id
        self._scopes = _scopes if _scopes is not None else {}
        self._search_fields = tuple(search_fields or ("name",))

    def scoped(
        self,
        org_id: str | None,
        *,
        scope_id: str | None = None,
    ) -> InMemoryRepository[ModelT]:
        """Return a tenant-scoped view over the same development store."""
        return InMemoryRepository(
            self.model,
            id_prefix=self.id_prefix,
            _items=self._items,
            _lock=self._lock,
            _org_id=org_id,
            _scope_id=scope_id or org_id,
            _scopes=self._scopes,
            search_fields=self._search_fields,
        )

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> ModelT | None:
        async with self._lock:
            item = self._items.get(item_id)
            if item is None or (
                not include_deleted and self._is_deleted(item)
            ) or not self._belongs_to_scope(item):
                return None
            return self._copy_item(item)

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
        if limit <= 0:
            return []

        async with self._lock:
            items = [
                item
                for item in self._items.values()
                if (include_deleted or not self._is_deleted(item))
                and self._belongs_to_scope(item)
                and self._matches_filters(item, filters)
                and self._matches_search(item, search, self._search_fields)
            ]
            ordered = self._sort_items(items, sort)
            after_cursor = self._cursor_boundary(cursor, sort)
            if after_cursor is not None:
                ordered = [
                    item
                    for item in ordered
                    if self._after_boundary(item, after_cursor, sort)
                ]
            return [self._copy_item(item) for item in ordered[:limit]]

    async def count(
        self,
        *,
        filters: Sequence[FilterClause] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        items = await self.list(
            limit=max(len(self._items), 1),
            filters=filters,
            search=search,
            include_deleted=include_deleted,
        )
        return len(items)

    async def create(self, data: dict[str, Any]) -> ModelT:
        async with self._lock:
            if data.get("id") is not None:
                raise ValueError("id is server-assigned")
            item_id = new_id(self.id_prefix)
            payload = dict(data)
            payload.update(
                id=item_id,
                created_at=data.get("created_at") or utcnow(),
                deleted_at=None,
                version=1,
            )
            if self._org_id is not None:
                payload["org_id"] = self._org_id
            item = self._build_model(payload)
            self._items[item_id] = item
            if self._scope_id is not None:
                self._scopes[item_id] = self._scope_id
            return self._copy_item(item)

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> ModelT | None:
        async with self._lock:
            item = self._items.get(item_id)
            if item is None or not self._belongs_to_scope(item):
                return None
            if self._is_deleted(item):
                return None
            actual_version = int(getattr(item, "version", 1))
            if actual_version != expected_version:
                raise ConcurrencyConflictError(
                    item_id,
                    expected_version,
                    actual_version=actual_version,
                )
            for key, value in data.items():
                if key not in {
                    "id",
                    "created_at",
                    "deleted_at",
                    "org_id",
                    "version",
                }:
                    setattr(item, key, value)
            setattr(item, "version", expected_version + 1)
            return self._copy_item(item)

    async def delete(self, item_id: str, *, soft: bool = True) -> bool:
        async with self._lock:
            item = self._items.get(item_id)
            if (
                item is None
                or not self._belongs_to_scope(item)
                or self._is_deleted(item)
            ):
                return False
            if soft:
                setattr(item, "deleted_at", utcnow())
                setattr(item, "version", int(getattr(item, "version", 1)) + 1)
            else:
                del self._items[item_id]
            return True

    async def restore(self, item_id: str) -> ModelT | None:
        async with self._lock:
            item = self._items.get(item_id)
            if (
                item is None
                or not self._belongs_to_scope(item)
                or not self._is_deleted(item)
            ):
                return None
            setattr(item, "deleted_at", None)
            setattr(item, "version", int(getattr(item, "version", 1)) + 1)
            return self._copy_item(item)

    async def bulk_create(self, items: Sequence[dict[str, Any]]) -> list[ModelT]:
        return [await self.create(dict(item)) for item in items]

    async def bulk_update(
        self,
        updates: Sequence[tuple[str, dict[str, Any]]],
    ) -> list[ModelT]:
        results: list[ModelT] = []
        for item_id, data in updates:
            payload = dict(data)
            raw_version = payload.pop("version", None)
            current = await self.get(item_id)
            if current is None:
                continue
            expected_version = int(
                raw_version
                if raw_version is not None
                else getattr(current, "version", 1),
            )
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
        for item_id in dict.fromkeys(item_ids):
            if await self.delete(item_id, soft=soft):
                count += 1
        return count

    @staticmethod
    def _is_deleted(item: ModelT) -> bool:
        return getattr(item, "deleted_at", None) is not None

    @staticmethod
    def _matches_filters(
        item: ModelT,
        filters: Sequence[FilterClause] | None,
    ) -> bool:
        for clause in filters or ():
            actual = getattr(item, clause.field, None)
            value = clause.value
            try:
                if clause.op is FilterOp.EQ:
                    matches = actual == value
                elif clause.op is FilterOp.NEQ:
                    matches = actual != value
                elif clause.op is FilterOp.IN:
                    matches = actual in value
                elif clause.op is FilterOp.GT:
                    matches = actual > value
                elif clause.op is FilterOp.GTE:
                    matches = actual >= value
                elif clause.op is FilterOp.LT:
                    matches = actual < value
                elif clause.op is FilterOp.LTE:
                    matches = actual <= value
                elif clause.op is FilterOp.CONTAINS:
                    matches = str(value) in str(actual)
                else:
                    return False
            except TypeError:
                return False
            if not matches:
                return False
        return True

    @staticmethod
    def _matches_search(
        item: ModelT,
        search: str | None,
        search_fields: Sequence[str],
    ) -> bool:
        if not search or not search.strip():
            return True
        needle = search.strip().casefold()
        return any(
            needle in str(value).casefold()
            for field in search_fields
            for value in [getattr(item, field, None)]
            if isinstance(value, str)
        )

    @staticmethod
    def _sort_items(
        items: list[ModelT],
        sort: Sequence[SortField] | None,
    ) -> list[ModelT]:
        fields = list(sort or [SortField(field="id")])
        if not any(field.field == "id" for field in fields):
            fields.append(SortField(field="id"))
        result = list(items)
        for field in reversed(fields):
            result.sort(
                key=lambda item: InMemoryRepository._sort_key(
                    getattr(item, field.field, None),
                ),
                reverse=field.direction is SortDirection.DESC,
            )
        return result

    @staticmethod
    def _sort_key(value: Any) -> tuple[bool, Any]:
        return value is None, value

    @staticmethod
    def _cursor_boundary(
        cursor: str | None,
        sort: Sequence[SortField] | None,
    ) -> tuple[str, str] | None:
        if not cursor:
            return None
        token = parse_cursor(cursor)
        return token.sort_value, token.last_id

    @staticmethod
    def _after_boundary(
        item: ModelT,
        boundary: tuple[str, str],
        sort: Sequence[SortField] | None,
    ) -> bool:
        field = (sort or [SortField(field="id")])[0]
        value = getattr(item, field.field, None)
        current = (
            InMemoryRepository._sort_key(value),
            str(getattr(item, "id", "")),
        )
        boundary_value = InMemoryRepository._coerce_cursor_value(
            boundary[0],
            value,
        )
        boundary_key = InMemoryRepository._sort_key(boundary_value)
        if current[0] == boundary_key:
            return current[1] > boundary[1]
        if field.direction is SortDirection.DESC:
            return current[0] < boundary_key
        return current[0] > boundary_key

    @staticmethod
    def _coerce_cursor_value(raw: str, sample: Any) -> Any:
        """Decode primitive cursor values using the current field type."""
        try:
            if isinstance(sample, bool):
                return raw.lower() == "true"
            if isinstance(sample, int):
                return int(raw)
            if isinstance(sample, float):
                return float(raw)
            if isinstance(sample, datetime):
                return datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            return raw
        if sample is None:
            return raw
        try:
            return sample.__class__(raw)
        except (TypeError, ValueError):
            return raw

    def _belongs_to_scope(self, item: ModelT) -> bool:
        """Return whether an item belongs to this repository view."""
        if self._scope_id is None:
            return True
        recorded_scope = self._scopes.get(str(getattr(item, "id", "")))
        if recorded_scope is not None:
            return recorded_scope == self._scope_id
        return self._org_id is not None and (
            getattr(item, "org_id", None) == self._org_id
        )

    @staticmethod
    def _copy_item(item: ModelT) -> ModelT:
        """Prevent callers from mutating repository state out of band."""
        model_copy = getattr(item, "model_copy", None)
        if model_copy is not None:
            return model_copy(deep=True)
        return copy.copy(item)

    def _build_model(self, payload: dict[str, Any]) -> ModelT:
        """Build either a Pydantic model or a simple generated model."""
        model_validate = getattr(self.model, "model_validate", None)
        if model_validate is not None:
            return model_validate(payload)
        item = self.model()
        for key, value in payload.items():
            setattr(item, key, value)
        return item


__all__ = ["InMemoryRepository"]
