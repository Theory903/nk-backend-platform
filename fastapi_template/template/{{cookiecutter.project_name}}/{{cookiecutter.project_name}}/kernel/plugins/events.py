"""Append-only plugin lifecycle events (P21)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class PluginEvent:
    plugin: str
    action: str
    detail: str = ""
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PluginEventBus:
    """In-process event log for plugin lifecycle transitions."""

    __slots__ = ("_events",)

    def __init__(self) -> None:
        self._events: list[PluginEvent] = []

    def emit(self, plugin: str, action: str, *, detail: str = "") -> None:
        self._events.append(
            PluginEvent(plugin=plugin, action=action, detail=detail),
        )

    def events(self) -> tuple[PluginEvent, ...]:
        return tuple(self._events)


__all__ = ["PluginEvent", "PluginEventBus"]
