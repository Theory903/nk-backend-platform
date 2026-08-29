"""Typed query primitives for filtering, sorting, searching and pagination.

Query construction is deliberately separate from repository execution.

The flow is:

    request
      -> parse
      -> validate against QueryAllowList
      -> normalize
      -> repository adapter

Only allow-listed fields can reach the persistence layer. This prevents
clients from turning query parameters into arbitrary database expressions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FilterOp(StrEnum):
    """Supported filter operations."""

    EQ = "eq"
    NEQ = "neq"
    IN = "in"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"


class SortDirection(StrEnum):
    """Supported sort directions."""

    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True, slots=True)
class FilterClause:
    """A single validated filter expression."""

    field: str
    op: FilterOp
    value: Any

    def __post_init__(self) -> None:
        if not self.field.strip():
            raise ValueError(
                "filter field must not be empty"
            )

        if self.op == FilterOp.IN:
            if isinstance(
                self.value,
                (str, bytes),
            ):
                raise ValueError(
                    "IN filter value must be a sequence"
                )

            if not isinstance(
                self.value,
                Sequence,
            ):
                raise ValueError(
                    "IN filter value must be a sequence"
                )


@dataclass(frozen=True, slots=True)
class SortField:
    """A validated sort expression."""

    field: str
    direction: SortDirection = SortDirection.ASC

    def __post_init__(self) -> None:
        if not self.field.strip():
            raise ValueError(
                "sort field must not be empty"
            )


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """
    Normalized query passed from the service layer to repositories.

    Repository adapters should execute this object rather than raw HTTP
    query parameters.
    """

    filters: tuple[FilterClause, ...] = ()
    sort: tuple[SortField, ...] = ()
    search: str | None = None
    cursor: str | None = None
    limit: int = 25
    include_deleted: bool = False

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError(
                "limit must be greater than zero"
            )

        if self.search is not None:
            normalized = self.search.strip()

            object.__setattr__(
                self,
                "search",
                normalized or None,
            )

        if self.cursor is not None:
            normalized = self.cursor.strip()

            object.__setattr__(
                self,
                "cursor",
                normalized or None,
            )


@dataclass(frozen=True, slots=True)
class QueryAllowList:
    """
    Per-resource query policy.

    Example:

        QueryAllowList(
            filter_fields=frozenset({"status", "owner_id"}),
            sort_fields=frozenset({"created_at", "name"}),
            search_fields=frozenset({"name", "email"}),
        )

    Field names are compared exactly. Never interpolate unvalidated client
    field names into SQL.
    """

    filter_fields: frozenset[str] = field(
        default_factory=frozenset
    )

    sort_fields: frozenset[str] = field(
        default_factory=frozenset
    )

    search_fields: frozenset[str] = field(
        default_factory=frozenset
    )

    def validate(
        self,
        query: QuerySpec,
    ) -> None:
        """Validate every query component against the resource policy."""

        self.validate_filters(
            query.filters
        )
        self.validate_sort(
            query.sort
        )
        self.validate_search(
            query.search
        )

    def validate_filters(
        self,
        filters: Sequence[FilterClause],
    ) -> None:
        """Validate filter fields."""

        if not filters:
            return

        if not self.filter_fields:
            raise ValueError(
                "filtering is not enabled for this resource"
            )

        self._validate_fields(
            (
                clause.field
                for clause in filters
            ),
            self.filter_fields,
            "filter",
        )

    def validate_sort(
        self,
        sort: Sequence[SortField],
    ) -> None:
        """Validate sort fields."""

        if not sort:
            return

        if not self.sort_fields:
            raise ValueError(
                "sorting is not enabled for this resource"
            )

        self._validate_fields(
            (
                item.field
                for item in sort
            ),
            self.sort_fields,
            "sort",
        )

    def validate_search(
        self,
        search: str | None,
    ) -> None:
        """Validate search configuration."""

        if not search:
            return

        if not self.search_fields:
            raise ValueError(
                "search is not enabled for this resource"
            )

    @staticmethod
    def _validate_fields(
        fields: Sequence[str] | Any,
        allowed: frozenset[str],
        kind: str,
    ) -> None:
        for name in fields:
            if name not in allowed:
                raise ValueError(
                    f"{kind} field {name!r} is not allowed"
                )

    def supports_filter(
        self,
        field: str,
    ) -> bool:
        """Return whether a filter field is allowed."""

        return field in self.filter_fields

    def supports_sort(
        self,
        field: str,
    ) -> bool:
        """Return whether a sort field is allowed."""

        return field in self.sort_fields

    def supports_search(
        self,
        field: str,
    ) -> bool:
        """Return whether a search field is allowed."""

        return field in self.search_fields


def normalize_query(
    query: QuerySpec,
    allow_list: QueryAllowList,
    *,
    max_limit: int = 100,
) -> QuerySpec:
    """
    Validate and normalize a query before repository execution.

    This is the boundary where untrusted API query state becomes an
    application-level query object.
    """

    if max_limit <= 0:
        raise ValueError(
            "max_limit must be greater than zero"
        )

    allow_list.validate(
        query
    )

    limit = min(
        query.limit,
        max_limit,
    )

    return QuerySpec(
        filters=tuple(
            query.filters
        ),
        sort=tuple(
            query.sort
        ),
        search=query.search,
        cursor=query.cursor,
        limit=limit,
        include_deleted=query.include_deleted,
    )


__all__ = [
    "FilterClause",
    "FilterOp",
    "QueryAllowList",
    "QuerySpec",
    "SortDirection",
    "SortField",
    "normalize_query",
]