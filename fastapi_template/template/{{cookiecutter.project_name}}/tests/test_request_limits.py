from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from {{cookiecutter.project_name}}.web.middleware.request_limits import (
    RequestBodyLimitMiddleware,
)


@pytest.fixture
def limited_app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=4,
    )

    @application.post("/")
    async def receive_body(request: Request) -> dict[str, int]:
        body = await request.body()
        return {"size": len(body)}

    return application


@pytest.fixture
async def client(limited_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(limited_app),
        base_url="http://test",
    ) as http_client:
        yield http_client


@pytest.mark.anyio
async def test_rejects_large_content_length(client: AsyncClient) -> None:
    response = await client.post("/", content=b"12345")

    assert response.status_code == 413


@pytest.mark.anyio
async def test_accepts_body_within_limit(client: AsyncClient) -> None:
    response = await client.post("/", content=b"1234")

    assert response.status_code == 200
    assert response.json() == {"size": 4}
