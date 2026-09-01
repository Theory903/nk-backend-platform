"""NK ERP feature pack: Manufacturing Operations."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.services.manufacturing import BomCreate, ManufacturingService, WorkOrderCreate


class _Pack:
    meta = ErpFeaturePackMeta(
        id="manufacturing_ops",
        name="Manufacturing Operations",
        requires=("db", "inventory_management", "procure_to_pay"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Explode BOM components for an item code")
        async def bom_explosion(item_code: str) -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            result = await ManufacturingService(ctx.db_session, org_id=ctx.org_id()).bom_explosion(item_code)
            return str(result)

        registry.register(bom_explosion)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/manufacturing", tags=["erp-features"])

        @router.post("/bom")
        async def create_bom(
            payload: BomCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            row = await ManufacturingService(ctx.db_session, org_id=ctx.org_id()).create_bom(payload)
            return {"id": str(row.id), "item_code": row.item_code, "items": row.items}

        @router.post("/work-orders")
        async def create_work_order(
            payload: WorkOrderCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            row = await ManufacturingService(ctx.db_session, org_id=ctx.org_id()).create_work_order(payload)
            return {"id": str(row.id), "production_item": row.production_item, "status": row.status}

        @router.get("/production-plan")
        async def production_plan(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            return await ManufacturingService(ctx.db_session, org_id=ctx.org_id()).production_plan()

        return router


PACK = _Pack()
