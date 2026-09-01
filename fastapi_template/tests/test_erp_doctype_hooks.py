"""Tests for universal DocType controller hooks on submit."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

ERP_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "erp"
)


def _strip_project_imports(code: str) -> str:
    out: list[str] = []
    skip = False
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("from {{cookiecutter.project_name}}") or stripped.startswith("from nk_erp_test"):
            skip = True
            continue
        if skip:
            if stripped == ")" or (line and not line.startswith((" ", "\t"))):
                skip = False
                if stripped != ")":
                    out.append(line)
            continue
        out.append(line)
    return "\n".join(out)


def _exec_hooks() -> dict:
    ns: dict = {}
    for rel in ("schemas/transaction.py", "services/pricing.py", "services/status_engine.py"):
        path = ERP_ROOT / rel
        code = _strip_project_imports(path.read_text(encoding="utf-8"))
        exec(compile(code, str(path), "exec"), ns)  # noqa: S102
    ns["TransactionDocument"].model_rebuild(_types_namespace=ns)
    ns["TransactionTotals"].model_rebuild(_types_namespace=ns)
    registry_path = ERP_ROOT / "schemas" / "doctype_registry.py"
    registry_code = _strip_project_imports(registry_path.read_text(encoding="utf-8"))
    ns["__file__"] = str(registry_path)
    exec(compile(registry_code, str(registry_path), "exec"), ns)  # noqa: S102
    hooks_path = ERP_ROOT / "services" / "doctype_hooks.py"
    hooks_code = _strip_project_imports(hooks_path.read_text(encoding="utf-8"))
    exec(compile(hooks_code, str(hooks_path), "exec"), ns)  # noqa: S102
    return ns


def test_recalculate_totals_from_json_items() -> None:
    ns = _exec_hooks()
    data = {
        "currency": "USD",
        "items": [{"item_code": "ITEM-A", "qty": 3, "rate": 50.0}],
        "taxes": [{"description": "VAT", "rate": 10.0, "charge_type": "On Net Total"}],
    }
    totals = ns["recalculate_totals"](data)
    assert totals["net_total"] == 150.0
    assert totals["total_taxes"] == 15.0
    assert totals["grand_total"] == 165.0


def test_sales_order_status_after_submit_payload() -> None:
    ns = _exec_hooks()

    class _Record:
        doctype = "Sales Order"
        docstatus = 1
        data = {"per_delivered": 0, "per_billed": 0}
        meta: dict = {}

    record = _Record()
    payload = ns["status_payload_from_record"](record, totals={"grand_total": 1000.0})
    status = ns["resolve_status"]("sales_order", payload)
    assert status == "To Deliver and Bill"


def test_build_posting_adapter_maps_internal_doctype() -> None:
    ns = _exec_hooks()

    class _Record:
        id = uuid4()
        doctype = "Sales Invoice"
        docstatus = 1
        data = {
            "items": [{"item_code": "X", "qty": 1, "rate": 10.0}],
            "customer": str(uuid4()),
            "posting_date": "2026-09-01",
        }
        meta = {"totals": {"grand_total": 10.0}}

    adapter = ns["build_posting_adapter"](_Record(), totals={"grand_total": 10.0})
    assert adapter.doctype == "sales_invoice"
    assert len(adapter.lines) == 1
    assert adapter.customer_id is not None


def test_doctype_hooks_module_exists() -> None:
    assert (ERP_ROOT / "services" / "doctype_hooks.py").is_file()
    text = (ERP_ROOT / "services" / "doctype.py").read_text(encoding="utf-8")
    assert "DoctypeHookService" in text
