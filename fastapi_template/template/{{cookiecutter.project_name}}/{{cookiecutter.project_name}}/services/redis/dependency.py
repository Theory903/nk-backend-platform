from __future__ import annotations

from redis.asyncio import ConnectionPool
from starlette.requests import Request

{%- if cookiecutter.enable_taskiq == "True" %}
from taskiq import TaskiqDepends
{%- endif %}

from {{cookiecutter.project_name}}.services.redis.lifespan import (
    REDIS_POOL_STATE_KEY,
)


def get_redis_pool(
    request: Request
    {%- if cookiecutter.enable_taskiq == "True" %}
    = TaskiqDepends()
    {%- endif %}
) -> ConnectionPool:  # pragma: no cover
    """
    Resolve the application-wide Redis connection pool.

    The pool is initialized during application startup and shared
    across request handlers.
    """

    pool = getattr(
        request.app.state,
        REDIS_POOL_STATE_KEY,
        None,
    )

    if pool is None:
        raise RuntimeError(
            "Redis connection pool is not initialized"
        )

    return pool
