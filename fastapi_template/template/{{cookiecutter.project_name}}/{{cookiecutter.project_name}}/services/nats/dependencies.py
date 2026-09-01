from __future__ import annotations

from fastapi import Request
from nats.aio.client import Client as NATS

from {{cookiecutter.project_name}}.services.nats.lifespan import NATS_STATE_KEY

{%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
from taskiq import TaskiqDepends
{%- endif %}


def get_nats(
    request: Request
    {%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
    = TaskiqDepends()
    {%- endif %}
) -> NATS:
    """
    Resolve the application-wide NATS client.

    The NATS connection must be initialized during application startup
    and stored in app.state.

    A single connection is shared by the FastAPI process.
    """

    client = getattr(
        request.app.state,
        NATS_STATE_KEY,
        None,
    )

    if client is None:
        raise RuntimeError(
            "NATS client is not initialized"
        )

    if getattr(client, "is_closed", False):
        raise RuntimeError(
            "NATS client is closed"
        )

    return client
