"""Capability manifest loader for the model gateway (P2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from {{cookiecutter.project_name}}.settings import settings

_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_MANIFEST = _PACKAGE_DIR / "capabilities.yaml"

_TASK_ALIASES: dict[str, str] = {
    "default": "chat",
    "reasoning": "reasoning",
    "fast": "fast",
}


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    provider: str
    model: str
    fallback: tuple[tuple[str, str], ...] = ()


def _capabilities_file() -> Path:
    override = getattr(settings, "llm_capabilities_file", None)
    if override:
        path = Path(override)
        if path.is_file():
            return path
    for candidate in (
        Path.cwd() / "ai" / "gateway" / "capabilities.yaml",
        _DEFAULT_MANIFEST,
    ):
        if candidate.is_file():
            return candidate
    return _DEFAULT_MANIFEST


def _parse_fallback(raw: object) -> tuple[tuple[str, str], ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError("fallback must be a list")
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            provider = str(item.get("provider", "")).strip()
            model = str(item.get("model", "")).strip()
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            provider, model = str(item[0]).strip(), str(item[1]).strip()
        else:
            raise ValueError(f"invalid fallback entry: {item!r}")
        if provider and model:
            pairs.append((provider, model))
    return tuple(pairs)


def _route_from_mapping(data: dict[str, object]) -> CapabilitySpec:
    provider = str(data.get("provider", settings.llm_provider)).strip()
    model = str(data.get("model", settings.llm_model)).strip()
    return CapabilitySpec(
        provider=provider,
        model=model,
        fallback=_parse_fallback(data.get("fallback")),
    )


def load_capability_routes() -> tuple[dict[str, CapabilitySpec], dict[str, str]]:
    """Load capability specs and task→capability aliases from YAML."""
    path = _capabilities_file()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_caps = payload.get("capabilities") or {}
    if not isinstance(raw_caps, dict) or not raw_caps:
        raise ValueError(f"capabilities manifest empty: {path}")

    routes: dict[str, CapabilitySpec] = {}
    for name, spec in raw_caps.items():
        cap_name = str(name).strip()
        if not cap_name:
            continue
        if not isinstance(spec, dict):
            raise TypeError(f"capability {cap_name!r} must be a mapping")
        routes[cap_name] = _route_from_mapping(spec)

    aliases = dict(_TASK_ALIASES)
    raw_aliases = payload.get("task_aliases") or {}
    if isinstance(raw_aliases, dict):
        for task, capability in raw_aliases.items():
            task_name = str(task).strip()
            cap_name = str(capability).strip()
            if task_name and cap_name:
                aliases[task_name] = cap_name

    if "chat" not in routes:
        routes["chat"] = CapabilitySpec(
            provider=settings.llm_provider,
            model=settings.llm_model,
        )
    aliases.setdefault("default", "chat")
    return routes, aliases


def resolve_capability(name: str, aliases: dict[str, str]) -> str:
    """Map a task or capability name to a canonical capability."""
    key = (name or "default").strip() or "default"
    if key in aliases:
        return aliases[key]
    return key


__all__ = ["CapabilitySpec", "load_capability_routes", "resolve_capability"]
