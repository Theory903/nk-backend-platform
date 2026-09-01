"""CRM schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


LEAD_STATUSES = (
    "Lead",
    "Open",
    "Replied",
    "Opportunity",
    "Quotation",
    "Lost Quotation",
    "Interested",
    "Converted",
    "Do Not Contact",
)


class LeadCreate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    email_id: str | None = None
    mobile_no: str | None = None
    status: str = Field(default="Lead")
    source: str | None = None


class LeadRead(LeadCreate):
    id: uuid.UUID
    org_id: str
    lead_name: str
    created_at: datetime
    updated_at: datetime


class OpportunityCreate(BaseModel):
    opportunity_from: str = Field(default="Lead")
    party_name: str = Field(min_length=1, max_length=200)
    status: str = Field(default="Open")
    sales_stage: str = Field(default="Prospecting")
    probability: float = Field(default=10.0, ge=0, le=100)
    expected_closing: datetime | None = None


class OpportunityRead(OpportunityCreate):
    id: uuid.UUID
    org_id: str
    created_at: datetime
    updated_at: datetime
