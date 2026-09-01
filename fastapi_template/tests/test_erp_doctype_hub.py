"""Universal DocType hub tests."""

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


def test_field_index_covers_all_doctypes() -> None:
    manifest = yaml.safe_load((ERP_ROOT / "schemas" / "doctypes" / "manifest.yaml").read_text())
    field_index = yaml.safe_load((ERP_ROOT / "schemas" / "doctypes" / "field_index.yaml").read_text())
    assert manifest["doctype_count"] >= 500
    assert field_index["doctype_count"] == manifest["doctype_count"]
    assert manifest.get("universal_api_count") == manifest["doctype_count"]
    assert len(field_index["doctypes"]) == manifest["doctype_count"]


def test_sales_order_in_field_index() -> None:
    field_index = yaml.safe_load((ERP_ROOT / "schemas" / "doctypes" / "field_index.yaml").read_text())
    so = field_index["doctypes"]["Sales Order"]
    assert so["is_submittable"] is True
    fieldnames = {f["fieldname"] for f in so["fields"]}
    assert "customer" in fieldnames
    assert "items" in fieldnames


def test_doctype_hub_pack_exists() -> None:
    path = ERP_ROOT / "features" / "doctype_hub" / "__init__.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "/doctypes" in text
    assert "submit_record" in text


def test_doctype_registry_slugify() -> None:
    code = (ERP_ROOT / "schemas" / "doctype_registry.py").read_text(encoding="utf-8")
    lines = [line for line in code.splitlines() if "{{cookiecutter.project_name}}" not in line]
    ns: dict = {"__file__": str(ERP_ROOT / "schemas" / "doctype_registry.py")}
    exec(compile("\n".join(lines), "doctype_registry.py", "exec"), ns)  # noqa: S102
    assert ns["slugify"]("Sales Order") == "sales-order"
    assert ns["slugify"]("Purchase Invoice") == "purchase-invoice"


def test_doctype_service_module_exists() -> None:
    assert (ERP_ROOT / "services" / "doctype.py").is_file()
    migration = (
        Path(__file__).resolve().parents[1]
        / "template"
        / "{{cookiecutter.project_name}}"
        / "{{cookiecutter.project_name}}"
        / "db_sa"
        / "migrations"
        / "versions"
        / "2026-09-02-erp_doctype.py"
    )
    assert migration.is_file()
    assert "erp_doctype_record" in migration.read_text()
