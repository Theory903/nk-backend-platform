from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi_template.input_model import BuilderContext


# ============================================================================
# Profile definitions
# ============================================================================

_MINIMAL: dict[str, Any] = {
    "api_type": "rest",
    "ci_type": "none",
    "db": "none",
    "orm": "none",
    "enable_routers": True,
}

_SAAS: dict[str, Any] = {
    **_MINIMAL,
    "ci_type": "github",
    "db": "postgresql",
    "orm": "sqlalchemy",
    "enable_redis": True,
    "enable_taskiq": True,
    "otlp_enabled": True,
    "prometheus_enabled": True,
    "add_users": True,
    "jwt_auth": True,
    "gunicorn": True,
    "enable_migrations": True,
}

_AI_SAAS: dict[str, Any] = {
    **_SAAS,
    "enable_llm": True,
    "enable_vector": True,
    "enable_rag_traditional": True,
}

_AGENTIC: dict[str, Any] = {
    **_AI_SAAS,
    "enable_agents": True,
    "enable_graphrag": True,
}

_PRODUCTION_AI: dict[str, Any] = {
    **_AGENTIC,
    "enable_audit": True,
    "enable_idempotency": True,
    "enable_nats": True,
}

_PRODUCTION_AI_LOCAL: dict[str, Any] = {
    **_AGENTIC,
    "enable_audit": True,
    "profile": "production-ai-local",
}

_FINTECH: dict[str, Any] = {
    **_SAAS,
    "enable_audit": True,
    "enable_idempotency": True,
    "enable_fintech": True,
}


PROFILES: dict[str, dict[str, Any]] = {
    "minimal": _MINIMAL,
    "saas": _SAAS,
    "ai-saas": _AI_SAAS,
    "agentic": _AGENTIC,
    "production-ai": _PRODUCTION_AI,
    "production-ai-local": _PRODUCTION_AI_LOCAL,
    "fintech": _FINTECH,
}

PROFILE_DESCRIPTIONS: dict[str, str] = {
    "minimal": "REST + no database + no infrastructure",
    "saas": (
        "REST + PostgreSQL/SQLAlchemy + Redis/Taskiq + JWT + migrations "
        "+ OTel/Prometheus + Gunicorn"
    ),
    "ai-saas": "SaaS baseline + LLM + vector storage + traditional RAG",
    "agentic": "AI SaaS + agent runtime + GraphRAG",
    "production-ai": (
        "Agentic stack + audit + idempotency + NATS (NK-native AI modules)"
    ),
    "production-ai-local": (
        "Agentic stack + audit, Ollama-only — no external API keys required"
    ),
    "fintech": "SaaS baseline + audit trail + idempotency + fintech primitives",
}

# Product-oriented intents are deliberately mapped to existing architecture
# profiles. This keeps the product-first CLI honest until dedicated domain
# packs exist for concerns such as data ingestion or high-scale deployment.
USE_CASE_PROFILES: dict[str, str | None] = {
    "minimal-api": "minimal",
    "saas": "saas",
    "enterprise-saas": "saas",
    "crud-platform": "saas",
    "integration-api": "saas",
    "data-platform": "saas",
    "search-platform": "saas",
    "knowledge-platform": "ai-saas",
    "ai-saas": "ai-saas",
    "ai-knowledge": "ai-saas",
    "agentic": "agentic",
    "production-ai": "production-ai",
    "production-ai-local": "production-ai-local",
    "automation-platform": "saas",
    "event-platform": "saas",
    "fintech": "fintech",
    "internal-tool": "saas",
    "developer-api": "saas",
    "webhook-platform": "saas",
    "high-scale-api": "saas",
    "custom": None,
}

USE_CASE_DESCRIPTIONS: dict[str, str] = {
    "minimal-api": "Small APIs, prototypes, and internal utilities",
    "saas": "Multi-user SaaS products",
    "enterprise-saas": "Enterprise SaaS with tenancy, RBAC, audit, and integrations",
    "crud-platform": "CRUD-heavy business applications",
    "integration-api": "API integrations, webhooks, and external systems",
    "data-platform": "Data ingestion, processing, and asynchronous workflows",
    "search-platform": "Search, indexing, and retrieval systems",
    "knowledge-platform": "Document and knowledge products",
    "ai-saas": "AI-powered SaaS applications",
    "ai-knowledge": "RAG and enterprise knowledge systems",
    "agentic": "Tool-using AI applications",
    "production-ai": "Production AI platform with full catalog and scale controls",
    "automation-platform": "Workflow and task automation",
    "event-platform": "Event-driven and message-based systems",
    "fintech": "Transactional and financial workloads",
    "internal-tool": "Admin panels, operations, and internal systems",
    "developer-api": "Public APIs and developer platforms",
    "webhook-platform": "Reliable inbound and outbound webhook infrastructure",
    "high-scale-api": "High-throughput production APIs",
    "custom": "Fully composable architecture",
}

# Options not explicitly defined by a profile are deliberately disabled when
# a profile is selected. This makes ``--profile`` a reproducible architecture
# choice instead of a partially pre-filled interactive questionnaire.
PROFILE_OPTION_DEFAULTS: dict[str, bool] = {
    "enable_redis": False,
    "add_users": False,
    "enable_rmq": False,
    "enable_taskiq": False,
    "enable_migrations": False,
    "add_dummy": False,
    "enable_routers": False,
    "self_hosted_swagger": False,
    "prometheus_enabled": False,
    "sentry_enabled": False,
    "enable_loguru": False,
    "otlp_enabled": False,
    "traefik_labels": False,
    "enable_kafka": False,
    "enable_nats": False,
    "gunicorn": False,
    "enable_llm": False,
    "enable_vector": False,
    "enable_rag_traditional": False,
    "enable_agents": False,
    "enable_graphrag": False,
    "enable_audit": False,
    "enable_idempotency": False,
    "enable_fintech": False,
    "cookie_auth": False,
    "jwt_auth": False,
}


# ============================================================================
# Validation
# ============================================================================
# Profile *names* are validated here. Feature dependency constraints live in
# fastapi_template.validation.validate_context (called before cookiecutter).


def validate_profile(name: str) -> None:
    """Raise ValueError when the requested profile does not exist."""
    if name not in PROFILES:
        available = ", ".join(sorted(PROFILES))
        raise ValueError(f"unknown profile '{name}'. available profiles: {available}")


# ============================================================================
# Profile resolution
# ============================================================================


def get_profile(name: str) -> dict[str, Any]:
    """
    Return a defensive copy of a profile.

    Global profile definitions are never exposed for mutation.
    """
    validate_profile(name)
    return deepcopy(PROFILES[name])


def expand_profile(
    name: str,
    context: BuilderContext,
) -> BuilderContext:
    """
    Apply a profile to the builder context.

    Existing values always win.

    A profile only supplies values for fields that are currently unset
    (``not context.is_set(key)`` — missing or ``None``). Explicit
    ``False`` / other values are preserved.
    """
    preset = get_profile(name)

    for key, value in preset.items():
        if not context.is_set(key):
            setattr(context, key, deepcopy(value))

    return context


def complete_profile(
    name: str,
    context: BuilderContext,
) -> BuilderContext:
    """
    Apply a profile and deterministic defaults for every optional feature.

    Explicit command-line values always win. This is used by the non-
    interactive profile path; omitting ``--profile`` continues to expose
    every option in the interactive wizard.
    """
    expanded = expand_profile(name, context)
    for key, value in PROFILE_OPTION_DEFAULTS.items():
        if not expanded.is_set(key):
            setattr(expanded, key, deepcopy(value))
    return expanded


# ============================================================================
# Profile inspection
# ============================================================================


def profile_names() -> tuple[str, ...]:
    """Return all supported profile names."""
    return tuple(sorted(PROFILES))


def profile_description(name: str) -> str:
    """Return the architecture summary shown by the generator CLI."""
    validate_profile(name)
    return PROFILE_DESCRIPTIONS[name]


def validate_use_case(name: str) -> None:
    """Raise ValueError when the requested use case does not exist."""
    if name not in USE_CASE_PROFILES:
        available = ", ".join(sorted(USE_CASE_PROFILES))
        raise ValueError(f"unknown use case '{name}'. available use cases: {available}")


def use_case_names() -> tuple[str, ...]:
    """Return all supported product-oriented use cases."""
    return tuple(sorted(USE_CASE_PROFILES))


def use_case_description(name: str) -> str:
    """Return the product-oriented summary shown by the generator CLI."""
    validate_use_case(name)
    return USE_CASE_DESCRIPTIONS[name]


def use_case_profile(name: str) -> str | None:
    """Return the architecture profile selected by a use case."""
    validate_use_case(name)
    return USE_CASE_PROFILES[name]


def profile_contains(
    name: str,
    key: str,
) -> bool:
    """Return whether a profile defines a particular option."""
    validate_profile(name)
    return key in PROFILES[name]


def profile_value(
    name: str,
    key: str,
    default: Any = None,
) -> Any:
    """Return a defensive copy of a profile option."""
    validate_profile(name)
    return deepcopy(PROFILES[name].get(key, default))


# ============================================================================
# Compatibility
# ============================================================================


def apply_profile(
    name: str,
    context: BuilderContext,
) -> BuilderContext:
    """Backward-compatible alias for expand_profile()."""
    return expand_profile(name, context)
