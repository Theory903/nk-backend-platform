"""Application bootstrap for agent tools and skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

from {{cookiecutter.project_name}}.agents.skills.factory import build_skill_loader, build_skill_runtime
from {{cookiecutter.project_name}}.agents.session_runtime import SessionRuntime
from {{cookiecutter.project_name}}.agents.session_store import SessionEventStore
from {{cookiecutter.project_name}}.agents.security_loader import (
    build_sandbox_policy,
    build_security_pipeline,
)
from {{cookiecutter.project_name}}.agents.tool_gateway import ToolGateway
from {{cookiecutter.project_name}}.agents.tool_policy import load_tool_policy_manifest
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.kernel.plugins.bootstrap import build_plugin_kernel
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext
from {{cookiecutter.project_name}}.llm.features.registry import register_feature_tools
from {{cookiecutter.project_name}}.llm.features.runtime import get_or_create_runtime
from {{cookiecutter.project_name}}.research.experiments.runtime import build_experiment_runtime
from {{cookiecutter.project_name}}.research.self_improving.pipeline import build_self_improving_pipeline
{%- if cookiecutter.db_info.name != "none" and cookiecutter.orm == "sqlalchemy" %}
from {{cookiecutter.project_name}}.erp.bootstrap import build_erp_context, register_erp_agent_tools
{%- endif %}


def _load_manifest(app: FastAPI) -> dict[str, Any]:
    cached = getattr(app.state, "platform_manifest", None)
    if isinstance(cached, dict):
        return cached
    for candidate in (Path.cwd() / "platform.yaml",):
        if candidate.is_file():
            loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            app.state.platform_manifest = loaded
            return loaded
    return {}


def build_feature_context(app: FastAPI) -> FeatureContext:
    """Resolve shared services for feature packs from application state."""
    runtime = get_or_create_runtime(app)
    hybrid = getattr(app.state, "hybrid_retriever", None)
    if hybrid is None:
        hybrid = runtime.hybrid_retriever
    return FeatureContext(
        rag_service=getattr(app.state, "rag_service", None),
        memory_store=runtime.memory_store,
        hybrid_retriever=hybrid,
    )


def build_tool_registry(
    app: FastAPI,
    ctx: FeatureContext | None = None,
) -> ToolRegistry:
    """Register default + feature-pack tools on a fresh registry."""
    registry = ToolRegistry()
    manifest = _load_manifest(app)
    context = ctx or build_feature_context(app)
    register_feature_tools(registry, manifest=manifest, ctx=context)
{%- if cookiecutter.db_info.name != "none" and cookiecutter.orm == "sqlalchemy" %}
    erp_ctx = build_erp_context(app)
    register_erp_agent_tools(registry, manifest=manifest, ctx=erp_ctx)
{%- endif %}
    return registry


def build_tool_gateway(
    app: FastAPI,
    registry: ToolRegistry | None = None,
) -> ToolGateway:
    """Compose the tool gateway over the registry with manifest policy."""
    manifest = load_tool_policy_manifest()
    reg = registry or build_tool_registry(app)
    security = build_security_pipeline(tool_policy=manifest.policy)
    return ToolGateway(
        registry=reg,
        security=security,
        audit_enabled=True,
    )


def build_session_runtime(app: FastAPI) -> SessionRuntime | None:
    """Compose session runtime when a durable state store is configured."""
    state_store = getattr(app.state, "state_store", None)
    if state_store is None:
        return None
    return SessionRuntime(SessionEventStore(state_store))


def wire_agent_bootstrap(app: FastAPI) -> None:
    """Attach tool registry, gateway, session runtime, skill loader, and plugin kernel."""
    manifest = _load_manifest(app)
    plugin_kernel = build_plugin_kernel(manifest, autostart=True)
    ctx = build_feature_context(app)
    registry = build_tool_registry(app, ctx)
    gateway = build_tool_gateway(app, registry)
    session_runtime = build_session_runtime(app)
    skill_runtime = build_skill_runtime(registry=registry, trusted_all=True)
    app.state.feature_context = ctx
    app.state.tool_registry = registry
    app.state.tool_gateway = gateway
    app.state.security_pipeline = gateway.security
    app.state.sandbox_policy = build_sandbox_policy()
    app.state.session_runtime = session_runtime
    app.state.skill_loader = skill_runtime.loader
    app.state.skill_runtime = skill_runtime
    app.state.plugin_kernel = plugin_kernel
    app.state.experiment_runtime = build_experiment_runtime()
    app.state.self_improving_pipeline = build_self_improving_pipeline(
        experiment_runtime=app.state.experiment_runtime,
    )
