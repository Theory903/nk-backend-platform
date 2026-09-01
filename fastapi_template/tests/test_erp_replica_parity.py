"""Toe-to-toe ERPNext replica structural parity tests."""

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


def test_replica_report_manifest_exists() -> None:
    manifest = ERP_ROOT / "schemas" / "reports" / "manifest.yaml"
    assert manifest.is_file()
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert data["report_count"] >= 170


def test_replica_controller_manifest_covers_doctypes() -> None:
    manifest = ERP_ROOT / "schemas" / "controllers" / "manifest.yaml"
    doctypes = yaml.safe_load((ERP_ROOT / "schemas" / "doctypes" / "manifest.yaml").read_text())
    controllers = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert controllers["doctype_count"] == doctypes["doctype_count"]
    assert controllers["controller_count"] >= 6


def test_accounts_receivable_replica_columns() -> None:
    columns = yaml.safe_load((ERP_ROOT / "schemas" / "reports" / "columns_index.yaml").read_text())
    ar = columns["reports"]["accounts-receivable"]
    fields = {c["field"] for c in ar}
    assert "party" in fields
    assert "outstanding" in fields


def test_controller_replica_validates_selling() -> None:
    path = ERP_ROOT / "services" / "controller_replica.py"
    text = path.read_text(encoding="utf-8")
    assert "ControllerReplica" in text
    assert "_validate_selling" in text
    assert "Customer is mandatory" in text
    assert "controller_replica" in (ERP_ROOT / "services" / "doctype.py").read_text()
    assert "controller_replica" in (ERP_ROOT / "services" / "documents.py").read_text()


def test_reports_service_returns_replica_flag() -> None:
    text = (ERP_ROOT / "services" / "reports.py").read_text(encoding="utf-8")
    assert "replica" in text
    assert "report_columns" in text
