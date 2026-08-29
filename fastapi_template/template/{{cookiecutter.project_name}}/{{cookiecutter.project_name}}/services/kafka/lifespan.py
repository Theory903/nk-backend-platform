from __future__ import annotations

from aiokafka import AIOKafkaProducer
from fastapi import FastAPI

from {{cookiecutter.project_name}}.settings import settings


KAFKA_PRODUCER_STATE_KEY = "kafka_producer"


def _lz4_available() -> bool:
    """Return True when aiokafka can use the lz4 codec."""
    try:
        from aiokafka.codec import has_lz4

        return bool(has_lz4() if callable(has_lz4) else has_lz4)
    except Exception:
        try:
            import lz4.frame  # noqa: F401
        except ImportError:
            return False
        return True


def _resolve_compression_type(
    configured: str | None,
) -> str | None:
    """
    Resolve producer ``compression_type``.

    Prefer ``settings.kafka_compression_type`` when present. Default is
    ``\"lz4\"``. If lz4 is requested but the codec is unavailable (no
    ``python-lz4`` / aiokafka lz4 support), fall back to ``\"gzip\"`` so
    startup does not fail. Set the setting to ``None`` to disable
    compression, or to ``\"gzip\"`` / ``\"snappy\"`` / ``\"zstd\"`` explicitly.
    """
    if configured is None:
        return None
    if configured == "lz4" and not _lz4_available():
        return "gzip"
    return configured


async def init_kafka(
    app: FastAPI,
) -> None:
    """
    Initialize the application-wide Kafka producer.

    One producer is created per FastAPI process and reused by all requests
    via ``get_kafka_producer`` / ``app.state``.

    Producer knobs prefer settings fields when defined
    (``kafka_acks``, ``kafka_enable_idempotence``, ``kafka_linger_ms``,
    ``kafka_compression_type``, ``kafka_request_timeout_ms``); otherwise
    defaults match production-safe values (acks=all, idempotence on,
    linger_ms=5, compression lz4→gzip fallback).
    """

    existing = getattr(
        app.state,
        KAFKA_PRODUCER_STATE_KEY,
        None,
    )

    if existing is not None:
        return

    compression = _resolve_compression_type(
        getattr(settings, "kafka_compression_type", "lz4"),
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,

        # Reliability.
        acks=getattr(settings, "kafka_acks", "all"),
        enable_idempotence=getattr(
            settings,
            "kafka_enable_idempotence",
            True,
        ),

        # Keep batching enabled without introducing excessive latency.
        linger_ms=getattr(settings, "kafka_linger_ms", 5),

        # Compression reduces network traffic for event-heavy workloads.
        # See ``_resolve_compression_type`` for lz4→gzip fallback.
        compression_type=compression,

        # Bound individual request latency.
        request_timeout_ms=getattr(
            settings,
            "kafka_request_timeout_ms",
            30_000,
        ),

        # Useful for tracing/observability at the Kafka layer.
        client_id=getattr(
            settings,
            "app_name",
            "{{cookiecutter.project_name}}",
        ),
    )

    try:
        await producer.start()
    except Exception:
        # Do not leave a half-initialized producer in app.state.
        try:
            await producer.stop()
        except Exception:
            pass

        raise

    setattr(
        app.state,
        KAFKA_PRODUCER_STATE_KEY,
        producer,
    )


async def shutdown_kafka(
    app: FastAPI,
) -> None:
    """
    Gracefully stop the application-wide Kafka producer.

    Safe if the producer was never started. aiokafka flushes pending
    records as part of shutdown.
    """

    producer: AIOKafkaProducer | None = getattr(
        app.state,
        KAFKA_PRODUCER_STATE_KEY,
        None,
    )

    if producer is None:
        return

    try:
        stop = getattr(producer, "stop", None)
        if callable(stop):
            result = stop()
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]
    finally:
        try:
            delattr(
                app.state,
                KAFKA_PRODUCER_STATE_KEY,
            )
        except AttributeError:
            pass
