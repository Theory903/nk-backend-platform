"""Support / SLA schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


ISSUE_STATUSES = ("Open", "Replied", "On Hold", "Resolved", "Closed")


class IssueCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    description: str | None = None
    priority: str = Field(default="Medium", max_length=32)
    issue_type: str | None = None
    customer_id: uuid.UUID | None = None


class IssueRead(IssueCreate):
    id: uuid.UUID
    org_id: str
    status: str
    agreement_status: str | None = None
    response_by: datetime | None = None
    sla_resolution_by: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IssueStatusUpdate(BaseModel):
    names: list[uuid.UUID] = Field(min_length=1)
    status: str = Field(min_length=1)
