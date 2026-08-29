"""Production-grade idempotency storage and request fingerprinting.

Semantics:

    same key + same fingerprint
        -> replay cached response

    same key + different fingerprint
        -> conflict

    new key
        -> acquire execution lease and execute

    expired key
        -> eligible for a new execution

The store abstraction is intentionally synchronous here. A Redis-backed
implementation can provide atomic SET NX / Lua operations without changing
the application-facing semantics.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Final


DEFAULT_TTL_S: Final[float] = 24 * 60 * 60
DEFAULT_LOCK_TTL_S: Final[float] = 60.0
MAX_KEY_LENGTH: Final[int] = 255


class IdempotencyError(RuntimeError):
    """Base idempotency error."""


class IdempotencyConflict(IdempotencyError):
    """The same idempotency key was used for a different request."""


class IdempotencyInProgress(IdempotencyError):
    """Another request currently owns the execution lease."""


class InvalidIdempotencyKey(IdempotencyError):
    """The supplied idempotency key is invalid."""


@dataclass(frozen=True, slots=True)
class CachedResponse:
    """Persisted response associated with an idempotency key."""

    status_code: int
    body: bytes
    content_type: str
    fingerprint: str
    created_at: float
    expires_at: float


class IdempotencyStore(ABC):
    """
    Storage contract for idempotency.

    Production implementations should make acquire_lock atomic across
    processes and hosts.
    """

    @abstractmethod
    def get(
        self,
        key: str,
    ) -> CachedResponse | None:
        """Return an unexpired cached response."""

    @abstractmethod
    def set(
        self,
        key: str,
        response: CachedResponse,
        *,
        ttl_s: float,
    ) -> None:
        """Store a response."""

    @abstractmethod
    def acquire_lock(
        self,
        key: str,
        *,
        ttl_s: float,
        owner: str,
    ) -> bool:
        """Atomically acquire an execution lease."""

    @abstractmethod
    def release_lock(
        self,
        key: str,
        *,
        owner: str,
    ) -> None:
        """Release a lease owned by the caller."""

    @abstractmethod
    def clear(
        self,
        key: str,
    ) -> None:
        """Remove cached response and execution state."""


@dataclass(slots=True)
class _Lock:
    owner: str
    expires_at: float


class InMemoryIdempotencyStore(IdempotencyStore):
    """
    Thread-safe in-memory implementation.

    Suitable for tests and single-process development only.

    It must NOT be used when multiple application workers/replicas share
    traffic.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._responses: dict[
            str,
            CachedResponse,
        ] = {}
        self._locks: dict[
            str,
            _Lock,
        ] = {}
        self._lock = RLock()

    def get(
        self,
        key: str,
    ) -> CachedResponse | None:
        now = self._clock()

        with self._lock:
            response = self._responses.get(key)

            if response is None:
                return None

            if response.expires_at <= now:
                self._responses.pop(
                    key,
                    None,
                )
                return None

            return response

    def set(
        self,
        key: str,
        response: CachedResponse,
        *,
        ttl_s: float,
    ) -> None:
        if ttl_s <= 0:
            raise ValueError(
                "ttl_s must be greater than zero"
            )

        now = self._clock()

        with self._lock:
            self._responses[key] = CachedResponse(
                status_code=response.status_code,
                body=response.body,
                content_type=response.content_type,
                fingerprint=response.fingerprint,
                created_at=response.created_at,
                expires_at=now + ttl_s,
            )

    def acquire_lock(
        self,
        key: str,
        *,
        ttl_s: float,
        owner: str,
    ) -> bool:
        if ttl_s <= 0:
            raise ValueError(
                "lock ttl_s must be greater than zero"
            )

        if not owner:
            raise ValueError(
                "lock owner must not be empty"
            )

        now = self._clock()

        with self._lock:
            current = self._locks.get(key)

            if (
                current is not None
                and current.expires_at > now
            ):
                return False

            self._locks[key] = _Lock(
                owner=owner,
                expires_at=now + ttl_s,
            )

            return True

    def release_lock(
        self,
        key: str,
        *,
        owner: str,
    ) -> None:
        with self._lock:
            current = self._locks.get(key)

            if current is None:
                return

            # Never allow one execution to release another execution's lease.
            if hmac.compare_digest(
                current.owner,
                owner,
            ):
                self._locks.pop(
                    key,
                    None,
                )

    def clear(
        self,
        key: str,
    ) -> None:
        with self._lock:
            self._responses.pop(
                key,
                None,
            )
            self._locks.pop(
                key,
                None,
            )

    def cleanup_expired(self) -> int:
        """Remove expired entries. Useful for tests/dev maintenance."""

        now = self._clock()
        removed = 0

        with self._lock:
            expired_responses = [
                key
                for key, response in self._responses.items()
                if response.expires_at <= now
            ]

            expired_locks = [
                key
                for key, lock in self._locks.items()
                if lock.expires_at <= now
            ]

            for key in expired_responses:
                self._responses.pop(
                    key,
                    None,
                )
                removed += 1

            for key in expired_locks:
                self._locks.pop(
                    key,
                    None,
                )
                removed += 1

        return removed


def validate_idempotency_key(
    key: str,
) -> str:
    """Validate and normalize an idempotency key."""

    if not isinstance(key, str):
        raise InvalidIdempotencyKey(
            "idempotency key must be a string"
        )

    key = key.strip()

    if not key:
        raise InvalidIdempotencyKey(
            "idempotency key must not be empty"
        )

    if len(key) > MAX_KEY_LENGTH:
        raise InvalidIdempotencyKey(
            f"idempotency key exceeds {MAX_KEY_LENGTH} characters"
        )

    return key


def compute_fingerprint(
    method: str,
    path: str,
    body: bytes,
) -> str:
    """
    Compute a deterministic request fingerprint.

    Method and path are normalized. Body bytes are hashed exactly as
    received, avoiding accidental JSON normalization differences.
    """

    normalized_method = method.strip().upper()
    normalized_path = path.strip()

    digest = hashlib.sha256()

    digest.update(
        normalized_method.encode("utf-8")
    )
    digest.update(b"\x00")
    digest.update(
        normalized_path.encode("utf-8")
    )
    digest.update(b"\x00")
    digest.update(body)

    return digest.hexdigest()


def verify_fingerprint(
    cached: CachedResponse,
    fingerprint: str,
) -> None:
    """Validate that a replay uses the original request fingerprint."""

    if not hmac.compare_digest(
        cached.fingerprint,
        fingerprint,
    ):
        raise IdempotencyConflict(
            "idempotency key was already used "
            "with a different request"
        )


_store: IdempotencyStore | None = None
_store_lock = RLock()


def get_idempotency_store() -> IdempotencyStore:
    """Return the configured process-wide idempotency store."""

    global _store

    if _store is None:
        with _store_lock:
            if _store is None:
                _store = InMemoryIdempotencyStore()

    return _store


def set_idempotency_store(
    store: IdempotencyStore,
) -> None:
    """Replace the process-wide store, primarily during application startup."""

    if not isinstance(
        store,
        IdempotencyStore,
    ):
        raise TypeError(
            "store must implement IdempotencyStore"
        )

    global _store

    with _store_lock:
        _store = store


__all__ = [
    "CachedResponse",
    "DEFAULT_LOCK_TTL_S",
    "DEFAULT_TTL_S",
    "IdempotencyConflict",
    "IdempotencyError",
    "IdempotencyInProgress",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "InvalidIdempotencyKey",
    "compute_fingerprint",
    "get_idempotency_store",
    "set_idempotency_store",
    "validate_idempotency_key",
    "verify_fingerprint",
]