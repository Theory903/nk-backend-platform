"""Unit tests for Kafka producer DI and lifespan."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from {{cookiecutter.project_name}}.services.kafka.dependencies import (
    get_kafka_producer,
)
from {{cookiecutter.project_name}}.services.kafka.lifespan import (
    KAFKA_PRODUCER_STATE_KEY,
    _resolve_compression_type,
    init_kafka,
    shutdown_kafka,
)


def test_get_kafka_producer_raises_when_unset() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(RuntimeError, match="not initialized"):
        get_kafka_producer(request)  # type: ignore[arg-type]


def test_get_kafka_producer_returns_from_app_state() -> None:
    producer = object()
    state = SimpleNamespace()
    setattr(state, KAFKA_PRODUCER_STATE_KEY, producer)
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    assert get_kafka_producer(request) is producer  # type: ignore[arg-type]


def test_resolve_compression_falls_back_when_lz4_missing() -> None:
    with patch(
        "{{cookiecutter.project_name}}.services.kafka.lifespan._lz4_available",
        return_value=False,
    ):
        assert _resolve_compression_type("lz4") == "gzip"
        assert _resolve_compression_type(None) is None
        assert _resolve_compression_type("gzip") == "gzip"


@pytest.mark.anyio
async def test_init_kafka_stores_single_producer() -> None:
    app = FastAPI()
    fake = MagicMock()
    fake.start = AsyncMock()
    fake.stop = AsyncMock()

    with patch(
        "{{cookiecutter.project_name}}.services.kafka.lifespan.AIOKafkaProducer",
        return_value=fake,
    ) as ctor:
        await init_kafka(app)
        await init_kafka(app)  # idempotent — no second create

    assert getattr(app.state, KAFKA_PRODUCER_STATE_KEY) is fake
    assert ctor.call_count == 1
    fake.start.assert_awaited_once()
    kwargs = ctor.call_args.kwargs
    assert kwargs["acks"] == "all"
    assert kwargs["enable_idempotence"] is True
    assert kwargs["linger_ms"] == 5
    assert kwargs["request_timeout_ms"] == 30_000


@pytest.mark.anyio
async def test_init_kafka_cleans_up_on_start_failure() -> None:
    app = FastAPI()
    fake = MagicMock()
    fake.start = AsyncMock(side_effect=RuntimeError("boom"))
    fake.stop = AsyncMock()

    with patch(
        "{{cookiecutter.project_name}}.services.kafka.lifespan.AIOKafkaProducer",
        return_value=fake,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await init_kafka(app)

    assert not hasattr(app.state, KAFKA_PRODUCER_STATE_KEY)
    fake.stop.assert_awaited_once()


@pytest.mark.anyio
async def test_shutdown_kafka_safe_when_missing() -> None:
    app = FastAPI()
    await shutdown_kafka(app)


@pytest.mark.anyio
async def test_shutdown_kafka_stops_and_clears() -> None:
    app = FastAPI()
    fake = MagicMock()
    fake.stop = AsyncMock()
    setattr(app.state, KAFKA_PRODUCER_STATE_KEY, fake)

    await shutdown_kafka(app)

    fake.stop.assert_awaited_once()
    assert not hasattr(app.state, KAFKA_PRODUCER_STATE_KEY)
