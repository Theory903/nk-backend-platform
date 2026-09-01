"""Build the plugin kernel from catalog + platform manifest (P21)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.kernel.plugins.contracts import PluginManifest, PluginType
from {{cookiecutter.project_name}}.kernel.plugins.events import PluginEventBus
from {{cookiecutter.project_name}}.kernel.plugins.lifecycle import PluginKernel
from {{cookiecutter.project_name}}.kernel.plugins.registry import PluginRegistry

_CATALOG_PATH = Path(__file__).with_name("catalog.yaml")


def _ai_enabled(manifest: dict[str, Any]) -> bool:
    ai = manifest.get("ai") or {}
    return bool(ai.get("enabled"))


def _agents_enabled(manifest: dict[str, Any]) -> bool:
    agents = manifest.get("agents") or {}
    return bool(agents.get("enabled"))


def _plugin_enabled(name: str, manifest: dict[str, Any]) -> bool:
    plugins = manifest.get("plugins") or {}
    if name in plugins:
        return bool(plugins[name])
    if name == "model_gateway":
        return _ai_enabled(manifest)
    if name in {"tool_gateway", "agent_runtime", "session_runtime", "harness", "eval_adapters", "security", "skills"}:
        return _agents_enabled(manifest)
    if name == "observability":
        return _ai_enabled(manifest)
    if name == "memory_store":
        return _agents_enabled(manifest)
    if name == "vector_store":
        knowledge = manifest.get("knowledge") or {}
        modules = manifest.get("modules") or {}
        return bool(knowledge.get("enabled") or modules.get("vector"))
    if name == "rag_context":
        knowledge = manifest.get("knowledge") or {}
        return bool(knowledge.get("enabled"))
    return False


@lru_cache(maxsize=1)
def load_plugin_catalog() -> dict[str, PluginManifest]:
    if not _CATALOG_PATH.is_file():
        return {}
    payload = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    raw_plugins = payload.get("plugins") or {}
    catalog: dict[str, PluginManifest] = {}
    for plugin_id, item in raw_plugins.items():
        if not isinstance(item, dict):
            continue
        data = dict(item)
        data.setdefault("name", plugin_id)
        data["type"] = PluginType(str(data.get("type", "protocol")))
        data["provides"] = tuple(data.get("provides") or ())
        data["requires"] = tuple(data.get("requires") or ())
        catalog[plugin_id] = PluginManifest.model_validate(data)
    return catalog


def register_catalog_plugins(
    registry: PluginRegistry,
    manifest: dict[str, Any] | None = None,
) -> None:
    """Register built-in plugins filtered by platform.yaml."""
    platform = manifest or {}
    for plugin_id, plugin_manifest in load_plugin_catalog().items():
        enabled = _plugin_enabled(plugin_id, platform)
        registry.register(plugin_manifest, enabled=enabled)


def build_plugin_kernel(
    manifest: dict[str, Any] | None = None,
    *,
    autostart: bool = False,
) -> PluginKernel:
    """Compose registry + lifecycle from catalog and platform manifest."""
    registry = PluginRegistry()
    register_catalog_plugins(registry, manifest)
    kernel = PluginKernel(registry, events=PluginEventBus())
    if autostart:
        kernel.start_all()
    return kernel


__all__ = [
    "build_plugin_kernel",
    "load_plugin_catalog",
    "register_catalog_plugins",
]
