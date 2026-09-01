"""ERPNext controller validation chain — toe-to-toe replica without Frappe runtime."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.erp.services.doctype_hooks import extract_lines, extract_taxes

_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "controllers" / "manifest.yaml"

SELLING_DOCTYPES = frozenset(
    {
        "Sales Order",
        "Quotation",
        "Delivery Note",
        "Sales Invoice",
        "POS Invoice",
    }
)
BUYING_DOCTYPES = frozenset(
    {
        "Purchase Order",
        "Purchase Receipt",
        "Purchase Invoice",
        "Request for Quotation",
        "Supplier Quotation",
    }
)
STOCK_DOCTYPES = frozenset(
    {
        "Stock Entry",
        "Stock Reconciliation",
        "Material Transfer",
        "Pick List",
        "Delivery Trip",
    }
)


@lru_cache(maxsize=1)
def _controller_map() -> dict[str, str]:
    if not _SCHEMA.is_file():
        return {}
    data = yaml.safe_load(_SCHEMA.read_text(encoding="utf-8")) or {}
    return {row["name"]: row.get("controller", "status_updater") for row in data.get("doctypes") or []}


class ControllerReplica:
    """Validate document payloads using ERPNext controller rules (subset port)."""

    def controller_for(self, doctype: str) -> str:
        return _controller_map().get(doctype, "status_updater")

    def validate(self, doctype: str, data: dict[str, Any], *, action: str = "save") -> list[str]:
        errors: list[str] = []
        controller = self.controller_for(doctype)

        if doctype in SELLING_DOCTYPES:
            errors.extend(self._validate_selling(data, doctype=doctype))
        if doctype in BUYING_DOCTYPES:
            errors.extend(self._validate_buying(data))
        if doctype in STOCK_DOCTYPES or controller == "stock_controller":
            errors.extend(self._validate_stock(data))
        if controller == "accounts_controller" and doctype in {"Journal Entry", "Payment Entry"}:
            errors.extend(self._validate_accounts(data))

        if action == "submit" and self._is_submittable(doctype):
            if not extract_lines(data) and doctype not in {"Journal Entry", "Payment Entry", "Lead", "Opportunity"}:
                if doctype not in STOCK_DOCTYPES and doctype not in {"Issue", "Timesheet", "Asset"}:
                    pass  # some masters submit without lines
            if doctype in SELLING_DOCTYPES | BUYING_DOCTYPES and not extract_lines(data):
                errors.append("At least one item row is required before submit")

        return errors

    @staticmethod
    def _validate_selling(data: dict[str, Any], *, doctype: str) -> list[str]:
        errors: list[str] = []
        if doctype != "Quotation" and not data.get("customer") and not data.get("customer_id"):
            errors.append("Customer is mandatory")
        if not data.get("company"):
            errors.append("Company is mandatory")
        return errors

    @staticmethod
    def _validate_buying(data: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not data.get("supplier") and not data.get("supplier_id"):
            errors.append("Supplier is mandatory")
        if not data.get("company"):
            errors.append("Company is mandatory")
        return errors

    @staticmethod
    def _validate_stock(data: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        lines = extract_lines(data)
        if not lines:
            errors.append("Stock items are mandatory")
        for line in lines:
            if not line.get("warehouse") and not data.get("from_warehouse"):
                errors.append("Warehouse is required on stock items")
                break
        return errors

    @staticmethod
    def _validate_accounts(data: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not data.get("accounts") and not data.get("payment_type"):
            if not extract_lines(data):
                errors.append("Accounts or payment details required")
        return errors

    @staticmethod
    def _is_submittable(doctype: str) -> bool:
        if not _SCHEMA.is_file():
            return False
        data = yaml.safe_load(_SCHEMA.read_text(encoding="utf-8")) or {}
        for row in data.get("doctypes") or []:
            if row["name"] == doctype:
                return bool(row.get("is_submittable"))
        return False

    def enrich_defaults(self, doctype: str, data: dict[str, Any]) -> dict[str, Any]:
        """Apply ERPNext default field values on create."""
        out = dict(data)
        out.setdefault("company", "NK Default")
        out.setdefault("currency", "USD")
        if doctype in SELLING_DOCTYPES | BUYING_DOCTYPES:
            out.setdefault("conversion_rate", 1.0)
            if extract_lines(out) and not extract_taxes(out):
                out.setdefault("taxes", [])
        return out
