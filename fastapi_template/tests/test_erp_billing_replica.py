"""ERPNext AR/AP aging replica tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

ERP_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "erp"
)


def _load_report_data() -> dict:
    path = ERP_ROOT / "services" / "report_data.py"
    ns: dict = {}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)  # noqa: S102
    return ns


def test_age_bucket_boundaries() -> None:
    ns = _load_report_data()
    ranges = [30, 60, 90, 120]
    assert ns["age_bucket"](10, ranges) == 1
    assert ns["age_bucket"](45, ranges) == 2
    assert ns["age_bucket"](200, ranges) == 5


def test_receivable_row_has_aging_columns() -> None:
    ns = _load_report_data()
    row = ns["build_receivable_row"](
        party_type="Customer",
        party="cust-1",
        party_account="Debtors - NK",
        voucher_type="Sales Invoice",
        voucher_no="SINV-00001",
        posting_date=date(2026, 8, 1),
        due_date=date(2026, 8, 31),
        amount=1000.0,
        outstanding=400.0,
        report_date=date(2026, 9, 1),
        ranges=[30, 60, 90, 120],
    )
    assert row["invoiced"] == 1000.0
    assert row["paid"] == 600.0
    assert row["outstanding"] == 400.0
    assert row["age"] == 1
    assert row["range1"] == 400.0
    assert row["party"] == "cust-1"


def test_billing_service_exports_replica_methods() -> None:
    text = (ERP_ROOT / "services" / "billing.py").read_text(encoding="utf-8")
    assert "receivable_payable_detail" in text
    assert "receivable_summary" in text
    assert "build_receivable_row" in text


def test_reports_use_ageing_columns() -> None:
    text = (ERP_ROOT / "services" / "reports.py").read_text(encoding="utf-8")
    assert "ageing_columns" in text
    assert "unmapped handler" not in text
