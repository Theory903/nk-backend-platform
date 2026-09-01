"""Aggregate HTTP routers for enabled ERP feature packs."""

from __future__ import annotations

from fastapi import APIRouter

from {{cookiecutter.project_name}}.erp.features.registry import enabled_packs


def build_erp_router(manifest: dict | None = None) -> APIRouter:
    """Mount one sub-router per enabled ERP pack under /erp."""
    root = APIRouter(prefix="/erp", tags=["erp-features"])
    for pack in enabled_packs(manifest):
        sub = pack.router()
        if sub is not None:
            root.include_router(sub)
    return root
