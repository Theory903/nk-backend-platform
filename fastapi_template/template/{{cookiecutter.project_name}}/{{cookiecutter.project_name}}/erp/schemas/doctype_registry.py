"""ERPNext DocType field schemas and registry."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_SCHEMAS_DIR = Path(__file__).resolve().parent / "doctypes"
_MANIFEST = _SCHEMAS_DIR / "manifest.yaml"
_FIELD_INDEX = _SCHEMAS_DIR / "field_index.yaml"


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    if not _MANIFEST.is_file():
        return {"doctypes": [], "doctype_count": 0}
    return yaml.safe_load(_MANIFEST.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def load_field_index() -> dict[str, Any]:
    if not _FIELD_INDEX.is_file():
        return {"doctypes": {}}
    return yaml.safe_load(_FIELD_INDEX.read_text(encoding="utf-8")) or {}


def list_doctypes(*, module: str | None = None) -> list[dict[str, Any]]:
    rows = load_manifest().get("doctypes") or []
    if module:
        rows = [r for r in rows if r.get("module") == module]
    return [
        {
            "name": r["name"],
            "module": r.get("module"),
            "field_count": r.get("field_count", 0),
            "is_submittable": r.get("is_submittable", False),
            "nk_table": r.get("nk_table"),
        }
        for r in rows
    ]


def get_doctype_meta(name: str) -> dict[str, Any] | None:
    manifest_rows = {r["name"]: r for r in load_manifest().get("doctypes") or []}
    base = manifest_rows.get(name)
    if base is None:
        return None
    fields = (load_field_index().get("doctypes") or {}).get(name) or {}
    return {
        **base,
        "fields": fields.get("fields") or [],
        "autoname": fields.get("autoname"),
    }


def slugify(doctype: str) -> str:
    return doctype.lower().replace(" ", "-").replace("/", "-")
