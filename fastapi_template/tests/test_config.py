"""Tests for the canonical typed generator configuration."""

from __future__ import annotations

import pytest

from fastapi_template.compatibility import CompatibilityError, validate_compatibility
from fastapi_template.config import GeneratorConfig, resolve_config
from fastapi_template.input_model import BuilderContext


def test_resolve_config_maps_context_to_stack_capabilities() -> None:
    config = resolve_config(
        BuilderContext(
            project_name="knowledge_app",
            profile="ai-saas",
            use_case="ai-knowledge",
            api_type="rest",
            db="postgresql",
            orm="sqlalchemy",
            ci_type="github",
            enable_llm=True,
            enable_vector=True,
            enable_rag_traditional=True,
            enable_redis=True,
            enable_taskiq=True,
            prometheus_enabled=True,
            otlp_enabled=True,
        ),
    )

    assert isinstance(config, GeneratorConfig)
    assert config.capabilities.rag is True
    assert config.use_case == "ai-knowledge"
    assert config.storage.vectors == "pgvector"
    assert config.storage.lexical == "postgresql-fts"
    assert config.storage.checkpoints == "none"
    assert config.observability == {
        "prometheus": True,
        "opentelemetry": True,
        "sentry": False,
    }


def test_compatibility_rejects_native_rag_without_postgresql() -> None:
    config = resolve_config(
        BuilderContext(
            project_name="knowledge_app",
            db="sqlite",
            orm="sqlalchemy",
            enable_llm=True,
            enable_vector=True,
            enable_rag_traditional=True,
        ),
    )

    with pytest.raises(CompatibilityError, match="native vector path"):
        validate_compatibility(config)


def test_compatibility_accepts_agentic_reference_path() -> None:
    config = resolve_config(
        BuilderContext(
            project_name="agent_app",
            db="postgresql",
            orm="sqlalchemy",
            enable_llm=True,
            enable_vector=True,
            enable_rag_traditional=True,
            enable_agents=True,
            enable_redis=True,
            enable_taskiq=True,
        ),
    )

    assert config.storage.checkpoints == "postgresql"
    validate_compatibility(config)


def test_compatibility_rejects_memory_only_audit() -> None:
    config = resolve_config(
        BuilderContext(
            project_name="audit_app",
            db="postgresql",
            orm="sqlalchemy",
            enable_audit=True,
        ),
    )

    with pytest.raises(CompatibilityError, match="shared Redis sink"):
        validate_compatibility(config)


def test_compatibility_rejects_agent_without_shared_state_store() -> None:
    config = resolve_config(
        BuilderContext(
            project_name="agent_app",
            db="postgresql",
            orm="sqlalchemy",
            enable_llm=True,
            enable_agents=True,
        ),
    )

    with pytest.raises(CompatibilityError, match="shared Redis state store"):
        validate_compatibility(config)
