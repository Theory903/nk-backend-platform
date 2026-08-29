from __future__ import annotations

import asyncio
from collections import defaultdict

from pydantic import ValidationError

from {{cookiecutter.project_name}}.industry.fintech.ledger.models import (
    JournalEntry,
    JournalStatus,
    LedgerDirection,
    LedgerLine,
    MAX_MINOR,
)


class LedgerInvariantError(ValueError):
    pass


class DuplicateReferenceError(ValueError):
    pass


class ImmutableEntryError(RuntimeError):
    pass


class LedgerService:
    def __init__(self, maker_checker_threshold_minor: int = 1_000_000_00) -> None:
        self._entries: dict[str, JournalEntry] = {}
        self._by_ref: dict[str, str] = {}
        self._lines: dict[str, list[LedgerLine]] = {}
        self._balances: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._threshold = maker_checker_threshold_minor

    async def post_transaction(
        self,
        lines: list[LedgerLine],
        external_reference: str,
        org_id: str,
    ) -> JournalEntry:
        if not lines:
            raise LedgerInvariantError("at least one line required")
        if external_reference in self._by_ref:
            raise DuplicateReferenceError(f"duplicate external_reference: {external_reference}")
        entry_id = lines[0].entry_id
        if any(ln.entry_id != entry_id for ln in lines):
            raise LedgerInvariantError("all lines must share same entry_id")
        debit = sum(ln.amount_minor for ln in lines if ln.direction == LedgerDirection.debit)
        credit = sum(ln.amount_minor for ln in lines if ln.direction == LedgerDirection.credit)
        if debit != credit:
            raise LedgerInvariantError(f"unbalanced: debit {debit} != credit {credit}")
        if debit > MAX_MINOR or credit > MAX_MINOR:
            raise LedgerInvariantError("amount overflow")
        status = JournalStatus.pending_approval if debit > self._threshold else JournalStatus.posted
        entry = JournalEntry(
            id=entry_id,
            org_id=org_id,
            external_reference=external_reference,
            status=status,
        )
        async with self._lock:
            if external_reference in self._by_ref:
                raise DuplicateReferenceError(f"duplicate external_reference: {external_reference}")
            self._entries[entry_id] = entry
            self._by_ref[external_reference] = entry_id
            self._lines[entry_id] = list(lines)
            if status == JournalStatus.posted:
                for ln in lines:
                    delta = ln.amount_minor if ln.direction == LedgerDirection.debit else -ln.amount_minor
                    self._balances[ln.account_id] += delta
        return entry

    async def approve_entry(self, entry_id: str, approver_id: str) -> JournalEntry:  # noqa: ARG002
        async with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                raise KeyError(entry_id)
            if entry.status != JournalStatus.pending_approval:
                raise LedgerInvariantError("only pending_approval can be approved")
            new_entry = JournalEntry(
                id=entry.id,
                org_id=entry.org_id,
                external_reference=entry.external_reference,
                status=JournalStatus.posted,
                created_at=entry.created_at,
            )
            self._entries[entry_id] = new_entry
            for ln in self._lines.get(entry_id, []):
                delta = ln.amount_minor if ln.direction == LedgerDirection.debit else -ln.amount_minor
                self._balances[ln.account_id] += delta
            return new_entry

    def get_balance(self, account_id: str) -> int:
        return self._balances.get(account_id, 0)

    def get_statement(self, account_id: str, limit: int = 50, offset: int = 0) -> list[LedgerLine]:
        all_lines: list[LedgerLine] = []
        for lines in self._lines.values():
            for ln in lines:
                if ln.account_id == account_id:
                    all_lines.append(ln)
        return all_lines[offset : offset + limit]

    def get_entry(self, entry_id: str) -> JournalEntry | None:
        return self._entries.get(entry_id)

    def update_entry(self, entry_id: str, **kwargs: object) -> None:  # noqa: ARG002
        raise ImmutableEntryError("journal entries are append-only, update forbidden")

    def delete_entry(self, entry_id: str) -> None:  # noqa: ARG002
        raise ImmutableEntryError("journal entries are append-only, delete forbidden")
