"""Dunning and collections — overdue AR identification."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpDocument, ErpPaymentLedger


class DunningService:
    """Identify overdue receivables and assign dunning levels."""

    LEVELS = (
        (30, "Reminder 1"),
        (60, "Reminder 2"),
        (90, "Final Notice"),
    )

    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def overdue_receivables(self, *, as_of: date | None = None) -> list[dict[str, Any]]:
        today = as_of or date.today()
        stmt = select(ErpPaymentLedger).where(
            ErpPaymentLedger.org_id == self._org_id,
            ErpPaymentLedger.party_type == "Customer",
            ErpPaymentLedger.outstanding > 0,
        )
        rows = list((await self._session.scalars(stmt)).all())
        overdue: list[dict[str, Any]] = []
        for row in rows:
            doc = await self._session.scalar(
                select(ErpDocument).where(
                    ErpDocument.org_id == self._org_id,
                    ErpDocument.id == row.voucher_id,
                )
            )
            if doc is None or doc.posting_date is None:
                continue
            terms = int((doc.meta or {}).get("payment_terms_days") or 30)
            due = doc.posting_date + timedelta(days=terms)
            if due >= today:
                continue
            days_overdue = (today - due).days
            level = self._dunning_level(days_overdue)
            overdue.append(
                {
                    "party_id": str(row.party_id),
                    "voucher_id": str(row.voucher_id),
                    "voucher_type": row.voucher_type,
                    "outstanding": row.outstanding,
                    "due_date": due.isoformat(),
                    "days_overdue": days_overdue,
                    "dunning_level": level,
                }
            )
        overdue.sort(key=lambda r: -r["days_overdue"])
        return overdue

    async def dunning_summary(self) -> str:
        rows = await self.overdue_receivables()
        if not rows:
            return "no overdue receivables"
        total = sum(r["outstanding"] for r in rows)
        return f"{len(rows)} overdue entries, total outstanding={total:.2f}"

    def _dunning_level(self, days_overdue: int) -> str:
        label = "Overdue"
        for threshold, name in self.LEVELS:
            if days_overdue >= threshold:
                label = name
        return label
