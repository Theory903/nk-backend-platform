"""Bank reconciliation — ERPNext Bank Transaction / reconciliation port."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpBankTransaction, ErpPaymentLedger
from {{cookiecutter.project_name}}.erp.schemas.bank import BankImportRequest, BankMatchSuggestion, BankReconcileRequest, BankRowImport


class BankReconciliationService:
    """Import bank lines, suggest matches, reconcile against payment ledger."""

    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def import_rows(self, payload: BankImportRequest) -> dict[str, Any]:
        created: list[str] = []
        for row in payload.rows:
            entity = ErpBankTransaction(
                org_id=self._org_id,
                bank_account=row.bank_account,
                posting_date=row.posting_date,
                description=row.description,
                deposit=row.deposit,
                withdrawal=row.withdrawal,
                reference=row.reference,
            )
            self._session.add(entity)
            await self._session.flush()
            created.append(str(entity.id))
        return {"imported": len(created), "ids": created}

    def parse_csv(self, content: str, *, bank_account: str = "Cash - NK") -> BankImportRequest:
        reader = csv.DictReader(io.StringIO(content.strip()))
        rows: list[BankRowImport] = []
        for raw in reader:
            date_str = (raw.get("date") or raw.get("posting_date") or "").strip()
            posting = date.fromisoformat(date_str) if date_str else date.today()
            deposit = float(raw.get("deposit") or raw.get("credit") or 0)
            withdrawal = float(raw.get("withdrawal") or raw.get("debit") or 0)
            rows.append(
                BankRowImport(
                    bank_account=raw.get("bank_account") or bank_account,
                    posting_date=posting,
                    description=str(raw.get("description") or raw.get("narration") or ""),
                    deposit=deposit,
                    withdrawal=withdrawal,
                    reference=raw.get("reference"),
                )
            )
        if not rows:
            raise ValueError("CSV contained no data rows")
        return BankImportRequest(rows=rows)

    async def list_transactions(self, *, reconciled: bool | None = None) -> list[dict[str, Any]]:
        stmt = select(ErpBankTransaction).where(ErpBankTransaction.org_id == self._org_id)
        if reconciled is not None:
            stmt = stmt.where(ErpBankTransaction.is_reconciled.is_(reconciled))
        stmt = stmt.order_by(ErpBankTransaction.posting_date.desc())
        rows = (await self._session.scalars(stmt)).all()
        return [
            {
                "id": str(row.id),
                "bank_account": row.bank_account,
                "posting_date": row.posting_date.isoformat(),
                "description": row.description,
                "deposit": row.deposit,
                "withdrawal": row.withdrawal,
                "reference": row.reference,
                "is_reconciled": row.is_reconciled,
                "matched_voucher_type": row.matched_voucher_type,
                "matched_voucher_id": str(row.matched_voucher_id) if row.matched_voucher_id else None,
            }
            for row in rows
        ]

    async def suggest_matches(self, *, limit: int = 20) -> list[dict[str, Any]]:
        bank_rows = await self.list_transactions(reconciled=False)
        stmt = select(ErpPaymentLedger).where(
            ErpPaymentLedger.org_id == self._org_id,
            ErpPaymentLedger.outstanding > 0,
        )
        ledger_rows = list((await self._session.scalars(stmt)).all())
        suggestions: list[dict[str, Any]] = []
        for bank in bank_rows[:limit]:
            amount = float(bank["deposit"] or bank["withdrawal"])
            if not amount:
                continue
            for ledger in ledger_rows:
                if abs(ledger.outstanding - amount) > 0.01:
                    continue
                suggestions.append(
                    BankMatchSuggestion(
                        bank_transaction_id=uuid.UUID(bank["id"]),
                        voucher_type=ledger.voucher_type,
                        voucher_id=ledger.voucher_id,
                        amount=ledger.outstanding,
                        score=1.0,
                    ).model_dump(mode="json")
                )
        return suggestions

    async def reconcile(self, payload: BankReconcileRequest) -> dict[str, Any]:
        bank = await self._session.scalar(
            select(ErpBankTransaction).where(
                ErpBankTransaction.org_id == self._org_id,
                ErpBankTransaction.id == payload.bank_transaction_id,
            )
        )
        if bank is None:
            raise LookupError("bank transaction not found")
        if bank.is_reconciled:
            raise ValueError("bank transaction already reconciled")
        ledger = await self._session.scalar(
            select(ErpPaymentLedger).where(
                ErpPaymentLedger.org_id == self._org_id,
                ErpPaymentLedger.voucher_type == payload.voucher_type,
                ErpPaymentLedger.voucher_id == payload.voucher_id,
            )
        )
        if ledger is None:
            raise LookupError("payment ledger entry not found")
        amount = bank.deposit or bank.withdrawal
        applied = min(ledger.outstanding, amount)
        ledger.outstanding -= applied
        bank.is_reconciled = True
        bank.matched_voucher_type = payload.voucher_type
        bank.matched_voucher_id = payload.voucher_id
        await self._session.flush()
        return {
            "bank_transaction_id": str(bank.id),
            "voucher_id": str(payload.voucher_id),
            "amount_applied": applied,
            "ledger_outstanding": ledger.outstanding,
        }
