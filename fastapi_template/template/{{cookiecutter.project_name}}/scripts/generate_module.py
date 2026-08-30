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
import json
import keyword
import re
from pathlib import Path


def snake_to_pascal(name: str) -> str:
    """Convert a snake-case identifier to a PascalCase class name."""
    return "".join(word.capitalize() for word in name.split("_"))


def generate_module(
    module_path: str,
    *,
    fields: list[tuple[str, str]] | None = None,
    project_root: Path | None = None,
) -> list[Path]:
    """Generate a CRUD module and return the files written to disk."""
    parts = _validate_module_path(module_path)
    domain, entity_name = parts
    pascal = snake_to_pascal(entity_name)
    plural = entity_name

    root = project_root or Path.cwd()
    package = _detect_package_name(root)
    if not (root / package / "core" / "crud.py").exists():
        raise ValueError(
            "nk generate requires the universal data layer; use a saas, "
            "ai-saas, agentic, or fintech profile",
        )
    _ensure_business_packages(root, domain)
    module_dir = root / "business" / "modules" / domain / entity_name
    module_dir.mkdir(parents=True, exist_ok=True)

    fields = _validate_fields(fields or [("name", "str")])
    query_fields = "{" + ", ".join(
        json.dumps(field_name)
        for field_name in sorted({name for name, _ in fields} | {"id"})
    ) + "}"
    search_query_fields = "{" + ", ".join(
        json.dumps(field_name)
        for field_name, field_type in fields
        if field_type == "str"
    ) + "}"
    defaults = {
        "bool": "False",
        "float": "0.0",
        "int": "0",
        "str": '""',
    }
    search_field_values = [json.dumps(field_name) for field_name, _ in fields]
    search_fields_expr = (
        "("
        + ", ".join(search_field_values)
        + ("," if len(search_field_values) == 1 else "")
        + ")"
    )
    if len(f"    search_fields={search_fields_expr},") > 88:
        search_fields_expr = "(\n" + ",\n".join(
            f"        {field_name}" for field_name in search_field_values
        ) + ",\n    )"
    model_fields = "\n".join(
        f"    {fname}: {ftype} = {defaults[ftype]}"
        for fname, ftype in fields
    )
    create_fields = "\n".join(f"    {fname}: {ftype}" for fname, ftype in fields)
    update_fields = "\n".join(
        f"    {fname}: {ftype} | None = None" for fname, ftype in fields
    )

    files: dict[str, str] = {
        "__init__.py": f'''"""{pascal} business module."""\n''',
        "models.py": f'''"""{pascal} domain model."""


class {pascal}:
    """Domain model for {entity_name}."""

{model_fields}
''',
        "schemas.py": f'''"""Pydantic schemas for {entity_name}."""

from pydantic import BaseModel


class {pascal}Create(BaseModel):
    """Fields accepted when creating a {entity_name}."""

{create_fields}


class {pascal}Update(BaseModel):
    """Fields accepted when updating a {entity_name}."""

{update_fields}


class {pascal}Read({pascal}Create):
    """Response representation of a {entity_name}."""

    id: str
''',
        "service.py": f'''"""CRUD service for {entity_name}."""

from {package}.core.crud import CrudService

from .models import {pascal}


class {pascal}Service(CrudService[{pascal}]):
    """Add custom business logic by overriding hooks."""
''',
        "repository.py": f'''"""Development repository for {entity_name}."""

from {package}.data.adapters.memory.repository import InMemoryRepository

from .models import {pascal}

repository = InMemoryRepository(
    {pascal},
    id_prefix="res",
    search_fields={search_fields_expr},
)
''',
        "router.py": f'''"""Auto-generated CRUD router for {entity_name}."""

from typing import NoReturn

from fastapi import {{"Depends, Request" if cookiecutter.add_users|string|lower == "true" else "Request"}}

from {package}.core.crud import CrudConfig, CrudContext, crud_router
from {package}.core.errors import Problem
from {package}.core.query import QueryAllowList
from {package}.data.adapters.memory.repository import InMemoryRepository
{%- if cookiecutter.add_users|string|lower == "true" %}
from {package}.identity.deps import CurrentUser, RequireCsrf
{%- endif %}
from {package}.settings import settings

from .repository import repository
from .schemas import (
    {pascal}Create,
    {pascal}Read,
    {pascal}Update,
)
from .service import {pascal}Service

if isinstance(repository, InMemoryRepository) and settings.environment.lower() not in (
    "dev",
    "development",
    "test",
    "pytest",
):
    raise RuntimeError(
        "generated module uses an in-memory repository; replace its repository "
        "with a production adapter before starting outside development"
    )


def _raise_not_authenticated() -> NoReturn:
    """Raise the standard authentication problem for protected modules."""
    raise Problem(
        title="Not Authenticated",
        status_code=401,
        detail="authentication credentials are required",
    )


async def _service_factory(request: Request) -> {pascal}Service:
    """Construct the default development service.

    Replace the repository instance with the configured production adapter
    when this module moves beyond local development.
    """
    principal = getattr(request.state, "principal", None)
    org_id: str | None = None
{%- if cookiecutter.add_users|string|lower == "true" %}
    if principal is None or not principal.is_authenticated:
        _raise_not_authenticated()
    org_id = principal.org_id
    scope_id = "org:" + org_id if org_id is not None else "user:" + principal.user_id
    scoped_repository = repository.scoped(org_id, scope_id=scope_id)
{%- else %}
    scoped_repository = repository
{%- endif %}
    return {pascal}Service(
        scoped_repository,
        context=CrudContext(
            principal=principal,
            org_id=org_id,
        ),
        config=CrudConfig(
            resource_name="{entity_name}",
            allow_list=QueryAllowList(
                filter_fields=frozenset({query_fields}),
                sort_fields=frozenset({query_fields}),
                search_fields=frozenset({search_query_fields}),
            ),
        ),
    )


router = crud_router(
    service_factory=_service_factory,
    prefix="/{plural}",
    tags=["{domain.title()}"],
    create_schema={pascal}Create,
    update_schema={pascal}Update,
    response_schema={pascal}Read,
    config=CrudConfig(
        resource_name="{entity_name}",
        allow_list=QueryAllowList(
            filter_fields=frozenset({query_fields}),
            sort_fields=frozenset({query_fields}),
            search_fields=frozenset({search_query_fields}),
        ),
    ),
{%- if cookiecutter.add_users|string|lower == "true" %}
    dependencies=[Depends(CurrentUser), Depends(RequireCsrf())],
{%- endif %}
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


def _validate_module_path(module_path: str) -> tuple[str, str]:
    """Validate the domain/entity convention used by discovery."""
    parts = tuple(part.strip() for part in module_path.split("."))
    if len(parts) != 2 or any(
        not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", part)
        or keyword.iskeyword(part)
        for part in parts
    ):
        raise ValueError(
            "module path must be '<domain>.<module>' using lowercase "
            "letters, digits, and underscores",
        )
    return parts[0], parts[1]


def _validate_fields(fields: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Allow only safe identifiers and non-executable primitive annotations."""
    allowed_types = {"bool", "float", "int", "str"}
    reserved = {
        "copy",
        "dict",
        "from_orm",
        "json",
        "model_config",
        "model_copy",
        "model_dump",
        "model_dump_json",
        "model_extra",
        "model_fields",
        "model_fields_set",
        "model_json_schema",
        "model_validate",
        "model_validate_json",
        "parse_obj",
        "parse_raw",
        "schema",
        "schema_json",
        "created_at",
        "deleted_at",
        "id",
        "org_id",
        "version",
    }
    seen: set[str] = set()
    for field_name, field_type in fields:
        if (
            not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", field_name)
            or keyword.iskeyword(field_name)
            or field_name in reserved
            or field_type not in allowed_types
            or field_name in seen
        ):
            raise ValueError(
                f"invalid field {field_name!r}:{field_type!r}; use unique, "
                "non-reserved lowercase names and one of "
                "bool, float, int, str",
            )
        seen.add(field_name)
    return fields


def _ensure_business_packages(root: Path, domain: str) -> None:
    """Create importable namespace packages for discovered modules."""
    for package_dir in (
        root / "business",
        root / "business" / "modules",
        root / "business" / "modules" / domain,
    ):
        package_dir.mkdir(parents=True, exist_ok=True)
        init_file = package_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""Generated business package."""\n')


def main() -> None:
    """Parse CLI arguments and generate the requested business module."""
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
    domain, entity = _validate_module_path(args.module_path)
    print(f"\nMounted by convention at /api/v1/{domain}/{entity}")
    print("Next steps:")
    print("  1. Add business logic to service.py hooks")
    print("  2. Run `uv run nk check`")


if __name__ == "__main__":
    main()
