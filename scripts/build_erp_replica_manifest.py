#!/usr/bin/env python3
"""Generate ERPNext replica manifests (reports + controllers) from temp/erpnext."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML required") from None

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "temp" / "erpnext"
ERP = (
    REPO
    / "fastapi_template"
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "erp"
)
REPORT_MANIFEST = ERP / "schemas" / "reports" / "manifest.yaml"
REPORT_COLUMNS = ERP / "schemas" / "reports" / "columns_index.yaml"
CONTROLLER_MANIFEST = ERP / "schemas" / "controllers" / "manifest.yaml"
DOCTYPE_MANIFEST = ERP / "schemas" / "doctypes" / "manifest.yaml"

FIELDNAME_RE = re.compile(r"""fieldname\s*=\s*['"]([\w]+)['"]""")

MODULE_CONTROLLER: dict[str, str] = {
    "accounts": "accounts_controller",
    "stock": "stock_controller",
    "selling": "selling_controller",
    "buying": "buying_controller",
    "manufacturing": "subcontracting_controller",
    "subcontracting": "subcontracting_controller",
    "assets": "accounts_controller",
    "projects": "accounts_controller",
    "support": "status_updater",
    "crm": "status_updater",
}


def _iter_reports() -> list[dict]:
    rows: list[dict] = []
    if not SOURCE.is_dir():
        return rows
    for path in sorted(SOURCE.rglob("*.json")):
        if path.parent.parent.name != "report":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("doctype") != "Report":
            continue
        report_id = path.parent.name.replace("_", "-")
        rows.append(
            {
                "id": report_id,
                "name": data.get("report_name") or data.get("name") or path.parent.name,
                "module": (data.get("module") or "").lower(),
                "ref_doctype": data.get("ref_doctype"),
                "report_type": data.get("report_type"),
                "upstream_path": str(path.relative_to(SOURCE)),
                "filters": data.get("filters") or [],
            }
        )
    return rows


def _extract_columns(py_path: Path) -> list[dict[str, str]]:
    if not py_path.is_file():
        return []
    text = py_path.read_text(encoding="utf-8", errors="ignore")
    if "get_columns" not in text:
        return []
    start = text.find("def get_columns")
    if start < 0:
        return []
    chunk = text[start : start + 12000]
    seen: set[str] = set()
    columns: list[dict[str, str]] = []
    for match in FIELDNAME_RE.finditer(chunk):
        field = match.group(1)
        if field in seen:
            continue
        seen.add(field)
        columns.append({"field": field, "label": field.replace("_", " ").title()})
    return columns


def _build_report_columns(reports: list[dict]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    for row in reports:
        py_path = SOURCE / row["upstream_path"].replace(".json", ".py")
        py_path = py_path.parent / f"{py_path.parent.name}.py"
        cols = _extract_columns(py_path)
        if cols:
            index[row["id"]] = cols
    return index


def _build_controllers() -> dict:
    if not DOCTYPE_MANIFEST.is_file():
        return {"doctypes": [], "count": 0}
    manifest = yaml.safe_load(DOCTYPE_MANIFEST.read_text(encoding="utf-8")) or {}
    rows = []
    for dt in manifest.get("doctypes") or []:
        module = (dt.get("module") or "").lower()
        controller = MODULE_CONTROLLER.get(module, "status_updater")
        rows.append(
            {
                "name": dt["name"],
                "module": module,
                "controller": controller,
                "is_submittable": bool(dt.get("is_submittable")),
                "nk_table": dt.get("nk_table"),
            }
        )
    return {
        "version": 1,
        "source": "temp/erpnext",
        "controller_count": len({r["controller"] for r in rows}),
        "doctype_count": len(rows),
        "doctypes": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    reports = _iter_reports()
    report_payload = {
        "version": 1,
        "source": "temp/erpnext",
        "report_count": len(reports),
        "reports": reports,
    }
    columns_payload = {
        "version": 1,
        "report_count": len(reports),
        "columns_extracted": 0,
        "reports": _build_report_columns(reports),
    }
    columns_payload["columns_extracted"] = len(columns_payload["reports"])
    controllers = _build_controllers()

    print(f"reports={len(reports)} columns={columns_payload['columns_extracted']} controllers={controllers['controller_count']}")
    if args.write:
        REPORT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        CONTROLLER_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        REPORT_MANIFEST.write_text(yaml.safe_dump(report_payload, sort_keys=False), encoding="utf-8")
        REPORT_COLUMNS.write_text(yaml.safe_dump(columns_payload, sort_keys=False), encoding="utf-8")
        CONTROLLER_MANIFEST.write_text(yaml.safe_dump(controllers, sort_keys=False), encoding="utf-8")
        print(f"wrote {REPORT_MANIFEST}")
        print(f"wrote {REPORT_COLUMNS}")
        print(f"wrote {CONTROLLER_MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
