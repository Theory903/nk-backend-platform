"""General ledger service."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpGlEntry


class GlLine(BaseModel):
    account: str = Field(min_length=1, max_length=128)
    debit: float = Field(default=0.0, ge=0)
    credit: float = Field(default=0.0, ge=0)


class JournalEntryCreate(BaseModel):
    posting_date: date | None = None
    lines: list[GlLine] = Field(min_length=2)
    voucher_type: str = "Journal Entry"
    voucher_id: uuid.UUID | None = None


class LedgerService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def post_journal(self, payload: JournalEntryCreate) -> dict[str, Any]:
        debit_total = sum(line.debit for line in payload.lines)
        credit_total = sum(line.credit for line in payload.lines)
        if round(debit_total, 2) != round(credit_total, 2):
            raise ValueError("debits and credits must balance")
        posting = payload.posting_date or date.today()
        voucher_id = payload.voucher_id or uuid.uuid4()
        rows: list[ErpGlEntry] = []
        for line in payload.lines:
            row = ErpGlEntry(
                org_id=self._org_id,
                account=line.account,
                debit=line.debit,
                credit=line.credit,
                voucher_type=payload.voucher_type,
                voucher_id=voucher_id,
                posting_date=posting,
            )
            self._session.add(row)
            rows.append(row)
        await self._session.flush()
        return {
            "voucher_id": str(voucher_id),
            "posting_date": posting.isoformat(),
            "entries": len(rows),
            "debit_total": debit_total,
            "credit_total": credit_total,
        }

    async def trial_balance(self) -> list[dict[str, Any]]:
        stmt = (
            select(
                ErpGlEntry.account,
                func.sum(ErpGlEntry.debit).label("debit"),
                func.sum(ErpGlEntry.credit).label("credit"),
            )
            .where(ErpGlEntry.org_id == self._org_id)
            .group_by(ErpGlEntry.account)
            .order_by(ErpGlEntry.account)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "account": account,
                "debit": float(debit or 0),
                "credit": float(credit or 0),
                "balance": float(debit or 0) - float(credit or 0),
            }
            for account, debit, credit in rows
        ]

    async def general_ledger_entries(self) -> list[dict[str, Any]]:
        stmt = (
            select(ErpGlEntry)
            .where(ErpGlEntry.org_id == self._org_id)
            .order_by(ErpGlEntry.posting_date.desc(), ErpGlEntry.account)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [
            {
                "posting_date": row.posting_date.isoformat(),
                "account": row.account,
                "debit": row.debit,
                "credit": row.credit,
                "voucher_type": row.voucher_type or "",
                "voucher_no": str(row.voucher_id)[:13] if row.voucher_id else "",
            }
            for row in rows
        ]
