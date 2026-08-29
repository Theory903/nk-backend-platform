"""Unit tests for Redis connection-pool DI and lifespan."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from redis.asyncio import ConnectionPool

from {{cookiecutter.project_name}}.services.redis.dependency import (
    get_redis_pool,
)
from {{cookiecutter.project_name}}.services.redis.lifespan import (
    REDIS_POOL_STATE_KEY,
    init_redis,
    shutdown_redis,
)


def test_get_redis_pool_raises_when_unset() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(RuntimeError, match="not initialized"):
        get_redis_pool(request)  # type: ignore[arg-type]


def test_get_redis_pool_returns_connection_pool() -> None:
    pool = object()
    state = SimpleNamespace()
    setattr(state, REDIS_POOL_STATE_KEY, pool)
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    result = get_redis_pool(request)  # type: ignore[arg-type]

    assert result is pool
    assert get_redis_pool.__annotations__["return"] in (
        ConnectionPool,
        "ConnectionPool",
    )


@pytest.mark.anyio
async def test_shutdown_redis_safe_when_missing() -> None:
    app = FastAPI()
    await shutdown_redis(app)


@pytest.mark.anyio
async def test_shutdown_redis_disconnects_and_clears() -> None:
    app = FastAPI()
    fake = MagicMock()
    fake.disconnect = AsyncMock()
    setattr(app.state, REDIS_POOL_STATE_KEY, fake)

    await shutdown_redis(app)

    fake.disconnect.assert_awaited_once()
    assert not hasattr(app.state, REDIS_POOL_STATE_KEY)


@pytest.mark.anyio
async def test_init_redis_stores_single_pool() -> None:
    app = FastAPI()
    fake = MagicMock()

    with patch(
        "{{cookiecutter.project_name}}.services.redis.lifespan.ConnectionPool"
    ) as pool_cls:
        pool_cls.from_url.return_value = fake
        init_redis(app)
        init_redis(app)  # idempotent — no second create

    assert getattr(app.state, REDIS_POOL_STATE_KEY) is fake
    assert pool_cls.from_url.call_count == 1
    kwargs = pool_cls.from_url.call_args.kwargs
    assert kwargs["max_connections"] == 50
    assert kwargs["decode_responses"] is False
