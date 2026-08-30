"""Development persistence adapters."""

from {{cookiecutter.project_name}}.data.adapters.memory.repository import (
    InMemoryRepository,
)

__all__ = ["InMemoryRepository"]
