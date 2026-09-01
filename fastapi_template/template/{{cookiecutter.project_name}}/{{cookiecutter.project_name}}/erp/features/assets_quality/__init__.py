"""NK ERP feature pack: Assets, Quality & Maintenance."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.services.assets import (
    AssetCreate,
    AssetsService,
    InspectionCreate,
    MaintenanceVisitCreate,
)


class _Pack:
    meta = ErpFeaturePackMeta(
        id="assets_quality",
        name="Assets, Quality & Maintenance",
        requires=("db", "erp_masters"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Depreciation schedule for an asset id")
        async def asset_depreciation_schedule(asset_id: str) -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            svc = AssetsService(ctx.db_session, org_id=ctx.org_id())
            try:
                return str(await svc.depreciation_schedule(uuid.UUID(asset_id)))
            except (LookupError, ValueError) as exc:
                return str(exc)

        registry.register(asset_depreciation_schedule)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/assets", tags=["erp-features"])

        @router.post("/assets")
        async def create_asset(
            payload: AssetCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            row = await AssetsService(ctx.db_session, org_id=ctx.org_id()).create_asset(payload)
            return {"id": str(row.id), "asset_name": row.asset_name, "status": row.status}

        @router.post("/quality-inspections")
        async def create_inspection(
            payload: InspectionCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            row = await AssetsService(ctx.db_session, org_id=ctx.org_id()).create_inspection(payload)
            return {"id": str(row.id), "item_code": row.item_code, "status": row.status}

        @router.post("/maintenance-visits")
        async def create_maintenance_visit(
            payload: MaintenanceVisitCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            row = await AssetsService(ctx.db_session, org_id=ctx.org_id()).create_maintenance_visit(payload)
            return {"id": str(row.id), "purpose": row.purpose, "status": row.status}

        @router.get("/assets/{asset_id}/depreciation")
        async def depreciation(
            asset_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            try:
                return await AssetsService(ctx.db_session, org_id=ctx.org_id()).depreciation_schedule(asset_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        return router


PACK = _Pack()
