from __future__ import annotations

from typing import Annotated

from aio_pika import Channel
from aio_pika.pool import Pool
from fastapi import Depends, Request

{%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
from taskiq import TaskiqDepends
{%- endif %}

from {{cookiecutter.project_name}}.services.rabbit.lifespan import (
    RMQ_CHANNEL_POOL_STATE_KEY,
)


def get_rmq_channel_pool(
    request: Request
    {%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
    = TaskiqDepends()
    {%- endif %}
) -> Pool[Channel]:
    """
    Resolve the application-wide RabbitMQ channel pool.

    The pool is created during application startup and shared by
    request handlers. Do not open a new connection per request.
    """

    pool = getattr(
        request.app.state,
        RMQ_CHANNEL_POOL_STATE_KEY,
        None,
    )

    if pool is None:
        raise RuntimeError(
            "RabbitMQ channel pool is not initialized"
        )

    return pool


RmqChannelPool = Annotated[
    Pool[Channel],
    Depends(get_rmq_channel_pool),
]
