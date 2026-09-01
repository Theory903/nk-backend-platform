"""NK ERP feature pack: Financial Accounting & GL."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.schemas.bank import BankCsvImport, BankImportRequest, BankReconcileRequest
from {{cookiecutter.project_name}}.erp.services.bank_reconciliation import BankReconciliationService
from {{cookiecutter.project_name}}.erp.services.ledger import JournalEntryCreate, LedgerService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="financial_accounting",
        name="Financial Accounting & GL",
        requires=("db", "erp_masters"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("Summarize GL trial balance totals")
        async def gl_balance() -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            rows = await LedgerService(ctx.db_session, org_id=ctx.org_id()).trial_balance()
            total = sum(r["balance"] for r in rows)
            return f"accounts={len(rows)} net_balance={total:.2f}"

        @agent_tool("Count unreconciled bank transactions")
        async def unreconciled_bank_count() -> str:
            if ctx is None or ctx.db_session is None:
                return "unavailable"
            rows = await BankReconciliationService(ctx.db_session, org_id=ctx.org_id()).list_transactions(
                reconciled=False
            )
            return f"unreconciled={len(rows)}"

        registry.register(gl_balance)
        registry.register(unreconciled_bank_count)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/accounts", tags=["erp-features"])

        @router.post("/journal-entries")
        async def create_journal_entry(
            payload: JournalEntryCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = LedgerService(ctx.db_session, org_id=ctx.org_id())
            try:
                return await svc.post_journal(payload)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.post("/payment-entries")
        async def create_payment_entry(
            payload: JournalEntryCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            entry = payload.model_copy(update={"voucher_type": "Payment Entry"})
            svc = LedgerService(ctx.db_session, org_id=ctx.org_id())
            try:
                return await svc.post_journal(entry)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.get("/trial-balance")
        async def trial_balance(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            return await LedgerService(ctx.db_session, org_id=ctx.org_id()).trial_balance()

        @router.post("/bank/import")
        async def import_bank_rows(
            payload: BankImportRequest,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            return await BankReconciliationService(ctx.db_session, org_id=ctx.org_id()).import_rows(payload)

        @router.post("/bank/import-csv")
        async def import_bank_csv(
            payload: BankCsvImport,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = BankReconciliationService(ctx.db_session, org_id=ctx.org_id())
            try:
                req = svc.parse_csv(payload.csv_text, bank_account=payload.bank_account)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return await svc.import_rows(req)

        @router.get("/bank/transactions")
        async def list_bank_transactions(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
            reconciled: bool | None = None,
        ) -> list[dict[str, Any]]:
            return await BankReconciliationService(ctx.db_session, org_id=ctx.org_id()).list_transactions(
                reconciled=reconciled
            )

        @router.get("/bank/suggest-matches")
        async def suggest_bank_matches(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            return await BankReconciliationService(ctx.db_session, org_id=ctx.org_id()).suggest_matches()

        @router.post("/bank/reconcile")
        async def reconcile_bank_transaction(
            payload: BankReconcileRequest,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = BankReconciliationService(ctx.db_session, org_id=ctx.org_id())
            try:
                return await svc.reconcile(payload)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        return router


PACK = _Pack()
