"""Resolve durable vs in-process memory backends (P1)."""

from __future__ import annotations

import logging
from typing import Any

from {{cookiecutter.project_name}}.agents.memory import MemoryStore
from {{cookiecutter.project_name}}.agents.memory_redis import RedisMemoryStore
from {{cookiecutter.project_name}}.llm.features.runtime import FeatureRuntime
from {{cookiecutter.project_name}}.settings import settings

logger = logging.getLogger(__name__)


def _resolve_memory_backend(app: Any) -> str:
    backend = settings.memory_backend.strip().lower()
    if backend != "auto":
        return backend
    if getattr(app.state, "redis_pool", None) is not None:
        return "redis"
    return "memory"


def configure_memory_store(app: Any, runtime: FeatureRuntime) -> None:
    """Replace the default in-memory store when Redis persistence is configured."""
    backend = _resolve_memory_backend(app)
    if backend == "memory":
        return
    if backend != "redis":
        logger.warning("unknown memory_backend=%s; keeping in-memory store", backend)
        return
    if getattr(app.state, "redis_pool", None) is None:
        logger.warning("memory_backend=redis but Redis is unavailable; using memory")
        return
    try:
        import redis

        client = redis.from_url(
            str(settings.redis_url),
            decode_responses=True,
        )
        runtime.memory_store = RedisMemoryStore(
            client,
            prefix=settings.memory_redis_prefix,
        )
        app.state.memory_redis_client = client
        logger.info("agent memory backend: redis (%s)", settings.memory_redis_prefix)
    except Exception:
        logger.exception("failed to configure Redis memory; using in-memory store")


__all__ = ["configure_memory_store"]
