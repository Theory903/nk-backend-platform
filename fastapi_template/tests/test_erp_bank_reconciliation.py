"""Bank reconciliation CSV parse tests."""

from __future__ import annotations

from pathlib import Path

ERP_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "erp"
)


def _load_bank_parser() -> type:
    schema_path = ERP_ROOT / "schemas" / "bank.py"
    schema_code = schema_path.read_text(encoding="utf-8")
    ns: dict = {"__file__": str(schema_path)}
    exec(compile(schema_code, str(schema_path), "exec"), ns)  # noqa: S102
    for model in ("BankRowImport", "BankImportRequest", "BankReconcileRequest", "BankMatchSuggestion", "BankCsvImport"):
        ns[model].model_rebuild(_types_namespace=ns)
    path = ERP_ROOT / "services" / "bank_reconciliation.py"
    code = path.read_text(encoding="utf-8")
    lines = [line for line in code.splitlines() if "{{cookiecutter.project_name}}" not in line]
    ns["__file__"] = str(path)
    exec(compile("\n".join(lines), str(path), "exec"), ns)  # noqa: S102
    return ns["BankReconciliationService"]


def test_bank_csv_parse_deposit_withdrawal() -> None:
    svc = _load_bank_parser()
    # session not needed for parse_csv
    parser = svc(session=None, org_id="test")  # type: ignore[arg-type]
    csv_text = "date,description,deposit,withdrawal\n2026-09-01,Wire in,500.00,0\n2026-09-02,Fee,0,25.50\n"
    payload = parser.parse_csv(csv_text)
    assert len(payload.rows) == 2
    assert payload.rows[0].deposit == 500.0
    assert payload.rows[1].withdrawal == 25.5


def test_bank_service_module_exists() -> None:
    assert (ERP_ROOT / "services" / "bank_reconciliation.py").is_file()
    assert (ERP_ROOT / "schemas" / "bank.py").is_file()
