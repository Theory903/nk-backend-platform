import pytest

from fastapi_template.input_model import BuilderContext
from fastapi_template.profiles import expand_profile


def test_unknown_profile_raises() -> None:
    with pytest.raises(KeyError):
        expand_profile("does-not-exist", BuilderContext())


def test_minimal_profile_sets_example_routers() -> None:
    ctx = expand_profile("minimal", BuilderContext())
    assert ctx.enable_routers is True


def test_saas_profile_sets_full_service_stack() -> None:
    ctx = expand_profile("saas", BuilderContext())
    assert ctx.db == "postgresql"
    assert ctx.orm == "sqlalchemy"
    assert ctx.enable_redis is True
    assert ctx.enable_taskiq is True
    assert ctx.otlp_enabled is True
    assert ctx.add_users is True
    assert ctx.enable_migrations is True


def test_ai_saas_inherits_saas_and_adds_retrieval_stack() -> None:
    ctx = expand_profile("ai-saas", BuilderContext())
    assert ctx.enable_redis is True
    assert ctx.enable_llm is True
    assert ctx.enable_vector is True
    assert ctx.enable_rag_traditional is True


def test_ai_saas_does_not_force_agentic_bits() -> None:
    ctx = expand_profile("ai-saas", BuilderContext())
    assert not ctx.dict().get("enable_agents")


def test_agentic_inherits_ai_and_enables_agents() -> None:
    ctx = expand_profile("agentic", BuilderContext())
    assert ctx.enable_llm is True
    assert ctx.enable_agents is True
    assert ctx.enable_graphrag is True


def test_fintech_extends_saas_with_audit_controls() -> None:
    ctx = expand_profile("fintech", BuilderContext())
    assert ctx.enable_audit is True
    assert ctx.enable_idempotency is True
    assert ctx.add_users is True


def test_expansion_never_overrides_explicit_choices() -> None:
    ctx = BuilderContext(db="mongodb", orm="beanie")
    expanded = expand_profile("saas", ctx)
    assert expanded.db == "mongodb"
    assert expanded.orm == "beanie"


def test_expansion_leaves_non_core_values_unset() -> None:
    ctx = expand_profile("minimal", BuilderContext())
    assert ctx.dict().get("enable_kafka") is None
