"""Map ERPNext upstream patterns to NK extension points.

Full upstream catalog: ``erp/features/catalog.yaml`` (536 doctypes + 170 reports → 13 packs).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErpPatternTarget:
    """Where an ERPNext pattern belongs in the NK platform."""

    pattern: str
    pack: str
    module: str
    upstream_path: str
    register_via: str
    notes: str


PATTERNS: tuple[ErpPatternTarget, ...] = (
    ErpPatternTarget(
        "taxes-and-totals",
        "pricing_taxes",
        "erp.services.pricing",
        "erpnext/controllers/taxes_and_totals.py",
        "erp/features/pricing_taxes + POST /api/erp/pricing/calculate-totals",
        "NK-native tax/grand-total engine (no Frappe Document).",
    ),
    ErpPatternTarget(
        "item-details",
        "pricing_taxes",
        "erp.services.masters",
        "erpnext/stock/get_item_details.py",
        "GET /api/erp/pricing/items/{code}/details",
        "Price list rate + tax template resolution subset.",
    ),
    ErpPatternTarget(
        "fifo-lifo-valuation",
        "inventory_management",
        "erp.services.valuation",
        "erpnext/stock/valuation.py",
        "erp/services/valuation.py + stock tools",
        "Pure-Python FIFO/LIFO ported from ERPNext.",
    ),
    ErpPatternTarget(
        "lead-mapper",
        "crm_pipeline",
        "erp.services.crm",
        "erpnext/crm/doctype/lead/mapper.py",
        "POST /api/erp/crm/leads/{id}/convert/customer",
        "Lead → Customer/Opportunity transform pipeline.",
    ),
    ErpPatternTarget(
        "status-updater",
        "crm_pipeline",
        "erp.services.status",
        "erpnext/controllers/status_updater.py",
        "PATCH status endpoints + status engine",
        "State machine specs (eval rules → predicates).",
    ),
    ErpPatternTarget(
        "issue-sla",
        "support_sla",
        "erp.services.support",
        "erpnext/support/doctype/issue/issue.py",
        "POST /api/erp/support/issues + SLA routes",
        "Issue lifecycle, split_issue, bulk set_status.",
    ),
    ErpPatternTarget(
        "gl-posting",
        "financial_accounting",
        "erp.services.ledger",
        "erpnext/accounts/general_ledger.py",
        "erp/features/financial_accounting",
        "Double-entry GL posting (future pack).",
    ),
    ErpPatternTarget(
        "so-mapper",
        "order_to_cash",
        "erp.services.selling",
        "erpnext/selling/doctype/sales_order/mapper.py",
        "POST /api/erp/selling/sales-orders/{id}/delivery-notes",
        "Sales order → delivery note / invoice mappers.",
    ),
    ErpPatternTarget(
        "po-mapper",
        "procure_to_pay",
        "erp.services.buying",
        "erpnext/buying/doctype/purchase_order/mapper.py",
        "POST /api/erp/buying/purchase-orders/{id}/receipts",
        "Purchase order → receipt / invoice mappers.",
    ),
    ErpPatternTarget(
        "report-execute",
        "reporting_analytics",
        "erp.services.reports",
        "erpnext/**/report/**/execute",
        "POST /api/erp/reports/run",
        "execute(filters) → columns, data, chart contract.",
    ),
)


def pattern_for(name: str) -> ErpPatternTarget | None:
    key = name.strip().lower().replace("_", "-")
    for item in PATTERNS:
        if item.pattern == key:
            return item
    return None
