"""Tests for Redis-backed agent memory (P1)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.agents.memory_redis import RedisMemoryStore


class _FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    def pipeline(self) -> "_FakePipeline":
        return _FakePipeline(self)

    def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self.lists.get(key, [])
        if not items:
            return []
        if end == -1:
            end = len(items) - 1
        return items[start : end + 1]

    def ltrim(self, key: str, start: int, end: int) -> None:
        items = self.lists.get(key, [])
        self.lists[key] = items[start : end + 1]

    def delete(self, key: str) -> None:
        self.lists.pop(key, None)

    def lrem(self, key: str, count: int, value: str) -> int:
        items = self.lists.get(key, [])
        if value not in items:
            return 0
        items.remove(value)
        return 1


class _FakePipeline:
    def __init__(self, client: _FakeRedis) -> None:
        self._client = client
        self._ops: list[tuple[str, tuple[object, ...]]] = []

    def rpush(self, key: str, value: str) -> None:
        self._ops.append(("rpush", (key, value)))

    def ltrim(self, key: str, start: int, end: int) -> None:
        self._ops.append(("ltrim", (key, start, end)))

    def execute(self) -> None:
        for op, args in self._ops:
            if op == "rpush":
                self._client.rpush(str(args[0]), str(args[1]))
            elif op == "ltrim":
                self._client.ltrim(str(args[0]), int(args[1]), int(args[2]))
        self._ops.clear()


def test_redis_memory_remember_and_recall() -> None:
    store = RedisMemoryStore(_FakeRedis(), prefix="test")
    store.remember("user-1", "likes pizza")
    store.remember("user-1", "has a dog")
    facts = store.recall("user-1")
    assert facts == ["likes pizza", "has a dog"]


def test_redis_memory_skips_duplicate_facts() -> None:
    client = _FakeRedis()
    store = RedisMemoryStore(client, prefix="test")
    store.remember("user-1", "same fact")
    store.remember("user-1", "same fact")
    assert client.lists["test:episodic:user-1"] == ["same fact"]
