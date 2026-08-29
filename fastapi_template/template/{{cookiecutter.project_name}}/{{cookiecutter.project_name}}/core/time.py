"""Timezone-aware UTC time primitives."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    """
    Return the current timezone-aware UTC timestamp.
    """

    return datetime.now(UTC)


def is_utc(value: datetime) -> bool:
    """
    Return whether ``value`` is timezone-aware and represents UTC.
    """

    if value.tzinfo is None:
        return False

    return value.utcoffset() == timedelta(0)


def ensure_utc(value: datetime) -> datetime:
    """
    Normalize an aware datetime to UTC.

    Naive datetimes are rejected because their timezone is ambiguous.
    """

    if value.tzinfo is None:
        raise ValueError(
            "naive datetime is not allowed; timezone information is required"
        )

    return value.astimezone(UTC)


__all__ = [
    "ensure_utc",
    "is_utc",
    "utcnow",
]
