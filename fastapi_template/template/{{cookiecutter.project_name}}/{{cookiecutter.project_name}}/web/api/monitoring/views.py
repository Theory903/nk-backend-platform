from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request, Response
from {{cookiecutter.project_name}}.settings import settings
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from fastapi import Depends
from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.core.security import constant_time_compare
from {{cookiecutter.project_name}}.identity.deps import CurrentUser
from {{cookiecutter.project_name}}.identity.permissions import has_permission
{%- endif %}
from fastapi.responses import JSONResponse
{%- if cookiecutter.prometheus_enabled in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.operations.metrics import (
    export_metrics,
    metrics_content_type,
)
{%- endif %}

router = APIRouter()

ReadinessCheck = Callable[[], Awaitable[None]]
_readiness_checks: dict[str, ReadinessCheck] = {}

{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
def require_metrics_access(request: Request) -> None:
    """Allow a dedicated scrape token or a scoped authenticated principal."""
    authorization = request.headers.get("authorization", "")
    scheme, _, credential = authorization.partition(" ")
    metrics_token = getattr(settings, "metrics_auth_token", None)
    if (
        metrics_token
        and scheme.lower() == "bearer"
        and constant_time_compare(credential.strip(), metrics_token)
    ):
        return

    principal = CurrentUser(
        request=request,
        authorization=authorization or None,
        session_cookie=request.cookies.get("session"),
        x_session_id=request.headers.get("X-Session-Id"),
        auth_cookie=request.cookies.get("auth_session"),
    )
    if not has_permission(principal, "ops.metrics"):
        raise Problem(
            title="Insufficient Permissions",
            status_code=403,
            detail="requires 'ops.metrics'",
        )
{%- endif %}


def register_readiness_check(
    name: str,
    check: ReadinessCheck,
    *,
    app: object | None = None,
) -> None:
    """Register a timeout-bounded readiness probe."""
    if app is not None:
        state = getattr(app, "state", None)
        if state is not None:
            checks = getattr(state, "readiness_checks", None)
            if checks is None:
                checks = {}
                state.readiness_checks = checks
            checks[name] = check
            return
    _readiness_checks[name] = check


@router.get("/health")
def health_check() -> dict[str, str]:
    """
    Liveness probe — dependency-free.

    Returns 200 when the process is up.
    """
    return {"status": "alive"}


@router.get("/build-info")
def build_info() -> dict[str, str]:
    """Return immutable build metadata for rollout and incident correlation."""
    return {
        "service": "{{cookiecutter.project_name}}",
        "version": str(getattr(settings, "service_version", "0.1.0")),
        "git_sha": os.getenv("GIT_SHA", "unknown"),
        "build_date": os.getenv("BUILD_DATE", "unknown"),
        "profile": "{{cookiecutter.profile}}",
    }


@router.get("/ready")
async def readiness_check(request: Request) -> Response:
    """
    Readiness probe — runs registered dependency checks.

    Returns 200 when all checks pass; 503 with failing check names otherwise.
    """
    shutdown_state = getattr(request.app.state, "shutdown_state", None)
    if shutdown_state is not None and not shutdown_state.is_ready:
        return JSONResponse(
            status_code=503,
            content={"detail": ["shutting_down"]},
        )

    if not getattr(request.app.state, "startup_complete", True):
        return JSONResponse(
            status_code=503,
            content={"detail": ["starting"]},
        )

    checks = dict(_readiness_checks)
    checks.update(getattr(request.app.state, "readiness_checks", {}))
    timeout_s = float(
        getattr(request.app.state, "readiness_timeout_s", 2.0)
    )

    async def run_check(
        name: str,
        check: ReadinessCheck,
    ) -> str | None:
        try:
            await asyncio.wait_for(check(), timeout=timeout_s)
            return None
        except Exception:
            return name

    failures = [
        name
        for name in await asyncio.gather(
            *(run_check(name, check) for name, check in list(checks.items()))
        )
        if name is not None
    ]

    if failures:
        return JSONResponse(
            status_code=503,
            content={"detail": failures},
        )
    return JSONResponse(content={"status": "ready"})


{%- if cookiecutter.prometheus_enabled in [True, "True", "true", 1, "1"] %}
@router.get(
    "/metrics"
    {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %},
    dependencies=[Depends(require_metrics_access)]
    {%- endif %}
)
def prometheus_metrics() -> Response:
    """Export platform metrics in Prometheus exposition format."""
    return Response(
        content=export_metrics(),
        media_type=metrics_content_type(),
    )
{%- endif %}
