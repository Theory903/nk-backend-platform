"""Stable NK plugin contract (DeepSeek Harness reference, no hard dependency)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PluginType(StrEnum):
    MODEL = "model"
    AGENT = "agent"
    TOOL = "tool"
    SKILL = "skill"
    MEMORY = "memory"
    RETRIEVER = "retriever"
    VECTOR_STORE = "vector_store"
    SANDBOX = "sandbox"
    EVALUATOR = "evaluator"
    WORKFLOW = "workflow"
    SCHEDULER = "scheduler"
    PROTOCOL = "protocol"
    STORAGE = "storage"
    SECURITY = "security"


class PluginState(StrEnum):
    DISCOVERED = "discovered"
    LOADED = "loaded"
    STARTED = "started"
    STOPPED = "stopped"
    FAILED = "failed"
    DISABLED = "disabled"


class PluginPermissions(BaseModel):
    """Capability-limited permissions declared by a plugin."""

    model_config = ConfigDict(extra="allow")

    network: bool = False
    filesystem: str = "none"
    subprocess: bool = False


class PluginHealth(BaseModel):
    """Health probe result for one plugin."""

    status: str = "healthy"
    detail: str = ""


class PluginManifest(BaseModel):
    """Machine-readable plugin declaration."""

    name: str = Field(min_length=1)
    type: PluginType
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    permissions: PluginPermissions = Field(default_factory=PluginPermissions)
    configuration: dict[str, Any] = Field(default_factory=dict)
    module: str = ""
    description: str = ""


class PluginRecord(BaseModel):
    """Runtime registration for one plugin."""

    model_config = ConfigDict(validate_assignment=True)

    manifest: PluginManifest
    state: PluginState = PluginState.DISCOVERED
    health: PluginHealth = Field(default_factory=PluginHealth)
    enabled: bool = True


__all__ = [
    "PluginHealth",
    "PluginManifest",
    "PluginPermissions",
    "PluginRecord",
    "PluginState",
    "PluginType",
]
