from typing import Any

from fastapi_template.input_model import BuilderContext

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
    "add_users": True,
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

_FINTECH: dict[str, Any] = {
    **_SAAS,
    "enable_audit": True,
    "enable_idempotency": True,
}

PROFILES: dict[str, dict[str, Any]] = {
    "minimal": _MINIMAL,
    "saas": _SAAS,
    "ai-saas": _AI_SAAS,
    "agentic": _AGENTIC,
    "fintech": _FINTECH,
}


def expand_profile(name: str, context: BuilderContext) -> BuilderContext:
    """
    Apply a named profile preset onto the builder context.

    Preset values never override choices already present in the context.

    :param name: profile key from PROFILES.
    :param context: current builder context.
    :return: the same context with preset defaults applied.
    """
    preset = PROFILES[name]
    data = context.dict()
    for key, value in preset.items():
        if data.get(key) is None:
            context[key] = value
    return context
