from pathlib import Path

import pytest

from fastapi_template.input_model import BuilderContext
from fastapi_template.profiles import (
    PROFILES,
    complete_profile,
    expand_profile,
    get_profile,
    profile_contains,
    profile_description,
    profile_names,
    profile_value,
    use_case_description,
    use_case_names,
    use_case_profile,
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
    assert ctx.prometheus_enabled is True
    assert ctx.add_users is True
    assert ctx.enable_migrations is True


def test_expand_profile_explicit_context_wins() -> None:
    ctx = BuilderContext(db="mongodb", orm="beanie", otlp_enabled=False)
    expanded = expand_profile("saas", ctx)
    assert expanded.db == "mongodb"
    assert expanded.orm == "beanie"
    assert expanded.otlp_enabled is False
    assert expanded.enable_redis is True


def test_complete_profile_resolves_all_optional_choices() -> None:
    ctx = complete_profile(
        "saas",
        BuilderContext(enable_kafka=True, enable_rmq=None, cookie_auth=None),
    )

    assert ctx.enable_kafka is True
    assert ctx.enable_redis is True
    assert ctx.jwt_auth is True
    assert ctx.gunicorn is True
    assert ctx.cookie_auth is False
    assert ctx.enable_nats is False
    assert ctx.enable_llm is False


def test_profile_description_is_architecture_facing() -> None:
    assert "PostgreSQL/SQLAlchemy" in profile_description("saas")


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


def test_production_ai_extends_agentic_with_scale_controls() -> None:
    ctx = expand_profile("production-ai", BuilderContext())
    assert ctx.enable_agents is True
    assert ctx.enable_graphrag is True
    assert ctx.enable_audit is True
    assert ctx.enable_idempotency is True
    assert ctx.enable_nats is True


def test_fintech_extends_saas_without_ai() -> None:
    ctx = expand_profile("fintech", BuilderContext())
    assert ctx.enable_audit is True
    assert ctx.enable_idempotency is True
    assert ctx.enable_fintech is True
    assert ctx.add_users is True
    assert ctx.otlp_enabled is True
    assert ctx.prometheus_enabled is True
    assert not ctx.dict().get("enable_llm")
    assert not ctx.dict().get("enable_vector")
    assert not ctx.dict().get("enable_agents")


def test_profile_inspection_helpers() -> None:
    assert "saas" in profile_names()
    assert profile_contains("fintech", "enable_fintech") is True
    assert profile_value("fintech", "enable_llm") is None
    assert profile_value("saas", "otlp_enabled") is True


def test_use_case_catalog_maps_product_intent_to_profiles() -> None:
    assert set(use_case_names()) == {
        "minimal-api",
        "saas",
        "enterprise-saas",
        "crud-platform",
        "integration-api",
        "data-platform",
        "search-platform",
        "knowledge-platform",
        "ai-saas",
        "ai-knowledge",
        "agentic",
        "automation-platform",
        "event-platform",
        "fintech",
        "internal-tool",
        "developer-api",
        "webhook-platform",
        "high-scale-api",
        "custom",
    }
    assert use_case_profile("enterprise-saas") == "saas"
    assert use_case_profile("ai-knowledge") == "ai-saas"
    assert use_case_profile("custom") is None
    assert "knowledge" in use_case_description("knowledge-platform")


def test_unknown_use_case_raises() -> None:
    with pytest.raises(ValueError, match="unknown use case"):
        use_case_profile("does-not-exist")


def test_otlp_compose_uses_otel_stack_service_name() -> None:
    text = OTLP_COMPOSE.read_text(encoding="utf-8")
    assert "http://otel-collector:4317" in text
    assert "otel-collector" in text
    assert "prometheus:" in text
    assert "loki:" in text
    assert "tempo:" in text
    assert "grafana:" in text
    assert "grafana/otel-lgtm:latest" not in text
    assert "${NK_GRAFANA_PORT:-${GRAFANA_PORT:-3000}}:3000" in text
    assert "healthcheck:" in text
