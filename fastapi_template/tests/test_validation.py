"""Tests for pre-cookiecutter feature dependency validation."""

from __future__ import annotations

import pytest

from fastapi_template.input_model import BuilderContext
from fastapi_template.validation import validate_context


def test_agents_require_llm() -> None:
    ctx = BuilderContext(
        project_name="x",
        db="none",
        orm="none",
        enable_agents=True,
        enable_llm=False,
    )
    with pytest.raises(ValueError, match="enable_agents requires --llm"):
        validate_context(ctx)


def test_rag_requires_llm_and_vector() -> None:
    ctx = BuilderContext(
        project_name="x",
        db="none",
        orm="none",
        enable_rag_traditional=True,
        enable_llm=True,
        enable_vector=False,
    )
    with pytest.raises(ValueError, match="enable_rag_traditional requires --vector"):
        validate_context(ctx)


def test_fintech_requires_audit_and_idempotency() -> None:
    ctx = BuilderContext(
        project_name="x",
        db="postgresql",
        orm="sqlalchemy",
        enable_fintech=True,
        enable_audit=False,
        enable_idempotency=True,
    )
    with pytest.raises(ValueError, match="enable_fintech requires --audit"):
        validate_context(ctx)


def test_orm_without_db_fails() -> None:
    ctx = BuilderContext(project_name="x", db="none", orm="sqlalchemy")
    with pytest.raises(ValueError, match="requires a database"):
        validate_context(ctx)


def test_valid_minimal_passes() -> None:
    ctx = BuilderContext(
        project_name="happy_app",
        db="none",
        orm="none",
        enable_routers=True,
    )
    validate_context(ctx)


def test_hyphenated_project_name_rejected() -> None:
    ctx = BuilderContext(project_name="happy-app", db="none", orm="none")
    with pytest.raises(ValueError, match="snake_case"):
        validate_context(ctx)


def test_valid_agentic_flags_pass() -> None:
    ctx = BuilderContext(
        project_name="x",
        db="postgresql",
        orm="sqlalchemy",
        enable_llm=True,
        enable_vector=True,
        enable_rag_traditional=True,
        enable_agents=True,
        enable_graphrag=True,
    )
    validate_context(ctx)
