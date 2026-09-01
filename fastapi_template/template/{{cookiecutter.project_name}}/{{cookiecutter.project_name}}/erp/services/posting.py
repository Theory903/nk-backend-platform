"""GL and stock posting on document submit — ERPNext controller port."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpDocument
from {{cookiecutter.project_name}}.erp.services.billing import BillingService, PaymentLedgerCreate
from {{cookiecutter.project_name}}.erp.services.payment_schedule import build_payment_schedule
from {{cookiecutter.project_name}}.erp.services.ledger import GlLine, JournalEntryCreate, LedgerService
from {{cookiecutter.project_name}}.erp.services.stock import StockEntryCreate, StockService

# Default COA mapping (NK seed — mirrors ERPNext default accounts)
DEFAULT_ACCOUNTS = {
    "debtors": "Debtors - NK",
    "creditors": "Creditors - NK",
    "sales": "Sales - NK",
    "cogs": "Cost of Goods Sold - NK",
    "stock": "Stock In Hand - NK",
    "tax": "Duties and Taxes - NK",
    "cash": "Cash - NK",
}


class PostingService:
    """Post stock + GL entries when documents are submitted."""

    STOCK_DOCTYPES = frozenset({"delivery_note", "purchase_receipt", "stock_entry"})
    SELLING_DOCTYPES = frozenset({"sales_invoice", "sales_order"})
    BUYING_DOCTYPES = frozenset({"purchase_invoice", "purchase_order"})

    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id
        self._ledger = LedgerService(session, org_id=org_id)
        self._stock = StockService(session, org_id=org_id)
        self._billing = BillingService(session, org_id=org_id)

    async def on_submit(self, doc: ErpDocument) -> dict[str, Any]:
        results: dict[str, Any] = {"gl": None, "stock": []}
        if doc.doctype in self.STOCK_DOCTYPES or doc.doctype == "delivery_note":
            results["stock"] = await self._post_stock(doc)
        if doc.doctype in {"sales_invoice", "purchase_invoice", "journal_entry"} or doc.doctype.endswith("_invoice"):
            results["gl"] = await self._post_sales_or_purchase_gl(doc)
            if doc.doctype == "sales_invoice" and doc.customer_id:
                await self._record_receivable(doc)
            elif doc.doctype == "purchase_invoice" and doc.supplier_id:
                await self._record_payable(doc)
        elif doc.doctype == "sales_order" and doc.totals.get("grand_total"):
            results["gl"] = await self._post_sales_order_gl(doc)
        return results

    async def _post_stock(self, doc: ErpDocument) -> list[dict[str, Any]]:
        posted: list[dict[str, Any]] = []
        sign = 1.0 if doc.doctype in {"purchase_receipt", "stock_entry"} else -1.0
        if doc.doctype == "purchase_receipt":
            sign = 1.0
        for line in doc.lines or []:
            qty = float(line.get("qty") or 0)
            if not qty:
                continue
            rate = float(line.get("rate") or line.get("valuation_rate") or 0)
            entry = StockEntryCreate(
                item_code=str(line.get("item_code") or "ITEM"),
                warehouse=str(line.get("warehouse") or "Stores - Default"),
                qty=sign * qty,
                valuation_rate=rate,
                voucher_type=doc.doctype,
                voucher_id=doc.id,
            )
            result = await self._stock.post_entry(entry)
            result["voucher_id"] = str(doc.id)
            posted.append(result)
        return posted

    async def _post_sales_or_purchase_gl(self, doc: ErpDocument) -> dict[str, Any]:
        totals = doc.totals or {}
        grand = float(totals.get("rounded_total") or totals.get("grand_total") or 0)
        tax = float(totals.get("total_taxes") or 0)
        net = float(totals.get("net_total") or grand - tax)
        is_sales = "sales" in doc.doctype or doc.customer_id is not None
        party_acc = DEFAULT_ACCOUNTS["debtors"] if is_sales else DEFAULT_ACCOUNTS["creditors"]
        income_expense = DEFAULT_ACCOUNTS["sales"] if is_sales else DEFAULT_ACCOUNTS["cogs"]
        lines = [
            GlLine(account=party_acc, debit=grand if is_sales else 0, credit=0 if is_sales else grand),
            GlLine(account=income_expense, debit=0 if is_sales else net, credit=net if is_sales else 0),
        ]
        if tax:
            lines.append(
                GlLine(
                    account=DEFAULT_ACCOUNTS["tax"],
                    debit=0 if is_sales else tax,
                    credit=tax if is_sales else 0,
                )
            )
        return await self._ledger.post_journal(
            JournalEntryCreate(
                posting_date=doc.posting_date or date.today(),
                lines=lines,
                voucher_type=doc.doctype,
                voucher_id=doc.id,
            )
        )

    async def _post_sales_order_gl(self, doc: ErpDocument) -> dict[str, Any] | None:
        # Sales orders typically don't post GL until invoice; reserve stock only
        return None

    async def _record_receivable(self, doc: ErpDocument) -> dict[str, Any]:
        return await self._record_party_ledger(doc, party_type="Customer", party_id=doc.customer_id)

    async def _record_payable(self, doc: ErpDocument) -> dict[str, Any]:
        return await self._record_party_ledger(doc, party_type="Supplier", party_id=doc.supplier_id)

    async def _record_party_ledger(
        self,
        doc: ErpDocument,
        *,
        party_type: str,
        party_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        if party_id is None:
            return {"skipped": True, "reason": "missing party"}
        grand = float((doc.totals or {}).get("rounded_total") or (doc.totals or {}).get("grand_total") or 0)
        posting = doc.posting_date or date.today()
        schedule = (doc.meta or {}).get("payment_schedule")
        if not schedule:
            schedule = build_payment_schedule(
                grand,
                posting,
                template_id=(doc.meta or {}).get("payment_terms_template"),
            )
        entries: list[dict[str, Any]] = []
        for term in schedule:
            amount = float(term.get("payment_amount") or term.get("outstanding") or 0)
            if amount <= 0:
                continue
            due_raw = term.get("due_date")
            due = date.fromisoformat(str(due_raw)[:10]) if due_raw else posting
            entries.append(
                await self._billing.record(
                    PaymentLedgerCreate(
                        party_type=party_type,
                        party_id=party_id,
                        voucher_type=doc.doctype,
                        voucher_id=doc.id,
                        amount=amount,
                        outstanding=amount,
                        payment_term=str(term.get("payment_term") or ""),
                        due_date=due,
                    )
                )
            )
        return {"terms": len(entries), "entries": entries}
