"""Feature dependency validation for BuilderContext (pre-cookiecutter gate)."""

from __future__ import annotations

import re

from fastapi_template.input_model import BuilderContext

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
            f"project_name={project_name!r} must be snake_case "
            f"(e.g. happy_app, not happy-app)",
        )

    enable_llm = _truthy(_get(context, "enable_llm"))
    enable_vector = _truthy(_get(context, "enable_vector"))
    enable_rag = _truthy(_get(context, "enable_rag_traditional"))
    enable_agents = _truthy(_get(context, "enable_agents"))
    enable_graphrag = _truthy(_get(context, "enable_graphrag"))
    enable_fintech = _truthy(_get(context, "enable_fintech"))
    enable_audit = _truthy(_get(context, "enable_audit"))
    enable_idempotency = _truthy(_get(context, "enable_idempotency"))
    enable_migrations = _truthy(_get(context, "enable_migrations"))
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
            f"enable_migrations requires an ORM with migrations "
            f"(got orm={orm!r})",
        )

    if add_users and db == "none":
        errors.append("add_users / identity requires a database (--db …)")

    if errors:
        hint = "; ".join(errors)
        raise ValueError(f"invalid project options: {hint}")
