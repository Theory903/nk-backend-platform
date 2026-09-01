"""NK ERP feature pack: Support & SLA Management."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.schemas.support import IssueCreate, IssueStatusUpdate
from {{cookiecutter.project_name}}.erp.services.support import SupportService


class SplitPayload(BaseModel):
    subject: str = Field(min_length=1, max_length=500)


class _Pack:
    meta = ErpFeaturePackMeta(
        id="support_sla",
        name="Support & SLA Management",
        requires=("db", "users", "erp_masters"),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: ErpFeatureContext | None = None,
    ) -> None:
        @agent_tool("Count open support issues")
        async def open_issues_count() -> str:
            if ctx is None or ctx.db_session is None:
                return "0"
            service = SupportService(ctx.db_session, org_id=ctx.org_id())
            count = await service.open_issue_count()
            return str(count)

        registry.register(open_issues_count)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/support", tags=["erp-features"])

        @router.post("/issues")
        async def create_issue(
            payload: IssueCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = SupportService(ctx.db_session, org_id=ctx.org_id())
            row = await service.create_issue(payload)
            return row.model_dump(mode="json")

        @router.get("/issues")
        async def list_issues(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            service = SupportService(ctx.db_session, org_id=ctx.org_id())
            rows = await service.list_issues()
            return [row.model_dump(mode="json") for row in rows]

        @router.patch("/issues/status")
        async def bulk_set_status(
            payload: IssueStatusUpdate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, int]:
            service = SupportService(ctx.db_session, org_id=ctx.org_id())
            return await service.bulk_set_status(payload)

        @router.post("/issues/{issue_id}/split")
        async def split_issue(
            issue_id: uuid.UUID,
            payload: SplitPayload,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = SupportService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await service.split_issue(issue_id, subject=payload.subject)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.get("/issues/{issue_id}/sla")
        async def sla_status(
            issue_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, object]:
            service = SupportService(ctx.db_session, org_id=ctx.org_id())
            try:
                return await service.sla_status(issue_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        return router


PACK = _Pack()
