"""Public LLM gateway API.

Provides a stable import surface for model routing while keeping provider
and routing implementation details internal.
"""

from {{cookiecutter.project_name}}.ai.gateway.router import (
    ModelRouter,
    get_router,
)

__all__ = [
    "ModelRouter",
    "get_router",
]