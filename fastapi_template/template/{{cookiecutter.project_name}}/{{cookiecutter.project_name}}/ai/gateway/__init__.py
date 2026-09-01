"""Public LLM gateway API.

Provides a stable import surface for model routing while keeping provider
and routing implementation details internal.
"""

from {{cookiecutter.project_name}}.ai.gateway.router import (
    ModelRouter,
    get_router,
)
from {{cookiecutter.project_name}}.ai.gateway.capabilities import resolve_capability

__all__ = [
    "ModelRouter",
    "get_router",
    "resolve_capability",
]