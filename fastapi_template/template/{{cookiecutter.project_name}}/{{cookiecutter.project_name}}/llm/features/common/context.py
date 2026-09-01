"""Runtime context shared across feature packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from {{cookiecutter.project_name}}.agents.memory import MemoryStore


@dataclass(slots=True)
class FeatureContext:
    """Services resolved at application startup."""

    rag_service: Any | None = None
    memory_store: MemoryStore | None = None
    hybrid_retriever: Any | None = None
    default_user_id: str = "default"
