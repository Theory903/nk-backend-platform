"""Factory helpers for the NK skill loader and runtime."""

from __future__ import annotations

from pathlib import Path

from . import SkillLoader, SkillLoaderConfig
from .runtime import SkillRuntime
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry

_SKILLS_ROOT = Path(__file__).resolve().parent


def skill_roots() -> list[Path]:
    """Return the default on-disk skill directories."""
    return [_SKILLS_ROOT]


def build_skill_loader(
    *,
    extra_roots: list[Path] | None = None,
    trusted_names: set[str] | None = None,
    trusted_all: bool = False,
) -> SkillLoader:
    """Build a SkillLoader over bundled and optional extra skill roots."""
    roots = skill_roots() + list(extra_roots or [])
    return SkillLoader(
        roots,
        trusted_names=trusted_names,
        trusted_all=trusted_all,
        config=SkillLoaderConfig(recursive=False),
    )


def build_skill_runtime(
    *,
    registry: ToolRegistry | None = None,
    extra_roots: list[Path] | None = None,
    trusted_names: set[str] | None = None,
    trusted_all: bool = False,
) -> SkillRuntime:
    """Build manifest-aware skill runtime over the default loader."""
    loader = build_skill_loader(
        extra_roots=extra_roots,
        trusted_names=trusted_names,
        trusted_all=trusted_all,
    )
    return SkillRuntime(loader, registry=registry)
