"""Wire gateway cache + embedder at application startup (P2)."""

from __future__ import annotations

import logging
from typing import Any

from {{cookiecutter.project_name}}.ai.gateway.semantic_cache import (
    InMemoryCompletionCache,
    RedisCompletionCache,
    configure_completion_cache,
)
from {{cookiecutter.project_name}}.settings import settings

logger = logging.getLogger(__name__)


def configure_gateway_runtime(app: Any) -> None:
    """Select completion cache backend and optional embedder for semantic tier."""
    if not getattr(settings, "llm_semantic_cache_enabled", True):
        configure_completion_cache(None)
        return

    embedder = None
    {%- if cookiecutter.enable_vector in [True, "True", "true", 1, "1"] %}
    try:
        from {{cookiecutter.project_name}}.ai.embeddings import get_embedding_provider

        embedder = get_embedding_provider(getattr(settings, "embedding_provider", "local"))
    except Exception as exc:
        logger.warning("semantic cache embedder unavailable: %s", exc)
    {%- endif %}

    if getattr(app.state, "redis_pool", None) is not None:
        try:
            import redis.asyncio as aioredis

            client = aioredis.Redis(
                connection_pool=app.state.redis_pool,
                decode_responses=True,
            )
            configure_completion_cache(
                RedisCompletionCache(client),
                embedder=embedder,
            )
            logger.info("model gateway cache: redis exact + semantic tier")
            return
        except Exception:
            logger.exception("failed to configure Redis completion cache")

    configure_completion_cache(InMemoryCompletionCache(), embedder=embedder)
    logger.info("model gateway cache: in-memory")


__all__ = ["configure_gateway_runtime"]
