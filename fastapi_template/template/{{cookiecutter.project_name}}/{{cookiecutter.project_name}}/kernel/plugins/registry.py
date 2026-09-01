"""Plugin registry with dependency-aware ordering (P21)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.kernel.plugins.capabilities import resolve_load_order
from {{cookiecutter.project_name}}.kernel.plugins.contracts import (
    PluginManifest,
    PluginRecord,
    PluginState,
)


class PluginRegistry:
    """In-memory plugin registry."""

    __slots__ = ("_records",)

    def __init__(self) -> None:
        self._records: dict[str, PluginRecord] = {}

    def register(self, manifest: PluginManifest, *, enabled: bool = True) -> None:
        if manifest.name in self._records:
            raise ValueError(f"plugin already registered: {manifest.name}")
        state = PluginState.DISCOVERED if enabled else PluginState.DISABLED
        self._records[manifest.name] = PluginRecord(
            manifest=manifest,
            state=state,
            enabled=enabled,
        )

    def get(self, name: str) -> PluginRecord | None:
        return self._records.get(name)

    def require(self, name: str) -> PluginRecord:
        record = self.get(name)
        if record is None:
            raise KeyError(f"plugin not found: {name}")
        return record

    def list_plugins(self, *, enabled_only: bool = False) -> tuple[PluginRecord, ...]:
        records = tuple(self._records.values())
        if enabled_only:
            records = tuple(record for record in records if record.enabled)
        return records

    def manifests(self) -> dict[str, PluginManifest]:
        return {name: record.manifest for name, record in self._records.items()}

    def load_order(self) -> list[str]:
        enabled = {name for name, record in self._records.items() if record.enabled}
        return resolve_load_order(self.manifests(), enabled=enabled)

    def mark_state(self, name: str, state: PluginState) -> None:
        record = self.require(name)
        record.state = state


__all__ = ["PluginRegistry"]
