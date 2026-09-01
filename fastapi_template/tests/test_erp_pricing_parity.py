"""Behavioral parity tests for NK ERP pricing and status engine."""

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


def _exec_template(rel: str, ns: dict | None = None) -> dict:
    path = ERP_ROOT / rel
    code = path.read_text(encoding="utf-8").replace("{{cookiecutter.project_name}}", "nk_erp_test")
    namespace = ns if ns is not None else {}
    exec(compile(code, str(path), "exec"), namespace)  # noqa: S102
    return namespace


def _pricing_bundle() -> dict:
    ns = _exec_template("schemas/transaction.py")
    ns["TransactionDocument"].model_rebuild(_types_namespace=ns)
    ns["TransactionTotals"].model_rebuild(_types_namespace=ns)
    path = ERP_ROOT / "services/pricing.py"
    code = path.read_text(encoding="utf-8")
    # Drop NK import block — symbols already in ns from schemas/transaction.py
    out: list[str] = []
    skip = False
    for line in code.splitlines():
        if line.strip().startswith("from {{cookiecutter.project_name}}"):
            skip = True
            continue
        if skip:
            if line.strip() == ")":
                skip = False
            continue
        out.append(line)
    exec(compile("\n".join(out), str(path), "exec"), ns)  # noqa: S102
    return ns


def test_pricing_net_total_and_tax() -> None:
    ns = _pricing_bundle()
    doc = ns["TransactionDocument"](
        items=[ns["ItemLine"](item_code="ITEM-1", qty=2, rate=100.0)],
        taxes=[ns["TaxLine"](description="VAT", rate=10.0, charge_type="On Net Total")],
    )
    totals = ns["PricingService"]().calculate(doc)
    assert totals.net_total == 200.0
    assert totals.total_taxes == 20.0
    assert totals.grand_total == 220.0


def test_pricing_grand_total_discount() -> None:
    ns = _pricing_bundle()
    doc = ns["TransactionDocument"](
        items=[ns["ItemLine"](qty=1, rate=1000.0)],
        additional_discount_percentage=10.0,
        apply_discount_on="Grand Total",
    )
    totals = ns["PricingService"]().calculate(doc)
    assert totals.discount_amount == 100.0
    assert totals.net_total == 900.0


def test_status_engine_sales_order_completed() -> None:
    ns = _exec_template("services/status_engine.py")
    label = ns["resolve_status"](
        "sales_order",
        {"docstatus": 1, "per_delivered": 100, "per_billed": 100, "status": "Draft"},
    )
    assert label == "Completed"


def test_status_engine_sales_order_to_deliver() -> None:
    ns = _exec_template("services/status_engine.py")
    label = ns["resolve_status"](
        "sales_order",
        {"docstatus": 1, "per_delivered": 0, "per_billed": 100, "status": "Draft"},
    )
    assert label == "To Deliver"


def test_parity_manifest_exists() -> None:
    path = ERP_ROOT / "parity.yaml"
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["lifecycle"]["docstatus_submitted"] is True
    assert data["coverage"]["feature_packs"] >= 14
    assert "nk_extras" in data


def test_lifecycle_services_exist() -> None:
    for rel in (
        "services/lifecycle.py",
        "services/status_engine.py",
        "services/posting.py",
        "services/item_details.py",
        "services/regional_tax.py",
        "services/dunning.py",
        "services/workflow.py",
        "tax_templates.yaml",
        "features/documents_hub/__init__.py",
    ):
        assert (ERP_ROOT / rel).is_file(), rel


def test_regional_tax_templates() -> None:
    import yaml

    path = ERP_ROOT / "tax_templates.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    templates = data.get("templates") or {}
    assert "india_gst_intra" in templates
    assert len(templates["india_gst_intra"]["taxes"]) == 2
    assert "eu_vat_standard" in templates


def test_doctype_manifest_exists() -> None:
    manifest = ERP_ROOT / "schemas" / "doctypes" / "manifest.yaml"
    assert manifest.is_file()
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert data["doctype_count"] >= 500
    assert data["implemented_count"] >= 20


def _load_regional_tax(ns: dict | None = None) -> dict:
    bundle = ns if ns is not None else _pricing_bundle()
    path = ERP_ROOT / "services/regional_tax.py"
    code = path.read_text(encoding="utf-8")
    out = [line for line in code.splitlines() if "{{cookiecutter.project_name}}" not in line]
    bundle["__file__"] = str(path)
    exec(compile("\n".join(out), str(path), "exec"), bundle)  # noqa: S102
    return bundle


def test_regional_tax_apply_india_gst() -> None:
    ns = _load_regional_tax()
    svc = ns["RegionalTaxService"]()
    doc = ns["TransactionDocument"](items=[ns["ItemLine"](qty=1, rate=1000.0)])
    _enriched, result = svc.apply_template(doc, "india_gst_intra")
    totals = result["totals"]
    assert totals["total_taxes"] == 180.0
    assert totals["grand_total"] == 1180.0


def test_regional_tax_resolve_us_ca() -> None:
    ns = _load_regional_tax()
    svc = ns["RegionalTaxService"]()
    assert svc.resolve_template(country="US", state="CA") == "us_sales_tax_ca"
