from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
{%- if cookiecutter.prometheus_enabled == "True" %}

from {{cookiecutter.project_name}}.operations.metrics import (
    export_metrics,
    metrics_content_type,
)
{%- endif %}

router = APIRouter()

ReadinessCheck = Callable[[], Awaitable[None]]
_readiness_checks: dict[str, ReadinessCheck] = {}


def register_readiness_check(name: str, check: ReadinessCheck) -> None:
    """Register an async readiness probe by name (overwrites on collision)."""
    _readiness_checks[name] = check


@router.get("/health")
def health_check() -> dict[str, str]:
    """
    Liveness probe — dependency-free.

    Returns 200 when the process is up.
    """
    return {"status": "alive"}


@router.get("/ready")
async def readiness_check() -> Response:
    """
    Readiness probe — runs registered dependency checks.

    Returns 200 when all checks pass; 503 with failing check names otherwise.
    """
    failures: list[str] = []
    for name, check in list(_readiness_checks.items()):
        try:
            await check()
        except Exception:
            failures.append(name)

    if failures:
        return JSONResponse(
            status_code=503,
            content={"detail": failures},
        )
    return JSONResponse(content={"status": "ready"})


{%- if cookiecutter.prometheus_enabled == "True" %}


@router.get("/metrics")
def prometheus_metrics() -> Response:
    """
    Export platform metrics in Prometheus exposition format.

    Safe when prometheus_client is not installed (returns a short comment body).
    """
    return Response(
        content=export_metrics(),
        media_type=metrics_content_type(),
    )
{%- endif %}
