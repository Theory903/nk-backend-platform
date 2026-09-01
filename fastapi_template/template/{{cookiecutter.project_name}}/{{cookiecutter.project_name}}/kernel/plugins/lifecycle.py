"""Plugin lifecycle manager (P21)."""

from __future__ import annotations

from typing import Any

from {{cookiecutter.project_name}}.kernel.plugins.contracts import (
    PluginHealth,
    PluginRecord,
    PluginState,
)
from {{cookiecutter.project_name}}.kernel.plugins.events import PluginEventBus
from {{cookiecutter.project_name}}.kernel.plugins.registry import PluginRegistry


class PluginKernel:
    """Discover, load, start, and health-check registered plugins."""

    __slots__ = ("_registry", "_events", "_started")

    def __init__(
        self,
        registry: PluginRegistry,
        *,
        events: PluginEventBus | None = None,
    ) -> None:
        self._registry = registry
        self._events = events or PluginEventBus()
        self._started = False

    @property
    def registry(self) -> PluginRegistry:
        return self._registry

    @property
    def events(self) -> PluginEventBus:
        return self._events

    def list_plugins(self, *, enabled_only: bool = False) -> tuple[PluginRecord, ...]:
        return self._registry.list_plugins(enabled_only=enabled_only)

    def load_all(self) -> list[str]:
        """Mark plugins loaded in dependency order."""
        loaded: list[str] = []
        for name in self._registry.load_order():
            record = self._registry.require(name)
            if not record.enabled:
                continue
            for requirement in record.manifest.requires:
                required = self._registry.require(requirement)
                if required.state not in {
                    PluginState.LOADED,
                    PluginState.STARTED,
                }:
                    raise RuntimeError(
                        f"plugin {name!r} requires {requirement!r} to be loaded first",
                    )
            self._registry.mark_state(name, PluginState.LOADED)
            self._events.emit(name, "loaded")
            loaded.append(name)
        return loaded

    def start_all(self) -> list[str]:
        """Start all loaded plugins (idempotent)."""
        if self._started:
            return list(self._registry.load_order())
        loaded = self.load_all()
        started: list[str] = []
        for name in loaded:
            record = self._registry.require(name)
            health = self._probe_plugin(record)
            record.health = health
            if health.status == "unhealthy":
                self._registry.mark_state(name, PluginState.FAILED)
                self._events.emit(name, "failed", detail=health.detail)
                continue
            self._registry.mark_state(name, PluginState.STARTED)
            self._events.emit(name, "started")
            started.append(name)
        self._started = True
        return started

    def health_all(self) -> dict[str, PluginHealth]:
        results: dict[str, PluginHealth] = {}
        for record in self._registry.list_plugins():
            if not record.enabled:
                results[record.manifest.name] = PluginHealth(
                    status="disabled",
                    detail="plugin disabled by platform manifest",
                )
                continue
            health = self._probe_plugin(record)
            record.health = health
            results[record.manifest.name] = health
        return results

    def capability_providers(self) -> dict[str, str]:
        from {{cookiecutter.project_name}}.kernel.plugins.capabilities import capability_index

        manifests = {
            record.manifest.name: record.manifest
            for record in self._registry.list_plugins(enabled_only=True)
        }
        return capability_index(manifests)

    @staticmethod
    def _probe_plugin(record: PluginRecord) -> PluginHealth:
        module_path = record.manifest.module.strip()
        if not module_path:
            return PluginHealth(status="healthy", detail="declarative plugin")
        try:
            import importlib

            importlib.import_module(module_path)
            return PluginHealth(status="healthy", detail=f"module import ok: {module_path}")
        except Exception as exc:
            return PluginHealth(
                status="unhealthy",
                detail=f"{type(exc).__name__}: {exc}",
            )


def format_plugin_report(kernel: PluginKernel) -> str:
    lines = ["Plugin kernel", "============="]
    for record in kernel.list_plugins():
        manifest = record.manifest
        status = record.state.value
        provides = ", ".join(manifest.provides) or "-"
        requires = ", ".join(manifest.requires) or "-"
        lines.append(
            f"{manifest.name:16} type={manifest.type.value:10} state={status:10} "
            f"provides=[{provides}] requires=[{requires}]",
        )
    return "\n".join(lines)


def format_health_report(health: dict[str, PluginHealth]) -> str:
    lines = ["Plugin health", "============="]
    for name, item in sorted(health.items()):
        lines.append(f"[{item.status.upper():9}] {name}: {item.detail or 'ok'}")
    healthy = sum(1 for item in health.values() if item.status == "healthy")
    lines.append(f"\n{healthy}/{len(health)} healthy")
    return "\n".join(lines)


__all__ = [
    "PluginKernel",
    "format_health_report",
    "format_plugin_report",
]
