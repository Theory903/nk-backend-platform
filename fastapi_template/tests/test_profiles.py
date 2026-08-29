from pathlib import Path

import pytest

from fastapi_template.input_model import BuilderContext
from fastapi_template.profiles import (
    PROFILES,
    expand_profile,
    get_profile,
    profile_contains,
    profile_names,
    profile_value,
)


OTLP_COMPOSE = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
    / "deploy"
    / "docker-compose.otlp.yml"
)


def test_unknown_profile_raises() -> None:
    with pytest.raises(ValueError, match="unknown profile"):
        expand_profile("does-not-exist", BuilderContext())


def test_get_profile_returns_defensive_copy() -> None:
    copy = get_profile("saas")
    copy["otlp_enabled"] = False
    assert PROFILES["saas"]["otlp_enabled"] is True


def test_expand_profile_fills_none_fields() -> None:
    ctx = expand_profile("saas", BuilderContext())
    assert ctx.db == "postgresql"
    assert ctx.orm == "sqlalchemy"
    assert ctx.enable_redis is True
    assert ctx.enable_taskiq is True
    assert ctx.otlp_enabled is True
    assert ctx.add_users is True
    assert ctx.enable_migrations is True


def test_expand_profile_explicit_context_wins() -> None:
    ctx = BuilderContext(db="mongodb", orm="beanie", otlp_enabled=False)
    expanded = expand_profile("saas", ctx)
    assert expanded.db == "mongodb"
    assert expanded.orm == "beanie"
    assert expanded.otlp_enabled is False
    assert expanded.enable_redis is True


def test_minimal_profile_sets_example_routers() -> None:
    ctx = expand_profile("minimal", BuilderContext())
    assert ctx.enable_routers is True


def test_ai_saas_inherits_saas_and_adds_retrieval_stack() -> None:
    ctx = expand_profile("ai-saas", BuilderContext())
    assert ctx.enable_redis is True
    assert ctx.enable_llm is True
    assert ctx.enable_vector is True
    assert ctx.enable_rag_traditional is True
    assert not ctx.dict().get("enable_agents")


def test_agentic_inherits_ai_and_enables_agents() -> None:
    ctx = expand_profile("agentic", BuilderContext())
    assert ctx.enable_llm is True
    assert ctx.enable_agents is True
    assert ctx.enable_graphrag is True


def test_fintech_extends_saas_without_ai() -> None:
    ctx = expand_profile("fintech", BuilderContext())
    assert ctx.enable_audit is True
    assert ctx.enable_idempotency is True
    assert ctx.enable_fintech is True
    assert ctx.add_users is True
    assert ctx.otlp_enabled is True
    assert not ctx.dict().get("enable_llm")
    assert not ctx.dict().get("enable_vector")
    assert not ctx.dict().get("enable_agents")


def test_profile_inspection_helpers() -> None:
    assert "saas" in profile_names()
    assert profile_contains("fintech", "enable_fintech") is True
    assert profile_value("fintech", "enable_llm") is None
    assert profile_value("saas", "otlp_enabled") is True


def test_otlp_compose_uses_otel_stack_service_name() -> None:
    text = OTLP_COMPOSE.read_text(encoding="utf-8")
    assert "http://otel-stack:4317" in text
    assert "otel-collector" not in text
    assert "3000:3000" in text
    assert "# - \"4317:4317\"" in text
    assert "# - \"4318:4318\"" in text
    assert "healthcheck:" in text
    assert "enable_taskiq" in text
