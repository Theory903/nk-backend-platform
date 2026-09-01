"""Support issue and SLA service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpIssue
from {{cookiecutter.project_name}}.erp.schemas.support import IssueCreate, IssueRead, IssueStatusUpdate


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SupportService:
    DEFAULT_RESPONSE_HOURS = 8
    DEFAULT_RESOLUTION_HOURS = 24

    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    def _apply_sla(self, issue: ErpIssue) -> None:
        now = _utcnow()
        issue.agreement_status = "First Response Due"
        issue.response_by = now + timedelta(hours=self.DEFAULT_RESPONSE_HOURS)
        issue.sla_resolution_by = now + timedelta(hours=self.DEFAULT_RESOLUTION_HOURS)

    async def create_issue(self, payload: IssueCreate) -> IssueRead:
        row = ErpIssue(org_id=self._org_id, **payload.model_dump())
        self._apply_sla(row)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return IssueRead.model_validate(row, from_attributes=True)

    async def get_issue(self, issue_id: uuid.UUID) -> ErpIssue | None:
        stmt = select(ErpIssue).where(ErpIssue.org_id == self._org_id, ErpIssue.id == issue_id)
        return await self._session.scalar(stmt)

    async def list_issues(self, *, limit: int = 50) -> list[IssueRead]:
        stmt = (
            select(ErpIssue)
            .where(ErpIssue.org_id == self._org_id)
            .order_by(ErpIssue.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [IssueRead.model_validate(row, from_attributes=True) for row in rows]

    async def bulk_set_status(self, payload: IssueStatusUpdate) -> dict[str, int]:
        updated = 0
        for issue_id in payload.names:
            issue = await self.get_issue(issue_id)
            if issue is None:
                continue
            issue.status = payload.status
            if payload.status == "Resolved":
                issue.agreement_status = "Fulfilled"
            updated += 1
        await self._session.flush()
        return {"updated": updated}

    async def split_issue(self, issue_id: uuid.UUID, *, subject: str) -> IssueRead:
        parent = await self.get_issue(issue_id)
        if parent is None:
            raise LookupError(f"issue {issue_id} not found")
        child = ErpIssue(
            org_id=self._org_id,
            subject=subject,
            description=parent.description,
            priority=parent.priority,
            issue_type=parent.issue_type,
            customer_id=parent.customer_id,
            issue_split_from=parent.id,
        )
        self._apply_sla(child)
        self._session.add(child)
        await self._session.flush()
        await self._session.refresh(child)
        return IssueRead.model_validate(child, from_attributes=True)

    async def open_issue_count(self) -> int:
        stmt = select(func.count()).where(
            ErpIssue.org_id == self._org_id,
            ErpIssue.status.in_(("Open", "Replied", "On Hold")),
        )
        return int(await self._session.scalar(stmt) or 0)

    async def sla_status(self, issue_id: uuid.UUID) -> dict[str, object]:
        issue = await self.get_issue(issue_id)
        if issue is None:
            raise LookupError(f"issue {issue_id} not found")
        now = _utcnow()
        return {
            "issue_id": str(issue.id),
            "status": issue.status,
            "agreement_status": issue.agreement_status,
            "response_by": issue.response_by.isoformat() if issue.response_by else None,
            "sla_resolution_by": issue.sla_resolution_by.isoformat() if issue.sla_resolution_by else None,
            "response_overdue": bool(issue.response_by and now > issue.response_by),
            "resolution_overdue": bool(issue.sla_resolution_by and now > issue.sla_resolution_by),
        }
