"""Load skill manifests from skill.yaml or SKILL.md frontmatter (P22)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from {{cookiecutter.project_name}}.agents.skills import Skill, SkillInvalid
from {{cookiecutter.project_name}}.agents.skills.manifest import (
    SkillEvaluation,
    SkillManifest,
    SkillPermissions,
)

_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\n(?P<meta>.*?)\n---[ \t]*(?:\n|$)",
    re.DOTALL,
)


def _coerce_manifest_payload(payload: dict) -> dict:
    data = dict(payload)
    tools = data.get("tools") or []
    if isinstance(tools, list):
        data["tools"] = tuple(str(item) for item in tools)
    permissions = data.get("permissions") or {}
    if isinstance(permissions, dict):
        data["permissions"] = SkillPermissions.model_validate(permissions)
    evaluation = data.get("evaluation") or {}
    if isinstance(evaluation, dict):
        data["evaluation"] = SkillEvaluation.model_validate(evaluation)
    return data


def load_manifest_file(path: Path) -> SkillManifest:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SkillInvalid(f"skill manifest must be a mapping: {path}")
    return SkillManifest.model_validate(_coerce_manifest_payload(payload))


def load_manifest_from_skill(skill: Skill) -> SkillManifest:
    """Resolve manifest from skill.yaml, YAML frontmatter, or skill metadata."""
    yaml_path = skill.path / "skill.yaml"
    if yaml_path.is_file():
        manifest = load_manifest_file(yaml_path)
        if manifest.name != skill.name:
            raise SkillInvalid(
                f"skill.yaml name {manifest.name!r} != discovered name {skill.name!r}",
            )
        return manifest

    marker = skill.path / "SKILL.md"
    if marker.is_file():
        raw = marker.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(raw)
        if match:
            payload = yaml.safe_load(match.group("meta")) or {}
            if isinstance(payload, dict) and (
                "tools" in payload
                or "permissions" in payload
                or "evaluation" in payload
            ):
                payload.setdefault("name", skill.name)
                payload.setdefault("description", skill.description)
                return SkillManifest.model_validate(_coerce_manifest_payload(payload))

    return SkillManifest(
        name=skill.name,
        description=skill.description,
    )


__all__ = ["load_manifest_file", "load_manifest_from_skill"]
