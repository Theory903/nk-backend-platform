"""Unit tests for RabbitMQ channel-pool DI and lifespan."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from {{cookiecutter.project_name}}.services.rabbit.dependencies import (
    get_rmq_channel_pool,
)
from {{cookiecutter.project_name}}.services.rabbit.lifespan import (
    RMQ_CHANNEL_POOL_STATE_KEY,
    RMQ_CONNECTION_STATE_KEY,
    init_rmq,
    shutdown_rmq,
)


def test_get_rmq_channel_pool_raises_when_unset() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(RuntimeError, match="not initialized"):
        get_rmq_channel_pool(request)  # type: ignore[arg-type]


def test_get_rmq_channel_pool_returns_when_set() -> None:
    pool = object()
    state = SimpleNamespace()
    setattr(state, RMQ_CHANNEL_POOL_STATE_KEY, pool)
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    assert get_rmq_channel_pool(request) is pool  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_shutdown_rmq_safe_when_missing() -> None:
    app = FastAPI()
    await shutdown_rmq(app)


@pytest.mark.anyio
async def test_init_rmq_stores_connection_and_pool() -> None:
    app = FastAPI()
    fake_connection = MagicMock()
    fake_connection.close = AsyncMock()
    fake_pool = MagicMock()
    fake_pool.close = AsyncMock()

    with (
        patch(
            "{{cookiecutter.project_name}}.services.rabbit.lifespan.connect_robust",
            new=AsyncMock(return_value=fake_connection),
        ) as connect,
        patch(
            "{{cookiecutter.project_name}}.services.rabbit.lifespan.Pool",
            return_value=fake_pool,
        ) as pool_ctor,
    ):
        await init_rmq(app)
        await init_rmq(app)  # idempotent — no second connect

    assert getattr(app.state, RMQ_CONNECTION_STATE_KEY) is fake_connection
    assert getattr(app.state, RMQ_CHANNEL_POOL_STATE_KEY) is fake_pool
    assert connect.await_count == 1
    assert pool_ctor.call_count == 1
    assert pool_ctor.call_args.kwargs.get("max_size") is not None


@pytest.mark.anyio
async def test_init_rmq_closes_connection_on_pool_failure() -> None:
    app = FastAPI()
    fake_connection = MagicMock()
    fake_connection.close = AsyncMock()

    with (
        patch(
            "{{cookiecutter.project_name}}.services.rabbit.lifespan.connect_robust",
            new=AsyncMock(return_value=fake_connection),
        ),
        patch(
            "{{cookiecutter.project_name}}.services.rabbit.lifespan.Pool",
            side_effect=RuntimeError("pool boom"),
        ),
    ):
        with pytest.raises(RuntimeError, match="pool boom"):
            await init_rmq(app)

    fake_connection.close.assert_awaited_once()
    assert not hasattr(app.state, RMQ_CHANNEL_POOL_STATE_KEY)
    assert not hasattr(app.state, RMQ_CONNECTION_STATE_KEY)


@pytest.mark.anyio
async def test_shutdown_rmq_closes_pool_then_connection() -> None:
    app = FastAPI()
    fake_pool = MagicMock()
    fake_pool.close = AsyncMock()
    fake_connection = MagicMock()
    fake_connection.close = AsyncMock()
    setattr(app.state, RMQ_CHANNEL_POOL_STATE_KEY, fake_pool)
    setattr(app.state, RMQ_CONNECTION_STATE_KEY, fake_connection)

    await shutdown_rmq(app)

    fake_pool.close.assert_awaited_once()
    fake_connection.close.assert_awaited_once()
    assert not hasattr(app.state, RMQ_CHANNEL_POOL_STATE_KEY)
    assert not hasattr(app.state, RMQ_CONNECTION_STATE_KEY)
