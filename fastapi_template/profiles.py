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
    "enable_fintech": True,
}


PROFILES: dict[str, dict[str, Any]] = {
    "minimal": _MINIMAL,
    "saas": _SAAS,
    "ai-saas": _AI_SAAS,
    "agentic": _AGENTIC,
    "fintech": _FINTECH,
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
        raise ValueError(
            f"unknown profile '{name}'. "
            f"available profiles: {available}"
        )


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


# ============================================================================
# Profile inspection
# ============================================================================


def profile_names() -> tuple[str, ...]:
    """Return all supported profile names."""
    return tuple(sorted(PROFILES))


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
