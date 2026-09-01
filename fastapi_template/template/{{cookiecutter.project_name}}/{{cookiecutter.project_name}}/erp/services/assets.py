"""Assets, quality, and maintenance service."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpAsset, ErpMaintenanceVisit, ErpQualityInspection


class AssetCreate(BaseModel):
    asset_name: str = Field(min_length=1, max_length=200)
    item_code: str | None = None
    gross_purchase_amount: float = Field(default=0.0, ge=0)
    depreciation_method: str = "Straight Line"


class InspectionCreate(BaseModel):
    item_code: str
    inspection_type: str = "Incoming"
    status: str = "Accepted"
    readings: list[dict[str, Any]] = Field(default_factory=list)


class MaintenanceVisitCreate(BaseModel):
    purpose: str = Field(min_length=1, max_length=500)
    customer_id: uuid.UUID | None = None


class AssetsService:
    STRAIGHT_LINE_YEARS = 5

    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def create_asset(self, payload: AssetCreate) -> ErpAsset:
        row = ErpAsset(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def create_inspection(self, payload: InspectionCreate) -> ErpQualityInspection:
        row = ErpQualityInspection(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def create_maintenance_visit(self, payload: MaintenanceVisitCreate) -> ErpMaintenanceVisit:
        row = ErpMaintenanceVisit(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def depreciation_schedule(self, asset_id: uuid.UUID) -> dict[str, Any]:
        stmt = select(ErpAsset).where(ErpAsset.org_id == self._org_id, ErpAsset.id == asset_id)
        asset = await self._session.scalar(stmt)
        if asset is None:
            raise LookupError(f"asset {asset_id} not found")
        annual = asset.gross_purchase_amount / self.STRAIGHT_LINE_YEARS
        return {
            "asset_id": str(asset.id),
            "asset_name": asset.asset_name,
            "method": asset.depreciation_method,
            "annual_depreciation": round(annual, 2),
            "years": self.STRAIGHT_LINE_YEARS,
        }

    async def list_assets(self) -> list[dict[str, Any]]:
        stmt = select(ErpAsset).where(ErpAsset.org_id == self._org_id).order_by(ErpAsset.created_at.desc())
        rows = (await self._session.scalars(stmt)).all()
        return [
            {
                "asset_name": r.asset_name,
                "status": r.status,
                "gross_purchase_amount": r.gross_purchase_amount,
            }
            for r in rows
        ]
