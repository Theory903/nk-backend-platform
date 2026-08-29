"""
Append-only audit events.

Audit logs are security-sensitive records and should be treated as immutable.

Architecture:

    Application
        │
        ▼
    AuditLogger
        │
        ├── validation / normalization
        │
        └── AuditSink
              │
              ├── InMemoryAuditSink  (dev/test)
              │
              └── SQL/Mongo sink      (production)

Audit events intentionally remain separate from Prometheus metrics and
ordinary application logs.

Do not put secrets, passwords, tokens, API keys, or raw credentials into
audit details.

Relation to ``identity.security_events``:
    Keep them separate. ``platform.audit`` is broader platform
    accountability (CRUD, admin, data lifecycle, integrations).
    ``SecurityEventLog`` stays auth/identity-specific. A bridge that
    mirrors selected security events into the audit sink can land later;
    do not merge the two stores.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AuditEvent",
    "AuditQuery",
    "AuditSink",
    "InMemoryAuditSink",
    "AuditLogger",
    "configure_audit_logger",
    "get_audit_log",
    "emit_audit",
    "utc_now",
    "generate_audit_id",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """
    Return a timezone-aware UTC timestamp.
    """
    return datetime.now(timezone.utc)


def generate_audit_id() -> str:
    """
    Generate a globally unique audit event ID.
    """
    return f"aud_{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Audit event
# ---------------------------------------------------------------------------


class AuditEvent(BaseModel):
    """
    Immutable security/audit event.

    Audit events should describe what happened, who caused it, and which
    resource/tenant was affected.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    id: str = Field(
        default_factory=generate_audit_id,
    )

    actor_id: str | None = None

    action: str

    resource: str | None = None

    resource_id: str | None = None

    org_id: str | None = None

    outcome: str = "success"

    request_id: str | None = None

    trace_id: str | None = None

    ip_address: str | None = None

    user_agent: str | None = None

    detail: dict[str, Any] = Field(
        default_factory=dict,
    )

    created_at: datetime = Field(
        default_factory=utc_now,
    )

    sequence: int | None = None

    def sanitized(self) -> AuditEvent:
        """
        Return an event with obviously sensitive fields removed.

        This is intentionally conservative. Applications should still avoid
        putting secrets into detail in the first place.
        """
        forbidden = {
            "password",
            "passwd",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "api_key",
            "authorization",
            "cookie",
            "credential",
            "private_key",
        }

        clean_detail = {
            key: value
            for key, value in self.detail.items()
            if key.lower() not in forbidden
        }

        return self.model_copy(
            update={
                "detail": clean_detail,
            }
        )


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class AuditQuery(BaseModel):
    """
    Query parameters for audit retrieval.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    org_id: str | None = None

    actor_id: str | None = None

    action: str | None = None

    resource: str | None = None

    resource_id: str | None = None

    outcome: str | None = None

    since: datetime | None = None

    until: datetime | None = None

    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
    )

    cursor: str | None = None


# ---------------------------------------------------------------------------
# Audit sink
# ---------------------------------------------------------------------------


class AuditSink(ABC):
    """
    Storage abstraction for audit events.

    Production implementations should provide durable append-only storage.
    """

    @abstractmethod
    async def append(
        self,
        event: AuditEvent,
    ) -> AuditEvent:
        raise NotImplementedError

    @abstractmethod
    async def get(
        self,
        event_id: str,
    ) -> AuditEvent | None:
        raise NotImplementedError

    @abstractmethod
    async def query(
        self,
        query: AuditQuery,
    ) -> list[AuditEvent]:
        raise NotImplementedError

    @abstractmethod
    async def count(
        self,
        query: AuditQuery,
    ) -> int:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class InMemoryAuditSink(AuditSink):
    """
    Development/test implementation.

    This is NOT durable and should not be used for production audit storage.
    """

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._by_id: dict[str, AuditEvent] = {}
        self._sequence = 0

    async def append(
        self,
        event: AuditEvent,
    ) -> AuditEvent:
        """
        Append an event exactly once within this process.
        """
        if event.id in self._by_id:
            raise ValueError(
                f"audit event already exists: {event.id}"
            )

        self._sequence += 1

        stored = event.model_copy(
            update={
                "sequence": self._sequence,
            }
        )

        self._events.append(stored)
        self._by_id[stored.id] = stored

        return stored

    async def get(
        self,
        event_id: str,
    ) -> AuditEvent | None:
        return self._by_id.get(event_id)

    async def query(
        self,
        query: AuditQuery,
    ) -> list[AuditEvent]:
        result = self._events

        if query.org_id is not None:
            result = [
                event
                for event in result
                if event.org_id == query.org_id
            ]

        if query.actor_id is not None:
            result = [
                event
                for event in result
                if event.actor_id == query.actor_id
            ]

        if query.action is not None:
            result = [
                event
                for event in result
                if event.action == query.action
            ]

        if query.resource is not None:
            result = [
                event
                for event in result
                if event.resource == query.resource
            ]

        if query.resource_id is not None:
            result = [
                event
                for event in result
                if event.resource_id == query.resource_id
            ]

        if query.outcome is not None:
            result = [
                event
                for event in result
                if event.outcome == query.outcome
            ]

        if query.since is not None:
            result = [
                event
                for event in result
                if event.created_at >= query.since
            ]

        if query.until is not None:
            result = [
                event
                for event in result
                if event.created_at <= query.until
            ]

        # Newest first.
        result = sorted(
            result,
            key=lambda event: (
                event.created_at,
                event.sequence or 0,
                event.id,
            ),
            reverse=True,
        )

        if query.cursor:
            result = self._after_cursor(
                result,
                query.cursor,
            )

        return result[: query.limit]

    async def count(
        self,
        query: AuditQuery,
    ) -> int:
        # Avoid applying pagination for count.
        unrestricted = query.model_copy(
            update={
                "limit": 1000,
                "cursor": None,
            }
        )

        result = await self.query(unrestricted)

        return len(result)

    @staticmethod
    def _after_cursor(
        events: Sequence[AuditEvent],
        cursor: str,
    ) -> list[AuditEvent]:
        """
        Simple in-memory cursor.

        Production storage should use a database-native keyset cursor.
        """
        try:
            cursor_time, cursor_id = cursor.split(
                ":",
                1,
            )
        except ValueError:
            return list(events)

        filtered: list[AuditEvent] = []

        for event in events:
            timestamp = event.created_at.timestamp()

            if timestamp < float(cursor_time) or (
                timestamp == float(cursor_time)
                and event.id < cursor_id
            ):
                filtered.append(event)

        return filtered


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------


class AuditLogger:
    """
    Application-facing audit logger.

    Application code depends on this class rather than a concrete database.
    """

    def __init__(
        self,
        sink: AuditSink,
    ) -> None:
        self.sink = sink

    async def record(
        self,
        *,
        action: str,
        actor_id: str | None = None,
        resource: str | None = None,
        resource_id: str | None = None,
        org_id: str | None = None,
        outcome: str = "success",
        request_id: str | None = None,
        trace_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """
        Record one immutable audit event.
        """
        if not action.strip():
            raise ValueError(
                "audit action cannot be empty"
            )

        event = AuditEvent(
            action=action,
            actor_id=actor_id,
            resource=resource,
            resource_id=resource_id,
            org_id=org_id,
            outcome=outcome,
            request_id=request_id,
            trace_id=trace_id,
            ip_address=ip_address,
            user_agent=user_agent,
            detail=dict(detail or {}),
        ).sanitized()

        return await self.sink.append(event)

    async def query(
        self,
        query: AuditQuery,
    ) -> list[AuditEvent]:
        return await self.sink.query(query)

    async def get(
        self,
        event_id: str,
    ) -> AuditEvent | None:
        return await self.sink.get(event_id)

    async def count(
        self,
        query: AuditQuery,
    ) -> int:
        return await self.sink.count(query)


# ---------------------------------------------------------------------------
# Compatibility / DI API
# ---------------------------------------------------------------------------


_default_sink: AuditSink = InMemoryAuditSink()

_default_audit_logger = AuditLogger(
    _default_sink,
)


def configure_audit_logger(sink: AuditSink) -> AuditLogger:
    """
    Replace the process-wide audit logger sink (DI / tests).

    Prefer injecting ``AuditLogger`` explicitly in application code.
    """
    global _default_sink, _default_audit_logger
    _default_sink = sink
    _default_audit_logger = AuditLogger(sink)
    return _default_audit_logger


def get_audit_log() -> AuditLogger:
    """
    Return the process-wide audit logger.
    """
    return _default_audit_logger


async def emit_audit(
    action: str,
    *,
    actor_id: str | None = None,
    resource: str | None = None,
    resource_id: str | None = None,
    org_id: str | None = None,
    outcome: str = "success",
    request_id: str | None = None,
    trace_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    """
    Convenience function for emitting an audit event.
    """
    return await get_audit_log().record(
        action=action,
        actor_id=actor_id,
        resource=resource,
        resource_id=resource_id,
        org_id=org_id,
        outcome=outcome,
        request_id=request_id,
        trace_id=trace_id,
        ip_address=ip_address,
        user_agent=user_agent,
        detail=detail,
    )
