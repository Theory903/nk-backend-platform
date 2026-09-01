"""NK ERP feature pack: Projects & Timesheets."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.services.projects import (
    ProjectCreate,
    ProjectsService,
    TaskCreate,
    TimesheetCreate,
)


class _Pack:
    meta = ErpFeaturePackMeta(
        id="projects_delivery",
        name="Projects & Timesheets",
        requires=("db", "users", "erp_masters"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Average project completion percent")
        async def project_progress() -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            stats = await ProjectsService(ctx.db_session, org_id=ctx.org_id()).project_progress()
            return str(stats)

        registry.register(project_progress)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/projects", tags=["erp-features"])

        @router.post("/projects")
        async def create_project(
            payload: ProjectCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            row = await ProjectsService(ctx.db_session, org_id=ctx.org_id()).create_project(payload)
            return {"id": str(row.id), "project_name": row.project_name, "status": row.status}

        @router.post("/tasks")
        async def create_task(
            payload: TaskCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            row = await ProjectsService(ctx.db_session, org_id=ctx.org_id()).create_task(payload)
            return {"id": str(row.id), "subject": row.subject, "status": row.status}

        @router.post("/timesheets")
        async def create_timesheet(
            payload: TimesheetCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            row = await ProjectsService(ctx.db_session, org_id=ctx.org_id()).create_timesheet(payload)
            return {"id": str(row.id), "hours": row.hours, "billable": row.billable}

        @router.get("/projects")
        async def list_projects(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            rows = await ProjectsService(ctx.db_session, org_id=ctx.org_id()).list_projects()
            return [
                {
                    "id": str(r.id),
                    "project_name": r.project_name,
                    "status": r.status,
                    "percent_complete": r.percent_complete,
                }
                for r in rows
            ]

        @router.get("/tasks")
        async def list_tasks(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
            project_id: uuid.UUID | None = None,
        ) -> list[dict[str, Any]]:
            rows = await ProjectsService(ctx.db_session, org_id=ctx.org_id()).list_tasks(project_id=project_id)
            return [{"id": str(r.id), "subject": r.subject, "status": r.status, "project_id": str(r.project_id or "")} for r in rows]

        return router


PACK = _Pack()
