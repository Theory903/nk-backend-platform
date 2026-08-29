"""
Redis helpers for locks and legacy wiring.

Prefer ``core.state.create_state_stores`` for application state.

``create_redis_client`` is for ``core.locks`` and other standalone
string-oriented clients. It does **not** own application lifecycle —
callers must close the client/pool.

decode_responses convention
---------------------------
* ``services.redis.lifespan`` builds ``app.state.redis_pool`` with
  ``decode_responses=False`` (binary-safe shared pool).
* redis-py takes ``decode_responses`` from the **pool**, not from a
  ``Redis(connection_pool=..., decode_responses=True)`` override.
* ``RedisExpiringStore`` / ``RedisSetStore`` / ``RedisCounterStore``
  accept both ``str`` and ``bytes`` (they decode when needed), so the
  shared pool works as-is::

      from redis.asyncio import Redis
      from {{cookiecutter.project_name}}.core.state import create_state_stores

      client = Redis(connection_pool=app.state.redis_pool)
      stores = create_state_stores(backend="redis", redis_client=client)

* ``create_redis_client(url)`` opens a separate URL-based client with
  ``decode_responses=True`` for locks / legacy string stores only.
"""

from __future__ import annotations

from typing import Any

from {{cookiecutter.project_name}}.core.state import (
    RedisCounterStore,
    RedisExpiringStore,
    RedisSetStore,
)

__all__ = [
    "RedisCounterStore",
    "RedisExpiringStore",
    "RedisSetStore",
    "create_redis_client",
]


def create_redis_client(url: str) -> Any:
    """
    Create an async redis-py client with ``decode_responses=True``.

    Intended for locks and legacy DI that need a URL-based string
    client. Application state should use the shared pool::

        Redis(connection_pool=app.state.redis_pool)

    The caller owns lifecycle and must close the client/pool.
    """
    import redis.asyncio as aioredis

    return aioredis.from_url(
        url,
        decode_responses=True,
    )
