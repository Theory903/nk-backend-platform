"""Unit tests for Mongo BeanieRepository helpers and concurrency path."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from {{cookiecutter.project_name}}.core.pagination import Cursor
from {{cookiecutter.project_name}}.core.query import FilterClause, FilterOp
from {{cookiecutter.project_name}}.data.adapters.mongo import repository as mongo_repo
from {{cookiecutter.project_name}}.data.adapters.mongo.repository import (
    BeanieRepository,
    _apply_cursor,
    _apply_filters,
    _apply_search,
    _escape_regex,
    _merge_or,
)
from {{cookiecutter.project_name}}.data.optimistic_lock import ConcurrencyConflictError


def test_escape_regex_escapes_metacharacters() -> None:
    assert _escape_regex("a.b*c?") == r"a\.b\*c\?"
    assert _escape_regex("plain") == "plain"


def test_apply_filters_eq_in_and_contains() -> None:
    query: dict[str, Any] = {"deleted_at": None}

    _apply_filters(
        query,
        [
            FilterClause(field="name", op=FilterOp.EQ, value="alpha"),
            FilterClause(field="org_id", op=FilterOp.IN, value=["o1", "o2"]),
        ],
    )

    assert query["name"] == "alpha"
    assert query["org_id"] == {"$in": ["o1", "o2"]}
    assert query["deleted_at"] is None

    contains_query: dict[str, Any] = {}
    _apply_filters(
        contains_query,
        [
            FilterClause(
                field="name",
                op=FilterOp.CONTAINS,
                value="a.b",
            ),
        ],
    )
    assert contains_query["name"]["$regex"] == r"a\.b"
    assert contains_query["name"]["$options"] == "i"


def test_apply_filters_comparison_ops() -> None:
    query: dict[str, Any] = {}
    _apply_filters(
        query,
        [
            FilterClause(field="n", op=FilterOp.GT, value=1),
            FilterClause(field="m", op=FilterOp.LTE, value=9),
            FilterClause(field="p", op=FilterOp.NEQ, value="x"),
        ],
    )
    assert query["n"] == {"$gt": 1}
    assert query["m"] == {"$lte": 9}
    assert query["p"] == {"$ne": "x"}


def test_apply_cursor_builds_strict_gt_or() -> None:
    oid = str(ObjectId())
    query: dict[str, Any] = {"deleted_at": None}
    cursor = Cursor(
        sort_value="2024-01-01T00:00:00+00:00",
        last_id=oid,
    )

    _apply_cursor(query, cursor, sort_field="created_at")

    assert "$or" in query
    assert query["$or"][0] == {
        "created_at": {"$gt": "2024-01-01T00:00:00+00:00"},
    }
    assert query["$or"][1]["created_at"] == "2024-01-01T00:00:00+00:00"
    assert "$gt" in query["$or"][1]["_id"]


def test_apply_cursor_rejects_invalid_id() -> None:
    query: dict[str, Any] = {}
    cursor = Cursor(sort_value="x", last_id="not-an-oid")

    with pytest.raises(ValueError, match="invalid record ID"):
        _apply_cursor(query, cursor, sort_field="created_at")


def test_search_and_cursor_do_not_clobber_or() -> None:
    oid = str(ObjectId())
    query: dict[str, Any] = {"deleted_at": None}

    _apply_search(query, "alpha", ("name",))
    assert "$or" in query
    search_or = list(query["$or"])

    _apply_cursor(
        query,
        Cursor(sort_value="ts", last_id=oid),
        sort_field="created_at",
    )

    assert "$or" not in query
    assert "$and" in query
    assert len(query["$and"]) == 2
    assert query["$and"][0] == {"$or": search_or}
    assert query["$and"][1]["$or"][0]["created_at"] == {"$gt": "ts"}
    assert query["deleted_at"] is None


def test_merge_or_appends_when_and_already_present() -> None:
    query: dict[str, Any] = {
        "$and": [{"$or": [{"name": "a"}]}],
    }
    _merge_or(query, [{"name": "b"}])
    assert query["$and"] == [
        {"$or": [{"name": "a"}]},
        {"$or": [{"name": "b"}]},
    ]


@pytest.mark.asyncio
async def test_update_raises_concurrency_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = str(ObjectId())
    repo = BeanieRepository()

    collection = MagicMock()
    collection.find_one_and_update = AsyncMock(return_value=None)

    existing = MagicMock()
    existing.version = 7

    monkeypatch.setattr(
        mongo_repo.RecordDocument,
        "get_pymongo_collection",
        classmethod(lambda cls: collection),
    )
    monkeypatch.setattr(
        mongo_repo.RecordDocument,
        "find_one",
        AsyncMock(return_value=existing),
    )

    with pytest.raises(ConcurrencyConflictError):
        await repo.update(
            item_id,
            {"name": "after"},
            expected_version=1,
        )

    collection.find_one_and_update.assert_awaited_once()
    call_args = collection.find_one_and_update.await_args
    assert call_args is not None
    query, update_doc = call_args.args[:2]
    assert query["version"] == 1
    assert update_doc["$set"]["name"] == "after"
    assert update_doc["$set"]["version"] == 2
    assert "$setOnInsert" not in update_doc
    assert "$inc" not in update_doc


@pytest.mark.asyncio
async def test_update_requires_expected_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = str(ObjectId())
    repo = BeanieRepository()

    with pytest.raises(TypeError):
        await repo.update(item_id, {"name": "after"})  # type: ignore[call-arg]
