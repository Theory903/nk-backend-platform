"""CRM persistence and conversion service."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpLead, ErpOpportunity
from {{cookiecutter.project_name}}.erp.schemas.crm import LeadCreate, LeadRead, OpportunityCreate, OpportunityRead
from {{cookiecutter.project_name}}.erp.schemas.masters import CustomerCreate
from {{cookiecutter.project_name}}.erp.services.masters import MastersService


def _lead_display_name(payload: LeadCreate) -> str:
    parts = [payload.first_name or "", payload.last_name or ""]
    name = " ".join(p for p in parts if p).strip()
    if name:
        return name
    return payload.company_name or payload.email_id or "Lead"


class CrmService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id
        self._masters = MastersService(session, org_id=org_id)

    async def create_lead(self, payload: LeadCreate) -> LeadRead:
        row = ErpLead(
            org_id=self._org_id,
            lead_name=_lead_display_name(payload),
            **payload.model_dump(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return LeadRead.model_validate(row, from_attributes=True)

    async def get_lead(self, lead_id: uuid.UUID) -> ErpLead | None:
        stmt = select(ErpLead).where(ErpLead.org_id == self._org_id, ErpLead.id == lead_id)
        return await self._session.scalar(stmt)

    async def list_leads(self, *, limit: int = 50) -> list[LeadRead]:
        stmt = (
            select(ErpLead)
            .where(ErpLead.org_id == self._org_id)
            .order_by(ErpLead.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [LeadRead.model_validate(row, from_attributes=True) for row in rows]

    async def convert_lead_to_customer(self, lead_id: uuid.UUID) -> dict[str, object]:
        lead = await self.get_lead(lead_id)
        if lead is None:
            raise LookupError(f"lead {lead_id} not found")
        customer = await self._masters.create_customer(
            CustomerCreate(
                customer_name=lead.company_name or lead.lead_name,
                email_id=lead.email_id,
                mobile_no=lead.mobile_no,
            )
        )
        lead.customer_id = customer.id
        lead.status = "Converted"
        await self._session.flush()
        return {"lead_id": str(lead_id), "customer": customer.model_dump(mode="json")}

    async def create_opportunity(self, payload: OpportunityCreate) -> OpportunityRead:
        row = ErpOpportunity(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return OpportunityRead.model_validate(row, from_attributes=True)

    async def list_opportunities(self, *, limit: int = 50) -> list[OpportunityRead]:
        stmt = (
            select(ErpOpportunity)
            .where(ErpOpportunity.org_id == self._org_id)
            .order_by(ErpOpportunity.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [OpportunityRead.model_validate(row, from_attributes=True) for row in rows]

    async def pipeline_summary(self) -> dict[str, int]:
        stmt = (
            select(ErpLead.status, func.count())
            .where(ErpLead.org_id == self._org_id)
            .group_by(ErpLead.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {status: count for status, count in rows}
