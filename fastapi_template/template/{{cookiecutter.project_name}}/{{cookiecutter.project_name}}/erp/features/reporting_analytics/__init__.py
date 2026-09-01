"""NK ERP feature pack: ERP Reporting Engine."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.services.reports import ReportRequest, ReportsService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="reporting_analytics",
        name="ERP Reporting Engine",
        requires=("db",),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Run an ERP report by name")
        async def run_erp_report(report: str) -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            result = await ReportsService(ctx.db_session, org_id=ctx.org_id()).run(ReportRequest(report=report))
            return f"rows={len(result.get('data', []))}"

        registry.register(run_erp_report)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/reports", tags=["erp-features"])

        @router.get("/catalog")
        async def report_catalog(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, str]]:
            return ReportsService(ctx.db_session, org_id=ctx.org_id()).catalog()

        @router.post("/run")
        async def run_report(
            payload: ReportRequest,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            return await ReportsService(ctx.db_session, org_id=ctx.org_id()).run(payload)

        return router


PACK = _Pack()
