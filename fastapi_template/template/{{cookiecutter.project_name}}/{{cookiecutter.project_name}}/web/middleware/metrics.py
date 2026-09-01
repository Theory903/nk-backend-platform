"""Request metrics middleware without third-party route introspection."""

from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from {{cookiecutter.project_name}}.operations.metrics import record_http_request

_KNOWN_METHODS = frozenset(
    {"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
)


class PrometheusMetricsMiddleware:
    """Record HTTP metrics while tolerating wrapped Starlette routes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Record a request after the downstream response body completes."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500
        recorded = False

        async def send_with_metrics(message: Message) -> None:
            nonlocal recorded, status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            elif message["type"] == "http.response.body" and not message.get(
                "more_body",
                False,
            ):
                record_http_request(
                    method=self._safe_method(scope.get("method", "UNKNOWN")),
                    path=self._route_path(scope),
                    status=status,
                    duration_s=time.perf_counter() - started,
                )
                recorded = True
            await send(message)

        try:
            await self.app(scope, receive, send_with_metrics)
        except Exception:
            if not recorded:
                record_http_request(
                    method=self._safe_method(scope.get("method", "UNKNOWN")),
                    path=self._route_path(scope),
                    status=status,
                    duration_s=time.perf_counter() - started,
                )
            raise

    @staticmethod
    def _route_path(scope: Scope) -> str:
        route = scope.get("route")
        return getattr(route, "path", None) or "unmatched"

    @staticmethod
    def _safe_method(method: str) -> str:
        """Keep client-controlled methods bounded as metric labels."""
        normalized = method.upper()
        return normalized if normalized in _KNOWN_METHODS else "OTHER"


__all__ = ["PrometheusMetricsMiddleware"]
