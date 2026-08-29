"""Security audit events for authentication lifecycle tracking.

The event model is intentionally storage-agnostic.

Development / tests:
    SecurityEventLog()  — in-memory append-only list

Production:
    Do **not** rely on the in-memory log across workers — it is not durable
    and not shared. Prefer an outbox-backed sink that writes into the same
    DB transaction as auth state, then relays to PostgreSQL, Kafka, or SIEM.

Never put secrets in ``metadata`` (or any other field): passwords, raw
refresh tokens, JWTs, API keys, reset tokens, MFA secrets, OAuth client
secrets, or authorization codes. A security audit log that becomes a
credential warehouse is an expensive joke.

Swap the process singleton via ``configure_security_log`` for DI / tests.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, Sequence, runtime_checkable

__all__ = [
    "SecurityEventType",
    "SecurityOutcome",
    "SecurityEvent",
    "SecurityEventSink",
    "SecurityEventLog",
    "configure_security_log",
    "get_security_log",
    "emit",
]


class SecurityEventType(StrEnum):
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGIN_BLOCKED = "auth.login.blocked"

    LOGOUT = "auth.logout"

    PASSWORD_CHANGED = "auth.password.changed"
    PASSWORD_RESET_REQUESTED = "auth.password.reset_requested"
    PASSWORD_RESET_COMPLETED = "auth.password.reset_completed"
    PASSWORD_RESET_FAILED = "auth.password.reset_failed"

    MFA_ENABLED = "auth.mfa.enabled"
    MFA_DISABLED = "auth.mfa.disabled"
    MFA_FAILED = "auth.mfa.failed"
    MFA_CHALLENGE_CREATED = "auth.mfa.challenge_created"
    MFA_CHALLENGE_FAILED = "auth.mfa.challenge_failed"

    SESSION_CREATED = "auth.session.created"
    SESSION_REVOKED = "auth.session.revoked"
    SESSION_ROTATED = "auth.session.rotated"
    SESSION_REUSE_DETECTED = "auth.session.reuse_detected"

    API_KEY_CREATED = "auth.api_key.created"
    API_KEY_REVOKED = "auth.api_key.revoked"
    API_KEY_ROTATED = "auth.api_key.rotated"

    OAUTH_LINKED = "auth.oauth.linked"
    OAUTH_UNLINKED = "auth.oauth.unlinked"
    OAUTH_LOGIN = "auth.oauth.login"

    ACCOUNT_LOCKED = "auth.account.locked"
    ACCOUNT_CREATED = "auth.account.created"
    ACCOUNT_UPDATED = "auth.account.updated"
    ACCOUNT_SUSPENDED = "auth.account.suspended"
    ACCOUNT_DEACTIVATED = "auth.account.deactivated"
    ACCOUNT_DELETED = "auth.account.deleted"

    TOKEN_REFRESHED = "auth.token.refreshed"
    TOKEN_REUSE_DETECTED = "auth.token.reuse_detected"

    EMAIL_VERIFIED = "auth.email.verified"

    SCIM_USER_CREATED = "auth.scim.user_created"
    SCIM_USER_UPDATED = "auth.scim.user_updated"
    SCIM_USER_DEACTIVATED = "auth.scim.user_deactivated"

    PERMISSION_DENIED = "auth.permission.denied"


class SecurityOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SecurityEvent:
    """
    Immutable security audit event.

    actor_id:
        Principal that performed the operation.

    subject_id:
        Resource/user affected by the operation.

    org_id:
        Tenant scope.

    request_id:
        Correlation ID for tracing the request across services.

    metadata:
        Safe, non-secret contextual information only.
    """

    event_type: SecurityEventType

    actor_id: str | None = None
    subject_id: str | None = None
    org_id: str | None = None

    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None

    method: str | None = None

    outcome: SecurityOutcome = SecurityOutcome.SUCCESS

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    timestamp: float = field(
        default_factory=time.time
    )

    id: str = field(
        default_factory=lambda: (
            f"sec_{uuid.uuid4().hex}"
        )
    )


@runtime_checkable
class SecurityEventSink(Protocol):
    """Thin durable-backend contract — replace ``SecurityEventLog`` in prod."""

    def record(
        self,
        event_type: SecurityEventType,
        *,
        actor_id: str | None = None,
        subject_id: str | None = None,
        org_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        method: str | None = None,
        outcome: SecurityOutcome = SecurityOutcome.SUCCESS,
        metadata: dict[str, Any] | None = None,
    ) -> SecurityEvent: ...


class SecurityEventLog:
    """
    In-memory append-only security event store.

    Intended for development and tests only. Not multi-worker durable —
    production should use an outbox / Postgres / Kafka-backed
    ``SecurityEventSink``.
    """

    def __init__(
        self,
        *,
        max_events: int = 100_000,
    ) -> None:
        if max_events <= 0:
            raise ValueError(
                "max_events must be greater than zero"
            )

        self._events: list[SecurityEvent] = []
        self._max_events = max_events

    def record(
        self,
        event_type: SecurityEventType,
        *,
        actor_id: str | None = None,
        subject_id: str | None = None,
        org_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        method: str | None = None,
        outcome: SecurityOutcome = SecurityOutcome.SUCCESS,
        metadata: dict[str, Any] | None = None,
    ) -> SecurityEvent:
        event = SecurityEvent(
            event_type=event_type,
            actor_id=actor_id,
            subject_id=subject_id,
            org_id=org_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            method=method,
            outcome=outcome,
            metadata=dict(metadata or {}),
        )

        self._events.append(event)

        if len(self._events) > self._max_events:
            del self._events[
                : len(self._events) - self._max_events
            ]

        return event

    def query(
        self,
        *,
        event_type: SecurityEventType | None = None,
        actor_id: str | None = None,
        subject_id: str | None = None,
        org_id: str | None = None,
        outcome: SecurityOutcome | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 100,
    ) -> list[SecurityEvent]:
        if limit <= 0:
            return []

        events: Sequence[SecurityEvent] = self._events

        if event_type is not None:
            events = [
                event
                for event in events
                if event.event_type == event_type
            ]

        if actor_id is not None:
            events = [
                event
                for event in events
                if event.actor_id == actor_id
            ]

        if subject_id is not None:
            events = [
                event
                for event in events
                if event.subject_id == subject_id
            ]

        if org_id is not None:
            events = [
                event
                for event in events
                if event.org_id == org_id
            ]

        if outcome is not None:
            events = [
                event
                for event in events
                if event.outcome == outcome
            ]

        if since is not None:
            events = [
                event
                for event in events
                if event.timestamp >= since
            ]

        if until is not None:
            events = [
                event
                for event in events
                if event.timestamp <= until
            ]

        return list(events[-limit:])

    def count(
        self,
        *,
        event_type: SecurityEventType | None = None,
        actor_id: str | None = None,
        subject_id: str | None = None,
        org_id: str | None = None,
        since: float | None = None,
    ) -> int:
        return len(
            self.query(
                event_type=event_type,
                actor_id=actor_id,
                subject_id=subject_id,
                org_id=org_id,
                since=since,
                limit=self._max_events,
            )
        )

    def clear(self) -> None:
        """Test-only helper."""
        self._events.clear()


_log_instance: SecurityEventSink = SecurityEventLog()


def configure_security_log(log: SecurityEventSink) -> None:
    """Replace the process-local security event sink (DI / tests)."""
    global _log_instance
    _log_instance = log


def get_security_log() -> SecurityEventSink:
    return _log_instance


def emit(
    event_type: SecurityEventType,
    *,
    actor_id: str | None = None,
    subject_id: str | None = None,
    org_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    method: str | None = None,
    outcome: SecurityOutcome = SecurityOutcome.SUCCESS,
    metadata: dict[str, Any] | None = None,
) -> SecurityEvent:
    """Emit a security audit event via the configured sink."""

    return get_security_log().record(
        event_type,
        actor_id=actor_id,
        subject_id=subject_id,
        org_id=org_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        method=method,
        outcome=outcome,
        metadata=metadata,
    )
