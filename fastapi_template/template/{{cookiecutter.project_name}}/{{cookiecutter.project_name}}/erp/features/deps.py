"""FastAPI dependencies for ERP feature packs."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.dependencies import get_db_session
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.runtime import get_or_create_runtime
from {{cookiecutter.project_name}}.platform.contracts import Scope


async def get_erp_context(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ErpFeatureContext:
    scope: Scope | None = getattr(request.state, "scope", None)
    org_id = scope.organization_id if scope else "default"
    return ErpFeatureContext(
        db_session=session,
        organization_id=org_id,
        runtime=get_or_create_runtime(request.app),
    )
