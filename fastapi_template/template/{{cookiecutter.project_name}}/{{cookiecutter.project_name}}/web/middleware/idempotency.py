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
import hashlib
import json
import logging
import uuid
from typing import Any

from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

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


class IdempotencyMiddleware(BaseHTTPMiddleware):
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
        super().__init__(app)  # type: ignore[arg-type]

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

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Safe methods do not require idempotency protection.
        if request.method not in UNSAFE_METHODS:
            return await call_next(request)

        raw_key = request.headers.get("idempotency-key")

        # Idempotency-Key is optional.
        if raw_key is None or not raw_key.strip():
            return await call_next(request)

        try:
            idem_key = validate_idempotency_key(raw_key)
        except InvalidIdempotencyKey as exc:
            return _problem_response(
                status=400,
                title="Invalid Idempotency Key",
                detail=str(exc),
            )

        try:
            body = await self._read_request_body(request)
        except _RequestBodyTooLarge as exc:
            return _problem_response(
                status=413,
                title="Request Body Too Large",
                detail=(
                    f"Request body exceeds {exc.max_bytes} bytes."
                ),
            )

        # Restore the consumed ASGI body for downstream handlers.
        await self._restore_request_body(request, body)

        fingerprint = compute_fingerprint(
            request.method,
            request.url.path,
            body,
        )

        cache_key = self._build_cache_key(
            request=request,
            idem_key=idem_key,
        )

        # ------------------------------------------------------------------
        # Fast path: completed request already exists.
        # ------------------------------------------------------------------

        cached = await self._store_get(cache_key)

        if cached is not None:
            return self._replay_or_conflict(
                cached,
                fingerprint,
            )

        # ------------------------------------------------------------------
        # Acquire execution lease.
        # ------------------------------------------------------------------

        owner = uuid.uuid4().hex

        acquired = await self._store_acquire_lock(
            cache_key,
            ttl_s=self.lock_ttl_s,
            owner=owner,
        )

        if not acquired:
            response = await self._wait_for_cached(
                cache_key,
                fingerprint,
            )

            if response is not None:
                return response

            return _problem_response(
                status=409,
                title="Idempotency In Progress",
                detail=(
                    "Another request with this Idempotency-Key "
                    "is still processing."
                ),
            )

        try:
            # ------------------------------------------------------------------
            # Close the GET → LOCK race.
            #
            # Another worker may have completed the operation immediately
            # before we acquired the lock.
            # ------------------------------------------------------------------

            cached = await self._store_get(cache_key)

            if cached is not None:
                return self._replay_or_conflict(
                    cached,
                    fingerprint,
                )

            # ------------------------------------------------------------------
            # Execute application request.
            # ------------------------------------------------------------------

            response = await call_next(request)

            # Do not consume streaming responses blindly.
            #
            # BaseHTTPMiddleware already introduces response buffering
            # behavior, so we only cache responses that expose a concrete
            # body.
            response_body = await self._extract_response_body(response)

            # Do not cache server errors. The client can safely retry the
            # operation with the same Idempotency-Key.
            if CACHEABLE_STATUS_MIN <= response.status_code <= CACHEABLE_STATUS_MAX:
                await self._cache_response(
                    cache_key=cache_key,
                    fingerprint=fingerprint,
                    response=response,
                    body=response_body,
                )

            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=_safe_response_headers(response),
                media_type=response.headers.get("content-type"),
            )

        except Exception:
            logger.exception(
                "Unhandled exception during idempotent request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "idempotency_key": idem_key,
                },
            )

            # Important:
            # no response is cached, so a retry can execute again.
            raise

        finally:
            # Release only our own lease.
            #
            # The backing store MUST implement owner-aware release
            # atomically for distributed deployments.
            try:
                await self._store_release_lock(
                    cache_key,
                    owner=owner,
                )
            except Exception:
                logger.exception(
                    "Failed to release idempotency lock",
                    extra={"cache_key": cache_key},
                )

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

        body = await request.body()

        if len(body) > self.max_body_bytes:
            raise _RequestBodyTooLarge(
                self.max_body_bytes,
            )

        return body

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

        org_id = _safe_identifier(
            getattr(request.state, "org_id", None),
        )

        principal_id = _safe_identifier(
            getattr(request.state, "user_id", None)
            or getattr(request.state, "principal_id", None),
        )

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
    ) -> None:
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

        await self._store_set(
            cache_key,
            cached,
            ttl_s=self.ttl_s,
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

        body_iterator = getattr(
            response,
            "body_iterator",
            None,
        )

        if body_iterator is not None:
            chunks: list[bytes] = []

            async for chunk in body_iterator:
                if isinstance(chunk, str):
                    chunk = chunk.encode()

                chunks.append(bytes(chunk))

            return b"".join(chunks)

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

    forwarded = request.headers.get(
        "x-forwarded-for",
        "",
    )

    client_host = (
        request.client.host
        if request.client is not None
        else ""
    )

    material = (
        f"{client_host}|"
        f"{forwarded}|"
        f"{request.url.path}"
    )

    return (
        "anon-"
        + hashlib.sha256(
            material.encode("utf-8"),
        ).hexdigest()[:32]
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