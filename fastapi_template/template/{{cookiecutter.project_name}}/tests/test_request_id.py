"""Tests for RequestIdMiddleware trust model."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from {{cookiecutter.project_name}}.core.logging import org_id_var, trace_id_var, user_id_var
from {{cookiecutter.project_name}}.web.middleware.request_id import RequestIdMiddleware


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/echo")
    async def echo(request: Request) -> dict:
        return {
            "request_id": getattr(request.state, "request_id", None),
            "trace_id": getattr(request.state, "trace_id", None),
            "log_org": org_id_var.get(),
            "log_user": user_id_var.get(),
            "log_trace": trace_id_var.get(),
        }

    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.fixture
def client(app: FastAPI):
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


class TestRequestIdHeaders:
    @pytest.mark.asyncio
    async def test_response_has_x_request_id(
        self,
        client: AsyncClient,
    ) -> None:
        resp = await client.get("/echo")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
        assert resp.headers["x-request-id"]
        assert resp.json()["request_id"] == resp.headers["x-request-id"]

    @pytest.mark.asyncio
    async def test_propagates_client_request_id(
        self,
        client: AsyncClient,
    ) -> None:
        resp = await client.get(
            "/echo",
            headers={"x-request-id": "client-rid-123"},
        )
        assert resp.headers["x-request-id"] == "client-rid-123"

    @pytest.mark.asyncio
    async def test_no_fake_trace_id_from_request_id(
        self,
        client: AsyncClient,
    ) -> None:
        """Without OTel, trace_id must not equal request_id."""
        resp = await client.get(
            "/echo",
            headers={"x-request-id": "client-rid-abc"},
        )
        body = resp.json()
        assert body["request_id"] == "client-rid-abc"
        assert body["trace_id"] == ""
        assert body["log_trace"] == ""
        assert "x-trace-id" not in resp.headers


class TestOrgNotFromHeader:
    @pytest.mark.asyncio
    async def test_x_org_id_header_not_trusted_for_logging(
        self,
        client: AsyncClient,
    ) -> None:
        resp = await client.get(
            "/echo",
            headers={"x-org-id": "spoofed-org"},
        )
        assert resp.status_code == 200
        assert resp.json()["log_org"] == ""

    @pytest.mark.asyncio
    async def test_principal_and_tenant_used_when_present(self) -> None:
        """Trusted principal/tenant on state are used for logging context."""
        app = FastAPI()
        captured: dict = {}

        @app.get("/p")
        async def route(request: Request) -> dict:
            captured["org"] = org_id_var.get()
            captured["user"] = user_id_var.get()
            return {"ok": True}

        class SeedTrustedState(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                request.state.principal = SimpleNamespace(
                    user_id="user-1",
                    org_id="org-from-principal",
                )
                request.state.tenant = SimpleNamespace(
                    org_id="org-from-tenant",
                )
                return await call_next(request)

        # LIFO: SeedTrustedState outermost so RequestId sees principal.
        app.add_middleware(RequestIdMiddleware)
        app.add_middleware(SeedTrustedState)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://t",
        ) as c:
            resp = await c.get("/p")
        assert resp.status_code == 200
        assert captured["org"] == "org-from-tenant"
        assert captured["user"] == "user-1"


class TestOTelTraceId:
    @pytest.mark.asyncio
    async def test_otel_trace_id_when_available(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_tid = "a" * 32

        monkeypatch.setattr(
            "{{cookiecutter.project_name}}.web.middleware.request_id._otel_trace_id",
            lambda: fake_tid,
        )

        app = FastAPI()

        @app.get("/echo")
        async def echo(request: Request) -> dict:
            return {
                "request_id": request.state.request_id,
                "trace_id": request.state.trace_id,
            }

        app.add_middleware(RequestIdMiddleware)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            resp = await client.get("/echo")

        assert resp.status_code == 200
        assert resp.headers.get("x-trace-id") == fake_tid
        assert resp.json()["trace_id"] == fake_tid
        assert resp.json()["trace_id"] != resp.json()["request_id"]
