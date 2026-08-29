"""Tests for security headers middleware and HTTPS / proxy HSTS rules."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from {{cookiecutter.project_name}}.web.middleware.security_headers import (
    SecurityHeadersMiddleware,
)


@pytest.fixture
def app_with_headers() -> FastAPI:
    app = FastAPI()

    @app.get("/test")
    async def test_route() -> dict:
        return {"ok": True}

    app.add_middleware(SecurityHeadersMiddleware, csp="default-src 'self'")
    return app


@pytest.fixture
def client(app_with_headers: FastAPI):
    return AsyncClient(
        transport=ASGITransport(app=app_with_headers),
        base_url="http://test",
    )


class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_nosniff_header_present(self, client: AsyncClient) -> None:
        resp = await client.get("/test")
        assert resp.headers["x-content-type-options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_frame_deny_header(self, client: AsyncClient) -> None:
        resp = await client.get("/test")
        assert resp.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_referrer_policy(self, client: AsyncClient) -> None:
        resp = await client.get("/test")
        assert (
            resp.headers["referrer-policy"]
            == "strict-origin-when-cross-origin"
        )

    @pytest.mark.asyncio
    async def test_csp_header_present(self, client: AsyncClient) -> None:
        resp = await client.get("/test")
        assert "content-security-policy" in resp.headers
        assert resp.headers["content-security-policy"] == "default-src 'self'"

    @pytest.mark.asyncio
    async def test_docs_csp_allows_swagger_cdn(self) -> None:
        app = FastAPI()

        @app.get("/api/docs")
        async def docs() -> dict:
            return {"docs": True}

        app.add_middleware(SecurityHeadersMiddleware)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/docs")
        csp = resp.headers["content-security-policy"]
        assert "cdn.jsdelivr.net" in csp
        assert "'unsafe-inline'" in csp

    @pytest.mark.asyncio
    async def test_hsts_absent_on_http(self, client: AsyncClient) -> None:
        resp = await client.get("/test")
        assert "strict-transport-security" not in resp.headers

    @pytest.mark.asyncio
    async def test_hsts_on_https_scheme(self) -> None:
        app = FastAPI()

        @app.get("/")
        async def root() -> dict:
            return {"ok": True}

        app.add_middleware(SecurityHeadersMiddleware)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="https://test",
        ) as client:
            resp = await client.get("/")
        assert "strict-transport-security" in resp.headers
        assert "max-age=" in resp.headers["strict-transport-security"]
        assert "includeSubDomains" in resp.headers["strict-transport-security"]

    @pytest.mark.asyncio
    async def test_hsts_via_trusted_proxy_forwarded_proto(self) -> None:
        app = FastAPI()

        @app.get("/")
        async def root() -> dict:
            return {"ok": True}

        app.add_middleware(
            SecurityHeadersMiddleware,
            trusted_proxy_count=1,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            resp = await client.get(
                "/",
                headers={"x-forwarded-proto": "https"},
            )
        assert "strict-transport-security" in resp.headers

    @pytest.mark.asyncio
    async def test_forwarded_proto_ignored_without_trusted_proxy(
        self,
    ) -> None:
        app = FastAPI()

        @app.get("/")
        async def root() -> dict:
            return {"ok": True}

        app.add_middleware(
            SecurityHeadersMiddleware,
            trusted_proxy_count=0,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            resp = await client.get(
                "/",
                headers={"x-forwarded-proto": "https"},
            )
        assert "strict-transport-security" not in resp.headers

    @pytest.mark.asyncio
    async def test_custom_csp_used(self, client: AsyncClient) -> None:
        resp = await client.get("/test")
        assert resp.headers["content-security-policy"] == "default-src 'self'"

    @pytest.mark.asyncio
    async def test_default_csp_when_none_provided(self) -> None:
        app = FastAPI()

        @app.get("/")
        async def root() -> dict:
            return {}

        app.add_middleware(SecurityHeadersMiddleware)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            resp = await client.get("/")
            csp = resp.headers["content-security-policy"]
            assert "default-src 'self'" in csp
