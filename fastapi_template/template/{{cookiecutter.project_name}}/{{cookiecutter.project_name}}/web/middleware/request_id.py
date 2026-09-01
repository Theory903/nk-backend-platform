"""
Request ID + logging context middleware.

Headers (``X-Request-Id``, ``X-Org-Id``, …) are **inputs** only.
Trusted identity for logging comes from ``request.state`` after auth /
tenant resolution:

    request.state.request_id
    request.state.trace_id
    request.state.principal
    request.state.tenant

Recommended middleware order (outer → inner):

    RequestId → SecurityHeaders → Auth / Tenant → Idempotency → app

``RequestIdMiddleware`` runs early so IDs exist for the whole request.
``principal`` / ``tenant`` are often still unset at entry; org/user in
logs may stay empty until auth middleware writes trusted state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from {{cookiecutter.project_name}}.core.logging import trace_context
from {{cookiecutter.project_name}}.core.logging import get_logger
from {{cookiecutter.project_name}}.core.security import get_request_id

logger = get_logger(__name__)


def _resolve_trusted_identity(request: Request) -> tuple[str | None, str | None]:
    """
    Resolve user_id / org_id from trusted request.state only.

    Never read ``X-Org-Id`` (or similar) headers here — those are
    untrusted client inputs until auth/tenant middleware validates them.
    """
    principal = getattr(request.state, "principal", None)
    user_id = getattr(principal, "user_id", None) if principal is not None else None
    org_id = getattr(principal, "org_id", None) if principal is not None else None

    tenant = getattr(request.state, "tenant", None)
    if tenant is not None:
        tenant_org = getattr(tenant, "org_id", None)
        if tenant_org is not None:
            org_id = tenant_org

    return user_id, org_id


def _otel_trace_id() -> str:
    """Return a real OpenTelemetry trace_id hex, or empty if unavailable."""
    try:
        from opentelemetry import trace as otel_trace

        span = otel_trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return ""


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Ensure every request carries ``x-request-id`` and propagates
    logging context from trusted state (not spoofable headers).

    Trace ID is taken from a valid OTel span only. Request ID is never
    reused as a fake trace ID.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = get_request_id(request)
        tid = _otel_trace_id()
        started = perf_counter()

        user_id, org_id = _resolve_trusted_identity(request)

        with trace_context(
            trace_id=tid or None,
            request_id=rid,
            org_id=org_id,
            user_id=user_id,
        ):
            request.state.request_id = rid
            request.state.trace_id = tid
            shutdown_state = getattr(request.app.state, "shutdown_state", None)
            task = asyncio.current_task()
            if shutdown_state is not None and task is not None:
                shutdown_state.track_task(task)
            try:
                response: Response = await call_next(request)
            finally:
                if shutdown_state is not None and task is not None:
                    shutdown_state.untrack_task(task)
            response.headers["x-request-id"] = rid
            if tid:
                response.headers["x-trace-id"] = tid
            route = request.scope.get("route")
            route_path = getattr(route, "path", None) or "unmatched"
            principal = getattr(request.state, "principal", None)
            tenant = getattr(request.state, "tenant", None)
            logger.info(
                "http.request.completed",
                extra={
                    "event": "http.request.completed",
                    "method": request.method,
                    "route": route_path,
                    "status_code": response.status_code,
                    "duration_ms": round(
                        (perf_counter() - started) * 1000,
                        3,
                    ),
                    "user_id": getattr(principal, "user_id", None),
                    "org_id": getattr(
                        tenant,
                        "org_id",
                        getattr(principal, "org_id", None),
                    ),
                },
            )
            return response


__all__ = ["RequestIdMiddleware"]
