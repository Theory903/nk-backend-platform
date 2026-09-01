#!/usr/bin/env python3
"""Generate erp/schemas/doctypes/manifest.yaml + field_index.yaml from temp/erpnext."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML required") from None

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "temp" / "erpnext"
OUT_DIR = (
    REPO
    / "fastapi_template"
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "erp"
    / "schemas"
    / "doctypes"
)
MANIFEST = OUT_DIR / "manifest.yaml"
FIELD_INDEX = OUT_DIR / "field_index.yaml"

IMPLEMENTED: dict[str, str] = {
    "Item": "erp_item",
    "Customer": "erp_customer",
    "Supplier": "erp_supplier",
    "Lead": "erp_lead",
    "Opportunity": "erp_opportunity",
    "Issue": "erp_issue",
    "Sales Order": "erp_document",
    "Quotation": "erp_document",
    "Delivery Note": "erp_document",
    "Sales Invoice": "erp_document",
    "Purchase Order": "erp_document",
    "Purchase Receipt": "erp_document",
    "Purchase Invoice": "erp_document",
    "Journal Entry": "erp_gl_entry",
    "GL Entry": "erp_gl_entry",
    "Stock Ledger Entry": "erp_stock_ledger_entry",
    "Project": "erp_project",
    "Task": "erp_task",
    "Timesheet": "erp_timesheet",
    "BOM": "erp_bom",
    "Work Order": "erp_work_order",
    "Asset": "erp_asset",
    "Quality Inspection": "erp_quality_inspection",
    "Maintenance Visit": "erp_maintenance_visit",
    "Payment Ledger Entry": "erp_payment_ledger",
    "Bank Transaction": "erp_bank_transaction",
}

SKIP_FIELD_TYPES = frozenset({"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold"})


def _iter_doctypes() -> list[dict]:
    rows: list[dict] = []
    if not SOURCE.is_dir():
        return rows
    for path in sorted(SOURCE.rglob("*.json")):
        if path.parent.name != path.stem:
            continue
        if path.parent.parent.name != "doctype":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("doctype") != "DocType":
            continue
        name = data.get("name") or path.stem.replace("_", " ").title()
        module = path.relative_to(SOURCE).parts[1] if len(path.relative_to(SOURCE).parts) > 1 else ""
        fields = data.get("fields") or []
        rows.append(
            {
                "name": name,
                "module": module,
                "field_count": len(fields),
                "is_submittable": bool(data.get("is_submittable")),
                "nk_table": IMPLEMENTED.get(name),
                "upstream_path": str(path.relative_to(SOURCE)),
                "_raw": data,
            }
        )
    return rows


def _compact_fields(raw: dict) -> list[dict]:
    out: list[dict] = []
    for field in raw.get("fields") or []:
        ftype = field.get("fieldtype") or ""
        if ftype in SKIP_FIELD_TYPES:
            continue
        out.append(
            {
                "fieldname": field.get("fieldname"),
                "fieldtype": ftype,
                "label": field.get("label"),
                "options": field.get("options"),
                "reqd": bool(field.get("reqd")),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write manifest.yaml + field_index.yaml")
    parser.add_argument("--limit", type=int, default=0, help="Limit doctypes (0=all)")
    args = parser.parse_args()

    rows = _iter_doctypes()
    if args.limit:
        rows = rows[: args.limit]

    manifest_rows = [{k: v for k, v in r.items() if k != "_raw"} for r in rows]
    implemented = [r for r in manifest_rows if r.get("nk_table")]
    universal = len(manifest_rows)  # all accessible via erp_doctype_record

    manifest = {
        "upstream": "frappe/erpnext",
        "doctype_count": len(manifest_rows),
        "implemented_count": len(implemented),
        "specialized_table_count": len(implemented),
        "universal_api_count": universal,
        "coverage_pct": 100.0,
        "specialized_coverage_pct": round(100.0 * len(implemented) / max(len(manifest_rows), 1), 1),
        "doctypes": manifest_rows,
    }

    field_index = {
        "upstream": "frappe/erpnext",
        "doctype_count": len(manifest_rows),
        "doctypes": {
            r["name"]: {
                "module": r["module"],
                "is_submittable": r["is_submittable"],
                "autoname": r["_raw"].get("autoname"),
                "fields": _compact_fields(r["_raw"]),
            }
            for r in rows
        },
    }

    print(yaml.safe_dump({**manifest, "field_index_doctypes": len(field_index["doctypes"])}, sort_keys=False)[:3000])
    if args.write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
        FIELD_INDEX.write_text(yaml.safe_dump(field_index, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(
            f"wrote {MANIFEST} + {FIELD_INDEX} ({len(manifest_rows)} doctypes, {len(implemented)} specialized)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
