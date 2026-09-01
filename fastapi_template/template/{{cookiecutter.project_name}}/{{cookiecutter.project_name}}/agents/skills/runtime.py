"""Skill runtime — manifest-aware discovery, validation, and context apply (P22)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.agents.skills import SkillLoader, SkillNotFound
from {{cookiecutter.project_name}}.agents.skills.manifest import SkillManifest
from {{cookiecutter.project_name}}.agents.skills.manifest_loader import load_manifest_from_skill
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry

_PRESETS_PATH = Path(__file__).with_name("presets.yaml")


@lru_cache(maxsize=1)
def load_skill_presets() -> dict[str, list[str]]:
    if not _PRESETS_PATH.is_file():
        return {}
    payload = yaml.safe_load(_PRESETS_PATH.read_text(encoding="utf-8")) or {}
    presets = payload.get("presets") or {}
    resolved: dict[str, list[str]] = {}
    for name, item in presets.items():
        if isinstance(item, dict):
            skills = item.get("skills") or []
            resolved[name] = [str(skill) for skill in skills]
    return resolved


class SkillRuntime:
    """Compose SkillLoader with manifests, tool validation, and presets."""

    __slots__ = ("_loader", "_registry", "_manifest_cache")

    def __init__(
        self,
        loader: SkillLoader,
        *,
        registry: ToolRegistry | None = None,
    ) -> None:
        self._loader = loader
        self._registry = registry
        self._manifest_cache: dict[str, SkillManifest] = {}

    @property
    def loader(self) -> SkillLoader:
        return self._loader

    def manifest(self, name: str) -> SkillManifest:
        if name in self._manifest_cache:
            return self._manifest_cache[name]
        skill = self._loader.get(name)
        loaded = load_manifest_from_skill(skill)
        self._manifest_cache[name] = loaded
        return loaded

    def manifests(self) -> dict[str, SkillManifest]:
        return {skill.name: self.manifest(skill.name) for skill in self._loader.discover()}

    def missing_tools(self, name: str) -> tuple[str, ...]:
        manifest = self.manifest(name)
        if self._registry is None or not manifest.tools:
            return ()
        available = set(self._registry.names())
        return tuple(tool for tool in manifest.tools if tool not in available)

    def validate(self, name: str) -> list[str]:
        """Return human-readable validation issues for a skill."""
        issues: list[str] = []
        missing = self.missing_tools(name)
        if missing:
            issues.append(f"missing tools: {', '.join(missing)}")
        manifest = self.manifest(name)
        if manifest.permissions.network and manifest.permissions.filesystem == "write":
            issues.append("high-privilege skill: network + filesystem write")
        return issues

    def apply(self, name: str, *, base_prompt: str = "") -> str:
        """Load trusted skill instructions and merge with a base system prompt."""
        instructions = self._loader.load(name)
        if not base_prompt.strip():
            return instructions
        return f"{base_prompt.strip()}\n\n{instructions}"

    def resolve_preset(self, preset: str) -> list[str]:
        available = set(self._loader.available())
        return [
            name
            for name in load_skill_presets().get(preset, [])
            if name in available
        ]

    def preset_skills(self, preset: str) -> tuple[SkillManifest, ...]:
        names = self.resolve_preset(preset)
        return tuple(self.manifest(name) for name in names)


def format_manifest_report(runtime: SkillRuntime) -> str:
    lines = ["Skill manifests", "==============="]
    for skill in runtime.loader.discover():
        manifest = runtime.manifest(skill.name)
        tools = ", ".join(manifest.tools) or "-"
        eval_name = manifest.evaluation.harness or "-"
        issues = runtime.validate(skill.name)
        status = "ok" if not issues else "warn"
        lines.append(
            f"{manifest.name:32} tools=[{tools}] eval={eval_name:20} [{status}]",
        )
        for issue in issues:
            lines.append(f"    ! {issue}")
    return "\n".join(lines)


__all__ = [
    "SkillRuntime",
    "format_manifest_report",
    "load_skill_presets",
]
