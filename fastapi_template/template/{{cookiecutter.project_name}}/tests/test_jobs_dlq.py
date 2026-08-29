"""Tests for jobs TaskEnqueuer, RetryPolicy, circuit breaker, and DLQ."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from {{cookiecutter.project_name}}.core.circuit_breaker import CircuitBreaker
from {{cookiecutter.project_name}}.jobs import (
    InMemoryDeadLetterQueue,
    RetryPolicy,
    TaskEnqueuer,
    enqueue,
    get_enqueuer,
)


@dataclass
class _FakeResult:
    task_id: str


class _FakeTask:
    def __init__(
        self,
        *,
        fail_times: int = 0,
        task_id: str = "task_ok",
    ) -> None:
        self.fail_times = fail_times
        self.task_id = task_id
        self.calls = 0

    async def kiq(self, payload: dict[str, Any]) -> _FakeResult:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"broker failure #{self.calls}")
        return _FakeResult(task_id=self.task_id)


class _FakeBroker:
    def __init__(self, tasks: dict[str, _FakeTask] | None = None) -> None:
        self._tasks = tasks or {}

    def find_task(self, task_name: str) -> _FakeTask | None:
        return self._tasks.get(task_name)


def _fast_policy(*, max_attempts: int = 3) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=max_attempts,
        base_delay_s=0.0,
        multiplier=1.0,
        max_delay_s=0.0,
        jitter=False,
    )


def _enqueuer(
    broker: _FakeBroker,
    *,
    dlq: InMemoryDeadLetterQueue | None = None,
    breaker: CircuitBreaker | None = None,
    retry_policy: RetryPolicy | None = None,
) -> TaskEnqueuer:
    return TaskEnqueuer(
        dlq=dlq or InMemoryDeadLetterQueue(),
        breaker=breaker or CircuitBreaker(failure_threshold=100),
        retry_policy=retry_policy or _fast_policy(),
        broker_loader=lambda: broker,
    )


@pytest.mark.anyio
async def test_successful_enqueue_returns_task_id() -> None:
    task = _FakeTask(task_id="tid-1")
    enq = _enqueuer(_FakeBroker({"email.send": task}))

    result = await enq.enqueue("email.send", {"to": "a@x"})

    assert result.accepted is True
    assert result.task_id == "tid-1"
    assert result.attempts == 1
    assert result.dlq_id is None
    assert task.calls == 1


@pytest.mark.anyio
async def test_retries_then_dlq_on_persistent_failure() -> None:
    task = _FakeTask(fail_times=10)
    dlq = InMemoryDeadLetterQueue()
    enq = _enqueuer(
        _FakeBroker({"email.send": task}),
        dlq=dlq,
        retry_policy=_fast_policy(max_attempts=3),
    )

    result = await enq.enqueue("email.send", {"to": "a@x"})

    assert result.accepted is False
    assert result.attempts == 3
    assert result.dlq_id is not None
    assert task.calls == 3
    item = await dlq.get(result.dlq_id)
    assert item is not None
    assert item.task_name == "email.send"
    assert item.reason == "enqueue_failed"
    assert item.attempts == 3
    assert "broker failure" in (item.last_error or "")


@pytest.mark.anyio
async def test_compat_enqueue_honors_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _FakeTask(fail_times=10)
    dlq = InMemoryDeadLetterQueue()
    breaker = CircuitBreaker(failure_threshold=100)
    enq = TaskEnqueuer(
        dlq=dlq,
        breaker=breaker,
        retry_policy=_fast_policy(max_attempts=9),
        broker_loader=lambda: _FakeBroker({"jobs.work": task}),
    )
    monkeypatch.setattr(
        "{{cookiecutter.project_name}}.jobs.get_enqueuer",
        lambda: enq,
    )

    task_id = await enqueue("jobs.work", {"n": 1}, retries=2)

    assert task_id is None
    assert task.calls == 2
    items = await dlq.list()
    assert len(items) == 1
    assert items[0].attempts == 2


@pytest.mark.anyio
async def test_circuit_open_fails_to_dlq() -> None:
    task = _FakeTask()
    dlq = InMemoryDeadLetterQueue()
    breaker = CircuitBreaker(
        failure_threshold=1,
        reset_timeout_s=60.0,
    )
    # Trip the breaker before enqueue.
    breaker.record_failure()
    assert breaker.allow() is False

    enq = _enqueuer(
        _FakeBroker({"email.send": task}),
        dlq=dlq,
        breaker=breaker,
        retry_policy=_fast_policy(max_attempts=1),
    )

    result = await enq.enqueue("email.send", {"to": "a@x"})

    assert result.accepted is False
    assert result.dlq_id is not None
    assert "circuit breaker is open" in (result.error or "")
    assert task.calls == 0
    item = await dlq.get(result.dlq_id)
    assert item is not None
    assert item.reason == "enqueue_failed"


@pytest.mark.anyio
async def test_dlq_list_get_remove() -> None:
    dlq = InMemoryDeadLetterQueue()

    id1 = await dlq.push(
        task_name="a",
        payload={"x": 1},
        reason="r1",
        attempts=1,
        last_error="e1",
    )
    id2 = await dlq.push(
        task_name="b",
        payload={"y": 2},
        reason="r2",
        attempts=2,
    )

    items = await dlq.list(limit=10)
    assert [i.id for i in items] == [id1, id2]

    got = await dlq.get(id1)
    assert got is not None
    assert got.task_name == "a"
    assert got.payload == {"x": 1}
    assert got.last_error == "e1"

    assert await dlq.remove(id1) is True
    assert await dlq.get(id1) is None
    assert await dlq.remove(id1) is False
    remaining = await dlq.list()
    assert len(remaining) == 1
    assert remaining[0].id == id2


@pytest.mark.anyio
async def test_missing_task_goes_to_dlq() -> None:
    dlq = InMemoryDeadLetterQueue()
    enq = _enqueuer(
        _FakeBroker({}),
        dlq=dlq,
        retry_policy=_fast_policy(max_attempts=2),
    )

    result = await enq.enqueue("missing.task", {"z": 1})

    assert result.accepted is False
    assert result.attempts == 2
    assert result.dlq_id is not None
    assert "task not found" in (result.error or "")
    item = await dlq.get(result.dlq_id)
    assert item is not None
    assert item.task_name == "missing.task"


@pytest.mark.anyio
async def test_retry_then_success() -> None:
    task = _FakeTask(fail_times=2, task_id="recovered")
    enq = _enqueuer(
        _FakeBroker({"email.send": task}),
        retry_policy=_fast_policy(max_attempts=3),
    )

    result = await enq.enqueue("email.send", {})

    assert result.accepted is True
    assert result.task_id == "recovered"
    assert result.attempts == 3
    assert task.calls == 3


def test_process_defaults_expose_enqueuer() -> None:
    assert get_enqueuer() is not None
