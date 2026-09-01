"""Payment schedule and multi-row AR term tests."""

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


def _load_schedule() -> dict:
    path = ERP_ROOT / "services" / "payment_schedule.py"
    ns: dict = {}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)  # noqa: S102
    return ns


def test_30_70_schedule_splits_amounts() -> None:
    ns = _load_schedule()
    rows = ns["build_payment_schedule"](1000.0, date(2026, 9, 1), template_id="30-70")
    assert len(rows) == 2
    assert rows[0]["payment_amount"] == 300.0
    assert rows[1]["payment_amount"] == 700.0
    assert rows[0]["payment_term"] == "Advance 30%"
    assert rows[1]["due_date"] == "2026-10-01"


def test_posting_records_per_term() -> None:
    text = (ERP_ROOT / "services" / "posting.py").read_text(encoding="utf-8")
    assert "_record_party_ledger" in text
    assert "payment_term" in text
    assert "build_payment_schedule" in text


def test_payment_ledger_model_has_term_fields() -> None:
    text = (
        ERP_ROOT.parent / "db_sa" / "models" / "erp" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "payment_term" in text
    assert "due_date" in text


def test_migration_payment_terms_exists() -> None:
    path = ERP_ROOT.parent / "db_sa" / "migrations" / "versions" / "2026-09-02-erp_payment_terms.py"
    assert path.is_file()
    assert "erp_payment_terms_20260902" in path.read_text()


def test_ar_report_includes_payment_term_column() -> None:
    text = (ERP_ROOT / "services" / "report_data.py").read_text(encoding="utf-8")
    assert '"payment_term"' in text
