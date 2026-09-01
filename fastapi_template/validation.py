"""Feature dependency validation for BuilderContext (pre-cookiecutter gate)."""

from __future__ import annotations

import re

from fastapi_template.compatibility import validate_compatibility
from fastapi_template.config import resolve_config
from fastapi_template.input_model import BuilderContext
from fastapi_template.profiles import validate_use_case

_ORM_WITH_MIGRATIONS = frozenset(
    {"sqlalchemy", "ormar", "tortoise", "piccolo", "beanie"},
)
_SQL_ORMS = frozenset({"sqlalchemy", "ormar", "tortoise", "piccolo", "psycopg"})
_MONGO_ORMS = frozenset({"beanie"})
_SNAKE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _truthy(value: object) -> bool:
    return value is True or value in ("True", "true", "1", 1)


def _get(ctx: BuilderContext, key: str, default: object = None) -> object:
    data = ctx.dict()
    return data.get(key, default)


def validate_context(context: BuilderContext) -> None:
    """
    Raise ValueError with a one-line fix hint when feature flags conflict.

    Call after profile expand + menu fill-in, before cookiecutter.
    """
    errors: list[str] = []

    project_name = _get(context, "project_name")
    if project_name is not None and not _SNAKE_NAME.match(str(project_name)):
        errors.append(
            f"project_name={project_name!r} must be snake_case (e.g. happy_app, not happy-app)",
        )

    use_case = _get(context, "use_case")
    if use_case not in (None, ""):
        try:
            validate_use_case(str(use_case))
        except ValueError as exc:
            errors.append(str(exc))

    enable_llm = _truthy(_get(context, "enable_llm"))
    enable_vector = _truthy(_get(context, "enable_vector"))
    enable_rag = _truthy(_get(context, "enable_rag_traditional"))
    enable_agents = _truthy(_get(context, "enable_agents"))
    enable_graphrag = _truthy(_get(context, "enable_graphrag"))
    enable_fintech = _truthy(_get(context, "enable_fintech"))
    enable_audit = _truthy(_get(context, "enable_audit"))
    enable_idempotency = _truthy(_get(context, "enable_idempotency"))
    enable_migrations = _truthy(_get(context, "enable_migrations"))
    enable_redis = _truthy(_get(context, "enable_redis"))
    add_users = _truthy(_get(context, "add_users"))

    db = _get(context, "db") or "none"
    orm = _get(context, "orm") or "none"

    if enable_agents and not enable_llm:
        errors.append("enable_agents requires --llm (or an AI profile)")
    if enable_graphrag and not enable_llm:
        errors.append("enable_graphrag requires --llm")
    if enable_rag and not enable_llm:
        errors.append("enable_rag_traditional requires --llm")
    if enable_rag and not enable_vector:
        errors.append("enable_rag_traditional requires --vector")

    if enable_fintech and not enable_audit:
        errors.append("enable_fintech requires --audit")
    if enable_fintech and not enable_idempotency:
        errors.append("enable_fintech requires --idempotency")

    if db == "none" and orm != "none":
        errors.append(f"orm={orm!r} requires a database (--db postgresql|…)")
    if db != "none" and orm == "none":
        errors.append(f"db={db!r} requires an ORM (--orm sqlalchemy|…)")

    if db == "mongodb" and orm not in _MONGO_ORMS | {"none"}:
        if orm in _SQL_ORMS:
            errors.append("mongodb requires --orm beanie")
    if db in {"postgresql", "mysql", "sqlite"} and orm in _MONGO_ORMS:
        errors.append(f"db={db!r} is incompatible with orm=beanie")

    if enable_migrations and orm not in _ORM_WITH_MIGRATIONS:
        errors.append(
            f"enable_migrations requires an ORM with migrations (got orm={orm!r})",
        )

    if add_users and db == "none":
        errors.append("add_users / identity requires a database (--db …)")
    if add_users and orm != "sqlalchemy":
        errors.append("add_users / identity currently requires --orm sqlalchemy")
    if add_users and not enable_migrations and not enable_redis:
        errors.append(
            "add_users / identity requires --migrations or --redis for durable stores",
        )
    if enable_idempotency and not enable_redis:
        errors.append(
            "enable_idempotency requires --redis for a durable shared store",
        )
    if enable_agents and not add_users:
        errors.append("enable_agents requires identity/authentication (--users)")

    if errors:
        hint = "; ".join(errors)
        raise ValueError(f"invalid project options: {hint}")

    # Run the canonical cross-layer rules after the legacy option checks so
    # callers receive the familiar error for existing combinations while all
    # new AI Stack constraints remain centralized.
    validate_compatibility(resolve_config(context))
