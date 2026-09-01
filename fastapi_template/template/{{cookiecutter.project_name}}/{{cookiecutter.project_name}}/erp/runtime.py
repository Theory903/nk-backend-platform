"""Shared runtime services for ERP feature packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from {{cookiecutter.project_name}}.erp.services.pricing import PricingService
from {{cookiecutter.project_name}}.erp.services.valuation import FIFOValuation, LIFOValuation


@dataclass(slots=True)
class ErpRuntime:
    """Process-local ERP services wired during application startup."""

    pricing: PricingService
    fifo: type[FIFOValuation] = FIFOValuation
    lifo: type[LIFOValuation] = LIFOValuation


def get_or_create_runtime(app: Any) -> ErpRuntime:
    runtime = getattr(app.state, "erp_runtime", None)
    if isinstance(runtime, ErpRuntime):
        return runtime
    runtime = ErpRuntime(pricing=PricingService())
    app.state.erp_runtime = runtime
    return runtime


__all__ = ["ErpRuntime", "get_or_create_runtime"]
