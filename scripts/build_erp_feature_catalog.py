#!/usr/bin/env python3
"""Build erp/features/catalog.yaml from temp/erpnext."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML required") from None

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "temp" / "erpnext"
OUT = (
    REPO
    / "fastapi_template"
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "erp"
    / "features"
    / "catalog.yaml"
)

# ERPNext module folder → NK feature pack
MODULE_TO_PACK: dict[str, str] = {
    "setup": "erp_masters",
    "utilities": "erp_masters",
    "crm": "crm_pipeline",
    "selling": "order_to_cash",
    "buying": "procure_to_pay",
    "stock": "inventory_management",
    "accounts": "financial_accounting",
    "support": "support_sla",
    "projects": "projects_delivery",
    "manufacturing": "manufacturing_ops",
    "assets": "assets_quality",
    "quality_management": "assets_quality",
    "maintenance": "assets_quality",
    "subcontracting": "manufacturing_ops",
    "portal": "erp_masters",
    "regional": "reporting_analytics",
    "erpnext_integrations": "erp_masters",
    "communication": "crm_pipeline",
    "telephony": "support_sla",
    "bulk_transaction": "erp_masters",
    "edi": "procure_to_pay",
}

PACK_META: dict[str, dict] = {
    "erp_masters": {
        "name": "ERP Master Data",
        "module": "erp.features.erp_masters",
        "requires": ["db", "users"],
        "description": "Company, item, customer, supplier, warehouse, COA masters",
        "priority": 1,
    },
    "crm_pipeline": {
        "name": "CRM & Sales Pipeline",
        "module": "erp.features.crm_pipeline",
        "requires": ["db", "users", "erp_masters"],
        "description": "Lead, opportunity, campaign, contract, pipeline analytics",
        "priority": 2,
    },
    "pricing_taxes": {
        "name": "Pricing & Tax Engine",
        "module": "erp.features.pricing_taxes",
        "requires": ["db", "erp_masters"],
        "description": "Tax/total calculation, pricing rules, item detail resolution",
        "priority": 3,
    },
    "order_to_cash": {
        "name": "Order to Cash",
        "module": "erp.features.order_to_cash",
        "requires": ["db", "users", "erp_masters", "pricing_taxes", "inventory_management"],
        "description": "Quotation, sales order, delivery note, sales invoice",
        "priority": 4,
    },
    "procure_to_pay": {
        "name": "Procure to Pay",
        "module": "erp.features.procure_to_pay",
        "requires": ["db", "users", "erp_masters", "pricing_taxes", "inventory_management"],
        "description": "RFQ, purchase order, purchase receipt, supplier scorecard",
        "priority": 5,
    },
    "inventory_management": {
        "name": "Inventory & Stock Ledger",
        "module": "erp.features.inventory_management",
        "requires": ["db", "erp_masters"],
        "description": "Stock ledger, valuation FIFO/LIFO, batch/serial, material request",
        "priority": 3,
    },
    "financial_accounting": {
        "name": "Financial Accounting & GL",
        "module": "erp.features.financial_accounting",
        "requires": ["db", "erp_masters"],
        "description": "Journal entry, GL posting, payment entry, fiscal periods",
        "priority": 6,
    },
    "billing_collections": {
        "name": "AR/AP & Collections",
        "module": "erp.features.billing_collections",
        "requires": ["db", "financial_accounting", "order_to_cash", "procure_to_pay"],
        "description": "Payment ledger, reconciliation, dunning, bank transactions",
        "priority": 7,
    },
    "support_sla": {
        "name": "Support & SLA Management",
        "module": "erp.features.support_sla",
        "requires": ["db", "users", "erp_masters"],
        "description": "Issue lifecycle, SLA deadlines, warranty claims",
        "priority": 2,
    },
    "projects_delivery": {
        "name": "Projects & Timesheets",
        "module": "erp.features.projects_delivery",
        "requires": ["db", "users", "erp_masters"],
        "description": "Project, task dependencies, timesheets, cost rollup",
        "priority": 5,
    },
    "manufacturing_ops": {
        "name": "Manufacturing Operations",
        "module": "erp.features.manufacturing_ops",
        "requires": ["db", "inventory_management", "procure_to_pay"],
        "description": "BOM, work order, production plan, job card",
        "priority": 8,
    },
    "assets_quality": {
        "name": "Assets, Quality & Maintenance",
        "module": "erp.features.assets_quality",
        "requires": ["db", "erp_masters"],
        "description": "Fixed assets, depreciation, quality inspection, maintenance",
        "priority": 8,
    },
    "reporting_analytics": {
        "name": "ERP Reporting Engine",
        "module": "erp.features.reporting_analytics",
        "requires": ["db"],
        "description": "Cross-domain reports: GL, AR/AP aging, pipeline, stock balance",
        "priority": 9,
    },
}

# Portable upstream patterns (not doctypes) indexed by pack
PORTABLE_PATTERNS: dict[str, list[dict[str, str]]] = {
    "pricing_taxes": [
        {
            "id": "taxes-and-totals",
            "name": "calculate_taxes_and_totals",
            "path": "erpnext/controllers/taxes_and_totals.py",
            "kind": "calculation",
        },
        {
            "id": "item-details",
            "name": "get_item_details",
            "path": "erpnext/stock/get_item_details.py",
            "kind": "lookup",
        },
        {
            "id": "pricing-rule",
            "name": "Pricing Rule",
            "path": "erpnext/accounts/doctype/pricing_rule",
            "kind": "doctype",
        },
    ],
    "crm_pipeline": [
        {
            "id": "lead-mapper",
            "name": "Lead → Customer/Opportunity/Quotation",
            "path": "erpnext/crm/doctype/lead/mapper.py",
            "kind": "mapper",
        },
        {
            "id": "status-updater-crm",
            "name": "Lead/Opportunity status_map",
            "path": "erpnext/controllers/status_updater.py",
            "kind": "workflow",
        },
    ],
    "order_to_cash": [
        {
            "id": "so-mapper",
            "name": "Sales Order → DN/SI/MR/Project",
            "path": "erpnext/selling/doctype/sales_order/mapper.py",
            "kind": "mapper",
        },
        {
            "id": "selling-controller",
            "name": "SellingController validation chain",
            "path": "erpnext/controllers/selling_controller.py",
            "kind": "controller",
        },
    ],
    "procure_to_pay": [
        {
            "id": "po-mapper",
            "name": "Purchase Order → PR/PI",
            "path": "erpnext/buying/doctype/purchase_order/mapper.py",
            "kind": "mapper",
        },
    ],
    "inventory_management": [
        {
            "id": "fifo-lifo",
            "name": "FIFOValuation / LIFOValuation",
            "path": "erpnext/stock/valuation.py",
            "kind": "calculation",
        },
        {
            "id": "stock-ledger",
            "name": "Stock ledger posting",
            "path": "erpnext/stock/stock_ledger.py",
            "kind": "ledger",
        },
    ],
    "financial_accounting": [
        {
            "id": "gl-posting",
            "name": "make_gl_entries",
            "path": "erpnext/accounts/general_ledger.py",
            "kind": "ledger",
        },
    ],
    "support_sla": [
        {
            "id": "issue-api",
            "name": "split_issue / set_status",
            "path": "erpnext/support/doctype/issue/issue.py",
            "kind": "api",
        },
        {
            "id": "sla-calc",
            "name": "Service Level Agreement deadlines",
            "path": "erpnext/support/doctype/service_level_agreement",
            "kind": "calculation",
        },
    ],
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _doctype_title(folder: Path) -> str:
    json_path = folder / f"{folder.name}.json"
    if json_path.is_file():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return str(data.get("name") or folder.name.replace("_", " ").title())
        except json.JSONDecodeError:
            pass
    return folder.name.replace("_", " ").title()


def _iter_doctypes() -> list[dict]:
    erp_root = SOURCE / "erpnext"
    if not erp_root.is_dir():
        return []
    upstream: list[dict] = []
    for module_dir in sorted(erp_root.iterdir()):
        if not module_dir.is_dir() or module_dir.name.startswith("."):
            continue
        doctype_root = module_dir / "doctype"
        if not doctype_root.is_dir():
            continue
        pack_id = MODULE_TO_PACK.get(module_dir.name)
        if not pack_id:
            continue
        for dt_dir in sorted(doctype_root.iterdir()):
            if not dt_dir.is_dir() or dt_dir.name.startswith("_"):
                continue
            if dt_dir.name == "__pycache__":
                continue
            rel = dt_dir.relative_to(SOURCE).as_posix()
            upstream.append(
                {
                    "id": _slug(dt_dir.name),
                    "name": _doctype_title(dt_dir),
                    "module": module_dir.name,
                    "pack": pack_id,
                    "path": rel,
                    "kind": "doctype",
                }
            )
    return upstream


def _iter_reports() -> list[dict]:
    erp_root = SOURCE / "erpnext"
    reports: list[dict] = []
    for report_py in sorted(erp_root.glob("**/report/**/*.py")):
        if report_py.name in {"__init__.py", "test_*.py"}:
            continue
        if report_py.name.startswith("test_"):
            continue
        parts = report_py.relative_to(erp_root).parts
        if len(parts) < 3 or parts[1] != "report":
            continue
        module = parts[0]
        pack_id = MODULE_TO_PACK.get(module, "reporting_analytics")
        reports.append(
            {
                "id": _slug(report_py.parent.name),
                "name": report_py.parent.name.replace("_", " ").title(),
                "module": module,
                "pack": pack_id if pack_id != "reporting_analytics" else "reporting_analytics",
                "path": report_py.relative_to(SOURCE).as_posix(),
                "kind": "report",
            }
        )
    return reports


def main() -> int:
    if not SOURCE.is_dir():
        print(f"Missing {SOURCE}", file=sys.stderr)
        return 1

    doctypes = _iter_doctypes()
    reports = _iter_reports()
    upstream = doctypes + reports

    pack_counts: dict[str, int] = {k: 0 for k in PACK_META}
    for row in upstream:
        pack_counts[row["pack"]] = pack_counts.get(row["pack"], 0) + 1

    catalog = {
        "version": 1,
        "source": "temp/erpnext",
        "license": "GPL-3.0",
        "upstream_url": "https://github.com/frappe/erpnext",
        "pack_count": len(PACK_META),
        "doctype_count": len(doctypes),
        "report_count": len(reports),
        "upstream_count": len(upstream),
        "packs": {
            pid: {
                **meta,
                "upstream_doctypes": pack_counts.get(pid, 0),
                "portable_patterns": PORTABLE_PATTERNS.get(pid, []),
            }
            for pid, meta in PACK_META.items()
        },
        "upstream": upstream,
        "not_portable": [
            "frappe.get_doc / Document ORM lifecycle (submit/cancel/amend)",
            "DocType JSON schema → port to SQLAlchemy + Pydantic",
            "frappe.model.mapper.get_mapped_doc → explicit transform services",
            "frappe.qb query builder → SQLAlchemy 2.0",
            "Desk UI (*.js), print formats, website portal routes",
            "Role/profile permission system → FastAPI RBAC deps",
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(
        f"catalog: {len(doctypes)} doctypes + {len(reports)} reports "
        f"→ {len(PACK_META)} packs → {OUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
