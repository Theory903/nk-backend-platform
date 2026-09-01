"""Simple document approval workflow — ERPNext workflow port (subset)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.erp.services.documents import DocumentService
from {{cookiecutter.project_name}}.erp.services.lifecycle import DocStatus

# action → allowed from-status → new status
WORKFLOW: dict[str, dict[str, str]] = {
    "sales_order": {
        "submit_for_approval": ("Draft", "Pending Approval"),
        "approve": ("Pending Approval", "Approved"),
        "reject": ("Pending Approval", "Rejected"),
    },
    "purchase_order": {
        "submit_for_approval": ("Draft", "Pending Approval"),
        "approve": ("Pending Approval", "Approved"),
        "reject": ("Pending Approval", "Rejected"),
    },
    "sales_invoice": {
        "submit_for_approval": ("Draft", "Pending Approval"),
        "approve": ("Pending Approval", "Approved"),
        "reject": ("Pending Approval", "Rejected"),
    },
}


class WorkflowService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id
        self._docs = DocumentService(session, org_id=org_id)

    async def transition(self, doc_id: uuid.UUID, action: str) -> dict[str, Any]:
        row = await self._docs.get(doc_id)
        if row is None:
            raise LookupError(f"document {doc_id} not found")
        rules = WORKFLOW.get(row.doctype, {})
        if action not in rules:
            raise ValueError(f"action {action!r} not allowed for {row.doctype}")
        from_status, to_status = rules[action]
        if row.status != from_status:
            raise ValueError(f"document status must be {from_status!r}, got {row.status!r}")
        updated = await self._docs.set_status(doc_id, to_status)
        if action == "approve" and updated.docstatus == DocStatus.DRAFT:
            updated = await self._docs.submit(doc_id)
        return updated.model_dump(mode="json")

    def allowed_actions(self, doctype: str, status: str) -> list[str]:
        rules = WORKFLOW.get(doctype, {})
        return [action for action, (frm, _to) in rules.items() if frm == status]
