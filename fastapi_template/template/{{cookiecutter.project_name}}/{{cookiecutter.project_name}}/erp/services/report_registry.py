"""Map all 170 ERPNext catalog reports to NK handler categories."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CATALOG = Path(__file__).resolve().parents[1] / "features" / "catalog.yaml"

# Explicit report id → handler (legacy aliases preserved)
_EXACT: dict[str, str] = {
    "account_balance": "general_ledger",
    "accounts_payable": "accounts_payable",
    "accounts_payable_summary": "accounts_payable",
    "accounts_receivable": "accounts_receivable",
    "accounts_receivable_summary": "accounts_receivable",
    "ap_aging": "accounts_payable",
    "ar_aging": "accounts_receivable",
    "balance_sheet": "trial_balance",
    "bank": "bank",
    "bank_clearance": "bank",
    "bank_reconciliation": "bank",
    "bank_reconciliation_statement": "bank",
    "bom_stock_report": "manufacturing",
    "cash_flow": "general_ledger",
    "consolidated_trial_balance": "trial_balance",
    "crm_pipeline": "crm_pipeline",
    "customer_ledger_summary": "general_ledger",
    "doctype_catalog": "doctype_catalog",
    "doctype_list": "doctype_catalog",
    "doctype_record_counts": "doctype_counts",
    "general_ledger": "general_ledger",
    "gl": "general_ledger",
    "gross_profit": "gross_profit",
    "issue_analytics": "issue_analytics",
    "order_analysis": "sales_orders",
    "pipeline": "crm_pipeline",
    "profitability": "gross_profit",
    "purchase_analytics": "purchase_register",
    "purchase_register": "purchase_register",
    "record_counts": "doctype_counts",
    "receivable": "accounts_receivable",
    "sales_analytics": "sales_register",
    "sales_order_analysis": "sales_orders",
    "sales_pipeline_analytics": "crm_pipeline",
    "sales_register": "sales_register",
    "stock": "stock_balance",
    "stock_analytics": "stock_balance",
    "stock_balance": "stock_balance",
    "stock_ledger": "stock_ledger",
    "support": "issue_analytics",
    "trial_balance": "trial_balance",
}

_MODULE_DEFAULT: dict[str, str] = {
    "accounts": "general_ledger",
    "assets": "assets",
    "buying": "purchase_register",
    "crm": "crm_pipeline",
    "manufacturing": "manufacturing",
    "projects": "projects",
    "regional": "general_ledger",
    "selling": "sales_register",
    "stock": "stock_balance",
    "support": "issue_analytics",
    "utilities": "doctype_catalog",
}


def _normalize(report: str) -> str:
    return report.lower().replace("-", "_").strip()


def classify_report(report_id: str, *, module: str = "") -> str:
    """Return handler category for a catalog report id."""
    key = _normalize(report_id)
    if key in _EXACT:
        return _EXACT[key]

    if "receivable" in key:
        return "accounts_receivable"
    if "payable" in key:
        return "accounts_payable"
    if "bank" in key or "clearance" in key:
        return "bank"
    if "trial_balance" in key or "balance_sheet" in key:
        return "trial_balance"
    if "gross_profit" in key or "profit" in key and "loss" in key:
        return "gross_profit"
    if "general_ledger" in key or "gl_entry" in key or key.endswith("_ledger"):
        return "general_ledger"
    if "stock_ledger" in key or "fifo" in key or "batch" in key:
        return "stock_ledger"
    if "stock" in key or "item" in key and "price" in key:
        return "stock_balance"
    if "sales_order" in key or "order_trends" in key:
        return "sales_orders"
    if "sales" in key or "quotation" in key or "selling" in key:
        return "sales_register"
    if "purchase" in key or "supplier" in key:
        return "purchase_register"
    if "pipeline" in key or "lead" in key or "opportunity" in key:
        return "crm_pipeline"
    if "payment_terms" in key or "payment_term" in key:
        return "payment_terms"
    if "issue" in key or "sla" in key:
        return "issue_analytics"
    if "bom" in key or "work_order" in key or "production" in key:
        return "manufacturing"
    if "project" in key or "timesheet" in key or "task" in key:
        return "projects"
    if "asset" in key or "depreciation" in key:
        return "assets"
    if "doctype" in key:
        return "doctype_catalog"

    mod = (module or "").lower()
    return _MODULE_DEFAULT.get(mod, "general_ledger")


@lru_cache(maxsize=1)
def catalog_reports() -> list[dict[str, Any]]:
    if not _CATALOG.is_file():
        return []
    data = yaml.safe_load(_CATALOG.read_text(encoding="utf-8")) or {}
    return [row for row in data.get("upstream", []) if row.get("kind") == "report"]


def wired_report_count() -> int:
    return len(catalog_reports())
