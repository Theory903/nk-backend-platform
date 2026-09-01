"""ERP reporting engine — execute(filters) contract for all catalog reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.erp.services.assets import AssetsService
from {{cookiecutter.project_name}}.erp.services.billing import BillingService
from {{cookiecutter.project_name}}.erp.services.crm import CrmService
from {{cookiecutter.project_name}}.erp.services.ledger import LedgerService
from {{cookiecutter.project_name}}.erp.services.manufacturing import ManufacturingService
from {{cookiecutter.project_name}}.erp.services.projects import ProjectsService
from {{cookiecutter.project_name}}.erp.services.report_columns import get_report_columns, map_row_to_replica
from {{cookiecutter.project_name}}.erp.services.report_data import ageing_columns, parse_ageing_ranges
from {{cookiecutter.project_name}}.erp.services.report_registry import catalog_reports, classify_report
from {{cookiecutter.project_name}}.erp.services.stock import StockService
from {{cookiecutter.project_name}}.erp.services.support import SupportService


class ReportRequest(BaseModel):
    report: str = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)


class ReportsService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    def catalog(self) -> list[dict[str, str]]:
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "module": r.get("module", ""),
                "pack": r.get("pack", ""),
                "handler": classify_report(r["id"], module=r.get("module", "")),
            }
            for r in catalog_reports()
        ]

    async def run(self, payload: ReportRequest) -> dict[str, Any]:
        report_key = _normalize(payload.report)
        module = ""
        for row in catalog_reports():
            if _normalize(row["id"]) == report_key or row["name"] == payload.report:
                module = row.get("module", "")
                break
        handler = classify_report(payload.report, module=module)
        columns, data = await self._dispatch(handler, report_key=report_key, filters=payload.filters)
        replica_columns = get_report_columns(payload.report, handler=handler, module=module)
        if handler in {"accounts_receivable", "accounts_payable"} and "summary" not in report_key:
            ranges = parse_ageing_ranges(str(payload.filters.get("range") or ""))
            replica_columns = ageing_columns(ranges)
        if replica_columns:
            columns = replica_columns
            data = [map_row_to_replica(row, replica_columns) for row in data]
        return {
            "report": payload.report,
            "handler": handler,
            "columns": columns,
            "data": data,
            "chart": None,
            "replica": True,
            "filters": payload.filters,
        }

    async def _dispatch(
        self,
        handler: str,
        *,
        report_key: str,
        filters: dict[str, Any],
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        billing = BillingService(self._session, org_id=self._org_id)
        stock = StockService(self._session, org_id=self._org_id)
        ledger = LedgerService(self._session, org_id=self._org_id)

        if handler == "crm_pipeline":
            summary = await CrmService(self._session, org_id=self._org_id).pipeline_summary()
            return [{"field": "status", "label": "Status"}, {"field": "count", "label": "Count"}], [
                {"status": k, "count": v} for k, v in summary.items()
            ]

        if handler == "trial_balance":
            return [{"field": "account", "label": "Account"}], await ledger.trial_balance()

        if handler == "general_ledger":
            return [{"field": "account", "label": "Account"}], await ledger.general_ledger_entries()

        if handler == "stock_balance":
            return [{"field": "item_code", "label": "Item"}], await stock.balance_replica()

        if handler == "stock_ledger":
            return [{"field": "item_code", "label": "Item"}], await stock.ledger_entries()

        if handler == "accounts_receivable":
            if "summary" in report_key:
                return [{"field": "party", "label": "Party"}], await billing.receivable_summary("Customer")
            return [{"field": "party", "label": "Party"}], await billing.receivable_payable_detail(
                "Customer", filters=filters
            )

        if handler == "accounts_payable":
            if "summary" in report_key:
                return [{"field": "party", "label": "Party"}], await billing.receivable_summary("Supplier")
            return [{"field": "party", "label": "Party"}], await billing.receivable_payable_detail(
                "Supplier", filters=filters
            )

        if handler == "issue_analytics":
            support = SupportService(self._session, org_id=self._org_id)
            return [{"field": "metric", "label": "Metric"}], [
                {"metric": "open_issues", "value": await support.open_issue_count()}
            ]

        if handler in {"sales_register", "purchase_register", "sales_orders"}:
            return await self._document_report(handler)

        if handler == "gross_profit":
            tb = await ledger.trial_balance()
            sales = next((r for r in tb if "Sales" in r["account"]), {"credit": 0})
            cogs = next((r for r in tb if "Cost of Goods" in r["account"]), {"debit": 0})
            gp = float(sales.get("credit", 0)) - float(cogs.get("debit", 0))
            return [{"field": "metric", "label": "Metric"}], [{"metric": "gross_profit", "value": gp}]

        if handler == "bank":
            from {{cookiecutter.project_name}}.erp.services.bank_reconciliation import BankReconciliationService

            return [{"field": "posting_date", "label": "Date"}], await BankReconciliationService(
                self._session, org_id=self._org_id
            ).list_transactions()

        if handler == "doctype_catalog":
            from {{cookiecutter.project_name}}.erp.schemas.doctype_registry import list_doctypes

            return [{"field": "name", "label": "DocType"}], list_doctypes()

        if handler == "doctype_counts":
            from {{cookiecutter.project_name}}.erp.services.doctype import DoctypeService

            return [{"field": "doctype", "label": "DocType"}], await DoctypeService(
                self._session, org_id=self._org_id
            ).counts_by_doctype()

        if handler == "manufacturing":
            return [{"field": "production_item", "label": "Item"}], await ManufacturingService(
                self._session, org_id=self._org_id
            ).production_plan()

        if handler == "projects":
            rows = await ProjectsService(self._session, org_id=self._org_id).list_projects()
            return [{"field": "project_name", "label": "Project"}], [
                {"project_name": r.project_name, "status": r.status, "percent_complete": r.percent_complete}
                for r in rows
            ]

        if handler == "assets":
            return [{"field": "asset_name", "label": "Asset"}], await AssetsService(
                self._session, org_id=self._org_id
            ).list_assets()

        if handler == "payment_terms":
            return await self._payment_terms_report()

        return [{"field": "value", "label": "Value"}], []

    async def _payment_terms_report(self) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        from {{cookiecutter.project_name}}.erp.services.documents import DocumentService

        columns = [
            {"field": "sales_order", "label": "Sales Order"},
            {"field": "payment_term", "label": "Payment Term"},
            {"field": "due_date", "label": "Due Date"},
            {"field": "payment_amount", "label": "Amount"},
            {"field": "outstanding", "label": "Outstanding"},
            {"field": "status", "label": "Status"},
        ]
        svc = DocumentService(self._session, org_id=self._org_id)
        rows: list[dict[str, Any]] = []
        for doc in await svc.list_by_type("sales_order"):
            schedule = (doc.meta or {}).get("payment_schedule") or []
            if not schedule and doc.doctype == "sales_order":
                grand = float(doc.totals.get("grand_total") or 0)
                from {{cookiecutter.project_name}}.erp.services.payment_schedule import build_payment_schedule

                schedule = build_payment_schedule(
                    grand,
                    doc.posting_date or date.today(),
                    template_id=(doc.meta or {}).get("payment_terms_template"),
                )
            for term in schedule:
                rows.append(
                    {
                        "sales_order": doc.docname,
                        "payment_term": term.get("payment_term"),
                        "due_date": term.get("due_date"),
                        "payment_amount": term.get("payment_amount"),
                        "outstanding": term.get("outstanding"),
                        "status": doc.erpnext_status or doc.status,
                    }
                )
        return columns, rows

    async def _document_report(self, handler: str) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        from {{cookiecutter.project_name}}.erp.services.documents import DocumentService

        svc = DocumentService(self._session, org_id=self._org_id)
        if handler == "sales_register":
            docs = await svc.list_by_type("sales_invoice")
            data = [
                {
                    "posting_date": (d.posting_date.isoformat() if d.posting_date else ""),
                    "customer": str(d.customer_id or ""),
                    "customer_name": str(d.customer_id or ""),
                    "voucher_no": d.docname,
                    "grand_total": d.totals.get("grand_total", 0),
                    "status": d.erpnext_status or d.status,
                }
                for d in docs
            ]
            return [{"field": "voucher_no", "label": "Invoice"}], data

        if handler == "purchase_register":
            docs = await svc.list_by_type("purchase_invoice")
            data = [
                {
                    "posting_date": (d.posting_date.isoformat() if d.posting_date else ""),
                    "supplier": str(d.supplier_id or ""),
                    "supplier_name": str(d.supplier_id or ""),
                    "voucher_no": d.docname,
                    "grand_total": d.totals.get("grand_total", 0),
                }
                for d in docs
            ]
            return [{"field": "voucher_no", "label": "Bill"}], data

        docs = await svc.list_by_type("sales_order")
        data = [
            {
                "name": d.docname,
                "customer": str(d.customer_id or ""),
                "status": d.erpnext_status or d.status,
                "per_delivered": d.per_delivered,
                "per_billed": d.per_billed,
                "grand_total": d.totals.get("grand_total", 0),
            }
            for d in docs
        ]
        return [{"field": "name", "label": "Order"}], data


def _normalize(report: str) -> str:
    return report.lower().replace("-", "_").strip()
