"""Unit tests for the in-memory query runtime engine."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from {{cookiecutter.project_name}}.core.pagination import make_cursor
from {{cookiecutter.project_name}}.core.query import (
    FilterClause,
    FilterOp,
    SortDirection,
    SortField,
)
from {{cookiecutter.project_name}}.data.query_runtime import (
    _safe_compare,
    apply_cursor,
    apply_filters,
    apply_query,
    apply_search,
    apply_sort,
    match_filter,
)


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    score: int | None = None
    tag: str | None = None


def test_safe_compare_none_ordering() -> None:
    assert _safe_compare(None, None) == 0
    assert _safe_compare(None, 1) == -1
    assert _safe_compare(1, None) == 1
    assert _safe_compare(1, 2) == -1
    assert _safe_compare(2, 1) == 1
    assert _safe_compare(1, 1) == 0


def test_safe_compare_heterogeneous_falls_back_to_str() -> None:
    # int vs str would raise TypeError under normal comparison
    assert _safe_compare(1, "a") == _safe_compare(str(1), "a")
    assert _safe_compare("a", 1) == _safe_compare("a", str(1))


def test_contains_is_casefold() -> None:
    item = Item(id="1", name="AlphaBeta")
    assert match_filter(
        item,
        FilterClause(field="name", op=FilterOp.CONTAINS, value="phab"),
    )
    assert match_filter(
        item,
        FilterClause(field="name", op=FilterOp.CONTAINS, value="ALPHABETA"),
    )
    assert not match_filter(
        item,
        FilterClause(field="name", op=FilterOp.CONTAINS, value="zzz"),
    )
    assert not match_filter(
        item,
        FilterClause(field="name", op=FilterOp.CONTAINS, value=None),
    )


def test_apply_filters_and_semantics() -> None:
    items = [
        Item(id="a", name="one", score=1),
        Item(id="b", name="two", score=2),
        Item(id="c", name="two", score=3),
    ]
    result = apply_filters(
        items,
        [
            FilterClause(field="name", op=FilterOp.EQ, value="two"),
            FilterClause(field="score", op=FilterOp.GTE, value=3),
        ],
    )
    assert [i.id for i in result] == ["c"]


def test_apply_search_or_across_fields() -> None:
    items = [
        Item(id="1", name="Alice", tag="ops"),
        Item(id="2", name="Bob", tag="alice-friend"),
        Item(id="3", name="Carol", tag="x"),
    ]
    result = apply_search(items, "ALI", ("name", "tag"))
    assert [i.id for i in result] == ["1", "2"]


def test_multi_sort_with_id_tie_break() -> None:
    items = [
        Item(id="c", name="same", score=1),
        Item(id="a", name="same", score=1),
        Item(id="b", name="same", score=2),
        Item(id="d", name="other", score=0),
    ]
    sorted_items = apply_sort(
        items,
        [
            SortField(field="name", direction=SortDirection.ASC),
            SortField(field="score", direction=SortDirection.DESC),
        ],
    )
    assert [i.id for i in sorted_items] == ["d", "b", "a", "c"]


def test_apply_sort_defaults_to_id_asc() -> None:
    items = [
        Item(id="c", name="z"),
        Item(id="a", name="y"),
        Item(id="b", name="x"),
    ]
    assert [i.id for i in apply_sort(items)] == ["a", "b", "c"]


def test_apply_cursor_asc_strict_gt() -> None:
    items = apply_sort(
        [
            Item(id="a", name="n", score=1),
            Item(id="b", name="n", score=1),
            Item(id="c", name="n", score=2),
        ],
        [SortField(field="score", direction=SortDirection.ASC)],
    )
    cursor = make_cursor(sort_value="1", last_id="a")
    result = apply_cursor(
        items,
        cursor,
        sort_field="score",
        direction=SortDirection.ASC,
    )
    assert [i.id for i in result] == ["b", "c"]


def test_apply_cursor_desc_strict_lt() -> None:
    items = apply_sort(
        [
            Item(id="a", name="n", score=1),
            Item(id="b", name="n", score=2),
            Item(id="c", name="n", score=3),
        ],
        [SortField(field="score", direction=SortDirection.DESC)],
    )
    cursor = make_cursor(sort_value="2", last_id="b")
    result = apply_cursor(
        items,
        cursor,
        sort_field="score",
        direction=SortDirection.DESC,
    )
    assert [i.id for i in result] == ["a"]


def test_apply_query_pipeline() -> None:
    items = [
        Item(id="1", name="Alpha", score=10, tag="keep"),
        Item(id="2", name="Beta", score=20, tag="drop"),
        Item(id="3", name="Alphabet", score=30, tag="keep"),
        Item(id="4", name="Gamma", score=40, tag="keep"),
    ]
    result = apply_query(
        items,
        filters=[FilterClause(field="tag", op=FilterOp.EQ, value="keep")],
        search="alp",
        search_fields=("name",),
        sort=[SortField(field="score", direction=SortDirection.ASC)],
        limit=10,
    )
    assert [i.id for i in result] == ["1", "3"]


def test_apply_query_cursor_and_limit() -> None:
    items = [
        Item(id="a", name="n", score=1),
        Item(id="b", name="n", score=2),
        Item(id="c", name="n", score=3),
        Item(id="d", name="n", score=4),
    ]
    cursor = make_cursor(sort_value="1", last_id="a")
    result = apply_query(
        items,
        sort=[SortField(field="score", direction=SortDirection.ASC)],
        cursor=cursor,
        cursor_sort_field="score",
        cursor_direction=SortDirection.ASC,
        limit=2,
    )
    assert [i.id for i in result] == ["b", "c"]


def test_apply_query_rejects_negative_limit() -> None:
    with pytest.raises(ValueError, match="limit must be >= 0"):
        apply_query([Item(id="a", name="n")], limit=-1)


def test_apply_query_limit_zero() -> None:
    assert apply_query([Item(id="a", name="n")], limit=0) == []
