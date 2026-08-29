#!/usr/bin/env python3
"""Scaffold a new CRUD business module inside a generated project.

Usage:
    python -m scripts.generate_module crm.leads [--fields name:str email:str]
    python -m scripts.generate_module catalog.products

Creates:
    business/modules/crm/leads/__init__.py
    business/modules/crm/leads/models.py
    business/modules/crm/leads/schemas.py
    business/modules/crm/leads/service.py
    business/modules/crm/leads/router.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def snake_to_pascal(name: str) -> str:
    return "".join(word.capitalize() for word in name.split("_"))


def generate_module(
    module_path: str,
    *,
    fields: list[tuple[str, str]] | None = None,
    project_root: Path | None = None,
) -> list[Path]:
    parts = module_path.split(".")
    entity_name = parts[-1]
    domain = parts[0] if len(parts) > 1 else "app"
    pascal = snake_to_pascal(entity_name)
    plural = entity_name

    root = project_root or Path.cwd()
    package = _detect_package_name(root)
    module_dir = root / "business" / "modules" / domain / entity_name
    module_dir.mkdir(parents=True, exist_ok=True)

    fields = fields or [("name", "str")]
    model_fields = "\n".join(f'    {fname}: {ftype} = ""' for fname, ftype in fields)
    create_fields = "\n".join(f"    {fname}: {ftype}" for fname, ftype in fields)
    update_fields = "\n".join(
        f"    {fname}: {ftype} | None = None" for fname, ftype in fields
    )

    files: dict[str, str] = {
        "__init__.py": "",
        "models.py": f'''"""{pascal} domain model."""


class {pascal}:
{model_fields}
''',
        "schemas.py": f'''"""Pydantic schemas for {entity_name}."""

from pydantic import BaseModel


class {pascal}Create(BaseModel):
{create_fields}


class {pascal}Update(BaseModel):
{update_fields}


class {pascal}Read({pascal}Create):
    id: str
''',
        "service.py": f'''"""CRUD service for {entity_name}."""

from {package}.business.modules.{domain}.{entity_name}.models import {pascal}
from {package}.core.crud import CrudService


class {pascal}Service(CrudService[{pascal}]):
    """Add custom business logic by overriding hooks."""
''',
        "router.py": f'''"""Auto-generated CRUD router for {entity_name}."""

from {package}.business.modules.{domain}.{entity_name}.schemas import (
    {pascal}Create,
    {pascal}Read,
    {pascal}Update,
)
from {package}.business.modules.{domain}.{entity_name}.service import {pascal}Service
from {package}.core.crud import CrudConfig, CrudContext, CrudService, crud_router


async def _service_factory() -> CrudService:
    """Wire repository, tenant, and audit into the service.

    Replace NotImplementedError with your DI / repository construction.
    """
    raise NotImplementedError(
        "provide repository wiring in {pascal} service_factory"
    )


router = crud_router(
    service_factory=_service_factory,
    prefix="/{plural}",
    tags=["{domain.title()}"],
    create_schema={pascal}Create,
    update_schema={pascal}Update,
    response_schema={pascal}Read,
    config=CrudConfig(resource_name="{entity_name}"),
)
''',
    }

    written: list[Path] = []
    for filename, content in files.items():
        filepath = module_dir / filename
        filepath.write_text(content)
        written.append(filepath)

    return written


def _detect_package_name(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        for line in pyproject.read_text().splitlines():
            if line.strip().startswith("name ="):
                return line.split("=")[1].strip().strip('"').strip("'")
    return "app"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a CRUD business module.")
    parser.add_argument("module_path", help="Dot-separated path, e.g. crm.leads")
    parser.add_argument(
        "--fields",
        nargs="*",
        default=["name:str"],
        help="Field definitions as name:type pairs. Default: name:str",
    )
    args = parser.parse_args()

    fields = []
    for field_spec in args.fields:
        if ":" in field_spec:
            fname, ftype = field_spec.split(":", 1)
        else:
            fname, ftype = field_spec, "str"
        fields.append((fname, ftype))

    written = generate_module(args.module_path, fields=fields)
    print(f"Module '{args.module_path}' generated:")
    for filepath in written:
        print(f"   {filepath}")
    print("\nNext steps:")
    print("  1. Implement _service_factory repository wiring in router.py")
    print("  2. Add business logic to service.py hooks")
    print("  3. Import router in web/api/router.py")
    print("  4. Run tests")


if __name__ == "__main__":
    main()
