"""NK ERP feature pack: Procure to Pay."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.schemas.documents import DocumentCreate
from {{cookiecutter.project_name}}.erp.services.documents import DocumentService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="procure_to_pay",
        name="Procure to Pay",
        requires=("db", "users", "erp_masters", "pricing_taxes", "inventory_management"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Get purchase order status by document id")
        async def purchase_order_status(order_id: str) -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            doc = await svc.get(uuid.UUID(order_id))
            return doc.status if doc else "not found"

        registry.register(purchase_order_status)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/buying", tags=["erp-features"])

        @router.post("/rfq")
        async def create_rfq(
            payload: DocumentCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.create("request_for_quotation", payload)
            return row.model_dump(mode="json")

        @router.post("/purchase-orders")
        async def create_purchase_order(
            payload: DocumentCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.create("purchase_order", payload, status="To Receive and Bill")
            return row.model_dump(mode="json")

        @router.get("/purchase-orders")
        async def list_purchase_orders(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> list[dict[str, Any]]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            rows = await svc.list_by_type("purchase_order")
            return [r.model_dump(mode="json") for r in rows]

        @router.post("/purchase-invoices")
        async def create_purchase_invoice(
            payload: DocumentCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.create("purchase_invoice", payload)
            return row.model_dump(mode="json")

        @router.get("/purchase-invoices")
        async def list_purchase_invoices(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> list[dict[str, Any]]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            rows = await svc.list_by_type("purchase_invoice")
            return [r.model_dump(mode="json") for r in rows]

        @router.get("/purchase-receipts")
        async def list_purchase_receipts(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> list[dict[str, Any]]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            rows = await svc.list_by_type("purchase_receipt")
            return [r.model_dump(mode="json") for r in rows]

        @router.post("/purchase-orders/{order_id}/receipts")
        async def make_purchase_receipt(
            order_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.map_document(order_id, "purchase_receipt")
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.post("/purchase-orders/{order_id}/purchase-invoices")
        async def make_purchase_invoice(
            order_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.map_document(order_id, "purchase_invoice")
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        return router


PACK = _Pack()
