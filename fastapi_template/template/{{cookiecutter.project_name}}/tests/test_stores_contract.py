"""Parametrized contract tests: same suite runs against InMemory and Redis backends."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from {{cookiecutter.project_name}}.stores import (
    InMemoryCounterStore,
    InMemoryExpiringStore,
    InMemorySetStore,
    get_counter_store,
    get_expiring_store,
    get_set_store,
)
from {{cookiecutter.project_name}}.stores.redis_store import create_redis_client


# Contract suite runs against in-memory only here.
# Redis backends are covered by FakeRedis tests in test_core_state.py
# and accessor injection tests below; live Redis is not part of unit CI.
BACKENDS = ["memory"]


@pytest.fixture(params=BACKENDS, ids=[f"backend={b}" for b in BACKENDS])
def expiring_store(request):
    return get_expiring_store(backend=request.param)


@pytest.fixture(params=BACKENDS, ids=[f"backend={b}" for b in BACKENDS])
def set_store(request):
    return get_set_store(backend=request.param)


@pytest.fixture(params=BACKENDS, ids=[f"backend={b}" for b in BACKENDS])
def counter_store(request):
    return get_counter_store(backend=request.param)


class TestLegacyAccessors:
    def test_memory_backend_works(self) -> None:
        assert isinstance(get_expiring_store(backend="memory"), InMemoryExpiringStore)
        assert isinstance(get_set_store(backend="memory"), InMemorySetStore)
        assert isinstance(get_counter_store(backend="memory"), InMemoryCounterStore)

    def test_redis_backend_without_client_raises(self) -> None:
        with pytest.raises(ValueError, match="redis_client"):
            get_expiring_store(backend="redis")
        with pytest.raises(ValueError, match="redis_client"):
            get_set_store(backend="redis")
        with pytest.raises(ValueError, match="redis_client"):
            get_counter_store(backend="redis")

    def test_redis_with_injected_client(self) -> None:
        redis = MagicMock(name="redis_client")
        expiring = get_expiring_store(backend="redis", redis_client=redis)
        sets = get_set_store(backend="redis", redis_client=redis)
        counters = get_counter_store(backend="redis", redis_client=redis)
        assert expiring._redis is redis  # noqa: SLF001
        assert sets._redis is redis  # noqa: SLF001
        assert counters._redis is redis  # noqa: SLF001

    def test_create_redis_client_still_callable(self) -> None:
        sentinel: Any = object()
        with patch(
            "redis.asyncio.from_url",
            return_value=sentinel,
        ) as from_url:
            client = create_redis_client("redis://example/0")
        assert client is sentinel
        from_url.assert_called_once_with(
            "redis://example/0",
            decode_responses=True,
        )

    def test_accessors_have_no_redis_url_param(self) -> None:
        import inspect

        for fn in (get_expiring_store, get_set_store, get_counter_store):
            params = inspect.signature(fn).parameters
            assert "redis_url" not in params
            assert "redis_client" in params


class TestExpiringStoreContract:
    @pytest.mark.asyncio
    async def test_set_and_get(self, expiring_store) -> None:
        await expiring_store.set("k1", {"data": 42}, ttl_s=60)
        assert await expiring_store.get("k1") == {"data": 42}

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, expiring_store) -> None:
        assert await expiring_store.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_delete_removes(self, expiring_store) -> None:
        await expiring_store.set("k2", "value", ttl_s=60)
        assert await expiring_store.delete("k2") is True
        assert await expiring_store.get("k2") is None

    @pytest.mark.asyncio
    async def test_exists_check(self, expiring_store) -> None:
        await expiring_store.set("k3", 123, ttl_s=60)
        assert await expiring_store.exists("k3") is True
        assert await expiring_store.exists("k4") is False


class TestSetStoreContract:
    @pytest.mark.asyncio
    async def test_add_and_contains(self, set_store) -> None:
        await set_store.add("myset", "member_a")
        await set_store.add("myset", "member_b")
        assert await set_store.contains("myset", "member_a") is True
        assert await set_store.contains("myset", "member_c") is False

    @pytest.mark.asyncio
    async def test_remove(self, set_store) -> None:
        await set_store.add("s", "x")
        assert await set_store.remove("s", "x") is True
        assert await set_store.contains("s", "x") is False
        assert await set_store.remove("s", "x") is False

    @pytest.mark.asyncio
    async def test_members(self, set_store) -> None:
        await set_store.add("s2", "a")
        await set_store.add("s2", "b")
        members = await set_store.members("s2")
        assert members == {"a", "b"}


class TestCounterStoreContract:
    @pytest.mark.asyncio
    async def test_increment(self, counter_store) -> None:
        key = f"counter_{id(counter_store)}"
        assert await counter_store.increment(key) == 1
        assert await counter_store.increment(key) == 2
        assert await counter_store.increment(key, 10) == 12

    @pytest.mark.asyncio
    async def test_get_value_default_zero(self, counter_store) -> None:
        assert await counter_store.get_value("nonexistent_counter") == 0
