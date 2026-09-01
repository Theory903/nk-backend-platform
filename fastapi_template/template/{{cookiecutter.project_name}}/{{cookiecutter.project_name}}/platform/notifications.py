"""Provider-neutral notification contracts with an in-memory local adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Notification:
    """A notification request with tenant and user scope."""

    user_id: str
    channel: str
    subject: str
    body: str
    org_id: str | None = None


class NotificationProvider(Protocol):
    async def send(self, notification: Notification) -> str:
        """Deliver and return a provider message ID."""


class InMemoryNotificationProvider:
    """Deterministic adapter for local development and tests."""

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    async def send(self, notification: Notification) -> str:
        if notification.channel not in {"email", "in_app", "sms", "push"}:
            raise ValueError(f"unsupported notification channel: {notification.channel}")
        self.sent.append(notification)
        return f"notification_{len(self.sent)}"


__all__ = ["InMemoryNotificationProvider", "Notification", "NotificationProvider"]
