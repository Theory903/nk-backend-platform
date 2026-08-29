"""
Production security headers middleware.

Adds browser-facing security headers while keeping the policy configurable.

Headers:
    - X-Content-Type-Options
    - X-Frame-Options
    - Referrer-Policy
    - Content-Security-Policy
    - Strict-Transport-Security (HTTPS only)
    - Permissions-Policy
    - Cross-Origin-Opener-Policy
    - Cross-Origin-Resource-Policy

Important:
    HSTS is emitted only when the request is known to be HTTPS.

    If TLS terminates at a reverse proxy/load balancer, ensure trusted
    proxy headers are normalized before this middleware runs.
"""

from __future__ import annotations

from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send


DEFAULT_CSP: Final[str] = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'"
)

# FastAPI docs UIs: Studio (/docs) is first-party; Swagger/ReDoc may use CDN + Google Fonts.
DOCS_CSP: Final[str] = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net; "
    "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
    "connect-src 'self'"
)

_DOCS_PATH_SUFFIXES: Final[tuple[str, ...]] = (
    "/docs",
    "/redoc",
    "/swagger",
    "/swagger-redirect",
    "/docs/oauth2-redirect",
)

DEFAULT_PERMISSIONS_POLICY: Final[str] = (
    "accelerometer=(), "
    "autoplay=(), "
    "camera=(), "
    "display-capture=(), "
    "document-domain=(), "
    "encrypted-media=(), "
    "fullscreen=(), "
    "geolocation=(), "
    "gyroscope=(), "
    "magnetometer=(), "
    "microphone=(), "
    "midi=(), "
    "payment=(), "
    "picture-in-picture=(), "
    "publickey-credentials-get=(), "
    "screen-wake-lock=(), "
    "usb=(), "
    "xr-spatial-tracking=()"
)

DEFAULT_REFERRER_POLICY: Final[str] = "strict-origin-when-cross-origin"


class SecurityHeadersMiddleware:
    """
    Add security headers to HTTP responses.

    This is implemented as pure ASGI middleware instead of
    BaseHTTPMiddleware to avoid unnecessary request/response wrapping.

    Configuration can disable individual headers by passing an empty
    string or None where supported.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        csp: str | None = DEFAULT_CSP,
        hsts_max_age: int = 31536000,
        hsts_include_subdomains: bool = True,
        hsts_preload: bool = False,
        permissions_policy: str | None = DEFAULT_PERMISSIONS_POLICY,
        referrer_policy: str | None = DEFAULT_REFERRER_POLICY,
        frame_options: str | None = "DENY",
        nosniff: bool = True,
        cross_origin_opener_policy: str | None = "same-origin",
        cross_origin_resource_policy: str | None = "same-origin",
        enable_hsts: bool = True,
        trusted_proxy_count: int = 0,
    ) -> None:
        if hsts_max_age < 0:
            raise ValueError("hsts_max_age must be >= 0")

        if trusted_proxy_count < 0:
            raise ValueError("trusted_proxy_count must be >= 0")

        if hsts_preload and hsts_max_age < 31536000:
            raise ValueError(
                "HSTS preload requires hsts_max_age >= 31536000"
            )

        self.app = app
        self.csp = csp.strip() if csp else None
        self.docs_csp = DOCS_CSP
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.hsts_preload = hsts_preload
        self.permissions_policy = (
            permissions_policy.strip()
            if permissions_policy
            else None
        )
        self.referrer_policy = (
            referrer_policy.strip()
            if referrer_policy
            else None
        )
        self.frame_options = (
            frame_options.strip()
            if frame_options
            else None
        )
        self.nosniff = nosniff
        self.cross_origin_opener_policy = (
            cross_origin_opener_policy.strip()
            if cross_origin_opener_policy
            else None
        )
        self.cross_origin_resource_policy = (
            cross_origin_resource_policy.strip()
            if cross_origin_resource_policy
            else None
        )
        self.enable_hsts = enable_hsts
        self.trusted_proxy_count = trusted_proxy_count

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_https = self._is_https(scope)
        path = scope.get("path") or ""
        csp_value = self._csp_for_path(path)

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] != "http.response.start":
                await send(message)
                return

            headers = list(message.get("headers", []))

            self._append_header(
                headers,
                b"x-content-type-options",
                b"nosniff",
                enabled=self.nosniff,
            )

            self._append_header(
                headers,
                b"x-frame-options",
                self.frame_options.encode("latin-1")
                if self.frame_options
                else b"",
                enabled=self.frame_options is not None,
            )

            self._append_header(
                headers,
                b"referrer-policy",
                self.referrer_policy.encode("latin-1")
                if self.referrer_policy
                else b"",
                enabled=self.referrer_policy is not None,
            )

            self._append_header(
                headers,
                b"content-security-policy",
                csp_value.encode("latin-1") if csp_value else b"",
                enabled=csp_value is not None,
            )

            self._append_header(
                headers,
                b"permissions-policy",
                self.permissions_policy.encode("latin-1")
                if self.permissions_policy
                else b"",
                enabled=self.permissions_policy is not None,
            )

            self._append_header(
                headers,
                b"cross-origin-opener-policy",
                self.cross_origin_opener_policy.encode("latin-1")
                if self.cross_origin_opener_policy
                else b"",
                enabled=self.cross_origin_opener_policy is not None,
            )

            self._append_header(
                headers,
                b"cross-origin-resource-policy",
                self.cross_origin_resource_policy.encode("latin-1")
                if self.cross_origin_resource_policy
                else b"",
                enabled=self.cross_origin_resource_policy is not None,
            )

            if self.enable_hsts and is_https:
                hsts = self._build_hsts()

                self._append_header(
                    headers,
                    b"strict-transport-security",
                    hsts.encode("latin-1"),
                    enabled=True,
                )

            message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)

    def _csp_for_path(self, path: str) -> str | None:
        """Use a CDN-friendly CSP for Swagger/ReDoc pages only."""
        if self.csp is None:
            return None
        normalized = path.rstrip("/") or "/"
        if any(
            normalized == suffix or normalized.endswith(suffix)
            for suffix in _DOCS_PATH_SUFFIXES
        ):
            return self.docs_csp
        return self.csp

    def _is_https(self, scope: Scope) -> bool:
        """
        Determine whether the original request used HTTPS.

        Direct HTTPS:
            scope["scheme"] == "https"

        Reverse proxy:
            If trusted_proxy_count > 0, inspect X-Forwarded-Proto.

        Do not enable forwarded-proto handling unless the application
        is actually behind a trusted proxy. Otherwise clients can spoof
        X-Forwarded-Proto.
        """
        if scope.get("scheme") == "https":
            return True

        if self.trusted_proxy_count <= 0:
            return False

        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
        }

        forwarded_proto = headers.get(b"x-forwarded-proto")

        if not forwarded_proto:
            return False

        # Standard proxy format is usually:
        # X-Forwarded-Proto: https
        #
        # Some proxy chains produce:
        # X-Forwarded-Proto: https,http
        #
        # The left-most value represents the original protocol.
        proto = forwarded_proto.decode(
            "latin-1",
            errors="ignore",
        ).split(",", 1)[0].strip().lower()

        return proto == "https"

    def _build_hsts(self) -> str:
        parts = [f"max-age={self.hsts_max_age}"]

        if self.hsts_include_subdomains:
            parts.append("includeSubDomains")

        if self.hsts_preload:
            parts.append("preload")

        return "; ".join(parts)

    @staticmethod
    def _append_header(
        headers: list[tuple[bytes, bytes]],
        name: bytes,
        value: bytes,
        *,
        enabled: bool,
    ) -> None:
        """
        Add a header only when it does not already exist.

        Existing application-specific headers win.
        """
        if not enabled:
            return

        name_lower = name.lower()

        for existing_name, _ in headers:
            if existing_name.lower() == name_lower:
                return

        headers.append((name, value))


__all__ = [
    "DEFAULT_CSP",
    "DOCS_CSP",
    "DEFAULT_PERMISSIONS_POLICY",
    "DEFAULT_REFERRER_POLICY",
    "SecurityHeadersMiddleware",
]