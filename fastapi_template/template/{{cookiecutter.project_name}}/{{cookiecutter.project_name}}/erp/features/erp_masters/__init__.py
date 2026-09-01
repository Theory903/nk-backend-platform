"""NK ERP feature pack: ERP Master Data."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.schemas.masters import (
    CustomerCreate,
    CustomerRead,
    ItemCreate,
    ItemRead,
    PaymentTermCreate,
    PaymentTermRead,
    PaymentTermsTemplateCreate,
    PaymentTermsTemplateRead,
    SupplierCreate,
    SupplierRead,
)
from {{cookiecutter.project_name}}.erp.services.masters import MastersService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="erp_masters",
        name="ERP Master Data",
        requires=("db", "users"),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: ErpFeatureContext | None = None,
    ) -> None:
        @agent_tool("Look up an item master by code")
        async def lookup_item(item_code: str) -> str:
            if ctx is None or ctx.db_session is None:
                return f"item:{item_code} (no db session)"
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            row = await service.get_item_by_code(item_code)
            if row is None:
                return f"item {item_code} not found"
            return f"{row.item_code}: {row.item_name} @ {row.standard_rate}"

        registry.register(lookup_item)

        @agent_tool("Look up a customer or supplier party name")
        async def lookup_party(party_type: str, name: str) -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            row = await service.lookup_party(party_type, name)
            if row is None:
                return f"{party_type}:{name} not found"
            return f"{row['party_type']} {row['name']} id={row['party_id']}"

        registry.register(lookup_party)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/masters", tags=["erp-features"])

        @router.get("/items")
        async def list_items(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            rows = await service.list_items()
            return [row.model_dump(mode="json") for row in rows]

        @router.post("/items")
        async def create_item(
            payload: ItemCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            row = await service.create_item(payload)
            return row.model_dump(mode="json")

        @router.get("/customers")
        async def list_customers(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            rows = await service.list_customers()
            return [row.model_dump(mode="json") for row in rows]

        @router.post("/customers")
        async def create_customer(
            payload: CustomerCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            row = await service.create_customer(payload)
            return row.model_dump(mode="json")

        @router.get("/suppliers")
        async def list_suppliers(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            rows = await service.list_suppliers()
            return [row.model_dump(mode="json") for row in rows]

        @router.post("/suppliers")
        async def create_supplier(
            payload: SupplierCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            row = await service.create_supplier(payload)
            return row.model_dump(mode="json")

        @router.get("/parties/{party_type}/{name}")
        async def lookup_party_route(
            party_type: str,
            name: str,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, str]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            row = await service.lookup_party(party_type, name)
            if row is None:
                raise HTTPException(status_code=404, detail="party not found")
            return row

        @router.get("/payment-terms")
        async def list_payment_terms(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            rows = await service.list_payment_terms()
            return [row.model_dump(mode="json") for row in rows]

        @router.post("/payment-terms")
        async def create_payment_term(
            payload: PaymentTermCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            row = await service.create_payment_term(payload)
            return row.model_dump(mode="json")

        @router.get("/payment-terms-templates")
        async def list_payment_terms_templates(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            rows = await service.list_payment_terms_templates()
            return [row.model_dump(mode="json") for row in rows]

        @router.post("/payment-terms-templates")
        async def create_payment_terms_template(
            payload: PaymentTermsTemplateCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            service = MastersService(ctx.db_session, org_id=ctx.org_id())
            row = await service.create_payment_terms_template(payload)
            return row.model_dump(mode="json")

        return router


PACK = _Pack()
