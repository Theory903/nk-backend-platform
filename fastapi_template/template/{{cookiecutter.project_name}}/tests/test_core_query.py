"""Unit tests for typed query primitives (QuerySpec / QueryAllowList)."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.core.query import (
    FilterClause,
    FilterOp,
    QueryAllowList,
    QuerySpec,
    SortDirection,
    SortField,
    normalize_query,
)


def _allow_list() -> QueryAllowList:
    return QueryAllowList(
        filter_fields=frozenset({"status", "owner_id"}),
        sort_fields=frozenset({"created_at", "name"}),
        search_fields=frozenset({"name", "email"}),
    )


def test_filter_clause_rejects_empty_field() -> None:
    with pytest.raises(ValueError, match="filter field must not be empty"):
        FilterClause(field="  ", op=FilterOp.EQ, value="x")


def test_sort_field_rejects_empty_field() -> None:
    with pytest.raises(ValueError, match="sort field must not be empty"):
        SortField(field="", direction=SortDirection.ASC)


def test_in_filter_rejects_str_and_bytes() -> None:
    with pytest.raises(ValueError, match="IN filter value must be a sequence"):
        FilterClause(field="status", op=FilterOp.IN, value="active")

    with pytest.raises(ValueError, match="IN filter value must be a sequence"):
        FilterClause(field="status", op=FilterOp.IN, value=b"active")


def test_in_filter_rejects_non_sequence() -> None:
    with pytest.raises(ValueError, match="IN filter value must be a sequence"):
        FilterClause(field="status", op=FilterOp.IN, value=42)


def test_in_filter_accepts_list_and_tuple() -> None:
    assert FilterClause(field="status", op=FilterOp.IN, value=["a", "b"]).value == [
        "a",
        "b",
    ]
    assert FilterClause(field="status", op=FilterOp.IN, value=("a",)).value == ("a",)


def test_allow_list_rejects_unknown_filter_field() -> None:
    allow = _allow_list()
    query = QuerySpec(
        filters=(FilterClause(field="secret", op=FilterOp.EQ, value=1),),
    )
    with pytest.raises(ValueError, match="filter field 'secret' is not allowed"):
        allow.validate(query)


def test_allow_list_rejects_unknown_sort_field() -> None:
    allow = _allow_list()
    query = QuerySpec(sort=(SortField(field="password"),))
    with pytest.raises(ValueError, match="sort field 'password' is not allowed"):
        allow.validate(query)


def test_normalize_caps_limit() -> None:
    allow = _allow_list()
    normalized = normalize_query(
        QuerySpec(limit=500),
        allow,
        max_limit=100,
    )
    assert normalized.limit == 100


def test_query_spec_strips_search_and_cursor() -> None:
    query = QuerySpec(search="  hello  ", cursor="  cur  ", limit=10)
    assert query.search == "hello"
    assert query.cursor == "cur"

    blank = QuerySpec(search="   ", cursor="\t", limit=10)
    assert blank.search is None
    assert blank.cursor is None


def test_normalize_strips_via_query_spec() -> None:
    allow = _allow_list()
    normalized = normalize_query(
        QuerySpec(search="  q  ", cursor="  c  ", limit=10),
        allow,
    )
    assert normalized.search == "q"
    assert normalized.cursor == "c"


def test_disabled_filter_raises() -> None:
    allow = QueryAllowList(
        sort_fields=frozenset({"name"}),
        search_fields=frozenset({"name"}),
    )
    query = QuerySpec(
        filters=(FilterClause(field="status", op=FilterOp.EQ, value="a"),),
    )
    with pytest.raises(ValueError, match="filtering is not enabled"):
        allow.validate(query)


def test_disabled_sort_raises() -> None:
    allow = QueryAllowList(
        filter_fields=frozenset({"status"}),
        search_fields=frozenset({"name"}),
    )
    query = QuerySpec(sort=(SortField(field="name"),))
    with pytest.raises(ValueError, match="sorting is not enabled"):
        allow.validate(query)


def test_disabled_search_raises() -> None:
    allow = QueryAllowList(
        filter_fields=frozenset({"status"}),
        sort_fields=frozenset({"name"}),
    )
    query = QuerySpec(search="needle")
    with pytest.raises(ValueError, match="search is not enabled"):
        allow.validate(query)


def test_normalize_rejects_non_positive_max_limit() -> None:
    with pytest.raises(ValueError, match="max_limit must be greater than zero"):
        normalize_query(QuerySpec(), QueryAllowList(), max_limit=0)


def test_query_spec_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit must be greater than zero"):
        QuerySpec(limit=0)


def test_supports_helpers() -> None:
    allow = _allow_list()
    assert allow.supports_filter("status") is True
    assert allow.supports_filter("nope") is False
    assert allow.supports_sort("created_at") is True
    assert allow.supports_search("email") is True
