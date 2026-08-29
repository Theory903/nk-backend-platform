"""Tests for async platform state primitives in core.state."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from {{cookiecutter.project_name}}.core.state import (
    InMemoryCounterStore,
    InMemoryExpiringStore,
    InMemorySetStore,
    RedisCounterStore,
    RedisExpiringStore,
    RedisSetStore,
    StateNamespace,
    create_state_stores,
)


class TestInMemoryExpiringStore:
    @pytest.mark.asyncio
    async def test_set_get_ttl_expire_delete(self) -> None:
        store = InMemoryExpiringStore[str]()
        await store.set("k", "v", ttl_s=60)
        assert await store.get("k") == "v"
        assert await store.exists("k") is True

        remaining = await store.ttl("k")
        assert remaining is not None
        assert 0 < remaining <= 60

        assert await store.expire("k", ttl_s=120) is True
        remaining2 = await store.ttl("k")
        assert remaining2 is not None
        assert remaining2 > remaining

        assert await store.delete("k") is True
        assert await store.get("k") is None
        assert await store.exists("k") is False

    @pytest.mark.asyncio
    async def test_set_if_absent_race(self) -> None:
        store = InMemoryExpiringStore[str]()
        first = await store.set_if_absent("token", "a", ttl_s=30)
        second = await store.set_if_absent("token", "b", ttl_s=30)
        assert first is True
        assert second is False
        assert await store.get("token") == "a"

    @pytest.mark.asyncio
    async def test_expired_get_returns_none(self) -> None:
        store = InMemoryExpiringStore[str]()
        await store.set("gone", "x", ttl_s=0.05)
        await asyncio.sleep(0.06)
        assert await store.get("gone") is None
        assert await store.ttl("gone") is None


class TestInMemorySetStore:
    @pytest.mark.asyncio
    async def test_add_contains_remove_members_clear(self) -> None:
        store = InMemorySetStore()
        assert await store.add("revoked", "a") is True
        assert await store.add("revoked", "a") is False
        await store.add("revoked", "b")
        assert await store.contains("revoked", "a") is True
        assert await store.members("revoked") == {"a", "b"}
        assert await store.remove("revoked", "a") is True
        assert await store.contains("revoked", "a") is False
        assert await store.clear("revoked") is True
        assert await store.members("revoked") == set()


class TestInMemoryCounterStore:
    @pytest.mark.asyncio
    async def test_increment_ttl_get_delete_expire(self) -> None:
        store = InMemoryCounterStore()
        assert await store.increment("hits", ttl_s=0.05) == 1
        assert await store.increment("hits", 2, ttl_s=0.05) == 3
        assert await store.get_value("hits") == 3
        assert await store.delete("hits") is True
        assert await store.get_value("hits") == 0

        await store.increment("ephemeral", ttl_s=0.05)
        await asyncio.sleep(0.06)
        assert await store.get_value("ephemeral") == 0


class TestStateNamespace:
    def test_key_and_scoped_format(self) -> None:
        ns = StateNamespace()
        assert ns.key("oauth", "abc") == "nk:oauth:abc"

        scoped = ns.scoped("sessions", org_id="org1", user_id="u1")
        assert scoped == "nk:sessions:org:org1:user:u1"

        org_only = ns.scoped("rate-limit", org_id="org1")
        assert org_only == "nk:rate-limit:org:org1"

        custom = StateNamespace(prefix="app")
        assert custom.key("csrf", "x") == "app:csrf:x"


class TestCreateStateStores:
    def test_memory_bundle(self) -> None:
        stores = create_state_stores(backend="memory", prefix="nk")
        assert isinstance(stores.expiring, InMemoryExpiringStore)
        assert isinstance(stores.sets, InMemorySetStore)
        assert isinstance(stores.counters, InMemoryCounterStore)
        assert stores.namespace.prefix == "nk"

    def test_redis_requires_client(self) -> None:
        with pytest.raises(ValueError, match="redis_client"):
            create_state_stores(backend="redis")

    def test_unsupported_backend(self) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            create_state_stores(backend="postgres")

    def test_create_state_stores_signature_has_no_redis_url(self) -> None:
        import inspect

        params = inspect.signature(create_state_stores).parameters
        assert "redis_url" not in params
        assert "redis_client" in params


class FakeRedis:
    """Minimal async Redis stub for unit tests."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.ttls: dict[str, int] = {}
        self.set_calls: list[dict[str, Any]] = []
        self.eval_calls: list[tuple[Any, ...]] = []

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        self.set_calls.append({"key": key, "value": value, "ex": ex, "nx": nx})
        if nx and key in self.data:
            return None
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def get(self, key: str) -> Any | None:
        return self.data.get(key)

    async def delete(self, key: str) -> int:
        existed = 1 if key in self.data else 0
        self.data.pop(key, None)
        self.ttls.pop(key, None)
        return existed

    async def exists(self, key: str) -> int:
        return 1 if key in self.data else 0

    async def expire(self, key: str, seconds: int) -> int:
        if key not in self.data:
            return 0
        self.ttls[key] = seconds
        return 1

    async def ttl(self, key: str) -> int:
        if key not in self.data:
            return -2
        return self.ttls.get(key, -1)

    async def sadd(self, key: str, member: str) -> int:
        bucket = self.data.setdefault(key, set())
        before = len(bucket)
        bucket.add(member)
        return 0 if len(bucket) == before else 1

    async def srem(self, key: str, member: str) -> int:
        bucket = self.data.get(key)
        if not bucket or member not in bucket:
            return 0
        bucket.remove(member)
        return 1

    async def sismember(self, key: str, member: str) -> int:
        return 1 if member in self.data.get(key, set()) else 0

    async def smembers(self, key: str) -> set[str]:
        return set(self.data.get(key, set()))

    async def eval(self, script: str, numkeys: int, *args: Any) -> int:
        self.eval_calls.append((script, numkeys, *args))
        key = args[0]
        amount = int(args[1])
        ttl = int(args[2])
        current = int(self.data.get(key, 0)) + amount
        self.data[key] = str(current)
        # Mirror Lua: expire only on first create (value == amount)
        if ttl != 0 and current == amount:
            self.ttls[key] = ttl
        return current


class TestRedisStoresWithFake:
    @pytest.mark.asyncio
    async def test_expiring_set_nx_and_roundtrip(self) -> None:
        redis = FakeRedis()
        store = RedisExpiringStore(redis)
        await store.set("k", {"n": 1}, ttl_s=30)
        assert await store.get("k") == {"n": 1}

        assert await store.set_if_absent("k", {"n": 2}, ttl_s=30) is False
        nx_calls = [c for c in redis.set_calls if c["nx"] is True]
        assert len(nx_calls) == 1
        assert nx_calls[0]["ex"] == 30

        assert await store.set_if_absent("fresh", "ok", ttl_s=10) is True
        assert json.loads(redis.data["fresh"]) == "ok"

    @pytest.mark.asyncio
    async def test_set_store_ops(self) -> None:
        redis = FakeRedis()
        store = RedisSetStore(redis)
        assert await store.add("s", "m1") is True
        assert await store.contains("s", "m1") is True
        assert await store.members("s") == {"m1"}
        assert await store.remove("s", "m1") is True
        await store.add("s", "m2")
        assert await store.clear("s") is True
        assert await store.clear("missing") is False

    @pytest.mark.asyncio
    async def test_counter_lua_first_increment_sets_ttl(self) -> None:
        redis = FakeRedis()
        store = RedisCounterStore(redis)
        assert await store.increment("c", ttl_s=60) == 1
        assert redis.ttls["c"] == 60
        assert await store.increment("c", 5, ttl_s=60) == 6
        # TTL not refreshed on subsequent increments (Lua first-create only)
        assert redis.ttls["c"] == 60
        assert len(redis.eval_calls) == 2
        assert "INCRBY" in redis.eval_calls[0][0]
        assert await store.get_value("c") == 6
        assert await store.delete("c") is True

    def test_create_state_stores_redis(self) -> None:
        redis = FakeRedis()
        stores = create_state_stores(backend="redis", redis_client=redis)
        assert isinstance(stores.expiring, RedisExpiringStore)
        assert isinstance(stores.sets, RedisSetStore)
        assert isinstance(stores.counters, RedisCounterStore)
