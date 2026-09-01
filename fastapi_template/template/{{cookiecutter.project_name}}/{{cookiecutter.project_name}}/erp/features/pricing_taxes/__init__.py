"""NK ERP feature pack: Pricing & Tax Engine."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.schemas.transaction import TransactionDocument
from {{cookiecutter.project_name}}.erp.services.item_details import ItemDetailsService
from {{cookiecutter.project_name}}.erp.services.regional_tax import RegionalTaxService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="pricing_taxes",
        name="Pricing & Tax Engine",
        requires=("db", "erp_masters"),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: ErpFeatureContext | None = None,
    ) -> None:
        @agent_tool("Calculate taxes and totals for a cart payload JSON")
        async def calculate_line_totals(cart_json: str) -> str:
            import json

            from {{cookiecutter.project_name}}.erp.schemas.transaction import ItemLine, TaxLine, TransactionDocument
            from {{cookiecutter.project_name}}.erp.services.pricing import PricingService

            try:
                payload = json.loads(cart_json)
            except json.JSONDecodeError:
                return "invalid json"
            doc = TransactionDocument(
                items=[ItemLine.model_validate(i) for i in payload.get("items", [])],
                taxes=[TaxLine.model_validate(t) for t in payload.get("taxes", [])],
            )
            totals = PricingService().calculate(doc)
            return str(totals.model_dump())

        registry.register(calculate_line_totals)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/pricing", tags=["erp-features"])

        @router.post("/calculate-totals")
        async def calculate_totals_route(
            payload: TransactionDocument,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            runtime = ctx.runtime
            if runtime is None:
                raise HTTPException(status_code=503, detail="ERP runtime unavailable")
            totals = runtime.pricing.calculate(payload)
            return totals.model_dump()

        @router.get("/items/{item_code}/details")
        async def item_details(
            item_code: str,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
            qty: float = 1.0,
            warehouse: str | None = None,
            price_list: str | None = None,
        ) -> dict[str, object]:
            if ctx.db_session is None:
                raise HTTPException(status_code=503, detail="ERP runtime unavailable")
            svc = ItemDetailsService(ctx.db_session, org_id=ctx.org_id())
            details = await svc.get(item_code, qty=qty, warehouse=warehouse, price_list=price_list)
            if not details.get("found"):
                raise HTTPException(status_code=404, detail=f"item {item_code} not found")
            return details

        @router.get("/tax-templates")
        async def list_tax_templates(country: str | None = None) -> list[dict[str, Any]]:
            return RegionalTaxService().list_templates(country=country)

        @router.post("/apply-tax-template/{template_id}")
        async def apply_tax_template(
            template_id: str,
            payload: TransactionDocument,
        ) -> dict[str, Any]:
            svc = RegionalTaxService()
            try:
                _doc, result = svc.apply_template(payload, template_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return result

        @router.post("/resolve-tax-template")
        async def resolve_tax_template(
            country: str,
            state: str | None = None,
            tax_category: str | None = None,
        ) -> dict[str, str | None]:
            svc = RegionalTaxService()
            template_id = svc.resolve_template(country=country, state=state, tax_category=tax_category)
            return {"template_id": template_id}

        return router


PACK = _Pack()
