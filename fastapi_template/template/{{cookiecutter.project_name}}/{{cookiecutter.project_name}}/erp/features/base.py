"""Feature pack contract for erp/features."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import APIRouter

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry


@dataclass(frozen=True, slots=True)
class ErpFeaturePackMeta:
    """Static metadata for one ERP feature pack."""

    id: str
    name: str
    requires: tuple[str, ...] = ()
    upstream_doctypes: int = 0


class ErpFeaturePack(Protocol):
    """One NK-native ERP pack (HTTP router + optional agent tools)."""

    meta: ErpFeaturePackMeta

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: Any | None = None,
    ) -> None:
        """Register agent tools provided by this pack."""

    def router(self) -> APIRouter | None:
        """Return an HTTP router or None when API-only via agents."""


def pack_router(pack: ErpFeaturePack) -> APIRouter | None:
    """Safe router accessor."""
    return pack.router()
