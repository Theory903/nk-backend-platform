"""NK ERP feature pack: Inventory & Stock Ledger."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.services.masters import MastersService
from {{cookiecutter.project_name}}.erp.services.stock import StockEntryCreate, StockService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="inventory_management",
        name="Inventory & Stock Ledger",
        requires=("db", "erp_masters"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Stock balance summary for an item code")
        async def stock_on_hand(item_code: str) -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            rows = await StockService(ctx.db_session, org_id=ctx.org_id()).balance(item_code=item_code)
            total = sum(r["qty"] for r in rows)
            return f"{item_code}: {total} total"

        registry.register(stock_on_hand)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/stock", tags=["erp-features"])

        @router.get("/balance")
        async def stock_balance(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
            item_code: str | None = None,
        ) -> list[dict[str, Any]]:
            return await StockService(ctx.db_session, org_id=ctx.org_id()).balance(item_code=item_code)

        @router.post("/entries")
        async def create_stock_entry(
            payload: StockEntryCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            return await StockService(ctx.db_session, org_id=ctx.org_id()).post_entry(payload)

        @router.get("/items/{item_code}/bins")
        async def item_bins(
            item_code: str,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> list[dict[str, Any]]:
            return await StockService(ctx.db_session, org_id=ctx.org_id()).balance(item_code=item_code)

        @router.get("/items/{item_code}/profile")
        async def item_stock_profile(
            item_code: str,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            masters = MastersService(ctx.db_session, org_id=ctx.org_id())
            item = await masters.get_item_by_code(item_code)
            balance = await StockService(ctx.db_session, org_id=ctx.org_id()).balance(item_code=item_code)
            if item is None:
                return {"item_code": item_code, "found": False, "balance": balance}
            return {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "is_stock_item": item.is_stock_item,
                "balance": balance,
            }

        @router.post("/material-requests")
        async def create_material_request(
            payload: StockEntryCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            from {{cookiecutter.project_name}}.erp.services.doctype import DoctypeRecordCreate, DoctypeService

            svc = DoctypeService(ctx.db_session, org_id=ctx.org_id())
            row = await svc.create(
                "Material Request",
                DoctypeRecordCreate(
                    data={
                        "material_request_type": "Purchase",
                        "items": [
                            {
                                "item_code": payload.item_code,
                                "qty": abs(payload.qty),
                                "warehouse": payload.warehouse,
                            }
                        ],
                    }
                ),
            )
            return row.model_dump(mode="json")

        return router


PACK = _Pack()
