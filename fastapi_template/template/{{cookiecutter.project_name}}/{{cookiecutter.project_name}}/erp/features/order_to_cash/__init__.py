"""NK ERP feature pack: Order to Cash."""

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
        id="order_to_cash",
        name="Order to Cash",
        requires=("db", "users", "erp_masters", "pricing_taxes", "inventory_management"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Get sales order status by document id")
        async def sales_order_status(order_id: str) -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            doc = await svc.get(uuid.UUID(order_id))
            return doc.status if doc else "not found"

        registry.register(sales_order_status)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/selling", tags=["erp-features"])

        @router.post("/quotations")
        async def create_quotation(
            payload: DocumentCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.create("quotation", payload)
            return row.model_dump(mode="json")

        @router.get("/quotations")
        async def list_quotations(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            rows = await svc.list_by_type("quotation")
            return [r.model_dump(mode="json") for r in rows]

        @router.post("/sales-orders")
        async def create_sales_order(
            payload: DocumentCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.create("sales_order", payload, status="To Deliver and Bill")
            return row.model_dump(mode="json")

        @router.get("/sales-orders")
        async def list_sales_orders(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            rows = await svc.list_by_type("sales_order")
            return [r.model_dump(mode="json") for r in rows]

        @router.post("/sales-invoices")
        async def create_sales_invoice(
            payload: DocumentCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.create("sales_invoice", payload)
            return row.model_dump(mode="json")

        @router.get("/sales-invoices")
        async def list_sales_invoices(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> list[dict[str, Any]]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            rows = await svc.list_by_type("sales_invoice")
            return [r.model_dump(mode="json") for r in rows]

        @router.get("/delivery-notes")
        async def list_delivery_notes(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> list[dict[str, Any]]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            rows = await svc.list_by_type("delivery_note")
            return [r.model_dump(mode="json") for r in rows]

        @router.post("/sales-orders/{order_id}/delivery-notes")
        async def make_delivery_note(
            order_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.map_document(order_id, "delivery_note")
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.post("/sales-orders/{order_id}/sales-invoices")
        async def make_sales_invoice(
            order_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DocumentService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.map_document(order_id, "sales_invoice")
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        return router


PACK = _Pack()
