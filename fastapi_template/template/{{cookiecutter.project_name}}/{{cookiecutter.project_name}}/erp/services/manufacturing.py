"""Manufacturing BOM and work order service."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpBom, ErpWorkOrder


class BomCreate(BaseModel):
    item_code: str
    quantity: float = 1.0
    items: list[dict[str, Any]] = Field(default_factory=list)


class WorkOrderCreate(BaseModel):
    production_item: str
    bom_id: uuid.UUID | None = None
    qty: float = Field(default=1.0, gt=0)


class ManufacturingService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def create_bom(self, payload: BomCreate) -> ErpBom:
        row = ErpBom(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def create_work_order(self, payload: WorkOrderCreate) -> ErpWorkOrder:
        row = ErpWorkOrder(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_boms(self) -> list[ErpBom]:
        stmt = select(ErpBom).where(ErpBom.org_id == self._org_id, ErpBom.is_active.is_(True))
        return list((await self._session.scalars(stmt)).all())

    async def bom_explosion(self, item_code: str) -> dict[str, Any]:
        stmt = select(ErpBom).where(ErpBom.org_id == self._org_id, ErpBom.item_code == item_code)
        bom = await self._session.scalar(stmt)
        if bom is None:
            return {"item_code": item_code, "components": []}
        return {"item_code": item_code, "components": bom.items, "quantity": bom.quantity}

    async def production_plan(self) -> list[dict[str, Any]]:
        stmt = select(ErpWorkOrder).where(ErpWorkOrder.org_id == self._org_id).order_by(ErpWorkOrder.created_at.desc())
        rows = (await self._session.scalars(stmt)).all()
        return [
            {
                "id": str(r.id),
                "production_item": r.production_item,
                "qty": r.qty,
                "status": r.status,
            }
            for r in rows
        ]
