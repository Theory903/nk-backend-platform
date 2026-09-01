"""ERPNext-accurate report column schemas for toe-to-toe replica output."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.erp.services.report_registry import classify_report

_SCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "reports"
_COLUMNS_INDEX = _SCHEMAS / "columns_index.yaml"
_REPORT_MANIFEST = _SCHEMAS / "manifest.yaml"

# ERPNext standard columns when upstream extraction missed get_columns
_HANDLER_COLUMNS: dict[str, list[dict[str, str]]] = {
    "accounts_receivable": [
        {"field": "party", "label": "Party"},
        {"field": "party_type", "label": "Party Type"},
        {"field": "invoiced", "label": "Invoiced"},
        {"field": "paid", "label": "Paid"},
        {"field": "outstanding", "label": "Outstanding"},
    ],
    "accounts_payable": [
        {"field": "party", "label": "Party"},
        {"field": "party_type", "label": "Party Type"},
        {"field": "invoiced", "label": "Invoiced"},
        {"field": "paid", "label": "Paid"},
        {"field": "outstanding", "label": "Outstanding"},
    ],
    "trial_balance": [
        {"field": "account", "label": "Account"},
        {"field": "debit", "label": "Debit"},
        {"field": "credit", "label": "Credit"},
        {"field": "balance", "label": "Balance"},
    ],
    "general_ledger": [
        {"field": "posting_date", "label": "Posting Date"},
        {"field": "account", "label": "Account"},
        {"field": "debit", "label": "Debit"},
        {"field": "credit", "label": "Credit"},
        {"field": "voucher_type", "label": "Voucher Type"},
        {"field": "voucher_no", "label": "Voucher No"},
    ],
    "stock_balance": [
        {"field": "item_code", "label": "Item"},
        {"field": "item_name", "label": "Item Name"},
        {"field": "warehouse", "label": "Warehouse"},
        {"field": "bal_qty", "label": "Balance Qty"},
        {"field": "bal_val", "label": "Balance Value"},
    ],
    "stock_ledger": [
        {"field": "posting_date", "label": "Posting Date"},
        {"field": "item_code", "label": "Item Code"},
        {"field": "warehouse", "label": "Warehouse"},
        {"field": "actual_qty", "label": "Qty"},
        {"field": "qty_after_transaction", "label": "Qty After Transaction"},
    ],
    "sales_register": [
        {"field": "posting_date", "label": "Posting Date"},
        {"field": "customer", "label": "Customer"},
        {"field": "customer_name", "label": "Customer Name"},
        {"field": "voucher_no", "label": "Invoice"},
        {"field": "grand_total", "label": "Grand Total"},
        {"field": "status", "label": "Status"},
    ],
    "purchase_register": [
        {"field": "posting_date", "label": "Posting Date"},
        {"field": "supplier", "label": "Supplier"},
        {"field": "supplier_name", "label": "Supplier Name"},
        {"field": "voucher_no", "label": "Bill No"},
        {"field": "grand_total", "label": "Grand Total"},
    ],
    "sales_orders": [
        {"field": "name", "label": "Sales Order"},
        {"field": "customer", "label": "Customer"},
        {"field": "status", "label": "Status"},
        {"field": "per_delivered", "label": "% Delivered"},
        {"field": "per_billed", "label": "% Billed"},
        {"field": "grand_total", "label": "Grand Total"},
    ],
    "crm_pipeline": [
        {"field": "status", "label": "Status"},
        {"field": "count", "label": "Count"},
    ],
    "manufacturing": [
        {"field": "production_item", "label": "Production Item"},
        {"field": "qty", "label": "Qty"},
        {"field": "status", "label": "Status"},
    ],
    "projects": [
        {"field": "project_name", "label": "Project"},
        {"field": "status", "label": "Status"},
        {"field": "percent_complete", "label": "% Complete"},
    ],
    "assets": [
        {"field": "asset_name", "label": "Asset Name"},
        {"field": "status", "label": "Status"},
        {"field": "gross_purchase_amount", "label": "Gross Purchase Amount"},
    ],
    "bank": [
        {"field": "posting_date", "label": "Posting Date"},
        {"field": "description", "label": "Description"},
        {"field": "deposit", "label": "Deposit"},
        {"field": "withdrawal", "label": "Withdrawal"},
        {"field": "is_reconciled", "label": "Reconciled"},
    ],
}


@lru_cache(maxsize=1)
def load_columns_index() -> dict[str, list[dict[str, str]]]:
    if not _COLUMNS_INDEX.is_file():
        return {}
    data = yaml.safe_load(_COLUMNS_INDEX.read_text(encoding="utf-8")) or {}
    return data.get("reports") or {}


@lru_cache(maxsize=1)
def load_report_manifest() -> list[dict[str, Any]]:
    if not _REPORT_MANIFEST.is_file():
        return []
    data = yaml.safe_load(_REPORT_MANIFEST.read_text(encoding="utf-8")) or {}
    return data.get("reports") or []


def normalize_report_id(report: str) -> str:
    return report.lower().replace("_", "-").strip()


def get_report_columns(report_id: str, *, handler: str, module: str = "") -> list[dict[str, str]]:
    key = normalize_report_id(report_id)
    extracted = load_columns_index().get(key)
    if extracted:
        return extracted
    return _HANDLER_COLUMNS.get(handler, [{"field": "value", "label": "Value"}])


def map_row_to_replica(row: dict[str, Any], columns: list[dict[str, str]]) -> dict[str, Any]:
    """Shape NK row keys into ERPNext report fieldnames."""
    aliases = {
        "party_id": "party",
        "customer_id": "customer",
        "supplier_id": "supplier",
        "docname": "voucher_no",
        "name": "voucher_no",
        "qty": "bal_qty",
        "metric": "value",
    }
    out: dict[str, Any] = {}
    fields = [c["field"] for c in columns]
    for field in fields:
        if field in row:
            out[field] = row[field]
            continue
        for src, dst in aliases.items():
            if dst == field and src in row:
                out[field] = row[src]
                break
        if field not in out:
            for src, dst in aliases.items():
                if src in row and field == dst:
                    out[field] = row[src]
                    break
    for key, value in row.items():
        if key in fields and key not in out:
            out[key] = value
    return out or dict(row)
