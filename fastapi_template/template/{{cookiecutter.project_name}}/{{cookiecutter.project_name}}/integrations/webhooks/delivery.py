"""Reliable signed webhook delivery with bounded retries."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import httpx

from .signer import WebhookSigner


@dataclass(frozen=True, slots=True)
class WebhookEndpoint:
    endpoint_id: str
    url: str
    secret: str
    enabled: bool = True


class WebhookDeliveryStore(Protocol):
    async def mark_delivered(self, endpoint_id: str, event_id: str) -> None:
        """Record a successful delivery idempotently."""


class WebhookDelivery:
    """HTTP delivery service with timeout, backoff, and signed payloads."""

    def __init__(self, *, timeout_s: float = 10.0, max_attempts: int = 3) -> None:
        if timeout_s <= 0 or max_attempts <= 0:
            raise ValueError("timeout_s and max_attempts must be positive")
        self.timeout_s = timeout_s
        self.max_attempts = max_attempts

    async def send(self, endpoint: WebhookEndpoint, event_id: str, payload: bytes) -> int:
        """Send once with bounded exponential backoff; return HTTP status."""
        if not endpoint.enabled:
            raise ValueError("webhook endpoint is disabled")
        signed = WebhookSigner(endpoint.secret).sign(payload, webhook_id=event_id)
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    response = await client.post(endpoint.url, content=signed.body, headers=signed.headers)
                response.raise_for_status()
                return response.status_code
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    await asyncio.sleep(0.25 * (2**attempt))
        raise RuntimeError(f"webhook delivery failed after {self.max_attempts} attempts") from last_error


__all__ = ["WebhookDelivery", "WebhookDeliveryStore", "WebhookEndpoint"]
