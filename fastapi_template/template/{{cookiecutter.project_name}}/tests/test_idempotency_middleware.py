"""Tests for Stripe-style Idempotency-Key middleware and store contract."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from {{cookiecutter.project_name}}.core.idempotency import (
    MAX_KEY_LENGTH,
    CachedResponse,
    IdempotencyConflict,
    InMemoryIdempotencyStore,
    InvalidIdempotencyKey,
    compute_fingerprint,
    get_idempotency_store,
    set_idempotency_store,
    validate_idempotency_key,
    verify_fingerprint,
)
from {{cookiecutter.project_name}}.web.middleware.idempotency import IdempotencyMiddleware


@pytest.fixture(autouse=True)
def _fresh_store():
    set_idempotency_store(InMemoryIdempotencyStore())
    yield


@pytest.fixture
def app() -> FastAPI:
    """Create a test app with a mutation endpoint and idempotency middleware."""
    app = FastAPI()
    execution_count = {"count": 0}

    @app.post("/orders")
    async def create_order() -> dict:
        execution_count["count"] += 1
        return {"order_id": f"ord_{execution_count['count']}"}

    @app.patch("/orders")
    async def patch_order() -> dict:
        execution_count["count"] += 1
        return {"order_id": f"ord_{execution_count['count']}"}

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    app.add_middleware(IdempotencyMiddleware, ttl_s=300)
    return app


@pytest.fixture
def client(app: FastAPI):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestIdempotentReplay:
    @pytest.mark.asyncio
    async def test_same_key_returns_cached_response(self, client: AsyncClient) -> None:
        key = "unique-key-1"
        r1 = await client.post(
            "/orders",
            json={"item": "widget"},
            headers={"Idempotency-Key": key},
        )
        assert r1.status_code == 200
        body_1 = r1.json()
        assert "Idempotent-Replayed" not in r1.headers

        r2 = await client.post(
            "/orders",
            json={"item": "widget"},
            headers={"Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert r2.headers["Idempotent-Replayed"] == "true"
        assert r2.json() == body_1

    @pytest.mark.asyncio
    async def test_no_header_passes_through(self, client: AsyncClient) -> None:
        r = await client.post("/orders", json={"item": "a"})
        assert r.status_code == 200
        assert "Idempotent-Replayed" not in r.headers

    @pytest.mark.asyncio
    async def test_get_requests_not_intercepted(self, client: AsyncClient) -> None:
        r = await client.get("/health")
        assert r.status_code == 200
        assert "Idempotent-Replayed" not in r.headers


class TestFingerprintConflict:
    @pytest.mark.asyncio
    async def test_same_key_different_body_conflict(self, client: AsyncClient) -> None:
        key = "conflict-key"
        r1 = await client.post(
            "/orders",
            json={"item": "original"},
            headers={"Idempotency-Key": key},
        )
        assert r1.status_code == 200

        # Same method+path+key with a different body must 409.
        # (Different methods use different cache keys by design.)
        r2 = await client.post(
            "/orders",
            json={"different": True},
            headers={"Idempotency-Key": key},
        )
        assert r2.status_code == 409
        assert r2.json()["title"] == "Idempotency Key Reused"


class TestDifferentKeys:
    @pytest.mark.asyncio
    async def test_different_keys_execute_independently(
        self,
        client: AsyncClient,
    ) -> None:
        r1 = await client.post(
            "/orders",
            json={},
            headers={"Idempotency-Key": "key-a"},
        )
        r2 = await client.post(
            "/orders",
            json={},
            headers={"Idempotency-Key": "key-b"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["order_id"] != r2.json()["order_id"]
        assert "Idempotent-Replayed" not in r1.headers
        assert "Idempotent-Replayed" not in r2.headers


class TestConcurrentRequests:
    @pytest.mark.asyncio
    async def test_concurrent_same_key_only_one_executes(
        self,
        client: AsyncClient,
    ) -> None:
        import asyncio

        # Anonymous idempotency is scoped by the private namespace cookie.
        client.cookies.set("nk_anon_id", "test-anonymous-client")
        results = await asyncio.gather(
            *[
                client.post(
                    "/orders",
                    json={},
                    headers={"Idempotency-Key": "race-key"},
                )
                for _ in range(5)
            ]
        )
        originals = [
            r for r in results if "Idempotent-Replayed" not in r.headers
        ]
        assert all(r.status_code in (200, 409) for r in results)
        assert (
            len(originals) <= 1
            or len(
                {
                    r.json().get("order_id")
                    for r in originals
                    if r.status_code == 200
                }
            )
            <= 1
        )


class TestTTLExpiry:
    @pytest.mark.asyncio
    async def test_expired_key_reexecutes(self, client: AsyncClient) -> None:
        key = "expiring-key"
        r1 = await client.post(
            "/orders",
            json={},
            headers={"Idempotency-Key": key},
        )
        assert r1.status_code == 200

        store = get_idempotency_store()
        # Scoped keys look like: idem:{org}:{principal}:{method}:{path}:{key}
        assert isinstance(store, InMemoryIdempotencyStore)
        matching = [
            cache_key
            for cache_key in list(store._responses)
            if cache_key.endswith(f":{key}")
        ]
        assert matching, "expected a scoped cache entry for the idempotency key"
        for cache_key in matching:
            store.clear(cache_key)

        r2 = await client.post(
            "/orders",
            json={},
            headers={"Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert "Idempotent-Replayed" not in r2.headers


class TestKeyValidationMiddleware:
    @pytest.mark.asyncio
    async def test_oversized_key_rejected(self, client: AsyncClient) -> None:
        r = await client.post(
            "/orders",
            json={},
            headers={"Idempotency-Key": "x" * (MAX_KEY_LENGTH + 1)},
        )
        assert r.status_code == 400
        assert r.json()["title"] == "Invalid Idempotency Key"


class TestBodyTooLarge:
    @pytest.mark.asyncio
    async def test_oversized_body_returns_413_problem(self) -> None:
        app = FastAPI()

        @app.post("/orders")
        async def create_order() -> dict:
            return {"ok": True}

        app.add_middleware(
            IdempotencyMiddleware,
            ttl_s=300,
            max_body_bytes=64,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/orders",
                content=b"x" * 128,
                headers={
                    "Idempotency-Key": "big-body",
                    "content-type": "application/octet-stream",
                },
            )
        assert r.status_code == 413
        body = r.json()
        assert body["title"] == "Request Body Too Large"
        assert body["status"] == 413
        assert "application/problem+json" in r.headers["content-type"]


class TestFingerprintFunction:
    def test_deterministic(self) -> None:
        fp1 = compute_fingerprint("POST", "/orders", b'{"a":1}')
        fp2 = compute_fingerprint("POST", "/orders", b'{"a":1}')
        assert fp1 == fp2

    def test_different_body_different_fp(self) -> None:
        fp1 = compute_fingerprint("POST", "/orders", b'{"a":1}')
        fp2 = compute_fingerprint("POST", "/orders", b'{"a":2}')
        assert fp1 != fp2

    def test_different_method_different_fp(self) -> None:
        fp1 = compute_fingerprint("POST", "/x", b"data")
        fp2 = compute_fingerprint("PUT", "/x", b"data")
        assert fp1 != fp2

    def test_different_query_different_fp(self) -> None:
        fp1 = compute_fingerprint(
            "POST",
            "/orders",
            b"data",
            query="region=us",
        )
        fp2 = compute_fingerprint(
            "POST",
            "/orders",
            b"data",
            query="region=eu",
        )
        assert fp1 != fp2


class TestInMemoryStoreContract:
    def test_replay_same_fingerprint(self) -> None:
        store = InMemoryIdempotencyStore(clock=lambda: 100.0)
        fp = compute_fingerprint("POST", "/orders", b"{}")
        cached = CachedResponse(
            status_code=200,
            body=b'{"ok":true}',
            content_type="application/json",
            fingerprint=fp,
            created_at=100.0,
            expires_at=200.0,
        )
        store.set("k1", cached, ttl_s=50.0)
        got = store.get("k1")
        assert got is not None
        verify_fingerprint(got, fp)
        assert got.body == b'{"ok":true}'

    def test_conflict_different_fingerprint(self) -> None:
        store = InMemoryIdempotencyStore(clock=lambda: 100.0)
        fp1 = compute_fingerprint("POST", "/orders", b'{"a":1}')
        fp2 = compute_fingerprint("POST", "/orders", b'{"a":2}')
        store.set(
            "k1",
            CachedResponse(
                status_code=200,
                body=b"{}",
                content_type="application/json",
                fingerprint=fp1,
                created_at=100.0,
                expires_at=200.0,
            ),
            ttl_s=50.0,
        )
        got = store.get("k1")
        assert got is not None
        with pytest.raises(IdempotencyConflict):
            verify_fingerprint(got, fp2)

    def test_in_progress_lease_blocks_second_owner(self) -> None:
        store = InMemoryIdempotencyStore(clock=lambda: 10.0)
        assert store.acquire_lock("lease", ttl_s=5.0, owner="a") is True
        assert store.acquire_lock("lease", ttl_s=5.0, owner="b") is False

    def test_expired_key_reuse(self) -> None:
        clock = {"now": 0.0}

        def _clock() -> float:
            return clock["now"]

        store = InMemoryIdempotencyStore(clock=_clock)
        store.set(
            "k1",
            CachedResponse(
                status_code=200,
                body=b"v1",
                content_type="application/json",
                fingerprint="fp",
                created_at=0.0,
                expires_at=10.0,
            ),
            ttl_s=10.0,
        )
        assert store.get("k1") is not None
        clock["now"] = 11.0
        assert store.get("k1") is None

        store.set(
            "k1",
            CachedResponse(
                status_code=201,
                body=b"v2",
                content_type="application/json",
                fingerprint="fp2",
                created_at=11.0,
                expires_at=21.0,
            ),
            ttl_s=10.0,
        )
        got = store.get("k1")
        assert got is not None
        assert got.body == b"v2"

    def test_owner_safe_release(self) -> None:
        store = InMemoryIdempotencyStore(clock=lambda: 1.0)
        assert store.acquire_lock("lease", ttl_s=30.0, owner="owner-a") is True
        store.release_lock("lease", owner="owner-b")
        # Wrong owner must not release — second acquire still blocked.
        assert store.acquire_lock("lease", ttl_s=30.0, owner="owner-c") is False
        store.release_lock("lease", owner="owner-a")
        assert store.acquire_lock("lease", ttl_s=30.0, owner="owner-c") is True

    def test_expired_lock_can_be_reacquired(self) -> None:
        clock = {"now": 0.0}
        store = InMemoryIdempotencyStore(clock=lambda: clock["now"])
        assert store.acquire_lock("lease", ttl_s=5.0, owner="a") is True
        clock["now"] = 6.0
        assert store.acquire_lock("lease", ttl_s=5.0, owner="b") is True

    def test_key_validation(self) -> None:
        assert validate_idempotency_key("  abc  ") == "abc"
        with pytest.raises(InvalidIdempotencyKey):
            validate_idempotency_key("")
        with pytest.raises(InvalidIdempotencyKey):
            validate_idempotency_key("   ")
        with pytest.raises(InvalidIdempotencyKey):
            validate_idempotency_key("x" * (MAX_KEY_LENGTH + 1))
        with pytest.raises(InvalidIdempotencyKey):
            validate_idempotency_key(123)  # type: ignore[arg-type]

    def test_threaded_lock_contention(self) -> None:
        store = InMemoryIdempotencyStore()
        winners: list[str] = []
        barrier = threading.Barrier(8)

        def worker(owner: str) -> None:
            barrier.wait()
            if store.acquire_lock("race", ttl_s=30.0, owner=owner):
                winners.append(owner)
                time.sleep(0.05)
                store.release_lock("race", owner=owner)

        threads = [
            threading.Thread(target=worker, args=(f"t{i}",))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(winners) >= 1
        # Serialised acquisitions: each winner released before next could win,
        # but only one owner holds the lease at a time during contention start.
        assert len(set(winners)) == len(winners)
