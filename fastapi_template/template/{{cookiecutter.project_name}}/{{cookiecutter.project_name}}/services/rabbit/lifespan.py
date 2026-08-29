from __future__ import annotations

from aio_pika import Channel, connect_robust
from aio_pika.pool import Pool
from fastapi import FastAPI

from {{cookiecutter.project_name}}.settings import settings


RMQ_CHANNEL_POOL_STATE_KEY = "rmq_channel_pool"
RMQ_CONNECTION_STATE_KEY = "rmq_connection"


def _resolve_rabbitmq_url() -> str:
    """Prefer rabbitmq_url; fall back to legacy rabbit_url."""
    url = getattr(settings, "rabbitmq_url", None)
    if url is None:
        url = getattr(settings, "rabbit_url", None)
    if url is None:
        raise RuntimeError("RabbitMQ URL is not configured")
    return str(url)


def _resolve_channel_pool_size() -> int:
    """Prefer rabbitmq_channel_pool_size; fall back to rabbit_channel_pool_size."""
    size = getattr(settings, "rabbitmq_channel_pool_size", None)
    if size is None:
        size = getattr(settings, "rabbit_channel_pool_size", 20)
    return int(size)


async def init_rmq(
    app: FastAPI,
) -> None:  # pragma: no cover
    """
    Initialize the application-wide RabbitMQ connection and channel pool.

    One robust connection and one channel pool are created per FastAPI
    process and reused by all requests. Do not connect per request.

    Next: wrap the pool behind a MessagePublisher abstraction so
    application services do not depend on aio_pika.Pool directly.
    """

    existing = getattr(
        app.state,
        RMQ_CHANNEL_POOL_STATE_KEY,
        None,
    )

    if existing is not None:
        return

    connection = await connect_robust(
        _resolve_rabbitmq_url(),
        client_properties={
            "connection_name": getattr(
                settings,
                "app_name",
                "{{cookiecutter.project_name}}",
            ),
        },
    )

    try:
        async def create_channel() -> Channel:
            return await connection.channel(
                publisher_confirms=True,
            )

        channel_pool = Pool(
            create_channel,
            max_size=_resolve_channel_pool_size(),
        )
    except Exception:
        try:
            await connection.close()
        except Exception:
            pass
        raise

    setattr(app.state, RMQ_CONNECTION_STATE_KEY, connection)
    setattr(app.state, RMQ_CHANNEL_POOL_STATE_KEY, channel_pool)


async def shutdown_rmq(
    app: FastAPI,
) -> None:  # pragma: no cover
    """
    Gracefully close RabbitMQ resources.

    Closes the channel pool first, then the connection, then clears
    state keys. Safe when resources were never initialized.
    """

    pool: Pool[Channel] | None = getattr(
        app.state,
        RMQ_CHANNEL_POOL_STATE_KEY,
        None,
    )

    connection = getattr(
        app.state,
        RMQ_CONNECTION_STATE_KEY,
        None,
    )

    try:
        if pool is not None:
            close = getattr(pool, "close", None)
            if callable(close):
                result = close()
                if hasattr(result, "__await__"):
                    await result  # type: ignore[misc]
    finally:
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass

        for key in (
            RMQ_CHANNEL_POOL_STATE_KEY,
            RMQ_CONNECTION_STATE_KEY,
        ):
            try:
                delattr(app.state, key)
            except (AttributeError, KeyError):
                # Starlette State raises KeyError for missing keys.
                pass


# Back-compat aliases for older call sites / generated docs.
init_rabbit = init_rmq
shutdown_rabbit = shutdown_rmq
