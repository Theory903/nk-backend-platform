from datetime import UTC, datetime, timedelta, timezone

import pytest

from {{cookiecutter.project_name}}.core.identifiers import (
    IdentifierError,
    is_valid_id,
    new_id,
)
from {{cookiecutter.project_name}}.core.time import ensure_utc, is_utc, utcnow


def test_new_id_uses_prefix_and_is_unique() -> None:
    """
    Identifiers carry their domain prefix and never collide.
    """
    first = new_id("usr")
    second = new_id("usr")

    assert first.startswith("usr_")
    assert second.startswith("usr_")
    assert first != second
    assert len(first.split("_", 1)[1]) == 32


def test_new_id_normalizes_prefix() -> None:
    """
    Prefixes are stripped and lowercased before validation.
    """
    value = new_id("  Usr  ")
    assert value.startswith("usr_")
    assert is_valid_id(value, prefix="usr")


def test_new_id_rejects_invalid_prefix() -> None:
    """
    Invalid prefixes raise IdentifierError.
    """
    with pytest.raises(IdentifierError):
        new_id("")
    with pytest.raises(IdentifierError):
        new_id("1usr")
    with pytest.raises(IdentifierError):
        new_id("USR!")
    with pytest.raises(IdentifierError):
        new_id("a" * 33)


def test_is_valid_id_without_prefix() -> None:
    """
    Generated IDs validate; malformed values do not.
    """
    value = new_id("evt")
    assert is_valid_id(value) is True
    assert is_valid_id("not-an-id") is False
    assert is_valid_id("evt_short") is False
    assert is_valid_id(123) is False  # type: ignore[arg-type]


def test_is_valid_id_with_prefix() -> None:
    """
    Optional prefix constrains validation to that domain.
    """
    value = new_id("file")
    assert is_valid_id(value, prefix="file") is True
    assert is_valid_id(value, prefix="usr") is False
    assert is_valid_id(value, prefix="  FILE  ") is True
    assert is_valid_id(value, prefix="1bad") is False


def test_utcnow_is_timezone_aware() -> None:
    """
    Timestamps are always timezone-aware UTC.
    """
    before = utcnow()
    moment = utcnow()
    after = utcnow()

    assert isinstance(moment, datetime)
    assert moment.tzinfo is not None
    assert is_utc(moment) is True
    assert moment.utcoffset() == timedelta(0)
    assert before <= moment <= after


def test_is_utc_true_for_utc_and_zero_offset() -> None:
    """
    Aware datetimes with a zero UTC offset count as UTC.
    """
    assert is_utc(datetime.now(UTC)) is True
    assert is_utc(datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)) is True
    assert is_utc(datetime(2026, 8, 27, 12, 0, tzinfo=timezone(timedelta(0)))) is True


def test_is_utc_false_for_naive_and_non_utc() -> None:
    """
    Naive and non-zero-offset datetimes are not UTC.
    """
    assert is_utc(datetime(2026, 8, 27, 12, 0)) is False
    assert is_utc(datetime(2026, 8, 27, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))) is False


def test_ensure_utc_converts_offset() -> None:
    """
    Offset-aware datetimes are normalized to UTC wall time.
    """
    ist = timezone(timedelta(hours=5, minutes=30))
    local = datetime(2026, 8, 27, 18, 30, tzinfo=ist)

    converted = ensure_utc(local)

    assert is_utc(converted) is True
    assert converted == datetime(2026, 8, 27, 13, 0, tzinfo=UTC)


def test_ensure_utc_rejects_naive() -> None:
    """
    Naive datetimes are rejected as ambiguous.
    """
    with pytest.raises(ValueError, match="naive datetime"):
        ensure_utc(datetime(2026, 8, 27, 12, 0))
