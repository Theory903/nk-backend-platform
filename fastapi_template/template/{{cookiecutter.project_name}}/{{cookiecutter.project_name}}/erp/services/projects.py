"""Projects and timesheets service."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpProject, ErpTask, ErpTimesheet


class ProjectCreate(BaseModel):
    project_name: str = Field(min_length=1, max_length=200)
    customer_id: uuid.UUID | None = None


class TaskCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    project_id: uuid.UUID | None = None
    priority: str = "Medium"


class TimesheetCreate(BaseModel):
    employee_name: str = Field(min_length=1, max_length=200)
    project_id: uuid.UUID | None = None
    hours: float = Field(ge=0)
    billable: bool = True


class ProjectsService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def create_project(self, payload: ProjectCreate) -> ErpProject:
        row = ErpProject(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def create_task(self, payload: TaskCreate) -> ErpTask:
        row = ErpTask(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def create_timesheet(self, payload: TimesheetCreate) -> ErpTimesheet:
        row = ErpTimesheet(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_projects(self) -> list[ErpProject]:
        stmt = select(ErpProject).where(ErpProject.org_id == self._org_id).order_by(ErpProject.created_at.desc())
        return list((await self._session.scalars(stmt)).all())

    async def list_tasks(self, *, project_id: uuid.UUID | None = None) -> list[ErpTask]:
        stmt = select(ErpTask).where(ErpTask.org_id == self._org_id).order_by(ErpTask.created_at.desc())
        if project_id is not None:
            stmt = stmt.where(ErpTask.project_id == project_id)
        return list((await self._session.scalars(stmt)).all())

    async def list_timesheets(self) -> list[ErpTimesheet]:
        stmt = select(ErpTimesheet).where(ErpTimesheet.org_id == self._org_id).order_by(ErpTimesheet.created_at.desc())
        return list((await self._session.scalars(stmt)).all())

    async def project_progress(self) -> dict[str, float]:
        rows = await self.list_projects()
        if not rows:
            return {"average_percent_complete": 0.0}
        avg = sum(r.percent_complete for r in rows) / len(rows)
        return {"average_percent_complete": avg, "project_count": float(len(rows))}
