from __future__ import annotations

from typing import Annotated

from aiokafka import AIOKafkaProducer
from fastapi import Depends, Request

{%- if cookiecutter.enable_taskiq == "True" %}
from taskiq import TaskiqDepends
{%- endif %}

from {{cookiecutter.project_name}}.services.kafka.lifespan import (
    KAFKA_PRODUCER_STATE_KEY,
)


def get_kafka_producer(
    request: Request
    {%- if cookiecutter.enable_taskiq == "True" %}
    = TaskiqDepends()
    {%- endif %}
) -> AIOKafkaProducer:
    """
    Resolve the application-wide Kafka producer.

    The producer must be created during application startup and stopped
    during application shutdown. Do not construct a producer per request.
    """
    producer = getattr(
        request.app.state,
        KAFKA_PRODUCER_STATE_KEY,
        None,
    )

    if producer is None:
        raise RuntimeError(
            "Kafka producer is not initialized"
        )

    return producer


KafkaProducer = Annotated[
    AIOKafkaProducer,
    Depends(get_kafka_producer),
]
