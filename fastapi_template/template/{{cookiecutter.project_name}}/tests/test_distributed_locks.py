"""Tests for distributed locks: mutual exclusion, TTL safety, ownership release."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from {{cookiecutter.project_name}}.core import locks as locks_mod
from {{cookiecutter.project_name}}.core.locks import (
    DEFAULT_LOCK_TTL_S,
    DEFAULT_TTL_S,
    InMemoryLockBackend,
    InvalidLockConfiguration,
    RedisLockBackend,
    close_lock_backends,
    distributed_lock,
    get_lock_backend,
)


@pytest.fixture
def backend() -> InMemoryLockBackend:
    return InMemoryLockBackend()


@pytest.fixture(autouse=True)
async def _reset_lock_module_state() -> None:
    await close_lock_backends()
    await locks_mod._memory_backend.close()
    yield
    await close_lock_backends()
    await locks_mod._memory_backend.close()


class TestMutualExclusion:
    @pytest.mark.anyio
    async def test_second_acquire_fails_while_held(
        self,
        backend: InMemoryLockBackend,
    ) -> None:
        token1 = await backend.acquire("resource", ttl_s=60)
        assert token1 is not None
        token2 = await backend.acquire("resource", ttl_s=60)
        assert token2 is None

    @pytest.mark.anyio
    async def test_release_allows_reacquire(
        self,
        backend: InMemoryLockBackend,
    ) -> None:
        token = await backend.acquire("res", ttl_s=60)
        assert token is not None
        await backend.release("res", owner_token=token)
        token2 = await backend.acquire("res", ttl_s=60)
        assert token2 is not None

    @pytest.mark.anyio
    async def test_different_keys_independent(
        self,
        backend: InMemoryLockBackend,
    ) -> None:
        t1 = await backend.acquire("key_a", ttl_s=60)
        t2 = await backend.acquire("key_b", ttl_s=60)
        assert t1 is not None
        assert t2 is not None


class TestTTLSafety:
    @pytest.mark.anyio
    async def test_expired_lease_reacquire(
        self,
        backend: InMemoryLockBackend,
    ) -> None:
        clock = {"now": 1000.0}

        backend = InMemoryLockBackend(clock=lambda: clock["now"])
        token = await backend.acquire("short_lock", ttl_s=0.05)
        assert token is not None

        clock["now"] = 1000.06

        new_token = await backend.acquire("short_lock", ttl_s=60)
        assert new_token is not None
        assert new_token != token


class TestOwnershipRelease:
    @pytest.mark.anyio
    async def test_release_with_wrong_token_fails(
        self,
        backend: InMemoryLockBackend,
    ) -> None:
        token = await backend.acquire("owned", ttl_s=60)
        assert token is not None
        released = await backend.release(
            "owned",
            owner_token="not-the-owner",
        )
        assert released is False
        still_held = await backend.acquire("owned", ttl_s=60)
        assert still_held is None

    @pytest.mark.anyio
    async def test_release_with_correct_token_succeeds(
        self,
        backend: InMemoryLockBackend,
    ) -> None:
        token = await backend.acquire("owned", ttl_s=60)
        assert token is not None
        released = await backend.release("owned", owner_token=token)
        assert released is True


class TestContextManager:
    @pytest.mark.anyio
    async def test_context_manager_acquires_and_releases(self) -> None:
        backend = InMemoryLockBackend()
        async with distributed_lock(
            "ctx_test",
            backend=backend,
        ) as acquired:
            assert acquired is True
            assert await backend.acquire("ctx_test", ttl_s=60) is None

        assert await backend.acquire("ctx_test", ttl_s=60) is not None

    @pytest.mark.anyio
    async def test_context_manager_releases_on_exception(self) -> None:
        backend = InMemoryLockBackend()
        with pytest.raises(RuntimeError):
            async with distributed_lock(
                "exception_test",
                backend=backend,
            ) as acquired:
                assert acquired is True
                raise RuntimeError("boom")

        assert await backend.acquire("exception_test", ttl_s=60) is not None

    @pytest.mark.anyio
    async def test_wait_timeout_returns_false(self) -> None:
        backend = InMemoryLockBackend()
        held = await backend.acquire("busy", ttl_s=60)
        assert held is not None

        started = time.monotonic()
        async with distributed_lock(
            "busy",
            wait_s=0.05,
            poll_interval_s=0.01,
            backend=backend,
        ) as acquired:
            assert acquired is False
        elapsed = time.monotonic() - started
        assert elapsed < 0.2

    @pytest.mark.anyio
    async def test_wait_and_eventually_acquire(self) -> None:
        backend = InMemoryLockBackend()

        async def quick_holder() -> None:
            token = await backend.acquire("contended", ttl_s=60)
            assert token is not None
            await asyncio.sleep(0.05)
            await backend.release("contended", owner_token=token)

        task = asyncio.create_task(quick_holder())
        await asyncio.sleep(0.01)

        async with distributed_lock(
            "contended",
            wait_s=5.0,
            poll_interval_s=0.02,
            backend=backend,
        ) as acquired:
            assert acquired is True

        await task


class TestInvalidConfiguration:
    @pytest.mark.anyio
    async def test_empty_key_rejected(self) -> None:
        with pytest.raises(InvalidLockConfiguration):
            async with distributed_lock(""):
                pass

    @pytest.mark.anyio
    async def test_non_positive_ttl_rejected(self) -> None:
        with pytest.raises(InvalidLockConfiguration):
            async with distributed_lock("k", ttl_s=0):
                pass

    @pytest.mark.anyio
    async def test_negative_wait_rejected(self) -> None:
        with pytest.raises(InvalidLockConfiguration):
            async with distributed_lock("k", wait_s=-1):
                pass

    @pytest.mark.anyio
    async def test_non_positive_poll_rejected(self) -> None:
        with pytest.raises(InvalidLockConfiguration):
            async with distributed_lock("k", poll_interval_s=0):
                pass

    @pytest.mark.anyio
    async def test_unsupported_backend_rejected(self) -> None:
        with pytest.raises(InvalidLockConfiguration):
            get_lock_backend(backend="postgres")

    @pytest.mark.anyio
    async def test_default_ttl_alias(self) -> None:
        assert DEFAULT_LOCK_TTL_S == DEFAULT_TTL_S == 30.0


class TestRedisLockBackend:
    @pytest.mark.anyio
    async def test_acquire_uses_set_nx_px(self) -> None:
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        backend = RedisLockBackend(redis, key_prefix="lock:")

        token = await backend.acquire("job", ttl_s=1.5)
        assert token is not None
        redis.set.assert_awaited_once()
        args, kwargs = redis.set.await_args
        assert args[0] == "lock:job"
        assert args[1] == token
        assert kwargs["nx"] is True
        assert kwargs["px"] == 1500

    @pytest.mark.anyio
    async def test_acquire_returns_none_when_held(self) -> None:
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=None)
        backend = RedisLockBackend(redis)

        assert await backend.acquire("job", ttl_s=30) is None

    @pytest.mark.anyio
    async def test_release_uses_lua_compare_and_delete(self) -> None:
        redis = AsyncMock()
        redis.eval = AsyncMock(return_value=1)
        backend = RedisLockBackend(redis, key_prefix="lock:")

        released = await backend.release(
            "job",
            owner_token="tok-1",
        )
        assert released is True
        redis.eval.assert_awaited_once()
        args = redis.eval.await_args.args
        assert "redis.call" in args[0]
        assert args[1] == 1
        assert args[2] == "lock:job"
        assert args[3] == "tok-1"

    @pytest.mark.anyio
    async def test_release_false_when_not_owner(self) -> None:
        redis = AsyncMock()
        redis.eval = AsyncMock(return_value=0)
        backend = RedisLockBackend(redis)

        released = await backend.release(
            "job",
            owner_token="stale",
        )
        assert released is False

    @pytest.mark.anyio
    async def test_get_lock_backend_redis_caches_client(self) -> None:
        fake_client = MagicMock()
        with patch(
            "{{cookiecutter.project_name}}.stores.redis_store.create_redis_client",
            return_value=fake_client,
        ) as create:
            b1 = get_lock_backend(
                backend="redis",
                redis_url="redis://example/0",
            )
            b2 = get_lock_backend(
                backend="redis",
                redis_url="redis://example/0",
            )
            assert b1 is b2
            create.assert_called_once_with("redis://example/0")

    @pytest.mark.anyio
    async def test_close_lock_backends_closes_redis(self) -> None:
        fake_client = MagicMock()
        fake_client.aclose = AsyncMock()
        with patch(
            "{{cookiecutter.project_name}}.stores.redis_store.create_redis_client",
            return_value=fake_client,
        ):
            get_lock_backend(
                backend="redis",
                redis_url="redis://example/1",
            )
            await close_lock_backends()
            fake_client.aclose.assert_awaited_once()
            assert locks_mod._redis_backend is None
