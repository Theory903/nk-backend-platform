"""Machine-readable skill manifest schema (P22)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SkillPermissions(BaseModel):
    """Declared capability limits for a skill."""

    model_config = ConfigDict(extra="allow")

    network: bool = False
    filesystem: str = "none"


class SkillEvaluation(BaseModel):
    """Harness/eval binding for a skill."""

    model_config = ConfigDict(extra="allow")

    harness: str | None = None
    scenario: str | None = None


class SkillManifest(BaseModel):
    """NK skill manifest — tools, permissions, evaluation."""

    name: str = Field(min_length=1)
    description: str = ""
    tools: tuple[str, ...] = ()
    permissions: SkillPermissions = Field(default_factory=SkillPermissions)
    evaluation: SkillEvaluation = Field(default_factory=SkillEvaluation)
    preset: str | None = None


__all__ = [
    "SkillEvaluation",
    "SkillManifest",
    "SkillPermissions",
]
