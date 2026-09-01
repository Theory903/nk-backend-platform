"""Shared runtime services for LLM feature packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from {{cookiecutter.project_name}}.agents.memory import MemoryStore


@dataclass(slots=True)
class FeatureRuntime:
    """Process-local services wired during application startup."""

    memory_store: MemoryStore
    hybrid_retriever: Any | None = None


def get_or_create_runtime(app: Any) -> FeatureRuntime:
    """Return the feature runtime, creating an in-memory default if needed."""
    runtime = getattr(app.state, "feature_runtime", None)
    if isinstance(runtime, FeatureRuntime):
        return runtime
    runtime = FeatureRuntime(memory_store=MemoryStore())
    app.state.feature_runtime = runtime
    return runtime


__all__ = ["FeatureRuntime", "get_or_create_runtime"]
