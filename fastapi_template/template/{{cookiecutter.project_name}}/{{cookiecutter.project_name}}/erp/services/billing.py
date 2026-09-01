"""AR/AP and payment ledger service."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpDocument, ErpPaymentLedger
from {{cookiecutter.project_name}}.erp.services.report_data import build_receivable_row, parse_ageing_ranges


class PaymentLedgerCreate(BaseModel):
    party_type: str
    party_id: uuid.UUID
    voucher_type: str
    voucher_id: uuid.UUID
    amount: float
    outstanding: float | None = None
    payment_term: str | None = None
    due_date: date | None = None


class ReconcileRequest(BaseModel):
    party_type: str
    party_id: uuid.UUID
    amount: float = Field(gt=0)


class BillingService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def record(self, payload: PaymentLedgerCreate) -> dict[str, Any]:
        row = ErpPaymentLedger(
            org_id=self._org_id,
            party_type=payload.party_type,
            party_id=payload.party_id,
            voucher_type=payload.voucher_type,
            voucher_id=payload.voucher_id,
            amount=payload.amount,
            outstanding=payload.outstanding if payload.outstanding is not None else payload.amount,
            payment_term=payload.payment_term,
            due_date=payload.due_date,
        )
        self._session.add(row)
        await self._session.flush()
        return {"id": str(row.id), "outstanding": row.outstanding}

    async def accounts_receivable(self) -> list[dict[str, Any]]:
        return await self.receivable_payable_detail("Customer")

    async def accounts_payable(self) -> list[dict[str, Any]]:
        return await self.receivable_payable_detail("Supplier")

    async def receivable_payable_detail(
        self,
        party_type: str,
        *,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        report_date = date.fromisoformat(str(filters["report_date"])) if filters.get("report_date") else date.today()
        ranges = parse_ageing_ranges(str(filters.get("range") or filters.get("ageing_range") or ""))
        party_account = "Debtors - NK" if party_type == "Customer" else "Creditors - NK"

        stmt = (
            select(ErpPaymentLedger)
            .where(
                ErpPaymentLedger.org_id == self._org_id,
                ErpPaymentLedger.party_type == party_type,
                ErpPaymentLedger.outstanding > 0,
            )
            .order_by(ErpPaymentLedger.created_at.desc())
        )
        ledger_rows = list((await self._session.scalars(stmt)).all())
        if not ledger_rows:
            return []

        voucher_ids = {row.voucher_id for row in ledger_rows}
        doc_stmt = select(ErpDocument).where(
            ErpDocument.org_id == self._org_id,
            ErpDocument.id.in_(voucher_ids),
        )
        docs = {doc.id: doc for doc in (await self._session.scalars(doc_stmt)).all()}

        rows: list[dict[str, Any]] = []
        for entry in ledger_rows:
            doc = docs.get(entry.voucher_id)
            posting_date = doc.posting_date if doc and doc.posting_date else entry.created_at.date()
            due_date = entry.due_date or (posting_date + timedelta(days=int(filters.get("credit_days") or 30)))
            voucher_no = doc.docname if doc else str(entry.voucher_id)[:13]
            payment_term = entry.payment_term or ""
            rows.append(
                build_receivable_row(
                    party_type=party_type,
                    party=str(entry.party_id),
                    party_account=party_account,
                    voucher_type=entry.voucher_type,
                    voucher_no=voucher_no,
                    posting_date=posting_date,
                    due_date=due_date,
                    amount=float(entry.amount),
                    outstanding=float(entry.outstanding),
                    report_date=report_date,
                    ranges=ranges,
                    currency=doc.currency if doc else "USD",
                    payment_term=payment_term,
                )
            )
        return rows

    async def receivable_summary(self, party_type: str) -> list[dict[str, Any]]:
        stmt = (
            select(
                ErpPaymentLedger.party_id,
                func.sum(ErpPaymentLedger.amount).label("invoiced"),
                func.sum(ErpPaymentLedger.outstanding).label("outstanding"),
            )
            .where(
                ErpPaymentLedger.org_id == self._org_id,
                ErpPaymentLedger.party_type == party_type,
                ErpPaymentLedger.outstanding > 0,
            )
            .group_by(ErpPaymentLedger.party_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "party_type": party_type,
                "party": str(pid),
                "invoiced": float(invoiced or 0),
                "paid": float(invoiced or 0) - float(outstanding or 0),
                "outstanding": float(outstanding or 0),
            }
            for pid, invoiced, outstanding in rows
        ]

    async def _outstanding(self, party_type: str) -> list[dict[str, Any]]:
        stmt = (
            select(
                ErpPaymentLedger.party_id,
                func.sum(ErpPaymentLedger.outstanding).label("outstanding"),
            )
            .where(
                ErpPaymentLedger.org_id == self._org_id,
                ErpPaymentLedger.party_type == party_type,
                ErpPaymentLedger.outstanding > 0,
            )
            .group_by(ErpPaymentLedger.party_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return [{"party_id": str(pid), "outstanding": float(out or 0)} for pid, out in rows]

    async def reconcile(self, payload: ReconcileRequest) -> dict[str, Any]:
        stmt = select(ErpPaymentLedger).where(
            ErpPaymentLedger.org_id == self._org_id,
            ErpPaymentLedger.party_type == payload.party_type,
            ErpPaymentLedger.party_id == payload.party_id,
            ErpPaymentLedger.outstanding > 0,
        )
        rows = list((await self._session.scalars(stmt)).all())
        remaining = payload.amount
        cleared = 0
        for row in rows:
            if remaining <= 0:
                break
            applied = min(row.outstanding, remaining)
            row.outstanding -= applied
            remaining -= applied
            cleared += 1
        await self._session.flush()
        return {"entries_touched": cleared, "amount_applied": payload.amount - remaining}

    async def outstanding_summary(self) -> str:
        ar = await self.accounts_receivable()
        ap = await self.accounts_payable()
        ar_total = sum(r["outstanding"] for r in ar)
        ap_total = sum(r["outstanding"] for r in ap)
        return f"AR={ar_total:.2f} AP={ap_total:.2f}"
