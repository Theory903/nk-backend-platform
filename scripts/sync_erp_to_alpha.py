#!/usr/bin/env python3
"""Sync rendered ERP module from cookiecutter template into alpha/ reference app."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = REPO / "fastapi_template" / "template" / "{{cookiecutter.project_name}}"
ALPHA_ROOT = REPO / "alpha"
PROJECT = "alpha"

COPY_PATHS = (
    "{{cookiecutter.project_name}}/erp",
    "{{cookiecutter.project_name}}/db_sa/models/erp",
    "{{cookiecutter.project_name}}/db_sa/migrations/versions/2026-09-01-erp_core.py",
    "{{cookiecutter.project_name}}/db_sa/migrations/versions/2026-09-01-erp_transactions.py",
    "{{cookiecutter.project_name}}/db_sa/migrations/versions/2026-09-02-erp_parity.py",
    "{{cookiecutter.project_name}}/db_sa/migrations/versions/2026-09-02-erp_bank.py",
    "{{cookiecutter.project_name}}/db_sa/migrations/versions/2026-09-02-erp_doctype.py",
    "{{cookiecutter.project_name}}/db_sa/migrations/versions/2026-09-02-erp_payment_terms.py",
    "{{cookiecutter.project_name}}/db_sa/migrations/versions/2026-09-02-erp_payment_terms_masters.py",
)

REGISTRY_TRUE = re.compile(
    r"\{% if cookiecutter\.db_info\.name != \"none\"[^%]*%\}True\{% else %\}False\{% endif %\}"
)
REGISTRY_ORM = re.compile(
    r"\{% if cookiecutter\.orm != \"sqlalchemy\"[^%]*%\}True\{% else %\}False\{% endif %\}"
)


def _render(text: str) -> str:
    text = text.replace("{{cookiecutter.project_name}}", PROJECT)
    text = REGISTRY_TRUE.sub("True", text)
    text = REGISTRY_ORM.sub("False", text)
    return text


def _sync_path(rel: str, *, dry_run: bool) -> None:
    src = TEMPLATE_ROOT / rel
    dst_rel = rel.replace("{{cookiecutter.project_name}}", PROJECT)
    dst = ALPHA_ROOT / dst_rel
    if not src.exists():
        print(f"skip missing {src}")
        return
    if src.is_dir():
        if dst.exists() and not dry_run:
            shutil.rmtree(dst)
        if dry_run:
            print(f"would copy tree {src} -> {dst}")
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        for path in dst.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".yaml", ".toml", ".md"}:
                path.write_text(_render(path.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"copied tree {dst_rel}")
        return
    if dry_run:
        print(f"would copy file {src} -> {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(_render(src.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"copied {dst_rel}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not ALPHA_ROOT.is_dir():
        raise SystemExit(f"alpha app not found at {ALPHA_ROOT}")
    for rel in COPY_PATHS:
        _sync_path(rel, dry_run=args.dry_run)
    print("Note: wire alpha/alpha/web/lifespan.py (wire_erp_bootstrap) and web/api/router.py manually if not present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
