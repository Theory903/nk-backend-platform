"""NK ERP feature pack: Document lifecycle hub (submit / cancel / amend)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.services.documents import DocumentService
from {{cookiecutter.project_name}}.erp.services.workflow import WorkflowService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="documents_hub",
        name="Document Lifecycle Hub",
        requires=("db", "pricing_taxes"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Submit an ERP document by id (ERPNext docstatus=1)")
        async def submit_erp_document(document_id: str) -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.submit(uuid.UUID(document_id))
            except (LookupError, ValueError) as exc:
                return str(exc)
            return f"submitted {row.docname} status={row.erpnext_status}"

        registry.register(submit_erp_document)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/documents", tags=["erp-features"])

        @router.get("/{doc_id}")
        async def get_document(
            doc_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.get(doc_id)
            if row is None:
                raise HTTPException(status_code=404, detail="document not found")
            return svc._read(row).model_dump(mode="json")

        @router.post("/{doc_id}/submit")
        async def submit_document(
            doc_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.submit(doc_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.post("/{doc_id}/cancel")
        async def cancel_document(
            doc_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.cancel(doc_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.post("/{doc_id}/amend")
        async def amend_document(
            doc_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.amend(doc_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.get("/{doc_id}/status")
        async def document_status(
            doc_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, str]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.get(doc_id)
            if row is None:
                raise HTTPException(status_code=404, detail="document not found")
            read = svc._read(row)
            return {
                "docname": read.docname,
                "status": read.status,
                "erpnext_status": read.erpnext_status or read.status,
                "docstatus": str(read.docstatus),
            }

        @router.get("/{doc_id}/workflow/actions")
        async def workflow_actions(
            doc_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.get(doc_id)
            if row is None:
                raise HTTPException(status_code=404, detail="document not found")
            wf = WorkflowService(ctx.db_session, org_id=ctx.org_id())
            return {
                "doctype": row.doctype,
                "status": row.status,
                "allowed_actions": wf.allowed_actions(row.doctype, row.status),
            }

        @router.post("/{doc_id}/workflow/{action}")
        async def workflow_transition(
            doc_id: uuid.UUID,
            action: str,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            wf = WorkflowService(ctx.db_session, org_id=ctx.org_id())
            try:
                return await wf.transition(doc_id, action)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        return router


PACK = _Pack()
