"""NK ERP feature pack: AR/AP & Collections."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.services.billing import BillingService, PaymentLedgerCreate, ReconcileRequest
from {{cookiecutter.project_name}}.erp.services.dunning import DunningService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="billing_collections",
        name="AR/AP & Collections",
        requires=("db", "financial_accounting", "order_to_cash", "procure_to_pay"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Summarize outstanding AR and AP")
        async def outstanding_invoices() -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            return await BillingService(ctx.db_session, org_id=ctx.org_id()).outstanding_summary()

        @agent_tool("List overdue receivables for dunning")
        async def overdue_dunning_list() -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            return await DunningService(ctx.db_session, org_id=ctx.org_id()).dunning_summary()

        registry.register(outstanding_invoices)
        registry.register(overdue_dunning_list)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/billing", tags=["erp-features"])

        @router.get("/receivable")
        async def accounts_receivable(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            return await BillingService(ctx.db_session, org_id=ctx.org_id()).accounts_receivable()

        @router.get("/payable")
        async def accounts_payable(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            return await BillingService(ctx.db_session, org_id=ctx.org_id()).accounts_payable()

        @router.get("/receivable/detail")
        async def accounts_receivable_detail(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
            report_date: str | None = None,
            range: str | None = None,
        ) -> list[dict[str, Any]]:
            filters: dict[str, Any] = {}
            if report_date:
                filters["report_date"] = report_date
            if range:
                filters["range"] = range
            return await BillingService(ctx.db_session, org_id=ctx.org_id()).receivable_payable_detail(
                "Customer", filters=filters
            )

        @router.get("/payable/detail")
        async def accounts_payable_detail(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
            report_date: str | None = None,
            range: str | None = None,
        ) -> list[dict[str, Any]]:
            filters: dict[str, Any] = {}
            if report_date:
                filters["report_date"] = report_date
            if range:
                filters["range"] = range
            return await BillingService(ctx.db_session, org_id=ctx.org_id()).receivable_payable_detail(
                "Supplier", filters=filters
            )

        @router.post("/ledger")
        async def record_ledger(
            payload: PaymentLedgerCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            return await BillingService(ctx.db_session, org_id=ctx.org_id()).record(payload)

        @router.post("/reconcile")
        async def reconcile_payments(
            payload: ReconcileRequest,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            return await BillingService(ctx.db_session, org_id=ctx.org_id()).reconcile(payload)

        @router.get("/dunning/overdue")
        async def overdue_receivables(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            return await DunningService(ctx.db_session, org_id=ctx.org_id()).overdue_receivables()

        return router


PACK = _Pack()
