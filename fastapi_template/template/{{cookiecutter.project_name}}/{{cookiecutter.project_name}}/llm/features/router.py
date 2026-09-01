"""Aggregate HTTP routers for enabled LLM feature packs."""

from __future__ import annotations

from fastapi import APIRouter

from {{cookiecutter.project_name}}.llm.features.registry import enabled_packs


def build_features_router(manifest: dict | None = None) -> APIRouter:
    """Mount one sub-router per enabled feature pack under /llm."""
    root = APIRouter(prefix="/llm", tags=["llm-features"])
    for pack in enabled_packs(manifest):
        sub = pack.router()
        if sub is not None:
            root.include_router(sub)
    return root
