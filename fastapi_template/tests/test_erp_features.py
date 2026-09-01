"""Tests for ERP feature packs and first-party erp/ module."""

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


def test_erp_catalog_maps_upstream() -> None:
    catalog_path = ERP_ROOT / "features" / "catalog.yaml"
    assert catalog_path.is_file()
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    assert data["doctype_count"] >= 500
    assert len(data["packs"]) >= 13


def test_first_party_erp_modules_exist() -> None:
    for rel in (
        "bootstrap.py",
        "runtime.py",
        "patterns.py",
        "services/pricing.py",
        "services/valuation.py",
        "services/masters.py",
        "services/crm.py",
        "services/support.py",
        "services/documents.py",
        "services/ledger.py",
        "services/stock.py",
        "services/billing.py",
        "services/reports.py",
        "services/lifecycle.py",
        "services/status_engine.py",
        "services/posting.py",
        "services/item_details.py",
        "services/regional_tax.py",
        "services/dunning.py",
        "services/workflow.py",
        "services/bank_reconciliation.py",
        "services/doctype.py",
        "services/doctype_hooks.py",
        "services/report_registry.py",
        "services/report_columns.py",
        "services/report_data.py",
        "services/payment_schedule.py",
        "services/controller_replica.py",
        "schemas/doctype_registry.py",
        "schemas/doctypes/field_index.yaml",
        "schemas/bank.py",
        "tax_templates.yaml",
        "schemas/doctypes/manifest.yaml",
        "schemas/transaction.py",
        "features/deps.py",
        "features/registry.py",
        "features/router.py",
    ):
        assert (ERP_ROOT / rel).is_file(), rel


def test_integrated_feature_packs_exist() -> None:
    for name in (
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
):
        path = ERP_ROOT / "features" / name / "__init__.py"
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert "501" not in text, f"{name} still has stub 501 handlers"


def test_erp_models_exist() -> None:
    models = (
        Path(__file__).resolve().parents[1]
        / "template"
        / "{{cookiecutter.project_name}}"
        / "{{cookiecutter.project_name}}"
        / "db_sa"
        / "models"
        / "erp"
        / "__init__.py"
    )
    assert models.is_file()


def test_pack_imports_use_cookiecutter_placeholders() -> None:
    import re

    bad = re.compile(r"(?<!\{)\{cookiecutter\.project_name\}(?!\})")
    for name in ("erp_masters", "crm_pipeline", "pricing_taxes", "support_sla"):
        text = (ERP_ROOT / "features" / name / "__init__.py").read_text(encoding="utf-8")
        assert bad.search(text) is None, name
        assert "{{cookiecutter.project_name}}" in text, name
