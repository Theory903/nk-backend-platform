"""Per-doctype controller hooks for universal DocType submit/cancel."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpDoctypeRecord
from {{cookiecutter.project_name}}.erp.schemas.doctype_registry import get_doctype_meta, slugify
from {{cookiecutter.project_name}}.erp.schemas.transaction import ItemLine, TaxLine, TransactionDocument
from {{cookiecutter.project_name}}.erp.services.billing import BillingService, ReconcileRequest
from {{cookiecutter.project_name}}.erp.services.posting import PostingService
from {{cookiecutter.project_name}}.erp.services.pricing import PricingService
from {{cookiecutter.project_name}}.erp.services.status_engine import resolve_status
from {{cookiecutter.project_name}}.erp.services.stock import StockEntryCreate, StockService

INTERNAL_DOCTYPE: dict[str, str] = {
    "Sales Order": "sales_order",
    "Quotation": "quotation",
    "Delivery Note": "delivery_note",
    "Sales Invoice": "sales_invoice",
    "Purchase Order": "purchase_order",
    "Purchase Receipt": "purchase_receipt",
    "Purchase Invoice": "purchase_invoice",
}

TRANSACTION_DOCTYPES = frozenset(INTERNAL_DOCTYPE)

STOCK_DOCTYPES = frozenset(
    {
        "Stock Entry",
        "Stock Reconciliation",
        "Material Transfer",
        "Pick List",
        "Delivery Trip",
        "Subcontracting Receipt",
    }
)

PAYMENT_DOCTYPES = frozenset({"Payment Entry", "Journal Entry"})

MANUFACTURING_DOCTYPES = frozenset(
    {
        "Work Order",
        "Job Card",
        "Production Plan",
        "BOM",
        "Subcontracting Order",
    }
)

STATUS_DOCTYPES = frozenset(
    {
        *TRANSACTION_DOCTYPES,
        *STOCK_DOCTYPES,
        *PAYMENT_DOCTYPES,
        *MANUFACTURING_DOCTYPES,
        "Lead",
        "Opportunity",
        "Issue",
        "Material Request",
        "Timesheet",
        "Asset",
        "Quality Inspection",
        "Maintenance Visit",
    }
)

STOCK_RECEIPT_PURPOSES = frozenset(
    {"Material Receipt", "Manufacture", "Repack", "Receive", "Purchase Receipt"}
)


def internal_doctype_key(doctype: str) -> str:
    if doctype in INTERNAL_DOCTYPE:
        return INTERNAL_DOCTYPE[doctype]
    return slugify(doctype).replace("-", "_")


def is_transaction_payload(data: dict[str, Any]) -> bool:
    return bool(data.get("items") or data.get("taxes"))


def _parse_uuid(value: Any) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def extract_lines(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("items") or data.get("lines") or data.get("stock_entry_details") or []
    lines: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        lines.append(
            {
                "item_code": row.get("item_code") or row.get("item_name"),
                "qty": float(row.get("qty") or row.get("transfer_qty") or 0),
                "rate": float(row.get("rate") or row.get("price_list_rate") or row.get("basic_rate") or 0),
                "warehouse": row.get("warehouse") or row.get("s_warehouse") or row.get("t_warehouse"),
                "valuation_rate": row.get("valuation_rate"),
            }
        )
    return lines


def extract_taxes(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("taxes") or []
    taxes: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        taxes.append(
            {
                "description": row.get("description") or row.get("account_head") or "",
                "rate": float(row.get("rate") or 0),
                "tax_amount": row.get("tax_amount"),
                "charge_type": row.get("charge_type") or "On Net Total",
                "included_in_print_rate": bool(row.get("included_in_print_rate")),
            }
        )
    return taxes


def recalculate_totals(data: dict[str, Any]) -> dict[str, Any]:
    doc = TransactionDocument(
        currency=str(data.get("currency") or "USD"),
        conversion_rate=float(data.get("conversion_rate") or 1.0),
        apply_discount_on=str(data.get("apply_discount_on") or "Grand Total"),
        additional_discount_percentage=float(data.get("additional_discount_percentage") or 0),
        discount_amount=float(data.get("discount_amount") or 0),
        shipping_amount=float(data.get("shipping_amount") or 0),
        items=[ItemLine.model_validate(line) for line in extract_lines(data)],
        taxes=[TaxLine.model_validate(tax) for tax in extract_taxes(data)],
    )
    totals = PricingService().calculate(doc)
    result = totals.model_dump()
    result["grand_total"] = totals.rounded_total or totals.grand_total
    return result


@dataclass
class PostingDocumentAdapter:
    id: uuid.UUID
    doctype: str
    lines: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)
    customer_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    posting_date: date | None = None
    docstatus: int = 1


def build_posting_adapter(record: ErpDoctypeRecord, *, totals: dict[str, Any]) -> PostingDocumentAdapter:
    data = record.data or {}
    customer = _parse_uuid(data.get("customer_id") or data.get("customer"))
    supplier = _parse_uuid(data.get("supplier_id") or data.get("supplier"))
    return PostingDocumentAdapter(
        id=record.id,
        doctype=internal_doctype_key(record.doctype),
        lines=extract_lines(data),
        totals=totals,
        customer_id=customer,
        supplier_id=supplier,
        posting_date=_parse_date(data.get("posting_date") or data.get("transaction_date")),
        docstatus=record.docstatus,
    )


def status_payload_from_record(record: ErpDoctypeRecord, *, totals: dict[str, Any] | None = None) -> dict[str, Any]:
    data = record.data or {}
    meta = record.meta or {}
    totals = totals or meta.get("totals") or {}
    return {
        "docstatus": record.docstatus,
        "status": data.get("status") or meta.get("erpnext_status"),
        "per_delivered": float(data.get("per_delivered") or meta.get("per_delivered") or 0),
        "per_billed": float(data.get("per_billed") or meta.get("per_billed") or 0),
        "per_received": float(data.get("per_received") or meta.get("per_received") or 0),
        "per_ordered": float(data.get("per_ordered") or meta.get("per_ordered") or 0),
        "customer_id": str(data.get("customer_id") or data.get("customer") or "") or None,
        "opportunity_id": data.get("opportunity_id") or meta.get("opportunity_id"),
        "outstanding_amount": float(
            data.get("outstanding_amount") or totals.get("grand_total") or totals.get("rounded_total") or 0
        ),
    }


class DoctypeHookService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id
        self._posting = PostingService(session, org_id=org_id)
        self._stock = StockService(session, org_id=org_id)
        self._billing = BillingService(session, org_id=org_id)

    async def on_submit(self, record: ErpDoctypeRecord) -> dict[str, Any]:
        results: dict[str, Any] = {"doctype": record.doctype}
        data = record.data or {}
        key = internal_doctype_key(record.doctype)

        if record.doctype in TRANSACTION_DOCTYPES or is_transaction_payload(data):
            totals = recalculate_totals(data)
            record.meta = {**record.meta, "totals": totals}
            record.data = {
                **data,
                "net_total": totals.get("net_total"),
                "total_taxes_and_charges": totals.get("total_taxes"),
                "grand_total": totals.get("grand_total"),
                "rounded_total": totals.get("rounded_total"),
            }
            adapter = build_posting_adapter(record, totals=totals)
            results["posting"] = await self._posting.on_submit(adapter)  # type: ignore[arg-type]
            results["totals"] = totals
        elif record.doctype in STOCK_DOCTYPES:
            results["stock"] = await self._post_stock(record)
        elif record.doctype in PAYMENT_DOCTYPES:
            results["payment"] = await self._apply_payment(record)
        elif record.doctype in MANUFACTURING_DOCTYPES:
            record.data.setdefault("status", "Submitted")
        elif record.doctype == "Issue":
            record.data.setdefault("status", "Open")
        elif record.doctype == "Material Request":
            record.data.setdefault("status", "Pending")
        elif record.doctype == "Timesheet":
            record.data.setdefault("status", "Submitted")
        elif self._is_submittable(record.doctype):
            record.data.setdefault("status", "Submitted")

        if record.doctype in STATUS_DOCTYPES or self._is_submittable(record.doctype):
            totals = record.meta.get("totals") or {}
            erpnext_status = resolve_status(key, status_payload_from_record(record, totals=totals))
            record.data["status"] = erpnext_status
            record.meta["erpnext_status"] = erpnext_status
            results["erpnext_status"] = erpnext_status

        return results

    async def on_cancel(self, record: ErpDoctypeRecord) -> dict[str, Any]:
        record.data["status"] = "Cancelled"
        key = internal_doctype_key(record.doctype)
        payload = status_payload_from_record(record)
        payload["docstatus"] = 2
        payload["status"] = "Cancelled"
        erpnext_status = resolve_status(key, payload)
        record.meta["erpnext_status"] = erpnext_status
        return {"erpnext_status": erpnext_status}

    async def _post_stock(self, record: ErpDoctypeRecord) -> list[dict[str, Any]]:
        purpose = str((record.data or {}).get("purpose") or record.doctype)
        sign = 1.0 if purpose in STOCK_RECEIPT_PURPOSES else -1.0
        posted: list[dict[str, Any]] = []
        for line in extract_lines(record.data or {}):
            qty = float(line.get("qty") or 0)
            if not qty:
                continue
            entry = StockEntryCreate(
                item_code=str(line.get("item_code") or "ITEM"),
                warehouse=str(line.get("warehouse") or "Stores - Default"),
                qty=sign * qty,
                valuation_rate=float(line.get("rate") or line.get("valuation_rate") or 0),
                voucher_type=record.doctype,
                voucher_id=record.id,
            )
            posted.append(await self._stock.post_entry(entry))
        return posted

    async def _apply_payment(self, record: ErpDoctypeRecord) -> dict[str, Any]:
        data = record.data or {}
        amount = float(data.get("paid_amount") or data.get("received_amount") or data.get("total") or 0)
        party_type = str(data.get("party_type") or "Customer")
        party_id = _parse_uuid(data.get("party") or data.get("party_id"))
        if amount <= 0 or party_id is None:
            return {"skipped": True, "reason": "missing party or amount"}
        return await self._billing.reconcile(
            ReconcileRequest(party_type=party_type, party_id=party_id, amount=amount)
        )

    @staticmethod
    def _is_submittable(doctype: str) -> bool:
        meta = get_doctype_meta(doctype)
        return bool(meta and meta.get("is_submittable"))
