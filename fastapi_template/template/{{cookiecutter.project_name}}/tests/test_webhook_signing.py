"""Tests for Standard Webhooks signing and verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from {{cookiecutter.project_name}}.integrations.webhooks.signer import (
    InMemoryWebhookReplayStore,
    WebhookSigner,
    WebhookVerifier,
    generate_webhook_secret,
)


SECRET = "whsec_test_secret_key_here"
PAYLOAD = '{"type": "order.created", "data": {"id": "ord_1"}}'
PAYLOAD_BYTES = PAYLOAD.encode("utf-8")


def _sign_headers(
    *,
    secret: str = SECRET,
    payload: str | bytes = PAYLOAD,
    webhook_id: str = "msg_test",
    timestamp: int | None = None,
) -> tuple[dict[str, str], bytes]:
    signer = WebhookSigner(secret)
    signed = signer.sign(
        payload,
        webhook_id=webhook_id,
        timestamp=timestamp if timestamp is not None else int(time.time()),
    )
    return signed.headers, signed.body


class TestWebhookSigner:
    def test_sign_produces_required_headers(self) -> None:
        signer = WebhookSigner(SECRET)
        result = signer.sign(PAYLOAD)
        assert isinstance(result.body, bytes)
        assert result.body == PAYLOAD_BYTES
        assert "webhook-id" in result.headers
        assert "webhook-timestamp" in result.headers
        assert "webhook-signature" in result.headers
        assert result.headers["webhook-id"].startswith("msg_")
        assert result.headers["webhook-signature"].startswith("v1,")

    def test_sign_accepts_bytes_body(self) -> None:
        signer = WebhookSigner(SECRET)
        result = signer.sign(PAYLOAD_BYTES, webhook_id="msg_bytes", timestamp=1700000000)
        assert result.body == PAYLOAD_BYTES
        assert result.headers["webhook-id"] == "msg_bytes"

    def test_sign_deterministic_with_fixed_inputs(self) -> None:
        signer = WebhookSigner(SECRET)
        r1 = signer.sign(PAYLOAD, webhook_id="msg_123", timestamp=1700000000)
        r2 = signer.sign(PAYLOAD, webhook_id="msg_123", timestamp=1700000000)
        assert r1.headers["webhook-signature"] == r2.headers["webhook-signature"]
        assert r1.body == r2.body

    def test_different_payload_different_signature(self) -> None:
        signer = WebhookSigner(SECRET)
        r1 = signer.sign('{"a": 1}', webhook_id="m1", timestamp=1700000000)
        r2 = signer.sign('{"a": 2}', webhook_id="m1", timestamp=1700000000)
        assert r1.headers["webhook-signature"] != r2.headers["webhook-signature"]


class TestWebhookVerifier:
    def test_sign_verify_roundtrip_str(self) -> None:
        headers, body = _sign_headers(payload=PAYLOAD)
        verifier = WebhookVerifier(SECRET)
        assert verifier.verify(
            webhook_id=headers["webhook-id"],
            timestamp=headers["webhook-timestamp"],
            signature=headers["webhook-signature"],
            payload=PAYLOAD,
        ) is True
        assert body == PAYLOAD_BYTES

    def test_sign_verify_roundtrip_bytes(self) -> None:
        headers, body = _sign_headers(payload=PAYLOAD_BYTES)
        verifier = WebhookVerifier(SECRET)
        assert verifier.verify(
            webhook_id=headers["webhook-id"],
            timestamp=headers["webhook-timestamp"],
            signature=headers["webhook-signature"],
            payload=body,
        ) is True

    def test_verify_wrong_secret_fails(self) -> None:
        headers, _ = _sign_headers(secret="whsec_correct")
        verifier = WebhookVerifier("whsec_wrong")
        assert verifier.verify(
            webhook_id=headers["webhook-id"],
            timestamp=headers["webhook-timestamp"],
            signature=headers["webhook-signature"],
            payload=PAYLOAD,
        ) is False

    def test_verify_tampered_payload_fails(self) -> None:
        headers, _ = _sign_headers()
        verifier = WebhookVerifier(SECRET)
        tampered = PAYLOAD.replace("order", "hacked")
        assert verifier.verify(
            webhook_id=headers["webhook-id"],
            timestamp=headers["webhook-timestamp"],
            signature=headers["webhook-signature"],
            payload=tampered,
        ) is False

    def test_verify_stale_timestamp_rejected(self) -> None:
        old_ts = int(time.time()) - 3600
        headers, _ = _sign_headers(timestamp=old_ts)
        verifier = WebhookVerifier(SECRET, tolerance_s=60)
        assert verifier.verify(
            webhook_id=headers["webhook-id"],
            timestamp=headers["webhook-timestamp"],
            signature=headers["webhook-signature"],
            payload=PAYLOAD,
        ) is False

    def test_verify_empty_headers_rejected(self) -> None:
        verifier = WebhookVerifier(SECRET)
        ts = str(int(time.time()))
        assert verifier.verify(
            webhook_id="",
            timestamp=ts,
            signature="v1,abc",
            payload=PAYLOAD,
        ) is False
        assert verifier.verify(
            webhook_id="msg_1",
            timestamp="",
            signature="v1,abc",
            payload=PAYLOAD,
        ) is False
        assert verifier.verify(
            webhook_id="msg_1",
            timestamp=ts,
            signature="",
            payload=PAYLOAD,
        ) is False

    def test_ignore_non_v1_signatures(self) -> None:
        headers, _ = _sign_headers()
        verifier = WebhookVerifier(SECRET)
        only_v0 = "v0," + headers["webhook-signature"].split(",", 1)[1]
        assert verifier.verify(
            webhook_id=headers["webhook-id"],
            timestamp=headers["webhook-timestamp"],
            signature=only_v0,
            payload=PAYLOAD,
        ) is False

    def test_accept_when_one_of_multiple_v1_matches(self) -> None:
        headers, _ = _sign_headers()
        verifier = WebhookVerifier(SECRET)
        garbage = "v1," + base64.b64encode(b"not-the-real-sig").decode("ascii")
        multi = f"v0,ignored {garbage} {headers['webhook-signature']}"
        assert verifier.verify(
            webhook_id=headers["webhook-id"],
            timestamp=headers["webhook-timestamp"],
            signature=multi,
            payload=PAYLOAD,
        ) is True

    def test_strict_base64_rejects_garbage(self) -> None:
        headers, _ = _sign_headers()
        verifier = WebhookVerifier(SECRET)
        assert verifier.verify(
            webhook_id=headers["webhook-id"],
            timestamp=headers["webhook-timestamp"],
            signature="v1,!!!not-valid-base64!!!",
            payload=PAYLOAD,
        ) is False

    def test_compare_digest_after_decode(self) -> None:
        """Expected HMAC is compared as raw bytes after strict b64 decode."""
        webhook_id = "msg_digest"
        timestamp = str(int(time.time()))
        signed_content = f"{webhook_id}.{timestamp}.".encode("utf-8") + PAYLOAD_BYTES
        digest = hmac.new(SECRET.encode("utf-8"), signed_content, hashlib.sha256).digest()
        # Wrong: compare encoded strings; right path decodes then compare_digest.
        encoded = base64.b64encode(digest).decode("ascii")
        verifier = WebhookVerifier(SECRET)
        assert verifier.verify(
            webhook_id=webhook_id,
            timestamp=timestamp,
            signature=f"v1,{encoded}",
            payload=PAYLOAD,
        ) is True


class TestReplayProtection:
    def test_verify_and_consume_rejects_second_delivery(self) -> None:
        headers, body = _sign_headers(webhook_id="msg_once")
        store = InMemoryWebhookReplayStore()
        verifier = WebhookVerifier(SECRET, replay_store=store)
        kwargs = {
            "webhook_id": headers["webhook-id"],
            "timestamp": headers["webhook-timestamp"],
            "signature": headers["webhook-signature"],
            "payload": body,
        }
        assert verifier.verify_and_consume(**kwargs) is True
        assert verifier.verify_and_consume(**kwargs) is False
        # Cryptographic verify still succeeds — replay is separate.
        assert verifier.verify(**kwargs) is True

    def test_verify_without_replay_store_does_not_consume(self) -> None:
        headers, body = _sign_headers(webhook_id="msg_no_store")
        verifier = WebhookVerifier(SECRET)
        kwargs = {
            "webhook_id": headers["webhook-id"],
            "timestamp": headers["webhook-timestamp"],
            "signature": headers["webhook-signature"],
            "payload": body,
        }
        assert verifier.verify_and_consume(**kwargs) is True
        assert verifier.verify_and_consume(**kwargs) is True


class TestSecretGeneration:
    def test_generate_has_prefix(self) -> None:
        secret = generate_webhook_secret()
        assert secret.startswith("whsec_")

    def test_generate_unique(self) -> None:
        s1 = generate_webhook_secret()
        s2 = generate_webhook_secret()
        assert s1 != s2
