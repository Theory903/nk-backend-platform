"""Deprecated compatibility shim for session management.

``SecureSessionStore`` is a deprecated alias for
``identity.session.SessionStore``. Prefer importing from ``session``
directly.

All session logic lives in ``identity.session`` — this module must not
grow a second implementation.
"""

from __future__ import annotations

from {{cookiecutter.project_name}}.identity.session import (
    DeviceInfo,
    Session,
    SessionRevocationReason,
    SessionStatus,
    SessionStore,
)

# Deprecated alias — same class, same behaviour.
SecureSessionStore = SessionStore

__all__ = [
    "DeviceInfo",
    "SecureSessionStore",
    "Session",
    "SessionRevocationReason",
    "SessionStatus",
    "SessionStore",
]
