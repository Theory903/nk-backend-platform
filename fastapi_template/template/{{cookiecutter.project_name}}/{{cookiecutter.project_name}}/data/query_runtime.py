"""In-memory query engine shared by adapters, tests, and local backends.

Provides deterministic filtering, searching, multi-field sorting, and
keyset cursor pagination using the same semantics as the persistence
adapters.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import cmp_to_key
from typing import Any

from {{cookiecutter.project_name}}.core.pagination import Cursor, parse_cursor
from {{cookiecutter.project_name}}.core.query import (
    FilterClause,
    FilterOp,
    SortDirection,
    SortField,
)


def _attr(obj: Any, name: str) -> Any:
    """Read a field from either a mapping or an object."""
    if isinstance(obj, dict):
        return obj.get(name)

    return getattr(obj, name, None)


def _safe_compare(left: Any, right: Any) -> int:
    """Compare heterogeneous values without raising on None/type mismatches."""
    if left is None and right is None:
        return 0
    if left is None:
        return -1
    if right is None:
        return 1

    try:
        if left < right:
            return -1
        if left > right:
            return 1
        return 0
    except TypeError:
        left_text = str(left)
        right_text = str(right)

        if left_text < right_text:
            return -1
        if left_text > right_text:
            return 1
        return 0


def match_filter(
    obj: Any,
    clause: FilterClause,
) -> bool:
    """Evaluate one filter clause against an object."""
    value = _attr(obj, clause.field)
    expected = clause.value

    match clause.op:
        case FilterOp.EQ:
            return value == expected

        case FilterOp.NEQ:
            return value != expected

        case FilterOp.IN:
            if expected is None:
                return False

            try:
                return value in expected
            except TypeError:
                return False

        case FilterOp.GT:
            return _safe_compare(value, expected) > 0

        case FilterOp.GTE:
            return _safe_compare(value, expected) >= 0

        case FilterOp.LT:
            return _safe_compare(value, expected) < 0

        case FilterOp.LTE:
            return _safe_compare(value, expected) <= 0

        case FilterOp.CONTAINS:
            if value is None or expected is None:
                return False

            return str(expected).casefold() in str(value).casefold()

    return False


def apply_filters(
    items: Sequence[Any],
    filters: Sequence[FilterClause] | None = None,
) -> list[Any]:
    """Apply all filters using AND semantics."""
    if not filters:
        return list(items)

    return [
        item
        for item in items
        if all(match_filter(item, clause) for clause in filters)
    ]


def apply_search(
    items: Sequence[Any],
    search: str | None,
    search_fields: Sequence[str],
) -> list[Any]:
    """
    Perform case-insensitive substring search across configured fields.

    Search fields are OR-ed together.
    """
    if not search or not search_fields:
        return list(items)

    needle = search.casefold().strip()

    if not needle:
        return list(items)

    result: list[Any] = []

    for item in items:
        for field_name in search_fields:
            value = _attr(item, field_name)

            if value is not None and needle in str(value).casefold():
                result.append(item)
                break

    return result


def _compare_items(
    left: Any,
    right: Any,
    sort_fields: Sequence[SortField],
) -> int:
    """Compare two items according to the complete sort specification."""
    for field in sort_fields:
        result = _safe_compare(
            _attr(left, field.field),
            _attr(right, field.field),
        )

        if result:
            if field.direction is SortDirection.DESC:
                result = -result

            return result

    # Stable deterministic tie-breaker.
    return _safe_compare(
        str(_attr(left, "id") or ""),
        str(_attr(right, "id") or ""),
    )


def apply_sort(
    items: Sequence[Any],
    sort: Sequence[SortField] | None = None,
) -> list[Any]:
    """
    Apply deterministic multi-column sorting.

    ID is always used as the final tie-breaker, making ordering stable
    enough for keyset pagination.
    """
    result = list(items)

    fields = tuple(sort or ())

    if not fields:
        fields = (
            SortField(
                field="id",
                direction=SortDirection.ASC,
            ),
        )

    result.sort(
        key=cmp_to_key(
            lambda left, right: _compare_items(
                left,
                right,
                fields,
            ),
        ),
    )

    return result


def _cursor_position(
    item: Any,
    sort_field: str,
) -> tuple[str, str]:
    """Return the canonical cursor position for an item."""
    return (
        str(_attr(item, sort_field) or ""),
        str(_attr(item, "id") or ""),
    )


def apply_cursor(
    items: Sequence[Any],
    cursor: str | None,
    *,
    sort_field: str = "id",
    direction: SortDirection = SortDirection.ASC,
) -> list[Any]:
    """
    Apply keyset pagination after the supplied cursor.

    Cursor ordering matches the repository contract:

        (sort_value, id)

    ASC:
        position > cursor

    DESC:
        position < cursor
    """
    if not cursor:
        return list(items)

    token: Cursor = parse_cursor(cursor)

    cursor_position = (
        token.sort_value,
        token.last_id,
    )

    result: list[Any] = []

    for item in items:
        position = _cursor_position(
            item,
            sort_field,
        )

        if direction is SortDirection.DESC:
            if position < cursor_position:
                result.append(item)
        elif position > cursor_position:
            result.append(item)

    return result


def apply_query(
    items: Sequence[Any],
    *,
    filters: Sequence[FilterClause] | None = None,
    search: str | None = None,
    search_fields: Sequence[str] = (),
    sort: Sequence[SortField] | None = None,
    cursor: str | None = None,
    cursor_sort_field: str = "id",
    cursor_direction: SortDirection = SortDirection.ASC,
    limit: int | None = None,
) -> list[Any]:
    """
    Execute the complete in-memory query pipeline.

    Pipeline:

        filters
          ↓
        search
          ↓
        sort
          ↓
        cursor
          ↓
        limit
    """
    result = apply_filters(
        items,
        filters,
    )

    result = apply_search(
        result,
        search,
        search_fields,
    )

    result = apply_sort(
        result,
        sort,
    )

    result = apply_cursor(
        result,
        cursor,
        sort_field=cursor_sort_field,
        direction=cursor_direction,
    )

    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be >= 0")

        result = result[:limit]

    return result