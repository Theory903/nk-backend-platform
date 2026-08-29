from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from nats.aio.client import Client as NATS

from {{cookiecutter.project_name}}.settings import settings


NATS_STATE_KEY = "nats"


async def _maybe_await(value: Any) -> None:
    if hasattr(value, "__await__"):
        await value


async def init_nats(
    app: FastAPI,
) -> None:  # pragma: no cover
    """
    Create and connect the process-wide NATS client.

    One client is created per FastAPI process and reused by all requests.
    """

    existing = getattr(
        app.state,
        NATS_STATE_KEY,
        None,
    )

    if existing is not None:
        return

    client = NATS()

    servers = getattr(
        settings,
        "nats_servers",
        None,
    )
    if servers is None:
        servers = ["nats://localhost:4222"]

    try:
        await client.connect(
            servers=servers,
            name=getattr(
                settings,
                "app_name",
                "{{cookiecutter.project_name}}",
            ),
            connect_timeout=5,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
        )
    except Exception:
        # Do not leave a half-initialized client in app.state.
        try:
            close = getattr(client, "close", None)
            if callable(close):
                await _maybe_await(close())
        except Exception:
            pass
        raise

    setattr(
        app.state,
        NATS_STATE_KEY,
        client,
    )


async def shutdown_nats(
    app: FastAPI,
) -> None:  # pragma: no cover
    """
    Gracefully drain and close the NATS connection.

    No-op when the client was never initialized.
    """

    client: NATS | None = getattr(
        app.state,
        NATS_STATE_KEY,
        None,
    )

    if client is None:
        return

    try:
        if not getattr(client, "is_closed", False):
            drain = getattr(client, "drain", None)
            if callable(drain):
                await _maybe_await(drain())
    finally:
        if not getattr(client, "is_closed", False):
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    await _maybe_await(close())
                except Exception:
                    pass

        try:
            delattr(
                app.state,
                NATS_STATE_KEY,
            )
        except AttributeError:
            pass
