"""Tests for cursor-based pagination: encoding, mixin boundary, edge cases."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import pytest

from {{cookiecutter.project_name}}.core.pagination import (
    Cursor,
    CursorPage,
    CursorPaginationMixin,
    InvalidCursorVersion,
    MalformedCursor,
    make_cursor,
    parse_cursor,
)


class TestCursorEncoding:
    def test_roundtrip(self) -> None:
        original = Cursor(
            sort_value="2024-01-01T00:00:00",
            last_id="rec_abc123",
        )
        token = original.encode()
        decoded = Cursor.decode(token)
        assert decoded.sort_value == original.sort_value
        assert decoded.last_id == original.last_id
        assert decoded.version == 1

    def test_make_and_parse(self) -> None:
        token = make_cursor("2024-06-01", "item_42")
        cursor = parse_cursor(token)
        assert cursor.sort_value == "2024-06-01"
        assert cursor.last_id == "item_42"

    def test_malformed_cursor_raises(self) -> None:
        with pytest.raises(MalformedCursor, match="malformed"):
            parse_cursor("not-a-valid-cursor!!!")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(MalformedCursor):
            parse_cursor("")

    def test_non_object_payload_raises(self) -> None:
        raw = json.dumps([1, 2, 3]).encode("utf-8")
        token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        with pytest.raises(MalformedCursor, match="object"):
            parse_cursor(token)

    def test_invalid_version_raises(self) -> None:
        raw = json.dumps(
            {"v": 99, "s": "2024-01-01", "i": "rec_1"},
            separators=(",", ":"),
        ).encode("utf-8")
        token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        with pytest.raises(InvalidCursorVersion, match="unsupported"):
            parse_cursor(token)

    def test_missing_id_raises(self) -> None:
        raw = json.dumps(
            {"v": 1, "s": "2024-01-01", "i": ""},
            separators=(",", ":"),
        ).encode("utf-8")
        token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        with pytest.raises(MalformedCursor, match="empty"):
            parse_cursor(token)

    def test_unicode_sort_value(self) -> None:
        token = make_cursor("日本語テスト", "rec_1")
        cursor = parse_cursor(token)
        assert cursor.sort_value == "日本語テスト"


class TestCursorPage:
    def test_has_items(self) -> None:
        page = CursorPage(items=[1, 2], next_cursor=None, has_more=False)
        assert page.has_items

    def test_empty_page(self) -> None:
        page = CursorPage[int](items=[], next_cursor=None, has_more=False)
        assert not page.has_items
        assert page.next_cursor is None
        assert page.has_more is False


@dataclass
class FakeRecord:
    id: str
    created_at: str


class _InMemoryMixin(CursorPaginationMixin):
    """Apply the same composite boundary as SQLAlchemy mixin, in memory."""

    def paginate(
        self,
        records: list[FakeRecord],
        *,
        cursor_token: str | None,
        limit: int,
    ) -> CursorPage[FakeRecord]:
        cursor = parse_cursor(cursor_token) if cursor_token else None
        filtered = list(records)
        if cursor is not None:
            filtered = [
                r
                for r in filtered
                if (r.created_at > cursor.sort_value)
                or (
                    r.created_at == cursor.sort_value
                    and r.id > cursor.last_id
                )
            ]
        filtered.sort(key=lambda r: (r.created_at, r.id))
        rows = filtered[: limit + 1]
        return self.build_cursor_page(rows, limit=limit)


@pytest.fixture
def sample_records() -> list[FakeRecord]:
    return [
        FakeRecord(
            id=f"rec_{i:03d}",
            created_at=f"2024-01-{i + 1:02d}T00:00:00Z",
        )
        for i in range(20)
    ]


@pytest.fixture
def pager() -> _InMemoryMixin:
    return _InMemoryMixin()


class TestPaginationLogic:
    """Exercise limit+1 / has_more and composite cursor boundary."""

    def test_first_page(
        self,
        sample_records: list[FakeRecord],
        pager: _InMemoryMixin,
    ) -> None:
        page = pager.paginate(sample_records, cursor_token=None, limit=5)
        assert len(page.items) == 5
        assert page.has_more is True
        assert page.next_cursor is not None

    def test_has_more_via_limit_plus_one(
        self,
        sample_records: list[FakeRecord],
        pager: _InMemoryMixin,
    ) -> None:
        page = pager.paginate(sample_records, cursor_token=None, limit=3)
        assert page.has_more is True
        assert len(page.items) == 3

        last_page = pager.paginate(
            sample_records,
            cursor_token=None,
            limit=len(sample_records),
        )
        assert last_page.has_more is False
        assert last_page.next_cursor is None
        assert len(last_page.items) == len(sample_records)

    def test_empty_page(
        self,
        pager: _InMemoryMixin,
    ) -> None:
        page = pager.paginate([], cursor_token=None, limit=10)
        assert page.items == []
        assert page.has_more is False
        assert page.next_cursor is None

    def test_walk_all_pages_no_duplicates_or_gaps(
        self,
        sample_records: list[FakeRecord],
        pager: _InMemoryMixin,
    ) -> None:
        all_seen: list[str] = []
        cursor: str | None = None

        while True:
            page = pager.paginate(
                sample_records,
                cursor_token=cursor,
                limit=7,
            )
            all_seen.extend(r.id for r in page.items)
            if not page.has_more:
                break
            cursor = page.next_cursor

        assert len(all_seen) == len(set(all_seen))
        assert len(all_seen) == len(sample_records)

    def test_no_duplicate_on_shared_sort_value(
        self,
        pager: _InMemoryMixin,
    ) -> None:
        """Rows sharing created_at must advance by id with `>`, not `>=`."""
        shared = "2024-01-15T00:00:00Z"
        records = [
            FakeRecord(id="rec_a", created_at=shared),
            FakeRecord(id="rec_b", created_at=shared),
            FakeRecord(id="rec_c", created_at=shared),
            FakeRecord(id="rec_d", created_at="2024-01-16T00:00:00Z"),
        ]

        page1 = pager.paginate(records, cursor_token=None, limit=2)
        assert [r.id for r in page1.items] == ["rec_a", "rec_b"]
        assert page1.has_more is True

        page2 = pager.paginate(
            records,
            cursor_token=page1.next_cursor,
            limit=2,
        )
        assert [r.id for r in page2.items] == ["rec_c", "rec_d"]
        # Shared-sort boundary must not re-emit rec_a/rec_b.
        assert "rec_a" not in {r.id for r in page2.items}
        assert "rec_b" not in {r.id for r in page2.items}

        all_ids = [r.id for r in page1.items] + [r.id for r in page2.items]
        assert all_ids == ["rec_a", "rec_b", "rec_c", "rec_d"]

    def test_last_page_has_no_next_cursor(
        self,
        sample_records: list[FakeRecord],
        pager: _InMemoryMixin,
    ) -> None:
        page = pager.paginate(
            sample_records,
            cursor_token=None,
            limit=len(sample_records),
        )
        assert page.has_more is False
        assert page.next_cursor is None

    def test_limit_larger_than_dataset(
        self,
        sample_records: list[FakeRecord],
        pager: _InMemoryMixin,
    ) -> None:
        page = pager.paginate(sample_records, cursor_token=None, limit=1000)
        assert len(page.items) == len(sample_records)
        assert page.has_more is False

    def test_stable_under_concurrent_inserts(
        self,
        sample_records: list[FakeRecord],
        pager: _InMemoryMixin,
    ) -> None:
        page1 = pager.paginate(sample_records, cursor_token=None, limit=5)
        seen_ids = {r.id for r in page1.items}

        new_record = FakeRecord(
            id="rec_new",
            created_at="2024-02-15T00:00:00Z",
        )
        expanded = sample_records + [new_record]

        cursor = page1.next_cursor
        while True:
            page = pager.paginate(
                expanded,
                cursor_token=cursor,
                limit=100,
            )
            seen_ids.update(r.id for r in page.items)
            if not page.has_more:
                break
            cursor = page.next_cursor

        assert seen_ids == {r.id for r in sample_records} | {"rec_new"}

    def test_apply_cursor_uses_strict_gt(
        self,
        pager: _InMemoryMixin,
    ) -> None:
        """Mixin.apply_cursor must compose `>` / `==`+`>` (not `>=`)."""

        @dataclass(frozen=True)
        class Expr:
            op: str
            left: Any
            right: Any

            def __or__(self, other: Any) -> Expr:
                return Expr("|", self, other)

            def __and__(self, other: Any) -> Expr:
                return Expr("&", self, other)

        class FakeCol:
            def __init__(self, name: str) -> None:
                self.name = name
                self.ops: list[str] = []

            def __gt__(self, other: Any) -> Expr:
                self.ops.append(">")
                return Expr(">", self.name, other)

            def __ge__(self, other: Any) -> Expr:
                self.ops.append(">=")
                return Expr(">=", self.name, other)

            def __eq__(self, other: Any) -> Expr:  # type: ignore[override]
                self.ops.append("==")
                return Expr("==", self.name, other)

            def asc(self) -> str:
                return f"{self.name}.asc()"

        class FakeModel:
            created_at = FakeCol("created_at")
            id = FakeCol("id")

        class FakeQuery:
            def __init__(self) -> None:
                self.where_clause: Any = None
                self.limit_n: int | None = None

            def where(self, clause: Any) -> FakeQuery:
                self.where_clause = clause
                return self

            def order_by(self, *args: Any) -> FakeQuery:
                return self

            def limit(self, n: int) -> FakeQuery:
                self.limit_n = n
                return self

        cursor = Cursor(sort_value="ts", last_id="id_1")
        query = FakeQuery()
        result = pager.apply_cursor(
            query,
            cursor=cursor,
            limit=5,
            model_class=FakeModel,
        )

        assert result.limit_n == 6  # limit + 1
        clause = result.where_clause
        assert isinstance(clause, Expr)
        assert clause.op == "|"
        assert clause.left == Expr(">", "created_at", "ts")
        assert clause.right == Expr(
            "&",
            Expr("==", "created_at", "ts"),
            Expr(">", "id", "id_1"),
        )
        assert ">=" not in FakeModel.created_at.ops
        assert ">=" not in FakeModel.id.ops
