"""
Standard Webhooks signing and verification.

Implements the Standard Webhooks signing model:

    webhook-id
    webhook-timestamp
    webhook-signature

The signed content is:

    <webhook-id>.<webhook-timestamp>.<raw-body>

The signature is:

    v1,<base64(HMAC-SHA256(secret, signed_content))>

Security properties:

- HMAC-SHA256
- Constant-time signature comparison
- Strict v1 signature handling
- Multiple v1 signatures supported
- Timestamp tolerance
- Raw-body preservation
- Strict Base64 decoding
- Optional replay protection
- Cryptographically random webhook IDs/secrets

Replay protection is deliberately separated from cryptographic verification.
A signature can be valid and still represent a previously processed message.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Protocol


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


SIGNATURE_VERSION = "v1"

DEFAULT_TOLERANCE_S = 300


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignedWebhook:
    """
    Signed outgoing webhook.

    body is bytes so callers can send the exact bytes that were signed.
    """

    body: bytes
    headers: dict[str, str]


# ---------------------------------------------------------------------------
# Replay protection
# ---------------------------------------------------------------------------


class WebhookReplayStore(Protocol):
    """
    Store used to prevent processing the same webhook ID more than once.
    """

    def seen(self, webhook_id: str) -> bool:
        """
        Return True if the webhook ID has already been processed.
        """

        ...

    def mark(
        self,
        webhook_id: str,
        *,
        ttl_s: int,
    ) -> None:
        """
        Mark a webhook ID as processed.
        """

        ...


class InMemoryWebhookReplayStore:
    """
    Development/test replay store.

    Production should use Redis or another shared atomic store.
    """

    def __init__(self) -> None:
        self._entries: dict[str, float] = {}

    def _cleanup(self) -> None:
        now = time.time()

        expired = [
            webhook_id
            for webhook_id, expires_at in self._entries.items()
            if expires_at <= now
        ]

        for webhook_id in expired:
            self._entries.pop(webhook_id, None)

    def seen(self, webhook_id: str) -> bool:
        self._cleanup()

        return webhook_id in self._entries

    def mark(
        self,
        webhook_id: str,
        *,
        ttl_s: int,
    ) -> None:
        self._cleanup()

        self._entries[webhook_id] = (
            time.time() + ttl_s
        )


# ---------------------------------------------------------------------------
# Secret validation
# ---------------------------------------------------------------------------


def _validate_secret(secret: str) -> None:
    if not isinstance(secret, str) or not secret:
        raise ValueError(
            "webhook secret must be a non-empty string"
        )


# ---------------------------------------------------------------------------
# Body normalization
# ---------------------------------------------------------------------------


def _body_bytes(
    payload: str | bytes,
) -> bytes:
    if isinstance(payload, bytes):
        return payload

    if isinstance(payload, str):
        return payload.encode("utf-8")

    raise TypeError(
        "payload must be str or bytes"
    )


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


class WebhookSigner:
    """
    Signs outgoing webhooks using HMAC-SHA256.
    """

    def __init__(
        self,
        secret: str,
    ) -> None:
        _validate_secret(secret)

        self._secret = secret.encode("utf-8")

    def sign(
        self,
        payload: str | bytes,
        *,
        webhook_id: str | None = None,
        timestamp: int | None = None,
    ) -> SignedWebhook:
        """
        Sign a webhook payload.

        The returned body is the exact byte sequence used to calculate
        the signature.
        """
        body = _body_bytes(payload)

        webhook_id = (
            webhook_id
            or f"msg_{uuid.uuid4().hex}"
        )

        if not webhook_id:
            raise ValueError(
                "webhook_id cannot be empty"
            )

        ts = (
            int(timestamp)
            if timestamp is not None
            else int(time.time())
        )

        signed_content = (
            f"{webhook_id}.{ts}."
        ).encode("utf-8") + body

        digest = hmac.new(
            self._secret,
            signed_content,
            hashlib.sha256,
        ).digest()

        encoded_signature = base64.b64encode(
            digest
        ).decode("ascii")

        return SignedWebhook(
            body=body,
            headers={
                "webhook-id": webhook_id,
                "webhook-timestamp": str(ts),
                "webhook-signature": (
                    f"{SIGNATURE_VERSION},"
                    f"{encoded_signature}"
                ),
            },
        )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class WebhookVerifier:
    """
    Verifies incoming Standard Webhooks.

    Cryptographic verification and replay detection are separate concerns:

        signature valid
            !=
        message has not already been processed
    """

    def __init__(
        self,
        secret: str,
        *,
        tolerance_s: int = DEFAULT_TOLERANCE_S,
        replay_store: WebhookReplayStore | None = None,
    ) -> None:
        _validate_secret(secret)

        if tolerance_s < 0:
            raise ValueError(
                "tolerance_s cannot be negative"
            )

        self._secret = secret.encode("utf-8")
        self._tolerance_s = tolerance_s
        self._replay_store = replay_store

    def _signed_content(
        self,
        *,
        webhook_id: str,
        timestamp: str,
        payload: bytes,
    ) -> bytes:
        return (
            f"{webhook_id}.{timestamp}."
        ).encode("utf-8") + payload

    @staticmethod
    def _decode_signature(
        encoded: str,
    ) -> bytes | None:
        """
        Strictly decode a Base64 signature.
        """
        if not encoded:
            return None

        try:
            return base64.b64decode(
                encoded,
                validate=True,
            )
        except (
            ValueError,
            binascii.Error,
        ):
            return None

    @staticmethod
    def _extract_v1_signatures(
        header: str,
    ) -> list[str]:
        """
        Extract all v1 signatures.

        Standard Webhooks can provide multiple signatures,
        for example during secret rotation.
        """
        if not header:
            return []

        signatures: list[str] = []

        for value in header.split():
            if "," not in value:
                continue

            version, encoded = value.split(
                ",",
                1,
            )

            if version == SIGNATURE_VERSION:
                if encoded:
                    signatures.append(encoded)

        return signatures

    def verify(
        self,
        *,
        webhook_id: str,
        timestamp: str,
        signature: str,
        payload: str | bytes,
    ) -> bool:
        """
        Cryptographically verify a webhook.

        Does not consume replay state.

        Use verify_and_consume() when the webhook should be accepted
        exactly once.
        """
        if not webhook_id:
            return False

        if not timestamp:
            return False

        if not signature:
            return False

        body = _body_bytes(payload)

        # ---------------------------------------------------------------
        # Timestamp validation
        # ---------------------------------------------------------------

        try:
            timestamp_int = int(timestamp)
        except (TypeError, ValueError):
            return False

        now = int(time.time())

        if abs(now - timestamp_int) > self._tolerance_s:
            return False

        # ---------------------------------------------------------------
        # Signature extraction
        # ---------------------------------------------------------------

        signatures = self._extract_v1_signatures(
            signature
        )

        if not signatures:
            return False

        # ---------------------------------------------------------------
        # HMAC calculation
        # ---------------------------------------------------------------

        signed_content = self._signed_content(
            webhook_id=webhook_id,
            timestamp=timestamp,
            payload=body,
        )

        expected = hmac.new(
            self._secret,
            signed_content,
            hashlib.sha256,
        ).digest()

        # ---------------------------------------------------------------
        # Compare every v1 signature.
        # ---------------------------------------------------------------

        for encoded_signature in signatures:
            candidate = self._decode_signature(
                encoded_signature
            )

            if candidate is None:
                continue

            if hmac.compare_digest(
                candidate,
                expected,
            ):
                return True

        return False

    def verify_and_consume(
        self,
        *,
        webhook_id: str,
        timestamp: str,
        signature: str,
        payload: str | bytes,
    ) -> bool:
        """
        Verify the webhook and atomically-ish consume its ID.

        In production the replay store MUST provide an atomic
        check-and-set operation. The simple protocol here is suitable
        for the in-memory implementation but Redis should use SET NX.
        """
        if not self.verify(
            webhook_id=webhook_id,
            timestamp=timestamp,
            signature=signature,
            payload=payload,
        ):
            return False

        if self._replay_store is None:
            return True

        if self._replay_store.seen(
            webhook_id
        ):
            return False

        self._replay_store.mark(
            webhook_id,
            ttl_s=self._tolerance_s,
        )

        return True


# ---------------------------------------------------------------------------
# Secret generation
# ---------------------------------------------------------------------------


def generate_webhook_secret() -> str:
    """
    Generate a Standard Webhooks-style secret.
    """
    return (
        "whsec_"
        + secrets.token_urlsafe(32)
    )


__all__ = [
    "DEFAULT_TOLERANCE_S",
    "SIGNATURE_VERSION",
    "InMemoryWebhookReplayStore",
    "SignedWebhook",
    "WebhookReplayStore",
    "WebhookSigner",
    "WebhookVerifier",
    "generate_webhook_secret",
]