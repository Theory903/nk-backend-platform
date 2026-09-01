"""Stock ledger service."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpStockLedgerEntry


class StockEntryCreate(BaseModel):
    item_code: str
    warehouse: str = "Stores - Default"
    qty: float
    valuation_rate: float = 0.0
    voucher_type: str = "Stock Entry"
    voucher_id: uuid.UUID | None = None


class StockService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def post_entry(self, payload: StockEntryCreate) -> dict[str, Any]:
        voucher_id = payload.voucher_id or uuid.uuid4()
        row = ErpStockLedgerEntry(
            org_id=self._org_id,
            item_code=payload.item_code,
            warehouse=payload.warehouse,
            qty=payload.qty,
            valuation_rate=payload.valuation_rate,
            voucher_type=payload.voucher_type,
            voucher_id=voucher_id,
        )
        self._session.add(row)
        await self._session.flush()
        return {"voucher_id": str(voucher_id), "item_code": payload.item_code, "qty": payload.qty}

    async def balance(self, *, item_code: str | None = None) -> list[dict[str, Any]]:
        stmt = select(
            ErpStockLedgerEntry.item_code,
            ErpStockLedgerEntry.warehouse,
            func.sum(ErpStockLedgerEntry.qty).label("qty"),
        ).where(ErpStockLedgerEntry.org_id == self._org_id)
        if item_code:
            stmt = stmt.where(ErpStockLedgerEntry.item_code == item_code)
        stmt = stmt.group_by(ErpStockLedgerEntry.item_code, ErpStockLedgerEntry.warehouse)
        rows = (await self._session.execute(stmt)).all()
        return [
            {"item_code": ic, "warehouse": wh, "qty": float(qty or 0)}
            for ic, wh, qty in rows
        ]

    async def balance_replica(self) -> list[dict[str, Any]]:
        rows = await self.balance()
        return [
            {
                "item_code": row["item_code"],
                "item_name": row["item_code"],
                "warehouse": row["warehouse"],
                "bal_qty": row["qty"],
                "bal_val": 0.0,
            }
            for row in rows
        ]

    async def ledger_entries(self) -> list[dict[str, Any]]:
        stmt = (
            select(ErpStockLedgerEntry)
            .where(ErpStockLedgerEntry.org_id == self._org_id)
            .order_by(ErpStockLedgerEntry.created_at.asc())
        )
        rows = list((await self._session.scalars(stmt)).all())
        running: dict[tuple[str, str], float] = {}
        out: list[dict[str, Any]] = []
        for row in rows:
            key = (row.item_code, row.warehouse)
            running[key] = running.get(key, 0.0) + float(row.qty)
            out.append(
                {
                    "posting_date": row.created_at.date().isoformat(),
                    "item_code": row.item_code,
                    "warehouse": row.warehouse,
                    "actual_qty": row.qty,
                    "qty_after_transaction": running[key],
                    "valuation_rate": row.valuation_rate,
                    "voucher_type": row.voucher_type,
                    "voucher_no": str(row.voucher_id)[:13],
                }
            )
        return out
