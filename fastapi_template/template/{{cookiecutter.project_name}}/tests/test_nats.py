"""NATS client dependency and lifecycle tests."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from nats.aio.client import Client as NATS
from starlette import status

from {{cookiecutter.project_name}}.services.nats.dependencies import get_nats
from {{cookiecutter.project_name}}.services.nats.lifespan import (
    NATS_STATE_KEY,
    shutdown_nats,
)



def _nats_available() -> bool:
    import socket
    try:
        with socket.create_connection(("localhost", 4222), timeout=0.5):
            return True
    except OSError:
        return False

def test_get_nats_raises_when_unset() -> None:
    request = Mock()
    request.app.state = SimpleNamespace()

    with pytest.raises(RuntimeError, match="not initialized"):
        get_nats(request)


def test_get_nats_raises_when_closed() -> None:
    client = Mock()
    client.is_closed = True
    request = Mock()
    request.app.state = SimpleNamespace(**{NATS_STATE_KEY: client})

    with pytest.raises(RuntimeError, match="closed"):
        get_nats(request)


def test_get_nats_returns_when_set() -> None:
    client = Mock()
    client.is_closed = False
    request = Mock()
    request.app.state = SimpleNamespace(**{NATS_STATE_KEY: client})

    assert get_nats(request) is client


@pytest.mark.anyio
async def test_shutdown_nats_noop_when_missing() -> None:
    app = Mock()
    app.state = SimpleNamespace()

    await shutdown_nats(app)


@pytest.mark.anyio
async def test_shutdown_nats_drains_and_clears() -> None:
    client = Mock()
    client.is_closed = False
    client.drain = AsyncMock()
    client.close = AsyncMock()
    app = Mock()
    app.state = SimpleNamespace(**{NATS_STATE_KEY: client})

    await shutdown_nats(app)

    client.drain.assert_awaited_once()
    assert not hasattr(app.state, NATS_STATE_KEY)


@pytest.mark.skipif(not _nats_available(), reason="NATS not available")
async def test_message_publishing(
    fastapi_app: FastAPI,
    client: AsyncClient,
    test_nats: NATS,
) -> None:
    """
    Test that messages are published correctly.

    It sends a message via the API, reads it from NATS, and
    validates that the received payload matches.
    """
    subject = uuid.uuid4().hex
    payload = uuid.uuid4().hex

    sub = await test_nats.subscribe(subject)
    try:
        {%- if cookiecutter.api_type == 'rest' %}
        url = fastapi_app.url_path_for("publish_nats_message")
        response = await client.post(
            url,
            json={
                "subject": subject,
                "message": payload,
            },
        )
        {%- elif cookiecutter.api_type == 'graphql' %}
        url = fastapi_app.url_path_for('handle_http_post')
        response = await client.post(
            url,
            json={
                "query": "mutation($message:NatsMessageDTO!)"
                         "{publishNatsMessage(message:$message)}",
                "variables": {
                    "message": {
                        "subject": subject,
                        "message": payload,
                    },
                },
            },
        )
        {%- endif %}
        assert response.status_code == status.HTTP_200_OK
        message = await asyncio.wait_for(sub.next_msg(), timeout=1.0)
        assert message.data == payload.encode()
    finally:
        await sub.unsubscribe()
