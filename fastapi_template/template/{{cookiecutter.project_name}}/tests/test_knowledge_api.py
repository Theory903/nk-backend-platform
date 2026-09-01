"""Tests for the authenticated knowledge answer route."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from {{cookiecutter.project_name}}.platform.contracts import Scope
from {{cookiecutter.project_name}}.web.api.knowledge import router


class FakeAnswerService:
    async def answer(self, payload):  # noqa: ANN001
        return {
            "answer": f"answered:{payload.query}",
            "citations": [],
            "abstained": False,
            "freshness_checked_at": "2026-01-01T00:00:00Z",
            "usage": {},
            "cached": False,
        }


async def test_knowledge_route_requires_authenticated_scope() -> None:
    unauthorized_app = FastAPI()
    unauthorized_app.include_router(router)
    unauthorized_app.state.rag_service = FakeAnswerService()

    async with AsyncClient(
        transport=ASGITransport(app=unauthorized_app),
        base_url="http://test",
    ) as client:
        unauthorized = await client.post(
            "/v1/answers",
            json={"query": "hello", "scope": {
                "principal_id": "untrusted",
                "organization_id": "untrusted",
            }},
        )
        assert unauthorized.status_code == 401

    authorized_app = FastAPI()
    authorized_app.include_router(router)
    authorized_app.state.rag_service = FakeAnswerService()

    @authorized_app.middleware("http")
    async def attach_scope(request, call_next):  # noqa: ANN001
        request.state.scope = Scope(
            principal_id="user-1",
            organization_id="org-1",
        )
        return await call_next(request)

    async with AsyncClient(
        transport=ASGITransport(app=authorized_app),
        base_url="http://test",
    ) as client:
        authorized = await client.post(
            "/v1/answers",
            json={"query": "hello", "scope": {
                "principal_id": "untrusted",
                "organization_id": "untrusted",
            }},
        )
        assert authorized.status_code == 200
        assert authorized.json()["answer"] == "answered:hello"
