"""Production cursor-based pagination.

Uses a stable composite cursor:

    (sort_value, id)

The cursor is opaque, URL-safe, validated, and versioned.

Ordering:

    sort_value ASC, id ASC

Next page condition:

    sort_value > cursor.sort_value
    OR
    (
        sort_value == cursor.sort_value
        AND id > cursor.last_id
    )

This avoids duplicates/skips when multiple rows share the same
sort value.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")

_CURSOR_VERSION = 1
_MAX_CURSOR_BYTES = 4096


class CursorError(ValueError):
    """Base cursor validation error."""


class MalformedCursor(CursorError):
    """Cursor cannot be decoded or has an invalid structure."""


class InvalidCursorVersion(CursorError):
    """Cursor version is unsupported."""


@dataclass(frozen=True, slots=True)
class Cursor:
    """Opaque cursor representing the last item in a page."""

    sort_value: str
    last_id: str
    version: int = _CURSOR_VERSION

    def encode(self) -> str:
        """Encode cursor into a compact URL-safe token."""

        payload = {
            "v": self.version,
            "s": self.sort_value,
            "i": self.last_id,
        }

        raw = json.dumps(
            payload,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        encoded = base64.urlsafe_b64encode(
            raw
        ).rstrip(b"=")

        return encoded.decode("ascii")

    @classmethod
    def decode(
        cls,
        token: str,
    ) -> Cursor:
        """Decode and validate an opaque cursor."""

        if not isinstance(token, str) or not token:
            raise MalformedCursor(
                "cursor must be a non-empty string"
            )

        if len(token) > _MAX_CURSOR_BYTES:
            raise MalformedCursor(
                "cursor exceeds maximum size"
            )

        try:
            # Restore base64 padding.
            padded = token.encode("ascii")
            padded += b"=" * (
                (-len(padded)) % 4
            )

            raw = base64.urlsafe_b64decode(
                padded
            )

            payload = json.loads(
                raw.decode("utf-8")
            )

        except (
            UnicodeError,
            UnicodeEncodeError,
            UnicodeDecodeError,
            ValueError,
            TypeError,
            binascii.Error,
            json.JSONDecodeError,
        ) as exc:
            raise MalformedCursor(
                "malformed cursor"
            ) from exc

        if not isinstance(payload, dict):
            raise MalformedCursor(
                "cursor payload must be an object"
            )

        version = payload.get("v")

        if version != _CURSOR_VERSION:
            raise InvalidCursorVersion(
                f"unsupported cursor version: {version!r}"
            )

        sort_value = payload.get("s")
        last_id = payload.get("i")

        if not isinstance(sort_value, str):
            raise MalformedCursor(
                "cursor sort value must be a string"
            )

        if not isinstance(last_id, str):
            raise MalformedCursor(
                "cursor id must be a string"
            )

        if not last_id:
            raise MalformedCursor(
                "cursor id must not be empty"
            )

        return cls(
            sort_value=sort_value,
            last_id=last_id,
            version=version,
        )


@dataclass(frozen=True, slots=True)
class CursorPage(Generic[T]):
    """A page of cursor-paginated results."""

    items: list[T]
    next_cursor: str | None
    has_more: bool

    @property
    def has_items(self) -> bool:
        return bool(self.items)


def make_cursor(
    sort_value: str,
    last_id: str,
) -> str:
    """Create an opaque pagination cursor."""

    if not last_id:
        raise ValueError(
            "last_id must not be empty"
        )

    return Cursor(
        sort_value=str(sort_value),
        last_id=str(last_id),
    ).encode()


def parse_cursor(
    token: str,
) -> Cursor:
    """Parse and validate a pagination cursor."""

    return Cursor.decode(token)


class CursorPaginationMixin:
    """
    SQLAlchemy cursor-pagination helper.

    The model must expose:

        id
        created_at

    Override ``cursor_sort_field`` when another stable field is desired.

    The sort field and ID together form the pagination boundary.
    """

    cursor_sort_field: str = "created_at"
    cursor_id_field: str = "id"

    def _cursor_columns(
        self,
        model_class: Any,
    ) -> tuple[Any, Any]:
        try:
            sort_column = getattr(
                model_class,
                self.cursor_sort_field,
            )
            id_column = getattr(
                model_class,
                self.cursor_id_field,
            )
        except AttributeError as exc:
            raise ValueError(
                f"{model_class!r} must define "
                f"{self.cursor_sort_field!r} and "
                f"{self.cursor_id_field!r}"
            ) from exc

        return sort_column, id_column

    def apply_cursor(
        self,
        query: Any,
        *,
        cursor: Cursor | None,
        limit: int,
        model_class: Any,
    ) -> Any:
        """
        Apply stable cursor filtering and ordering.

        Fetches ``limit + 1`` rows so callers can determine ``has_more``
        without running an expensive COUNT query.
        """

        if limit <= 0:
            raise ValueError(
                "limit must be greater than zero"
            )

        sort_column, id_column = self._cursor_columns(
            model_class
        )

        if cursor is not None:
            query = query.where(
                (
                    sort_column > cursor.sort_value
                )
                | (
                    (sort_column == cursor.sort_value)
                    & (
                        id_column > cursor.last_id
                    )
                )
            )

        return (
            query
            .order_by(
                sort_column.asc(),
                id_column.asc(),
            )
            .limit(limit + 1)
        )

    def build_cursor_page(
        self,
        rows: list[T],
        *,
        limit: int,
    ) -> CursorPage[T]:
        """Build a page and its next cursor."""

        if limit <= 0:
            raise ValueError(
                "limit must be greater than zero"
            )

        has_more = len(rows) > limit
        items = list(rows[:limit])

        if not items:
            return CursorPage(
                items=[],
                next_cursor=None,
                has_more=False,
            )

        if not has_more:
            return CursorPage(
                items=items,
                next_cursor=None,
                has_more=False,
            )

        last = items[-1]

        sort_value = getattr(
            last,
            self.cursor_sort_field,
            None,
        )

        last_id = getattr(
            last,
            self.cursor_id_field,
            None,
        )

        if sort_value is None:
            raise ValueError(
                f"last item has no "
                f"{self.cursor_sort_field!r}"
            )

        if last_id is None:
            raise ValueError(
                f"last item has no "
                f"{self.cursor_id_field!r}"
            )

        next_cursor = make_cursor(
            str(sort_value),
            str(last_id),
        )

        return CursorPage(
            items=items,
            next_cursor=next_cursor,
            has_more=True,
        )


__all__ = [
    "Cursor",
    "CursorError",
    "CursorPage",
    "CursorPaginationMixin",
    "InvalidCursorVersion",
    "MalformedCursor",
    "make_cursor",
    "parse_cursor",
]