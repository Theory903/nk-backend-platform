"""Authentication middleware for generated services.

The middleware protects application routes by default when identity is
enabled. Health, documentation, static assets, and authentication bootstrap
routes remain public so probes and first-login flows can function.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from {{cookiecutter.project_name}}.core.errors import Problem, problem_response
from {{cookiecutter.project_name}}.identity.deps import (
    CurrentUser,
    get_csrf_protection,
)
from {{cookiecutter.project_name}}.platform.tenancy import (
    get_tenant_authorization,
)
from {{cookiecutter.project_name}}.settings import settings


class AuthMiddleware(BaseHTTPMiddleware):
    """Resolve and require an authenticated principal for protected paths."""

    def __init__(
        self,
        app,
        *,
        public_prefixes: Iterable[str] = (
            "/api/health",
            "/api/ready",
            "/api/build-info",
            "/api/metrics",
            "/api/openapi.json",
            "/api/docs",
            "/api/swagger",
            "/api/redoc",
            "/static",
            "/api/auth",
            "/auth",
        ),
        allowed_origins: Iterable[str] = (),
    ) -> None:
        super().__init__(app)
        self.public_prefixes = tuple(public_prefixes)
        self.allowed_origins = frozenset(
            origin.rstrip("/")
            for origin in allowed_origins
            if origin.strip()
        )

    def _is_public(self, path: str) -> bool:
        return any(path == prefix or path.startswith(prefix + "/") for prefix in self.public_prefixes)

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._is_auth_bootstrap(request.url.path):
            if not self._origin_allowed(request):
                return problem_response(
                    status_code=403,
                    title="Origin Validation Failed",
                    detail="request origin is not allowed",
                    instance=str(request.url),
                )
            try:
                self._require_cookie_csrf(request)
            except Problem as exc:
                return problem_response(
                    status_code=exc.status_code,
                    title=exc.title,
                    detail=exc.detail,
                    headers=exc.headers,
                    extensions=exc.extensions,
                    instance=exc.instance or str(request.url),
                )
            response = await call_next(request)
            self._set_cookie_csrf(response, request)
            return response

        if self._is_public(request.url.path):
            return await call_next(request)

        try:
            principal = await asyncio.to_thread(
                CurrentUser,
                request=request,
                authorization=request.headers.get("Authorization"),
                session_cookie=request.cookies.get("session"),
                x_session_id=request.headers.get("X-Session-Id"),
                auth_cookie=request.cookies.get("auth_session"),
            )
            requested_org_id = request.headers.get("X-Org-Id")
            if requested_org_id:
                request.state.tenant_context = (
                    await get_tenant_authorization().resolve_context(
                        principal,
                        org_id=requested_org_id.strip(),
                    )
                )
        except Problem as exc:
            return problem_response(
                status_code=exc.status_code,
                title=exc.title,
                detail=exc.detail,
                headers=exc.headers,
                extensions=exc.extensions,
                instance=exc.instance or str(request.url),
            )

        return await call_next(request)

    @staticmethod
    def _is_auth_bootstrap(path: str) -> bool:
        return path.startswith("/api/auth/") or path == "/api/auth"

    def _origin_allowed(self, request: Request) -> bool:
        """Validate browser origins for public cookie-auth mutations."""
        if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
            return True

        origin = request.headers.get("origin")
        if not origin:
            return True

        normalized = origin.rstrip("/")
        if normalized in self.allowed_origins:
            return True

        request_origin = f"{request.url.scheme}://{request.url.netloc}"
        return normalized == request_origin.rstrip("/")

    def _require_cookie_csrf(self, request: Request) -> None:
        if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        auth_cookie = request.cookies.get("auth_session")
        if not auth_cookie:
            return
        supplied = request.headers.get("X-CSRF-Token", "")
        if not get_csrf_protection().validate_token(
            auth_cookie,
            supplied,
        ):
            raise Problem(
                title="CSRF Validation Failed",
                status_code=403,
                detail="missing or invalid CSRF token",
            )

    def _set_cookie_csrf(self, response: Response, request: Request) -> None:
        auth_cookie = request.cookies.get("auth_session")
        if not auth_cookie or request.cookies.get("csrf_token"):
            return
        token = get_csrf_protection().generate_token(auth_cookie)
        response.set_cookie(
            "csrf_token",
            token,
            secure=settings.secure_cookies,
            httponly=False,
            samesite="lax",
            max_age=settings.session_cookie_max_age_seconds,
        )


__all__ = ["AuthMiddleware"]
