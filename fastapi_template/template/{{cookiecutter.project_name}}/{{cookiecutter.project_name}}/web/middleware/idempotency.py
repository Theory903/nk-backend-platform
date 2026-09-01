"""
Idempotency middleware.

Provides Stripe-style replay protection for unsafe HTTP methods.

Guarantees:

    1. Requests without Idempotency-Key pass through.
    2. Same key + same request fingerprint replays the cached response.
    3. Same key + different fingerprint returns 409.
    4. Concurrent identical requests serialize behind a short-lived lease.
    5. Failed 5xx responses are not permanently cached.
    6. Idempotency state is scoped by tenant/principal when available.
    7. Request bodies are bounded before being buffered.
    8. Lock release is owner-aware.

For distributed production deployments, the backing IdempotencyStore
must use Redis/database atomic primitives rather than process-local
state. The default in-memory store is process-local and is not safe
across multiple workers or nodes — wire a Redis-backed
``IdempotencyStore`` in production.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import hashlib
import json
import logging
import uuid
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from {{cookiecutter.project_name}}.core.idempotency import (
    DEFAULT_LOCK_TTL_S,
    CachedResponse,
    IdempotencyConflict,
    IdempotencyStore,
    InvalidIdempotencyKey,
    compute_fingerprint,
    get_idempotency_store,
    validate_idempotency_key,
    verify_fingerprint,
)

logger = logging.getLogger(__name__)


UNSAFE_METHODS = frozenset(
    {
        "POST",
        "PATCH",
        "PUT",
        "DELETE",
    }
)

DEFAULT_TTL_S = 24 * 60 * 60
DEFAULT_WAIT_S = 2.0
DEFAULT_POLL_INTERVAL_S = 0.1
DEFAULT_MAX_BODY_BYTES = 10 * 1024 * 1024

# HTTP responses that are safe to persist for replay.
CACHEABLE_STATUS_MIN = 200
CACHEABLE_STATUS_MAX = 499


class IdempotencyMiddleware:
    """
    Distributed idempotency middleware.

    The logical key is scoped as:

        idem:{tenant}:{principal}:{method}:{path}:{key}

    This prevents one tenant/user from accidentally replaying another
    tenant/user's request.

    If no authenticated identity is available, the key falls back to
    a request-scoped anonymous namespace.
    """

    def __init__(
        self,
        app: object,
        *,
        ttl_s: float = DEFAULT_TTL_S,
        lock_ttl_s: float = DEFAULT_LOCK_TTL_S,
        wait_timeout_s: float = DEFAULT_WAIT_S,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        store: IdempotencyStore | None = None,
    ) -> None:
        self.app = app

        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")

        if lock_ttl_s <= 0:
            raise ValueError("lock_ttl_s must be positive")

        if wait_timeout_s < 0:
            raise ValueError("wait_timeout_s must be non-negative")

        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be positive")

        if max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")

        self.ttl_s = ttl_s
        self.lock_ttl_s = lock_ttl_s
        self.wait_timeout_s = wait_timeout_s
        self.poll_interval_s = poll_interval_s
        self.max_body_bytes = max_body_bytes
        self.store = store or get_idempotency_store()

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Process HTTP requests without BaseHTTPMiddleware buffering."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        if request.method not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        raw_key = request.headers.get("idempotency-key")
        if raw_key is None or not raw_key.strip():
            await self.app(scope, receive, send)
            return
        if request.headers.get("X-Org-Id") and not getattr(
            request.state,
            "tenant_context",
            None,
        ):
            # Tenant membership is resolved inside route dependencies. Never
            # use an unvalidated selector as a replay namespace.
            await self.app(scope, receive, send)
            return

        try:
            idem_key = validate_idempotency_key(raw_key)
            body = await self._read_request_body(request)
        except InvalidIdempotencyKey as exc:
            response = _problem_response(
                status=400,
                title="Invalid Idempotency Key",
                detail=str(exc),
            )
            await response(scope, receive, send)
            return
        except _RequestBodyTooLarge as exc:
            response = _problem_response(
                status=413,
                title="Request Body Too Large",
                detail=f"Request body exceeds {exc.max_bytes} bytes.",
            )
            await response(scope, receive, send)
            return

        await self._restore_request_body(request, body)
        fingerprint = compute_fingerprint(
            request.method,
            request.url.path,
            body,
            query=request.url.query,
        )
        cache_key = self._build_cache_key(
            request=request,
            idem_key=idem_key,
        )

        cached = await self._store_get(cache_key)
        if cached is not None:
            response = self._replay_or_conflict(cached, fingerprint)
            await response(scope, receive, send)
            return

        owner = uuid.uuid4().hex
        acquired = await self._store_acquire_lock(
            cache_key,
            ttl_s=self.lock_ttl_s,
            owner=owner,
        )
        if not acquired:
            response = await self._wait_for_cached(cache_key, fingerprint)
            if response is None:
                response = _problem_response(
                    status=409,
                    title="Idempotency In Progress",
                    detail=(
                        "Another request with this Idempotency-Key "
                        "is still processing."
                    ),
                )
            await response(scope, receive, send)
            return

        capture = _ResponseCapture(send, max_bytes=self.max_body_bytes)
        lease_state = {"owned": True}
        renewal_task = asyncio.create_task(
            self._renew_lock(cache_key, owner=owner, state=lease_state),
        )
        try:
            cached = await self._store_get(cache_key)
            if cached is not None:
                response = self._replay_or_conflict(cached, fingerprint)
                await response(scope, receive, send)
                return

            await self.app(scope, request._receive, capture)  # type: ignore[attr-defined]
            if capture.passthrough:
                return

            response = capture.as_response()
            if response is None:
                return

            anonymous = _is_anonymous(request)
            anonymous_cookie_missing = (
                anonymous and "nk_anon_id" not in request.cookies
            )
            if anonymous_cookie_missing:
                _set_anonymous_cookie(response, request)

            has_replay_sensitive_headers = (
                capture.has_header("set-cookie")
                or capture.has_header("location")
            )
            if (
                not has_replay_sensitive_headers
                and CACHEABLE_STATUS_MIN <= response.status_code <= CACHEABLE_STATUS_MAX
            ):
                await self._cache_response(
                    cache_key=cache_key,
                    fingerprint=fingerprint,
                    response=response,
                    body=capture.body,
                    owner=owner,
                    lease_owned=lease_state["owned"],
                )
            if anonymous_cookie_missing:
                await response(scope, request._receive, send)  # type: ignore[attr-defined]
            else:
                await capture.send_buffered()
        finally:
            renewal_task.cancel()
            with suppress(asyncio.CancelledError):
                await renewal_task
            try:
                await self._store_release_lock(cache_key, owner=owner)
            except Exception:
                logger.exception(
                    "Failed to release idempotency lock",
                    extra={"cache_key": cache_key},
                )

    async def _renew_lock(
        self,
        cache_key: str,
        *,
        owner: str,
        state: dict[str, bool],
    ) -> None:
        """Keep the lease alive while a long-running request executes."""
        interval = max(0.1, self.lock_ttl_s / 3)
        while True:
            await asyncio.sleep(interval)
            extended = await self._store_extend_lock(
                cache_key,
                ttl_s=self.lock_ttl_s,
                owner=owner,
            )
            if not extended:
                state["owned"] = False
                logger.warning(
                    "Idempotency lease renewal failed",
                    extra={"cache_key": cache_key},
                )
                return

    async def _read_request_body(
        self,
        request: Request,
    ) -> bytes:
        """
        Read the request body with an explicit size limit.

        Avoids allowing the idempotency middleware to become an accidental
        memory-amplification endpoint.
        """

        content_length = request.headers.get("content-length")

        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = None

            if (
                declared_size is not None
                and declared_size > self.max_body_bytes
            ):
                raise _RequestBodyTooLarge(
                    self.max_body_bytes,
                )

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await request._receive()  # type: ignore[attr-defined]
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            chunk = bytes(message.get("body", b""))
            total += len(chunk)
            if total > self.max_body_bytes:
                raise _RequestBodyTooLarge(self.max_body_bytes)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        return b"".join(chunks)

    async def _restore_request_body(
        self,
        request: Request,
        body: bytes,
    ) -> None:
        """
        Restore the request body after middleware consumption.
        """

        async def receive() -> dict[str, Any]:
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }

        request._receive = receive  # type: ignore[attr-defined]

    def _build_cache_key(
        self,
        *,
        request: Request,
        idem_key: str,
    ) -> str:
        """
        Build a tenant/principal scoped idempotency key.

        Authentication middleware should populate request.state before
        this middleware runs.
        """

        principal = getattr(request.state, "principal", None)
        tenant_context = getattr(request.state, "tenant_context", None)
        org_id = _safe_identifier(
            getattr(tenant_context, "org_id", None)
            or getattr(principal, "org_id", None)
            or getattr(request.state, "org_id", None),
        )

        principal_id = _safe_identifier(
            getattr(principal, "user_id", None)
            or getattr(request.state, "user_id", None)
            or getattr(request.state, "principal_id", None),
        )

        # Authentication dependencies run inside the application call. Until
        # then, bind the key to the presented credential without persisting it.
        credential = (
            request.headers.get("Authorization")
            or request.cookies.get("session")
            or request.cookies.get("auth_session")
        )
        credential_id = _safe_identifier(credential)
        if credential_id:
            principal_id = f"{principal_id or 'credential'}:{credential_id}"

        # Anonymous requests still need a stable namespace.
        if not principal_id:
            principal_id = _anonymous_namespace(request)

        scope = org_id or "global"

        return (
            f"idem:"
            f"{scope}:"
            f"{principal_id}:"
            f"{request.method}:"
            f"{request.url.path}:"
            f"{idem_key}"
        )

    async def _wait_for_cached(
        self,
        cache_key: str,
        fingerprint: str,
    ) -> Response | None:
        """
        Wait briefly for the request holding the lease to complete.
        """

        deadline = asyncio.get_running_loop().time() + self.wait_timeout_s

        while True:
            cached = await self._store_get(cache_key)

            if cached is not None:
                return self._replay_or_conflict(
                    cached,
                    fingerprint,
                )

            if asyncio.get_running_loop().time() >= deadline:
                return None

            await asyncio.sleep(self.poll_interval_s)

    async def _cache_response(
        self,
        *,
        cache_key: str,
        fingerprint: str,
        response: Response,
        body: bytes,
        owner: str,
        lease_owned: bool,
    ) -> bool:
        if not lease_owned:
            return False
        now = _utc_timestamp()

        cached = CachedResponse(
            status_code=response.status_code,
            body=body,
            content_type=response.headers.get(
                "content-type",
                "application/octet-stream",
            ),
            fingerprint=fingerprint,
            created_at=now,
            expires_at=now + self.ttl_s,
        )

        return await self._store_set_if_owner(
            cache_key,
            cached,
            ttl_s=self.ttl_s,
            owner=owner,
        )

    def _replay_or_conflict(
        self,
        cached: CachedResponse,
        fingerprint: str,
    ) -> Response:
        try:
            verify_fingerprint(
                cached,
                fingerprint,
            )
        except IdempotencyConflict:
            return _problem_response(
                status=409,
                title="Idempotency Key Reused",
                detail=(
                    "This Idempotency-Key was used with "
                    "a different request."
                ),
            )

        return Response(
            content=cached.body,
            status_code=cached.status_code,
            media_type=cached.content_type,
            headers={
                "Idempotent-Replayed": "true",
            },
        )

    async def _extract_response_body(
        self,
        response: Response,
    ) -> bytes:
        """
        Extract a concrete response body.

        Large/streaming responses should generally bypass idempotency
        caching rather than being fully accumulated in memory.
        """

        body = getattr(
            response,
            "body",
            None,
        )

        if body is None:
            return b""

        return bytes(body)

    # ------------------------------------------------------------------
    # Store adapters
    #
    # These wrappers isolate synchronous legacy stores from the event loop.
    # If your production IdempotencyStore becomes async, remove to_thread().
    # ------------------------------------------------------------------

    async def _store_get(
        self,
        key: str,
    ) -> CachedResponse | None:
        return await asyncio.to_thread(
            self.store.get,
            key,
        )

    async def _store_set(
        self,
        key: str,
        value: CachedResponse,
        *,
        ttl_s: float,
    ) -> None:
        await asyncio.to_thread(
            self.store.set,
            key,
            value,
            ttl_s=ttl_s,
        )

    async def _store_set_if_owner(
        self,
        key: str,
        value: CachedResponse,
        *,
        ttl_s: float,
        owner: str,
    ) -> bool:
        setter = getattr(self.store, "set_if_owner", None)
        if setter is None:
            return False
        return bool(
            await asyncio.to_thread(
                setter,
                key,
                value,
                ttl_s=ttl_s,
                owner=owner,
            ),
        )

    async def _store_acquire_lock(
        self,
        key: str,
        *,
        ttl_s: float,
        owner: str,
    ) -> bool:
        return await asyncio.to_thread(
            self.store.acquire_lock,
            key,
            ttl_s=ttl_s,
            owner=owner,
        )

    async def _store_release_lock(
        self,
        key: str,
        *,
        owner: str,
    ) -> None:
        await asyncio.to_thread(
            self.store.release_lock,
            key,
            owner=owner,
        )

    async def _store_extend_lock(
        self,
        key: str,
        *,
        ttl_s: float,
        owner: str,
    ) -> bool:
        extend = getattr(self.store, "extend_lock", None)
        if extend is None:
            return False
        return bool(
            await asyncio.to_thread(
                extend,
                key,
                ttl_s=ttl_s,
                owner=owner,
            ),
        )


class _ResponseCapture:
    """Capture bounded responses while preserving oversized streams."""

    def __init__(self, send: Any, *, max_bytes: int) -> None:
        self._send = send
        self._max_bytes = max_bytes
        self._start: dict[str, Any] | None = None
        self._chunks: list[bytes] = []
        self._size = 0
        self.passthrough = False

    @property
    def body(self) -> bytes:
        return b"".join(self._chunks)

    def has_header(self, name: str) -> bool:
        if self._start is None:
            return False
        normalized = name.lower().encode("latin-1")
        return any(
            key.lower() == normalized
            for key, _value in self._start.get("headers", [])
        )

    async def __call__(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "http.response.start":
            self._start = message
            return
        if message_type != "http.response.body":
            await self._send(message)
            return
        if self.passthrough:
            await self._send(message)
            return

        chunk = bytes(message.get("body", b""))
        if self._size + len(chunk) <= self._max_bytes:
            self._chunks.append(chunk)
            self._size += len(chunk)
            return

        self.passthrough = True
        if self._start is not None:
            await self._send(self._start)
        for buffered in self._chunks:
            await self._send(
                {
                    "type": "http.response.body",
                    "body": buffered,
                    "more_body": True,
                },
            )
        self._chunks.clear()
        await self._send(message)

    def as_response(self) -> Response | None:
        if self._start is None or self.passthrough:
            return None
        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in self._start.get("headers", [])
        }
        return Response(
            content=self.body,
            status_code=int(self._start["status"]),
            headers=headers,
        )

    async def send_buffered(self) -> None:
        if self._start is None or self.passthrough:
            return
        await self._send(self._start)
        await self._send(
            {
                "type": "http.response.body",
                "body": self.body,
                "more_body": False,
            },
        )


class _RequestBodyTooLarge(Exception):
    """
    Internal exception used by the middleware's body-size guard.
    """

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(
            f"request body exceeds {max_bytes} bytes",
        )


def _problem_response(
    *,
    status: int,
    title: str,
    detail: str,
) -> Response:
    return Response(
        content=json.dumps(
            {
                "type": "about:blank",
                "title": title,
                "status": status,
                "detail": detail,
            },
        ),
        status_code=status,
        media_type="application/problem+json",
    )


def _safe_response_headers(
    response: Response,
) -> dict[str, str]:
    """
    Preserve normal application headers while avoiding hop-by-hop headers.
    """

    hop_by_hop = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }

    return {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in hop_by_hop
        and key.lower() != "content-length"
    }


def _safe_identifier(value: Any) -> str:
    """
    Normalize identifiers before inserting them into store keys.
    """

    if value is None:
        return ""

    value = str(value).strip()

    if not value:
        return ""

    # Avoid uncontrolled key expansion / delimiter injection.
    return hashlib.sha256(
        value.encode("utf-8"),
    ).hexdigest()[:32]


def _anonymous_namespace(
    request: Request,
) -> str:
    """
    Anonymous idempotency namespace.

    IP is intentionally not used directly because it can be shared by many
    users. The endpoint + authenticated context should be preferred whenever
    authentication exists.
    """

    anonymous_id = getattr(request.state, "idempotency_anonymous_id", None)
    if not anonymous_id:
        anonymous_id = request.cookies.get("nk_anon_id") or uuid.uuid4().hex
        request.state.idempotency_anonymous_id = anonymous_id

    material = f"{anonymous_id}|{request.url.path}"

    return (
        "anon-"
        + hashlib.sha256(
            material.encode("utf-8"),
        ).hexdigest()[:32]
    )


def _is_anonymous(request: Request) -> bool:
    principal = getattr(request.state, "principal", None)
    return principal is None or getattr(principal, "is_anonymous", True)


def _set_anonymous_cookie(response: Response, request: Request) -> None:
    """Give unauthenticated clients a private, retry-stable namespace."""
    principal = getattr(request.state, "principal", None)
    if principal is not None and not getattr(principal, "is_anonymous", True):
        return
    anonymous_id = getattr(request.state, "idempotency_anonymous_id", None)
    if anonymous_id is None or request.cookies.get("nk_anon_id"):
        return
    response.set_cookie(
        "nk_anon_id",
        anonymous_id,
        max_age=DEFAULT_TTL_S,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )


def _utc_timestamp() -> float:
    """
    Wall-clock timestamp for persisted cache metadata.

    Store TTL itself should remain the authoritative expiration mechanism.
    """
    import time

    return time.time()


__all__ = [
    "CACHEABLE_STATUS_MAX",
    "CACHEABLE_STATUS_MIN",
    "DEFAULT_MAX_BODY_BYTES",
    "DEFAULT_POLL_INTERVAL_S",
    "DEFAULT_TTL_S",
    "DEFAULT_WAIT_S",
    "IdempotencyMiddleware",
    "UNSAFE_METHODS",
]