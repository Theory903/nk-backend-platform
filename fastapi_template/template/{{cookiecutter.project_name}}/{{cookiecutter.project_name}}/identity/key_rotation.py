"""Signing-key rotation with introduce → dual-accept → retire.

Rotation guarantees:

    K1 signs
        ↓
    K2 introduced
        ↓
    K2 signs
    K1 + K2 verify
        ↓
    K1 grace period expires
        ↓
    K2 signs
    K2 verifies

**In-memory is not multi-worker source of truth.** This manager keeps the
key ring in process memory under an ``RLock``. Multiple workers / pods /
processes will each hold a divergent ring. Production deployments must
persist the ring in a shared KMS or secret store (see ``KeyRingStore``)
and load it at startup / on rotate.

This implementation supports HMAC-based signing keys and currently
implements HS256 only.

JWT integration (light hook — ``identity.jwt`` already accepts ``kid``):

    kid = manager.current_key_id()
    key = manager.get_key(kid) if kid else None
    # Map ``key.secret`` into the string form your JWT layer expects.
    create_access_token(subject, secret=..., kid=kid)
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol, runtime_checkable

__all__ = [
    "SUPPORTED_ALGORITHMS",
    "SigningKey",
    "KeyRingStore",
    "KeyRotationManager",
]

SUPPORTED_ALGORITHMS = frozenset({"HS256"})


@dataclass(frozen=True)
class SigningKey:
    """A single signing key in the rotation ring."""

    key_id: str
    secret: bytes
    algorithm: str = "HS256"
    created_at: float = field(default_factory=time.time)

    # Timestamp after which verification must stop accepting this key.
    retired_at: float | None = None

    @property
    def is_valid(self) -> bool:
        """Whether this key may currently verify signatures."""
        return self.retired_at is None or time.time() < self.retired_at


@runtime_checkable
class KeyRingStore(Protocol):
    """Optional persistence backend for multi-process key rings.

    Stub only — ``KeyRotationManager`` does not load/save through this yet.
    Implement against a shared KMS / secret store for production.
    """

    def load(self) -> tuple[dict[str, SigningKey], str | None]:
        """Return ``(keys_by_id, signing_key_id)``."""
        ...

    def save(
        self,
        keys: dict[str, SigningKey],
        signing_key_id: str | None,
    ) -> None:
        """Persist the full ring and current signer id."""
        ...


class KeyRotationManager:
    """
    Thread-safe signing-key rotation manager.

    Rotation lifecycle:

        introduce_key()
            K1 becomes signing key.

        introduce_key()
            K2 becomes signing key.
            K1 remains valid until its grace period expires.

        force_retire(K1)
            K1 is immediately rejected for verification.

        retire_expired()
            Removes keys whose grace period has elapsed.

    New signatures always use the current signing key.

    Verification accepts every non-expired key in the ring (dual-accept
    during grace).

    Process-local only — see module docstring for multi-worker caveats.
    """

    def __init__(
        self,
        *,
        grace_period_s: float = 3600.0,
    ) -> None:
        if grace_period_s < 0:
            raise ValueError("grace_period_s cannot be negative")

        self.grace_period_s = grace_period_s

        self._keys: dict[str, SigningKey] = {}
        self._signing_key_id: str | None = None

        self._lock = RLock()

    # ------------------------------------------------------------------
    # Key lifecycle
    # ------------------------------------------------------------------

    def introduce_key(
        self,
        *,
        algorithm: str = "HS256",
        secret: bytes | None = None,
        key_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Introduce a new signing key.

        Existing signing key enters its grace period (dual-accept).

        Returns:

            (key_id, secret_hex)

        The secret should be stored securely and should not normally be
        returned through an HTTP API.
        """

        algorithm = algorithm.upper()

        if algorithm not in SUPPORTED_ALGORITHMS:
            raise ValueError(f"unsupported signing algorithm: {algorithm}")

        if secret is None:
            secret = secrets.token_bytes(32)

        if len(secret) < 32:
            raise ValueError("HS256 signing secret must be at least 32 bytes")

        with self._lock:
            now = time.time()

            # Move current signing key into dual-accept/grace period.
            if self._signing_key_id is not None:
                old_key = self._keys[self._signing_key_id]

                self._keys[self._signing_key_id] = SigningKey(
                    key_id=old_key.key_id,
                    secret=old_key.secret,
                    algorithm=old_key.algorithm,
                    created_at=old_key.created_at,
                    retired_at=now + self.grace_period_s,
                )

            new_key_id = key_id or self._generate_key_id()

            if new_key_id in self._keys:
                raise ValueError(f"signing key already exists: {new_key_id}")

            new_key = SigningKey(
                key_id=new_key_id,
                secret=secret,
                algorithm=algorithm,
                created_at=now,
            )

            self._keys[new_key_id] = new_key
            self._signing_key_id = new_key_id

            return (new_key_id, secret.hex())

    @staticmethod
    def _generate_key_id() -> str:
        return f"k_{secrets.token_hex(8)}"

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    def sign(
        self,
        message: str | bytes,
    ) -> tuple[str, str]:
        """
        Sign using the current signing key.

        Returns:

            (key_id, signature_hex)
        """

        message_bytes = (
            message.encode("utf-8") if isinstance(message, str) else message
        )

        with self._lock:
            key = self._get_current_signing_key()

            signature = self._sign_with_key(key, message_bytes)

            return (key.key_id, signature)

    def _get_current_signing_key(self) -> SigningKey:
        if self._signing_key_id is None:
            self.introduce_key()

        assert self._signing_key_id is not None

        key = self._keys.get(self._signing_key_id)

        if key is None:
            raise RuntimeError("current signing key is missing")

        if not key.is_valid:
            raise RuntimeError("current signing key is retired")

        return key

    @staticmethod
    def _sign_with_key(
        key: SigningKey,
        message: bytes,
    ) -> str:
        if key.algorithm == "HS256":
            return hmac.new(
                key.secret,
                message,
                hashlib.sha256,
            ).hexdigest()

        raise ValueError(f"unsupported signing algorithm: {key.algorithm}")

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_signature(
        self,
        message: str | bytes,
        signature: str | bytes,
        *,
        key_id: str | None = None,
        algorithm: str = "HS256",
    ) -> str | None:
        """
        Verify a signature.

        If ``key_id`` is supplied, only that key is checked.

        If ``key_id`` is absent, all currently valid keys are checked
        (dual-accept during grace).

        Returns the matching key ID, otherwise None.
        """

        message_bytes = (
            message.encode("utf-8") if isinstance(message, str) else message
        )

        algorithm = algorithm.upper()

        if algorithm not in SUPPORTED_ALGORITHMS:
            return None

        signature_bytes = self._decode_signature(signature)

        if signature_bytes is None:
            return None

        with self._lock:
            if key_id is not None:
                key = self._keys.get(key_id)

                if key is None or not key.is_valid:
                    return None

                if key.algorithm != algorithm:
                    return None

                return (
                    key.key_id
                    if self._matches(key, message_bytes, signature_bytes)
                    else None
                )

            # Dual-accept: try every currently valid key.
            for key in self._keys.values():
                if not key.is_valid:
                    continue

                if key.algorithm != algorithm:
                    continue

                if self._matches(key, message_bytes, signature_bytes):
                    return key.key_id

        return None

    @staticmethod
    def _decode_signature(
        signature: str | bytes,
    ) -> bytes | None:
        if isinstance(signature, bytes):
            return signature

        if not signature:
            return None

        try:
            return bytes.fromhex(signature)
        except ValueError:
            return None

    @staticmethod
    def _matches(
        key: SigningKey,
        message: bytes,
        signature: bytes,
    ) -> bool:
        expected = KeyRotationManager._sign_with_key(key, message)

        try:
            expected_bytes = bytes.fromhex(expected)
        except ValueError:
            return False

        return hmac.compare_digest(signature, expected_bytes)

    # ------------------------------------------------------------------
    # Retirement
    # ------------------------------------------------------------------

    def force_retire(
        self,
        key_id: str,
    ) -> bool:
        """Immediately stop accepting a key for verification.

        Cannot retire the current signing key — introduce a replacement
        first.
        """

        with self._lock:
            key = self._keys.get(key_id)

            if key is None:
                return False

            if key_id == self._signing_key_id:
                raise ValueError(
                    "cannot retire the current signing key; "
                    "introduce another key first"
                )

            self._keys[key_id] = SigningKey(
                key_id=key.key_id,
                secret=key.secret,
                algorithm=key.algorithm,
                created_at=key.created_at,
                retired_at=time.time(),
            )

            return True

    def retire_expired(self) -> int:
        """
        Remove keys whose grace period has expired.

        Returns the number of removed keys.

        This should normally run as periodic maintenance.
        """

        now = time.time()

        with self._lock:
            expired = [
                key_id
                for key_id, key in self._keys.items()
                if (
                    key.retired_at is not None
                    and now >= key.retired_at
                    and key_id != self._signing_key_id
                )
            ]

            for key_id in expired:
                del self._keys[key_id]

            return len(expired)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def active_key_ids(self) -> list[str]:
        """Return IDs of keys currently accepted for verification."""

        with self._lock:
            return [
                key_id for key_id, key in self._keys.items() if key.is_valid
            ]

    def current_key_id(self) -> str | None:
        """Return the key ID currently used for signing."""

        with self._lock:
            return self._signing_key_id

    def get_key(
        self,
        key_id: str,
    ) -> SigningKey | None:
        """Return key metadata.

        Do not expose ``secret`` outside trusted key-management code.
        """

        with self._lock:
            return self._keys.get(key_id)

    def key_count(self) -> int:
        with self._lock:
            return len(self._keys)
