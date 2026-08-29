from __future__ import annotations

from fastapi import FastAPI
from redis.asyncio import ConnectionPool

from {{cookiecutter.project_name}}.settings import settings


REDIS_POOL_STATE_KEY = "redis_pool"


def init_redis(app: FastAPI) -> None:  # pragma: no cover
    """
    Create the application-wide Redis connection pool.

    The pool is shared by request handlers and should not be
    recreated per request.
    """

    if getattr(app.state, REDIS_POOL_STATE_KEY, None) is not None:
        return

    app.state.redis_pool = ConnectionPool.from_url(
        str(settings.redis_url),
        max_connections=getattr(
            settings,
            "redis_max_connections",
            50,
        ),
        decode_responses=False,
    )


async def shutdown_redis(app: FastAPI) -> None:  # pragma: no cover
    """
    Gracefully close the Redis connection pool.
    """

    pool: ConnectionPool | None = getattr(
        app.state,
        REDIS_POOL_STATE_KEY,
        None,
    )

    if pool is None:
        return

    await pool.disconnect()

    try:
        delattr(app.state, REDIS_POOL_STATE_KEY)
    except AttributeError:
        pass
