"""All 170 ERPNext catalog reports must resolve to a handler."""

from __future__ import annotations

from pathlib import Path

import yaml

ERP_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "erp"
)

HANDLERS = frozenset(
    {
        "accounts_receivable",
        "accounts_payable",
        "trial_balance",
        "general_ledger",
        "bank",
        "stock_balance",
        "stock_ledger",
        "sales_register",
        "purchase_register",
        "sales_orders",
        "gross_profit",
        "crm_pipeline",
        "issue_analytics",
        "doctype_catalog",
        "doctype_counts",
        "manufacturing",
        "projects",
        "assets",
        "payment_terms",
    }
)


def _load_registry() -> dict:
    path = ERP_ROOT / "services" / "report_registry.py"
    code = path.read_text(encoding="utf-8").replace("{{cookiecutter.project_name}}", "nk_erp_test")
    ns: dict = {"__file__": str(path)}
    exec(compile(code, str(path), "exec"), ns)  # noqa: S102
    return ns


def test_all_catalog_reports_classify() -> None:
    catalog = yaml.safe_load((ERP_ROOT / "features" / "catalog.yaml").read_text())
    reports = [r for r in catalog["upstream"] if r.get("kind") == "report"]
    assert len(reports) == 170
    ns = _load_registry()
    for row in reports:
        handler = ns["classify_report"](row["id"], module=row.get("module", ""))
        assert handler in HANDLERS, f"{row['id']} -> {handler}"


def test_wired_report_count() -> None:
    ns = _load_registry()
    assert ns["wired_report_count"]() == 170


def test_report_registry_module_exists() -> None:
    assert (ERP_ROOT / "services" / "report_registry.py").is_file()
    text = (ERP_ROOT / "services" / "reports.py").read_text(encoding="utf-8")
    assert "report_registry" in text
    assert "extend ReportsService" not in text
