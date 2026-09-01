"""Server-side session management.

Single source of truth for browser / opaque sessions.

Development uses in-memory storage. Production should replace the backing
store with Redis while preserving the public ``SessionStore`` interface.

Sessions are opaque identifiers. Authentication state remains server-side.

``SecureSessionStore`` in ``session_lifecycle`` is a deprecated alias —
import ``SessionStore`` from this module.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SessionStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    ROTATED = "rotated"


class SessionRevocationReason(StrEnum):
    LOGOUT = "logout"
    ROTATED = "rotated"
    EXPIRED = "expired"
    ACCOUNT_DISABLED = "account_disabled"
    ADMIN = "admin"
    SECURITY = "security"
    CONCURRENT_LIMIT = "concurrent_limit"


@dataclass
class DeviceInfo:
    """Client device metadata for audit and multi-device listing.

    ``ip_address`` / ``user_agent`` are observational only — never bind
    authentication to a fixed IP.
    """

    device_id: str
    user_agent: str
    ip_address: str

    created_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    principal_id: str

    data: dict[str, Any] = field(default_factory=dict)

    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    expires_at: float = 0.0
    idle_expires_at: float = 0.0

    status: SessionStatus = SessionStatus.ACTIVE

    rotated_from: str | None = None
    rotated_to: str | None = None

    revoked_at: float | None = None
    revoked_reason: SessionRevocationReason | None = None

    user_agent: str = ""
    ip_address: str = ""

    device_id: str = field(default_factory=lambda: secrets.token_hex(16))

    @property
    def is_active(self) -> bool:
        return self.status is SessionStatus.ACTIVE

    @property
    def device(self) -> DeviceInfo:
        """Compatibility view matching the former nested DeviceInfo shape."""
        return DeviceInfo(
            device_id=self.device_id,
            user_agent=self.user_agent,
            ip_address=self.ip_address,
            created_at=self.created_at,
            last_seen_at=self.last_activity,
        )


class SessionStore:
    """
    Server-side session manager.

    The session ID is the only value that should normally reach the client.

    ``create`` returns an opaque ``str`` id. ``get`` returns a dict for
    ``deps`` compatibility. ``get_session`` returns the ``Session`` object.
    """

    def __init__(
        self,
        default_ttl_s: int | None = None,
        *,
        max_lifetime_s: int | None = None,
        idle_timeout_s: int | None = 3600,
        max_concurrent_sessions: int = 5,
    ) -> None:
        if default_ttl_s is not None and max_lifetime_s is not None:
            raise ValueError(
                "pass only one of default_ttl_s or max_lifetime_s"
            )

        lifetime = (
            default_ttl_s
            if default_ttl_s is not None
            else max_lifetime_s
            if max_lifetime_s is not None
            else 86400
        )

        if lifetime <= 0:
            which = (
                "max_lifetime_s"
                if max_lifetime_s is not None
                else "default_ttl_s"
            )
            raise ValueError(f"{which} must be positive")

        if idle_timeout_s is not None and idle_timeout_s <= 0:
            raise ValueError("idle_timeout_s must be positive")

        if max_concurrent_sessions <= 0:
            raise ValueError(
                "max_concurrent_sessions must be positive"
            )

        self._ttl = lifetime
        self.default_ttl_s = lifetime
        self.max_lifetime_s = lifetime

        self._idle_timeout = idle_timeout_s
        self.idle_timeout_s = idle_timeout_s

        self._max_concurrent = max_concurrent_sessions
        self.max_concurrent = max_concurrent_sessions

        self._sessions: dict[str, Session] = {}

    def create(
        self,
        principal_id: str,
        data: dict[str, Any] | None = None,
        *,
        ttl_s: int | None = None,
        user_agent: str = "",
        ip_address: str = "",
        device_id: str | None = None,
    ) -> str:
        """
        Create a new server-side session.

        Returns only the opaque session identifier.
        """
        if not principal_id:
            raise ValueError("principal_id is required")

        lifetime = self._ttl if ttl_s is None else ttl_s

        if lifetime <= 0:
            raise ValueError("ttl_s must be positive")

        self._enforce_concurrent_limit(principal_id)

        now = time.time()
        session_id = secrets.token_urlsafe(32)

        idle_expiry = (
            now + self._idle_timeout
            if self._idle_timeout is not None
            else now + lifetime
        )

        expires_at = now + lifetime

        session = Session(
            session_id=session_id,
            principal_id=principal_id,
            data=dict(data or {}),
            created_at=now,
            last_activity=now,
            expires_at=expires_at,
            idle_expires_at=min(idle_expiry, expires_at),
            user_agent=user_agent,
            ip_address=ip_address,
            device_id=device_id or secrets.token_hex(16),
        )

        self._sessions[session_id] = session
        return session_id

    def get(
        self,
        session_id: str,
        *,
        touch: bool = True,
    ) -> dict[str, Any] | None:
        """
        Resolve a session.

        Returns a compatibility dictionary containing the principal and
        session metadata, or None if the session is invalid.
        """
        session = self.get_session(session_id, touch=touch)
        if session is None:
            return None
        return self._serialize(session)

    def get_session(
        self,
        session_id: str,
        *,
        touch: bool = True,
    ) -> Session | None:
        session = self._sessions.get(session_id)

        if session is None:
            return None

        if not session.is_active:
            return None

        now = time.time()

        if now >= session.expires_at:
            self._expire(session)
            return None

        if now >= session.idle_expires_at:
            self._expire(session)
            return None

        if touch:
            session.last_activity = now
            if self._idle_timeout is not None:
                session.idle_expires_at = min(
                    now + self._idle_timeout,
                    session.expires_at,
                )

        return session

    def rotate(
        self,
        session_id: str,
        *,
        user_agent: str = "",
        ip_address: str = "",
    ) -> str | None:
        """
        Rotate the session identifier.

        The original absolute expiry is preserved. Rotation therefore cannot
        extend the maximum lifetime of the authentication session. The old
        record is kept as ``ROTATED`` (not deleted) for reuse detection.
        """
        old = self.get_session(session_id, touch=False)

        if old is None:
            return None

        now = time.time()

        if now >= old.expires_at:
            self._expire(old)
            return None

        self._enforce_concurrent_limit(
            old.principal_id,
            exclude_session=session_id,
        )

        new_session_id = secrets.token_urlsafe(32)

        idle_expiry = (
            now + self._idle_timeout
            if self._idle_timeout is not None
            else old.expires_at
        )

        new_session = Session(
            session_id=new_session_id,
            principal_id=old.principal_id,
            data=dict(old.data),
            created_at=now,
            last_activity=now,
            expires_at=old.expires_at,
            idle_expires_at=min(idle_expiry, old.expires_at),
            rotated_from=old.session_id,
            user_agent=user_agent or old.user_agent,
            ip_address=ip_address or old.ip_address,
            device_id=old.device_id,
        )

        old.rotated_to = new_session_id
        self._sessions[new_session_id] = new_session

        self._revoke(
            old,
            SessionRevocationReason.ROTATED,
            status=SessionStatus.ROTATED,
        )

        return new_session_id

    def revoke(
        self,
        session_id: str,
        *,
        reason: SessionRevocationReason = SessionRevocationReason.LOGOUT,
    ) -> bool:
        session = self._sessions.get(session_id)

        if session is None:
            return False

        if not session.is_active:
            return False

        self._revoke(session, reason)
        return True

    def revoke_all_for_principal(
        self,
        principal_id: str,
        *,
        except_session: str | None = None,
        reason: SessionRevocationReason = (
            SessionRevocationReason.ACCOUNT_DISABLED
        ),
    ) -> int:
        """Revoke every active session for a principal."""
        count = 0

        for sid, session in self._sessions.items():
            if sid == except_session:
                continue
            if session.principal_id != principal_id:
                continue
            if not session.is_active:
                continue

            self._revoke(session, reason)
            count += 1

        return count

    def list_for_principal(
        self,
        principal_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[Session]:
        sessions = [
            session
            for session in self._sessions.values()
            if session.principal_id == principal_id
        ]

        now = time.time()
        sessions = [
            session
            for session in sessions
            if session.expires_at > now and session.idle_expires_at > now
        ]
        if not include_inactive:
            sessions = [s for s in sessions if s.is_active]

        sessions.sort(
            key=lambda s: (s.last_activity, s.session_id),
            reverse=True,
        )
        return sessions

    def list_sessions(
        self,
        principal_id: str,
        *,
        include_revoked: bool = False,
    ) -> list[Session]:
        """Alias for ``list_for_principal`` (SecureSessionStore name)."""
        return self.list_for_principal(
            principal_id,
            include_inactive=include_revoked,
        )

    def list_devices(
        self,
        principal_id: str,
    ) -> list[dict[str, Any]]:
        """Return active device/session information."""
        return [
            {
                "device_id": session.device_id,
                "session_id": session.session_id,
                "user_agent": session.user_agent,
                "ip_address": session.ip_address,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
            }
            for session in self.list_for_principal(principal_id)
        ]

    def update_data(
        self,
        session_id: str,
        updates: dict[str, Any],
    ) -> bool:
        session = self.get_session(session_id, touch=False)
        if session is None:
            return False
        session.data.update(updates)
        return True

    def delete_data(
        self,
        session_id: str,
        *keys: str,
    ) -> bool:
        session = self.get_session(session_id, touch=False)
        if session is None:
            return False
        for key in keys:
            session.data.pop(key, None)
        return True

    def cleanup_expired(self) -> int:
        """
        Remove inactive or expired sessions from memory.

        Housekeeping only — expiry validation never depends on this.
        """
        now = time.time()
        removed = 0

        for session_id, session in list(self._sessions.items()):
            if session.is_active and now < session.expires_at and now < session.idle_expires_at:
                continue
            del self._sessions[session_id]
            removed += 1

        return removed

    def _enforce_concurrent_limit(
        self,
        principal_id: str,
        *,
        exclude_session: str | None = None,
    ) -> None:
        active = [
            session
            for session in self._sessions.values()
            if (
                session.principal_id == principal_id
                and session.is_active
                and session.session_id != exclude_session
            )
        ]

        if len(active) < self._max_concurrent:
            return

        active.sort(key=lambda session: session.last_activity)
        evict_count = len(active) - self._max_concurrent + 1

        for session in active[:evict_count]:
            self._revoke(
                session,
                SessionRevocationReason.CONCURRENT_LIMIT,
            )

    @staticmethod
    def _revoke(
        session: Session,
        reason: SessionRevocationReason,
        *,
        status: SessionStatus = SessionStatus.REVOKED,
    ) -> None:
        if not session.is_active:
            return
        session.status = status
        session.revoked_at = time.time()
        session.revoked_reason = reason

    @staticmethod
    def _expire(session: Session) -> None:
        if not session.is_active:
            return
        session.status = SessionStatus.EXPIRED
        session.revoked_at = time.time()
        session.revoked_reason = SessionRevocationReason.EXPIRED

    @staticmethod
    def _serialize(session: Session) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "principal_id": session.principal_id,
            "data": dict(session.data),
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "expires_at": session.expires_at,
            "idle_expires_at": session.idle_expires_at,
            "device_id": session.device_id,
            "user_agent": session.user_agent,
            "ip_address": session.ip_address,
            "status": session.status.value,
        }


class RedisSessionStore(SessionStore):
    """Shared opaque-session store for deployments with Redis."""

    def __init__(
        self,
        redis_client: Any,
        *,
        prefix: str = "nk:session",
        secret: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not secret:
            raise ValueError("session digest secret is required")
        self._redis = redis_client
        self._prefix = prefix.rstrip(":")
        self._secret = secret.encode("utf-8")

    def _key(self, session_id: str) -> str:
        # Callers pass the internal digest; external IDs are hashed by
        # _lookup_digest before reaching this method.
        return f"{self._prefix}:{session_id}"

    def _digest(self, session_id: str) -> str:
        return hmac.new(
            self._secret,
            session_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _lookup_digest(self, session_id: str) -> str:
        # A digest is an internal storage key, never an accepted bearer
        # credential. Always hash values supplied at the API boundary.
        return self._digest(session_id)

    def _index_key(self) -> str:
        return f"{self._prefix}:index"

    def _session_lock(self, session_id: str) -> Any:
        digest = self._lookup_digest(session_id)
        return self._redis.lock(
            f"{self._prefix}:mutate:{digest}",
            timeout=30,
            blocking_timeout=5,
        )

    def _digest_lock(self, digest: str) -> Any:
        return self._redis.lock(
            f"{self._prefix}:mutate:{digest}",
            timeout=30,
            blocking_timeout=5,
        )

    def create(self, principal_id: str, data: dict[str, Any] | None = None, **kwargs: Any) -> str:
        session_id = super().create(principal_id, data, **kwargs)
        session = super().get_session(session_id, touch=False)
        if session is not None:
            self._persist(session)
            self._enforce_durable_limit(principal_id)
        return session_id

    def get_session(self, session_id: str, *, touch: bool = True) -> Session | None:
        digest = self._lookup_digest(session_id)
        raw = self._redis.get(self._key(digest))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        session = self._decode(
            json.loads(raw),
            session_id=session_id,
        )
        now = time.time()
        if not session.is_active or now >= session.expires_at or now >= session.idle_expires_at:
            self._redis.delete(self._key(digest))
            self._redis.srem(self._index_key(), digest)
            return None
        if touch:
            session.last_activity = now
            if self.idle_timeout_s is not None:
                session.idle_expires_at = min(
                    now + self.idle_timeout_s,
                    session.expires_at,
                )
            # Do not persist a read-modify-write touch. A concurrent revoke
            # or rotation must never be resurrected by a stale authentication
            # read; durable lifecycle mutations use explicit locks.
        return session

    def revoke(self, session_id: str, *, reason: SessionRevocationReason = SessionRevocationReason.LOGOUT) -> bool:
        lock = self._session_lock(session_id)
        if not lock.acquire():
            return False
        try:
            session = self.get_session(session_id, touch=False)
            if session is None or not session.is_active:
                return False
            self._revoke(session, reason)
            self._persist(session)
            return True
        finally:
            lock.release()

    def list_for_principal(
        self,
        principal_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[Session]:
        sessions: list[Session] = []
        for raw_digest in self._redis.smembers(self._index_key()):
            digest = (
                raw_digest.decode("utf-8")
                if isinstance(raw_digest, bytes)
                else str(raw_digest)
            )
            raw = self._redis.get(self._key(digest))
            if raw is None:
                self._redis.srem(self._index_key(), digest)
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            session = self._decode(
                json.loads(raw),
                session_id="",
            )
            setattr(session, "_storage_digest", digest)
            if (
                session.expires_at <= time.time()
                or session.idle_expires_at <= time.time()
            ):
                self._redis.delete(self._key(digest))
                self._redis.srem(self._index_key(), digest)
                continue
            if session.principal_id == principal_id and (
                include_inactive or session.is_active
            ):
                sessions.append(session)
        sessions.sort(key=lambda item: (item.last_activity, item.session_id), reverse=True)
        return sessions

    def _enforce_durable_limit(self, principal_id: str) -> None:
        # Redis' list/read/revoke sequence must be serialized across API
        # instances. Without the lock, concurrent logins can both observe the
        # same pre-limit state and leave too many active sessions.
        lock_name = hashlib.sha256(
            principal_id.encode("utf-8"),
        ).hexdigest()
        lock = self._redis.lock(
            f"{self._prefix}:limit:{lock_name}",
            timeout=10,
            blocking_timeout=5,
        )
        if not lock.acquire():
            raise RuntimeError(
                "could not acquire distributed session-limit lock",
            )
        try:
            active = self.list_for_principal(principal_id)
            for session in active[self.max_concurrent :]:
                self._revoke_digest(
                    getattr(session, "_storage_digest"),
                    reason=SessionRevocationReason.CONCURRENT_LIMIT,
                )
        finally:
            lock.release()

    def revoke_all_for_principal(
        self,
        principal_id: str,
        *,
        except_session: str | None = None,
        reason: SessionRevocationReason = SessionRevocationReason.ACCOUNT_DISABLED,
    ) -> int:
        count = 0
        for session in self.list_for_principal(principal_id):
            if (
                except_session is not None
                and getattr(session, "_storage_digest")
                == self._lookup_digest(except_session)
            ):
                continue
            if self._revoke_digest(
                getattr(session, "_storage_digest"),
                reason=reason,
            ):
                count += 1
        return count

    def _revoke_digest(
        self,
        digest: str,
        *,
        reason: SessionRevocationReason,
    ) -> bool:
        lock = self._digest_lock(digest)
        if not lock.acquire():
            return False
        try:
            raw = self._redis.get(self._key(digest))
            if raw is None:
                return False
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            session = self._decode(json.loads(raw), session_id="")
            if not session.is_active:
                return False
            self._revoke(session, reason)
            ttl = max(1, int(session.expires_at - time.time()))
            self._redis.set(
                self._key(digest),
                json.dumps(self._encode(session)),
                ex=ttl,
            )
            return True
        finally:
            lock.release()

    def rotate(
        self,
        session_id: str,
        *,
        user_agent: str = "",
        ip_address: str = "",
    ) -> str | None:
        lock = self._session_lock(session_id)
        if not lock.acquire():
            return None
        try:
            old = self.get_session(session_id, touch=False)
            if old is None or time.time() >= old.expires_at:
                return None
            now = time.time()
            new_session_id = secrets.token_urlsafe(32)
            idle_expiry = (
                now + self.idle_timeout_s
                if self.idle_timeout_s is not None
                else old.expires_at
            )
            new_session = Session(
                session_id=new_session_id,
                principal_id=old.principal_id,
                data=dict(old.data),
                created_at=now,
                last_activity=now,
                expires_at=old.expires_at,
                idle_expires_at=min(idle_expiry, old.expires_at),
                rotated_from=self._lookup_digest(old.session_id),
                user_agent=user_agent or old.user_agent,
                ip_address=ip_address or old.ip_address,
                device_id=old.device_id,
            )
            old.rotated_to = self._lookup_digest(new_session_id)
            self._revoke(old, SessionRevocationReason.ROTATED, status=SessionStatus.ROTATED)
            self._persist(old)
            self._persist(new_session)
            return new_session_id
        finally:
            lock.release()

    def update_data(self, session_id: str, updates: dict[str, Any]) -> bool:
        lock = self._session_lock(session_id)
        if not lock.acquire():
            return False
        try:
            session = self.get_session(session_id, touch=False)
            if session is None:
                return False
            session.data.update(updates)
            self._persist(session)
            return True
        finally:
            lock.release()

    def delete_data(self, session_id: str, *keys: str) -> bool:
        lock = self._session_lock(session_id)
        if not lock.acquire():
            return False
        try:
            session = self.get_session(session_id, touch=False)
            if session is None:
                return False
            for key in keys:
                session.data.pop(key, None)
            self._persist(session)
            return True
        finally:
            lock.release()

    def _persist(self, session: Session) -> None:
        ttl = max(1, int(session.expires_at - time.time()))
        digest = self._lookup_digest(session.session_id)
        self._redis.set(self._key(digest), json.dumps(self._encode(session)), ex=ttl)
        self._redis.sadd(
            self._index_key(),
            self._lookup_digest(session.session_id),
        )

    def _encode(self, session: Session) -> dict[str, Any]:
        data = SessionStore._serialize(session)
        data.pop("session_id", None)
        data.update(
            status=session.status.value,
            revoked_reason=session.revoked_reason.value if session.revoked_reason else None,
            rotated_from=session.rotated_from,
            rotated_to=session.rotated_to,
        )
        return data

    @staticmethod
    def _decode(
        data: dict[str, Any],
        *,
        session_id: str,
    ) -> Session:
        return Session(
            session_id=session_id,
            principal_id=str(data["principal_id"]),
            data=dict(data.get("data") or {}),
            created_at=float(data.get("created_at", time.time())),
            last_activity=float(data.get("last_activity", time.time())),
            expires_at=float(data["expires_at"]),
            idle_expires_at=float(data["idle_expires_at"]),
            status=SessionStatus(str(data.get("status", SessionStatus.ACTIVE.value))),
            rotated_from=data.get("rotated_from"),
            rotated_to=data.get("rotated_to"),
            revoked_at=data.get("revoked_at"),
            revoked_reason=(
                SessionRevocationReason(str(data["revoked_reason"]))
                if data.get("revoked_reason")
                else None
            ),
            user_agent=str(data.get("user_agent", "")),
            ip_address=str(data.get("ip_address", "")),
            device_id=str(data.get("device_id", "")),
        )


__all__ = [
    "DeviceInfo",
    "Session",
    "SessionRevocationReason",
    "SessionStatus",
    "SessionStore",
    "RedisSessionStore",
]
