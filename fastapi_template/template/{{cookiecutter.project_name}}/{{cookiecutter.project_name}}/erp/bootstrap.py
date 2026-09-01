"""Application bootstrap for ERP domain packs."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.registry import register_erp_tools
from {{cookiecutter.project_name}}.erp.runtime import get_or_create_runtime


def build_erp_context(app: FastAPI) -> ErpFeatureContext:
    runtime = get_or_create_runtime(app)
    org_id = "default"
    return ErpFeatureContext(runtime=runtime, organization_id=org_id)


def register_erp_agent_tools(
    registry: ToolRegistry,
    *,
    manifest: dict[str, Any] | None = None,
    ctx: ErpFeatureContext | None = None,
) -> list[str]:
    return register_erp_tools(registry, manifest=manifest, ctx=ctx)


def wire_erp_bootstrap(app: FastAPI) -> None:
    """Attach ERP runtime to application state."""
    app.state.erp_runtime = get_or_create_runtime(app)
    app.state.erp_context = build_erp_context(app)
