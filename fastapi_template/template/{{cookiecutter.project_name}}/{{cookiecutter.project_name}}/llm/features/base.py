"""Feature pack contract for llm/features."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from fastapi import APIRouter

from {{cookiecutter.project_name}}.agents.tools import AgentTool, ToolRegistry


@dataclass(frozen=True, slots=True)
class FeaturePackMeta:
    """Static metadata for one feature pack."""

    id: str
    name: str
    requires: tuple[str, ...] = ()
    upstream_templates: int = 0


class FeaturePack(Protocol):
    """One NK-native feature pack (tools + optional HTTP router)."""

    meta: FeaturePackMeta

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        """Register agent tools provided by this pack."""

    def router(self) -> APIRouter | None:
        """Return an HTTP router or None when API-only via agents."""


def pack_router(pack: FeaturePack) -> APIRouter | None:
    """Safe router accessor."""
    return pack.router()


def merge_tools(registry: ToolRegistry, tools: list[AgentTool]) -> None:
    for tool in tools:
        if registry.get(tool.name) is None:
            registry.register(tool)
