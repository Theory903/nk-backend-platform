"""Load tool gateway policy and MCP server manifests (P4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.agents.security import ToolPolicy
from {{cookiecutter.project_name}}.settings import settings

_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_POLICY = _PACKAGE_DIR / "tool_policy.yaml"


@dataclass(frozen=True, slots=True)
class McpServerSpec:
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None
    prefix: str = ""
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ToolPolicyManifest:
    policy: ToolPolicy
    mcp_servers: tuple[McpServerSpec, ...]


def _policy_file() -> Path:
    override = getattr(settings, "tool_policy_file", None)
    if override:
        path = Path(override)
        if path.is_file():
            return path
    for candidate in (Path.cwd() / "agents" / "tool_policy.yaml", _DEFAULT_POLICY):
        if candidate.is_file():
            return candidate
    return _DEFAULT_POLICY


def _parse_mcp_server(raw: dict[str, Any]) -> McpServerSpec:
    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError("mcp server name is required")
    args = raw.get("args") or []
    if not isinstance(args, list):
        raise ValueError(f"mcp server {name!r} args must be a list")
    return McpServerSpec(
        name=name,
        transport=str(raw.get("transport", "stdio")).strip().lower(),
        command=(str(raw["command"]).strip() if raw.get("command") else None),
        args=tuple(str(item) for item in args),
        url=(str(raw["url"]).strip() if raw.get("url") else None),
        prefix=str(raw.get("prefix", "")).strip(),
        enabled=bool(raw.get("enabled", True)),
    )


def load_tool_policy_manifest() -> ToolPolicyManifest:
    """Load gateway policy and MCP server definitions."""
    path = _policy_file()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_policy = payload.get("policy") or {}
    if not isinstance(raw_policy, dict):
        raise TypeError("policy must be a mapping")

    allowed_raw = raw_policy.get("allowed_tools")
    allowed = None if allowed_raw is None else frozenset(str(x) for x in allowed_raw)
    denied = frozenset(str(x) for x in (raw_policy.get("denied_tools") or []))
    policy = ToolPolicy(
        allowed_tools=allowed,
        denied_tools=denied,
        high_risk_requires_approval=bool(
            raw_policy.get("high_risk_requires_approval", True),
        ),
    )

    servers: list[McpServerSpec] = []
    for item in payload.get("mcp_servers") or []:
        if isinstance(item, dict):
            servers.append(_parse_mcp_server(item))

    return ToolPolicyManifest(policy=policy, mcp_servers=tuple(servers))


__all__ = ["McpServerSpec", "ToolPolicyManifest", "load_tool_policy_manifest"]
