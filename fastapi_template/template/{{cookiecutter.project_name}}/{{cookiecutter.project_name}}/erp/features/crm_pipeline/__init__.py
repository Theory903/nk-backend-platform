"""NK ERP feature pack: CRM & Sales Pipeline."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.schemas.crm import LeadCreate, OpportunityCreate
from {{cookiecutter.project_name}}.erp.services.crm import CrmService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="crm_pipeline",
        name="CRM & Sales Pipeline",
        requires=("db", "users", "erp_masters"),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: ErpFeatureContext | None = None,
    ) -> None:
        @agent_tool("Summarize CRM pipeline stages and counts")
        async def crm_pipeline_summary() -> str:
            if ctx is None or ctx.db_session is None:
                return "CRM pipeline unavailable (no db session)"
            service = CrmService(ctx.db_session, org_id=ctx.org_id())
            summary = await service.pipeline_summary()
            return str(summary)

        registry.register(crm_pipeline_summary)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/crm", tags=["erp-features"])

        @router.post("/leads")
        async def create_lead(
            payload: LeadCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = CrmService(ctx.db_session, org_id=ctx.org_id())
            row = await service.create_lead(payload)
            return row.model_dump(mode="json")

        @router.get("/leads")
        async def list_leads(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            service = CrmService(ctx.db_session, org_id=ctx.org_id())
            rows = await service.list_leads()
            return [row.model_dump(mode="json") for row in rows]

        @router.post("/leads/{lead_id}/convert/customer")
        async def convert_lead_customer(
            lead_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = CrmService(ctx.db_session, org_id=ctx.org_id())
            try:
                return await service.convert_lead_to_customer(lead_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @router.post("/opportunities")
        async def create_opportunity(
            payload: OpportunityCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = CrmService(ctx.db_session, org_id=ctx.org_id())
            row = await service.create_opportunity(payload)
            return row.model_dump(mode="json")

        @router.get("/opportunities")
        async def list_opportunities(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> list[dict[str, Any]]:
            service = CrmService(ctx.db_session, org_id=ctx.org_id())
            rows = await service.list_opportunities()
            return [row.model_dump(mode="json") for row in rows]

        @router.get("/reports/pipeline")
        async def pipeline_report(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> dict[str, int]:
            service = CrmService(ctx.db_session, org_id=ctx.org_id())
            return await service.pipeline_summary()

        return router


PACK = _Pack()
