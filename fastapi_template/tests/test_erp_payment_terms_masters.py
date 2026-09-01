"""Payment term masters + templates tests."""

from __future__ import annotations

from pathlib import Path

ERP_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "erp"
)


def test_payment_term_models_exist() -> None:
    text = (ERP_ROOT.parent / "db_sa" / "models" / "erp" / "__init__.py").read_text(encoding="utf-8")
    assert "class ErpPaymentTerm" in text
    assert "class ErpPaymentTermsTemplate" in text


def test_payment_term_schemas_exist() -> None:
    text = (ERP_ROOT / "schemas" / "masters.py").read_text(encoding="utf-8")
    assert "class PaymentTermCreate" in text
    assert "class PaymentTermsTemplateCreate" in text


def test_masters_service_has_term_methods() -> None:
    text = (ERP_ROOT / "services" / "masters.py").read_text(encoding="utf-8")
    assert "async def create_payment_term" in text
    assert "async def list_payment_terms" in text
    assert "async def create_payment_terms_template" in text
    assert "async def list_payment_terms_templates" in text


def test_masters_routes_expose_term_endpoints() -> None:
    text = (ERP_ROOT / "features" / "erp_masters" / "__init__.py").read_text(encoding="utf-8")
    assert "/payment-terms" in text
    assert "/payment-terms-templates" in text


def test_payment_term_migration_exists() -> None:
    path = ERP_ROOT.parent / "db_sa" / "migrations" / "versions" / "2026-09-02-erp_payment_terms_masters.py"
    assert path.is_file()
    assert "erp_payment_terms_masters_20260902" in path.read_text()


def test_payment_schedule_uses_terms_key() -> None:
    text = (ERP_ROOT / "services" / "payment_schedule.py").read_text(encoding="utf-8")
    assert "if terms:" in text
    assert 'invoice_portion' in text
    assert 'credit_days' in text
