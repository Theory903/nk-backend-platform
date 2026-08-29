"""
Legacy store accessors.

Prefer ``core.state.create_state_stores`` for new code.

These helpers are retained for backwards compatibility. For the Redis
backend they require an already-created ``redis_client`` — they never
open a URL or construct a Redis connection. Pass a client built from
``app.state.redis_pool`` (see ``stores.redis_store`` docstring).
"""

from __future__ import annotations

from {{cookiecutter.project_name}}.core.state import (
    CounterStore,
    ExpiringStore,
    InMemoryCounterStore,
    InMemoryExpiringStore,
    InMemorySetStore,
    SetStore,
    create_state_stores,
)


def get_expiring_store(
    backend: str = "memory",
    redis_client: object | None = None,
) -> ExpiringStore:
    """Return an expiring state store. Redis backend requires ``redis_client``."""

    if backend == "redis":
        if redis_client is None:
            raise ValueError(
                "redis_client is required when backend='redis'"
            )

        return create_state_stores(
            backend="redis",
            redis_client=redis_client,
        ).expiring

    if backend == "memory":
        return InMemoryExpiringStore()

    raise ValueError(f"unknown state-store backend: {backend!r}")


def get_set_store(
    backend: str = "memory",
    redis_client: object | None = None,
) -> SetStore:
    """Return a set state store. Redis backend requires ``redis_client``."""

    if backend == "redis":
        if redis_client is None:
            raise ValueError(
                "redis_client is required when backend='redis'"
            )

        return create_state_stores(
            backend="redis",
            redis_client=redis_client,
        ).sets

    if backend == "memory":
        return InMemorySetStore()

    raise ValueError(f"unknown state-store backend: {backend!r}")


def get_counter_store(
    backend: str = "memory",
    redis_client: object | None = None,
) -> CounterStore:
    """Return a counter state store. Redis backend requires ``redis_client``."""

    if backend == "redis":
        if redis_client is None:
            raise ValueError(
                "redis_client is required when backend='redis'"
            )

        return create_state_stores(
            backend="redis",
            redis_client=redis_client,
        ).counters

    if backend == "memory":
        return InMemoryCounterStore()

    raise ValueError(f"unknown state-store backend: {backend!r}")


__all__ = [
    "CounterStore",
    "ExpiringStore",
    "SetStore",
    "InMemoryCounterStore",
    "InMemoryExpiringStore",
    "InMemorySetStore",
    "get_expiring_store",
    "get_set_store",
    "get_counter_store",
]
