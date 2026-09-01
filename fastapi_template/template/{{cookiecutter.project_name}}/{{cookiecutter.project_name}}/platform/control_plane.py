"""Control-plane registry kept separate from runtime execution state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    """Versioned model, prompt, tool, or policy registration."""

    name: str
    version: str
    kind: str
    active: bool = False
    registered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class ControlPlaneRegistry:
    """In-memory registry for local control-plane workflows."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], RegistryEntry] = {}
        self._lock = RLock()

    def register(self, entry: RegistryEntry) -> RegistryEntry:
        if not entry.name.strip() or not entry.version.strip():
            raise ValueError("registry name and version cannot be empty")
        with self._lock:
            key = (entry.kind, entry.name)
            self._entries[(entry.kind, entry.name, entry.version)] = entry
            if entry.active:
                self._deactivate_other_versions(key, entry.version)
        return entry

    def activate(self, kind: str, name: str, version: str) -> RegistryEntry:
        with self._lock:
            key = (kind, name, version)
            entry = self._entries.get(key)
            if entry is None:
                raise KeyError(f"unknown registry entry: {kind}/{name}/{version}")
            active = RegistryEntry(
                name=entry.name,
                version=entry.version,
                kind=entry.kind,
                active=True,
                registered_at=entry.registered_at,
            )
            self._entries[key] = active
            self._deactivate_other_versions((kind, name), version)
            return active

    def active(self, kind: str, name: str) -> RegistryEntry | None:
        with self._lock:
            return next(
                (
                    entry
                    for (entry_kind, entry_name, _), entry in self._entries.items()
                    if entry_kind == kind and entry_name == name and entry.active
                ),
                None,
            )

    def _deactivate_other_versions(
        self,
        identity: tuple[str, str],
        active_version: str,
    ) -> None:
        for key, entry in list(self._entries.items()):
            if key[:2] == identity and key[2] != active_version and entry.active:
                self._entries[key] = RegistryEntry(
                    name=entry.name,
                    version=entry.version,
                    kind=entry.kind,
                    active=False,
                    registered_at=entry.registered_at,
                )


__all__ = ["ControlPlaneRegistry", "RegistryEntry"]
