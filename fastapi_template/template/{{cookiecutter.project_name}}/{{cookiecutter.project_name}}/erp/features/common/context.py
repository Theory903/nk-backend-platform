"""Runtime context for ERP feature packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from {{cookiecutter.project_name}}.erp.runtime import ErpRuntime


@dataclass(slots=True)
class ErpFeatureContext:
    """Services injected when ERP packs register tools/routes."""

    db_session: AsyncSession | None = None
    organization_id: str = "default"
    runtime: ErpRuntime | None = None

    def org_id(self) -> str:
        return self.organization_id or "default"
