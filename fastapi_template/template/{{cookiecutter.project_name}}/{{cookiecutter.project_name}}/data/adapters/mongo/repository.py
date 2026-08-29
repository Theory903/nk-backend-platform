"""Production MongoDB repository implementing the platform Repository protocol.

Design:
- Beanie/MongoDB persistence
- ObjectId boundary conversion
- soft-delete support
- cursor pagination
- allow-listed filtering/sorting/search
- optimistic concurrency
- Mongo-native bulk operations
- async I/O only
- bounded queries
- no full collection materialization
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from beanie import PydanticObjectId
from bson.errors import InvalidId
from pydantic import BaseModel
from pymongo import ReturnDocument, UpdateOne

from {{cookiecutter.project_name}}.core.pagination import Cursor, parse_cursor
from {{cookiecutter.project_name}}.core.query import (
    FilterClause,
    FilterOp,
    SortDirection,
    SortField,
)
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.adapters.mongo.documents import RecordDocument
from {{cookiecutter.project_name}}.data.models import Record
from {{cookiecutter.project_name}}.data.optimistic_lock import (
    ConcurrencyConflictError,
)


class BeanieRepository:
    """Async MongoDB repository for Record."""

    cursor_sort_field = "created_at"
    searchable_fields: tuple[str, ...] = ("name",)

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> BaseModel | None:
        """Fetch a record by ID."""

        object_id = _to_object_id(item_id)

        if object_id is None:
            return None

        query: dict[str, Any] = {
            "_id": object_id,
        }

        if not include_deleted:
            query["deleted_at"] = None

        document = await RecordDocument.find_one(query)

        if document is None:
            return None

        return document.to_domain()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        data: dict[str, Any],
    ) -> BaseModel:
        """Validate, persist and return a new record."""

        record = Record.model_validate(data)

        document = RecordDocument.from_domain(
            record,
        )

        await document.insert()

        return document.to_domain()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> BaseModel | None:
        """
        Atomically update a record using optimistic locking.

        The update is conditional on ``version == expected_version``.
        Stale versions raise ConcurrencyConflictError; missing rows
        return None.
        """

        object_id = _to_object_id(item_id)

        if object_id is None:
            return None

        set_fields = {
            key: value
            for key, value in data.items()
            if key
            not in {
                "id",
                "_id",
                "created_at",
                "version",
            }
        }

        if not set_fields:
            current = await self.get(item_id)
            if current is None:
                return None
            if int(current.version) != expected_version:
                raise ConcurrencyConflictError(
                    item_id,
                    expected_version,
                    actual_version=int(current.version),
                )
            return current

        query: dict[str, Any] = {
            "_id": object_id,
            "deleted_at": None,
            "version": expected_version,
        }

        update_document: dict[str, Any] = {
            "$set": {
                **set_fields,
                "version": expected_version + 1,
            },
        }

        collection = (
            RecordDocument.get_pymongo_collection()
        )

        raw = await collection.find_one_and_update(
            query,
            update_document,
            return_document=ReturnDocument.AFTER,
        )

        if raw is None:
            existing = await RecordDocument.find_one(
                {
                    "_id": object_id,
                    "deleted_at": None,
                },
            )

            if existing is not None:
                raise ConcurrencyConflictError(
                    item_id,
                    expected_version,
                    actual_version=int(existing.version),
                )

            return None

        return _document_from_raw(raw).to_domain()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(
        self,
        item_id: str,
        *,
        soft: bool = True,
    ) -> bool:
        """Delete a record, using soft-delete by default."""

        object_id = _to_object_id(item_id)

        if object_id is None:
            return False

        if soft:
            result = await RecordDocument.find_one(
                {
                    "_id": object_id,
                    "deleted_at": None,
                },
            ).update(
                {
                    "$set": {
                        "deleted_at": utcnow(),
                    },
                    "$inc": {
                        "version": 1,
                    },
                },
            )

            return bool(result)

        result = await RecordDocument.find_one(
            {
                "_id": object_id,
            },
        ).delete()

        return bool(result)

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    async def restore(
        self,
        item_id: str,
    ) -> BaseModel | None:
        """Restore a soft-deleted record."""

        object_id = _to_object_id(item_id)

        if object_id is None:
            return None

        document = await RecordDocument.find_one(
            {
                "_id": object_id,
                "deleted_at": {
                    "$ne": None,
                },
            },
        )

        if document is None:
            return None

        document.deleted_at = None
        document.version += 1

        await document.replace()

        return document.to_domain()

    # ------------------------------------------------------------------
    # List
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
        """
        Query records directly in MongoDB.

        Unlike the original implementation, this never loads the entire
        collection into Python.
        """

        if limit <= 0:
            return []

        query: dict[str, Any] = {}

        if not include_deleted:
            query["deleted_at"] = None

        _apply_filters(
            query,
            filters or (),
        )

        _apply_search(
            query,
            search,
            self.searchable_fields,
        )

        cursor_value = (
            parse_cursor(cursor)
            if cursor
            else None
        )

        if cursor_value is not None:
            _apply_cursor(
                query,
                cursor_value,
                sort_field=self.cursor_sort_field,
            )

        sort_spec = _build_sort(
            sort
            or (
                SortField(
                    field=self.cursor_sort_field,
                    direction=SortDirection.ASC,
                ),
            ),
        )

        documents = (
            await RecordDocument.find(
                query,
            )
            .sort(sort_spec)
            .limit(limit)
            .to_list()
        )

        return [
            document.to_domain()
            for document in documents
        ]

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    async def count(
        self,
        *,
        filters: Sequence[FilterClause] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        """Count matching records without materializing documents."""

        query: dict[str, Any] = {}

        if not include_deleted:
            query["deleted_at"] = None

        _apply_filters(
            query,
            filters or (),
        )

        _apply_search(
            query,
            search,
            self.searchable_fields,
        )

        return await RecordDocument.find(
            query,
        ).count()

    # ------------------------------------------------------------------
    # Bulk create
    # ------------------------------------------------------------------

    async def bulk_create(
        self,
        items: Sequence[dict[str, Any]],
    ) -> list[BaseModel]:
        """Insert records in one MongoDB bulk operation."""

        if not items:
            return []

        documents = [
            RecordDocument.from_domain(
                _normalize_record(item),
            )
            for item in items
        ]

        await RecordDocument.insert_many(
            documents,
        )

        return [
            document.to_domain()
            for document in documents
        ]

    # ------------------------------------------------------------------
    # Bulk update
    # ------------------------------------------------------------------

    async def bulk_update(
        self,
        updates: Sequence[
            tuple[str, dict[str, Any]]
        ],
    ) -> list[BaseModel]:
        """Update multiple records with MongoDB bulk_write.

        Payload ``version`` is treated as expected_version when present.
        Future: typed ``UpdateOperation`` with mandatory expected_version.
        """

        if not updates:
            return []

        operations: list[UpdateOne] = []

        for item_id, data in updates:
            object_id = _to_object_id(item_id)

            if object_id is None:
                continue

            payload = dict(data)
            raw_version = payload.pop("version", None)

            update_data = {
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "id",
                    "_id",
                    "created_at",
                }
            }

            if not update_data:
                continue

            if raw_version is None:
                # Remaining bypass until UpdateOperation lands: silent $inc.
                query: dict[str, Any] = {
                    "_id": object_id,
                    "deleted_at": None,
                }
                doc: dict[str, Any] = {
                    "$set": update_data,
                    "$inc": {"version": 1},
                }
            else:
                expected_version = int(raw_version)
                query = {
                    "_id": object_id,
                    "deleted_at": None,
                    "version": expected_version,
                }
                doc = {
                    "$set": {
                        **update_data,
                        "version": expected_version + 1,
                    },
                }

            operations.append(UpdateOne(query, doc))

        if not operations:
            return []

        collection = (
            RecordDocument.get_pymongo_collection()
        )

        await collection.bulk_write(
            operations,
            ordered=False,
        )

        ids = [
            item_id
            for item_id, _ in updates
            if _to_object_id(item_id) is not None
        ]

        results: list[BaseModel] = []

        for item_id in ids:
            item = await self.get(item_id)

            if item is not None:
                results.append(item)

        return results

    # ------------------------------------------------------------------
    # Bulk delete
    # ------------------------------------------------------------------

    async def bulk_delete(
        self,
        item_ids: Sequence[str],
        *,
        soft: bool = True,
    ) -> int:
        """Delete multiple records using MongoDB bulk operations."""

        object_ids = [
            object_id
            for item_id in item_ids
            if (
                object_id := _to_object_id(item_id)
            )
            is not None
        ]

        if not object_ids:
            return 0

        collection = (
            RecordDocument.get_pymongo_collection()
        )

        if soft:
            result = await collection.update_many(
                {
                    "_id": {
                        "$in": object_ids,
                    },
                    "deleted_at": None,
                },
                {
                    "$set": {
                        "deleted_at": utcnow(),
                    },
                    "$inc": {
                        "version": 1,
                    },
                },
            )

            return int(
                result.modified_count,
            )

        result = await collection.delete_many(
            {
                "_id": {
                    "$in": object_ids,
                },
            },
        )

        return int(
            result.deleted_count,
        )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _apply_filters(
    query: dict[str, Any],
    filters: Sequence[FilterClause],
) -> None:
    """Translate validated query clauses into MongoDB predicates."""

    for clause in filters:
        field = clause.field
        value = clause.value

        match clause.op:
            case FilterOp.EQ:
                query[field] = value

            case FilterOp.NEQ:
                query[field] = {
                    "$ne": value,
                }

            case FilterOp.IN:
                query[field] = {
                    "$in": value,
                }

            case FilterOp.GT:
                query[field] = {
                    "$gt": value,
                }

            case FilterOp.GTE:
                query[field] = {
                    "$gte": value,
                }

            case FilterOp.LT:
                query[field] = {
                    "$lt": value,
                }

            case FilterOp.LTE:
                query[field] = {
                    "$lte": value,
                }

            case FilterOp.CONTAINS:
                query[field] = {
                    "$regex": _escape_regex(
                        str(value),
                    ),
                    "$options": "i",
                }

            case _:
                raise ValueError(
                    f"unsupported filter operator: {clause.op}"
                )


def _apply_search(
    query: dict[str, Any],
    search: str | None,
    fields: Sequence[str],
) -> None:
    """Apply bounded case-insensitive text search."""

    if not search or not fields:
        return

    escaped = _escape_regex(
        search.strip(),
    )

    if not escaped:
        return

    _merge_or(
        query,
        [
            {
                field: {
                    "$regex": escaped,
                    "$options": "i",
                },
            }
            for field in fields
        ],
    )


def _apply_cursor(
    query: dict[str, Any],
    cursor: Cursor,
    *,
    sort_field: str,
) -> None:
    """
    Apply a stable cursor predicate.

    Ordering is:

        sort_field ASC, _id ASC

    The cursor therefore advances using:

        sort > cursor.sort_value
        OR
        sort == cursor.sort_value AND id > cursor.last_id
    """

    object_id = _to_object_id(
        cursor.last_id,
    )

    if object_id is None:
        raise ValueError(
            "cursor contains an invalid record ID"
        )

    _merge_or(
        query,
        [
            {
                sort_field: {
                    "$gt": _coerce_cursor_value(
                        cursor.sort_value,
                    ),
                },
            },
            {
                sort_field: _coerce_cursor_value(
                    cursor.sort_value,
                ),
                "_id": {
                    "$gt": object_id,
                },
            },
        ],
    )


def _merge_or(
    query: dict[str, Any],
    or_clause: list[dict[str, Any]],
) -> None:
    """
    Attach an ``$or`` predicate without clobbering an existing one.

    When search and cursor both need ``$or``, combine under ``$and`` so
    neither clause is overwritten:

        {$and: [{$or: search}, {$or: cursor}]}
    """

    new_clause: dict[str, Any] = {
        "$or": or_clause,
    }

    if "$or" in query:
        existing = {
            "$or": query.pop("$or"),
        }
        query.setdefault("$and", []).extend(
            [
                existing,
                new_clause,
            ],
        )
        return

    if "$and" in query:
        query["$and"].append(new_clause)
        return

    query["$or"] = or_clause


def _build_sort(
    fields: Sequence[SortField],
) -> list[tuple[str, int]]:
    """Convert typed sorting into MongoDB sort tuples."""

    result: list[tuple[str, int]] = []

    for item in fields:
        direction = (
            1
            if item.direction
            == SortDirection.ASC
            else -1
        )

        result.append(
            (
                item.field,
                direction,
            ),
        )

    # Stable deterministic tie-breaker.
    if "_id" not in {
        field
        for field, _ in result
    }:
        result.append(
            ("_id", 1),
        )

    return result


def _coerce_cursor_value(
    value: str,
) -> Any:
    """
    Convert common cursor values back to Mongo-compatible values.

    ISO timestamps are intentionally not guessed here. The repository
    should encode/decode the actual sort type at the cursor boundary.
    """

    return value


def _normalize_record(
    data: dict[str, Any],
) -> Record:
    """Validate raw bulk input through the domain model."""

    return Record.model_validate(
        data,
    )


def _escape_regex(
    value: str,
) -> str:
    """Prevent user input from becoming an arbitrary Mongo regex."""

    return re.escape(value)


def _to_object_id(
    value: str,
) -> PydanticObjectId | None:
    """Safely convert an external ID into a Mongo ObjectId."""

    try:
        return PydanticObjectId(value)
    except (
        TypeError,
        ValueError,
        InvalidId,
    ):
        return None


def _document_from_raw(
    raw: dict[str, Any],
) -> RecordDocument:
    """Hydrate a Beanie document from a raw MongoDB dict."""

    payload = dict(raw)

    if "_id" in payload and "id" not in payload:
        payload["id"] = payload.pop("_id")

    return RecordDocument.model_validate(payload)


__all__ = [
    "BeanieRepository",
]
