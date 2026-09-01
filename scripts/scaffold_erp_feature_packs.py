"""Generate NK-native ERP feature pack modules from catalog.

NOTE: Integrated packs are hand-maintained under erp/features/*.
This script only regenerates stub packs when explicitly requested.
Do NOT run against integrated pack ids — they will be overwritten.
"""

from __future__ import annotations

import sys
from pathlib import Path

INTEGRATED_PACKS = frozenset({
    "erp_masters",
    "crm_pipeline",
    "pricing_taxes",
    "support_sla",
    "inventory_management",
    "order_to_cash",
    "procure_to_pay",
    "financial_accounting",
    "billing_collections",
    "projects_delivery",
    "manufacturing_ops",
    "assets_quality",
    "reporting_analytics",
    "documents_hub",
    "doctype_hub",
})

ROOT = Path(__file__).resolve().parents[1] / (
    "fastapi_template/template/{{cookiecutter.project_name}}/{{cookiecutter.project_name}}/erp/features"
)

# pack_id → (route_prefix, primary endpoints, agent tools)
PACKS: dict[str, dict] = {
    "erp_masters": {
        "meta": ("erp_masters", "ERP Master Data", ("db", "users")),
        "route": "masters",
        "endpoints": [
            ("GET", "/items", "list_items"),
            ("GET", "/customers", "list_customers"),
            ("GET", "/suppliers", "list_suppliers"),
        ],
        "tools": ["lookup_item", "lookup_party"],
    },
    "crm_pipeline": {
        "meta": ("crm_pipeline", "CRM & Sales Pipeline", ("db", "users", "erp_masters")),
        "route": "crm",
        "endpoints": [
            ("POST", "/leads", "create_lead"),
            ("POST", "/leads/{lead_id}/convert/customer", "convert_lead_customer"),
            ("GET", "/opportunities", "list_opportunities"),
            ("GET", "/reports/pipeline", "pipeline_report"),
        ],
        "tools": ["crm_pipeline_summary"],
    },
    "pricing_taxes": {
        "meta": ("pricing_taxes", "Pricing & Tax Engine", ("db", "erp_masters")),
        "route": "pricing",
        "endpoints": [
            ("POST", "/calculate-totals", "calculate_totals"),
            ("GET", "/items/{item_code}/details", "item_details"),
        ],
        "tools": ["calculate_line_totals"],
    },
    "order_to_cash": {
        "meta": (
            "order_to_cash",
            "Order to Cash",
            ("db", "users", "erp_masters", "pricing_taxes", "inventory_management"),
        ),
        "route": "selling",
        "endpoints": [
            ("POST", "/quotations", "create_quotation"),
            ("POST", "/sales-orders", "create_sales_order"),
            ("POST", "/sales-orders/{order_id}/delivery-notes", "make_delivery_note"),
        ],
        "tools": ["sales_order_status"],
    },
    "procure_to_pay": {
        "meta": (
            "procure_to_pay",
            "Procure to Pay",
            ("db", "users", "erp_masters", "pricing_taxes", "inventory_management"),
        ),
        "route": "buying",
        "endpoints": [
            ("POST", "/purchase-orders", "create_purchase_order"),
            ("POST", "/rfq", "create_rfq"),
            ("POST", "/purchase-orders/{order_id}/receipts", "make_purchase_receipt"),
        ],
        "tools": ["purchase_order_status"],
    },
    "inventory_management": {
        "meta": ("inventory_management", "Inventory & Stock Ledger", ("db", "erp_masters")),
        "route": "stock",
        "endpoints": [
            ("GET", "/balance", "stock_balance"),
            ("POST", "/entries", "create_stock_entry"),
            ("GET", "/items/{item_code}/bins", "item_bins"),
        ],
        "tools": ["stock_on_hand"],
    },
    "financial_accounting": {
        "meta": ("financial_accounting", "Financial Accounting & GL", ("db", "erp_masters")),
        "route": "accounts",
        "endpoints": [
            ("POST", "/journal-entries", "create_journal_entry"),
            ("POST", "/payment-entries", "create_payment_entry"),
            ("GET", "/trial-balance", "trial_balance"),
        ],
        "tools": ["gl_balance"],
    },
    "billing_collections": {
        "meta": (
            "billing_collections",
            "AR/AP & Collections",
            ("db", "financial_accounting", "order_to_cash", "procure_to_pay"),
        ),
        "route": "billing",
        "endpoints": [
            ("GET", "/receivable", "accounts_receivable"),
            ("GET", "/payable", "accounts_payable"),
            ("POST", "/reconcile", "reconcile_payments"),
        ],
        "tools": ["outstanding_invoices"],
    },
    "support_sla": {
        "meta": ("support_sla", "Support & SLA Management", ("db", "users", "erp_masters")),
        "route": "support",
        "endpoints": [
            ("POST", "/issues", "create_issue"),
            ("PATCH", "/issues/status", "bulk_set_status"),
            ("POST", "/issues/{issue_id}/split", "split_issue"),
            ("GET", "/issues/{issue_id}/sla", "sla_status"),
        ],
        "tools": ["open_issues_count"],
    },
    "projects_delivery": {
        "meta": ("projects_delivery", "Projects & Timesheets", ("db", "users", "erp_masters")),
        "route": "projects",
        "endpoints": [
            ("POST", "/projects", "create_project"),
            ("POST", "/tasks", "create_task"),
            ("POST", "/timesheets", "create_timesheet"),
        ],
        "tools": ["project_progress"],
    },
    "manufacturing_ops": {
        "meta": (
            "manufacturing_ops",
            "Manufacturing Operations",
            ("db", "inventory_management", "procure_to_pay"),
        ),
        "route": "manufacturing",
        "endpoints": [
            ("POST", "/bom", "create_bom"),
            ("POST", "/work-orders", "create_work_order"),
            ("GET", "/production-plan", "production_plan"),
        ],
        "tools": ["bom_explosion"],
    },
    "assets_quality": {
        "meta": ("assets_quality", "Assets, Quality & Maintenance", ("db", "erp_masters")),
        "route": "assets",
        "endpoints": [
            ("POST", "/assets", "create_asset"),
            ("POST", "/quality-inspections", "create_inspection"),
            ("POST", "/maintenance-visits", "create_maintenance_visit"),
        ],
        "tools": ["asset_depreciation_schedule"],
    },
    "reporting_analytics": {
        "meta": ("reporting_analytics", "ERP Reporting Engine", ("db",)),
        "route": "reports",
        "endpoints": [
            ("POST", "/run", "run_report"),
            ("GET", "/catalog", "report_catalog"),
        ],
        "tools": ["run_erp_report"],
    },
}

TEMPLATE = '''"""NK ERP feature pack: {name}.

Upstream reference: frappe/erpnext (GPL-3.0). Business logic ported to NK services —
not a direct code copy of Frappe ORM/desk layers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from {{{{cookiecutter.project_name}}}}.agents.tools import ToolRegistry, agent_tool
from {{{{cookiecutter.project_name}}}}.erp.features.base import ErpFeaturePackMeta


class _Pack:
    meta = ErpFeaturePackMeta(
        id="{pid}",
        name="{name}",
        requires={requires},
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: Any | None = None,
    ) -> None:
{tool_body}

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/{prefix}", tags=["erp-features"])

{route_handlers}

        return router


PACK = _Pack()
'''


def _tool_body(tools: list[str], pack_id: str) -> str:
    lines: list[str] = []
    for tool in tools:
        if tool == "lookup_item":
            lines += [
                '        @agent_tool("Look up an item master by code")',
                "        async def lookup_item(item_code: str) -> str:",
                '            return f"item:{item_code} (erp_masters stub — wire SQLAlchemy model)"',
                "        registry.register(lookup_item)",
            ]
        elif tool == "calculate_line_totals":
            lines += [
                '        @agent_tool("Calculate taxes and totals for a cart payload")',
                "        async def calculate_line_totals(cart_json: str) -> str:",
                "            from {{cookiecutter.project_name}}.erp.features.common.pricing import calculate_totals_stub",
                "            return str(calculate_totals_stub(cart_json))",
                "        registry.register(calculate_line_totals)",
            ]
        elif tool == "crm_pipeline_summary":
            lines += [
                '        @agent_tool("Summarize CRM pipeline stages and counts")',
                "        async def crm_pipeline_summary() -> str:",
                '            return "CRM pipeline stub — wire Lead/Opportunity models"',
                "        registry.register(crm_pipeline_summary)",
            ]
        elif tool == "open_issues_count":
            lines += [
                '        @agent_tool("Count open support issues")',
                "        async def open_issues_count() -> str:",
                '            return "0 open issues (support_sla stub)"',
                "        registry.register(open_issues_count)",
            ]
        else:
            lines += [
                f'        @agent_tool("ERP tool stub for {pack_id}/{tool}")',
                f"        async def {tool}(query: str = '') -> str:",
                f'            return "{pack_id}.{tool} stub"',
                f"        registry.register({tool})",
            ]
    if not lines:
        lines.append("        pass")
    return "\n".join(lines)


def _route_handlers(endpoints: list[tuple[str, str, str]]) -> str:
    blocks: list[str] = []
    for method, path, handler in endpoints:
        blocks.append(f"        @router.{method.lower()}({path!r})")
        blocks.append(f"        async def {handler}(request: Request) -> dict[str, str]:")
        blocks.append(
            f'            raise HTTPException(status_code=501, detail="{handler} not implemented — port from ERPNext upstream")'
        )
        blocks.append("")
    return "\n".join(blocks)


def main() -> None:
    skipped = 0
    for pid, spec in PACKS.items():
        if pid in INTEGRATED_PACKS:
            skipped += 1
            continue
        pid_val, name, requires = spec["meta"]
        content = TEMPLATE.format(
            pid=pid_val,
            name=name,
            requires=requires,
            prefix=spec["route"],
            tool_body=_tool_body(spec["tools"], pid),
            route_handlers=_route_handlers(spec["endpoints"]),
        )
        dest = ROOT / pid / "__init__.py"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        print("wrote", dest)
    if skipped:
        print(f"skipped {skipped} integrated pack(s)")
    if skipped == len(PACKS):
        print("all packs integrated — nothing to scaffold", file=sys.stderr)
        return


if __name__ == "__main__":
    main()
