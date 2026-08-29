"""Tests for graceful shutdown: readiness flip, drain, cleanup, singleton."""

from __future__ import annotations

import asyncio

import pytest

from {{cookiecutter.project_name}}.core.graceful import (
    ShutdownError,
    ShutdownState,
    ShutdownStats,
    get_shutdown_state,
    reset_shutdown_state,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_shutdown_state()
    yield
    reset_shutdown_state()


class TestShutdownState:
    def test_initial_state_ready(self) -> None:
        state = ShutdownState()
        assert not state.is_shutting_down
        assert state.is_ready is True
        assert state.is_complete is False

    def test_readiness_flips_on_trigger(self) -> None:
        state = ShutdownState()
        assert state.is_ready is True

        first = state.trigger(reason="test")
        second = state.trigger(reason="again")

        assert first is True
        assert second is False
        assert state.is_shutting_down is True
        assert state.is_ready is False

    def test_invalid_timeouts_rejected(self) -> None:
        with pytest.raises(ValueError, match="drain_timeout_s"):
            ShutdownState(drain_timeout_s=0)
        with pytest.raises(ValueError, match="cleanup_timeout_s"):
            ShutdownState(cleanup_timeout_s=-1)


class TestDrain:
    @pytest.mark.anyio
    async def test_drain_waits_for_in_flight_tasks(self) -> None:
        state = ShutdownState(drain_timeout_s=5.0)
        completed: list[int] = []

        async def slow_task() -> None:
            await asyncio.sleep(0.05)
            completed.append(1)

        task = asyncio.create_task(slow_task())
        state.track_task(task)

        total, drained, timed_out = await state.drain()

        assert total == 1
        assert drained == 1
        assert timed_out is False
        assert len(completed) == 1
        assert task.done()

    @pytest.mark.anyio
    async def test_drain_timeout_cancels_hung_tasks(self) -> None:
        state = ShutdownState(drain_timeout_s=0.05)

        async def hung_task() -> None:
            await asyncio.sleep(999)

        task = asyncio.create_task(hung_task())
        state.track_task(task)

        total, drained, timed_out = await state.drain()

        assert total == 1
        assert drained == 0
        assert timed_out is True
        assert task.cancelled() or task.done()

    @pytest.mark.anyio
    async def test_untrack_removes_task_from_drain(self) -> None:
        state = ShutdownState(drain_timeout_s=1.0)

        async def hang() -> None:
            await asyncio.sleep(999)

        task = asyncio.create_task(hang())
        state.track_task(task)
        state.untrack_task(task)

        total, drained, timed_out = await state.drain()
        assert total == 0
        assert drained == 0
        assert timed_out is False
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestCleanup:
    @pytest.mark.anyio
    async def test_cleanup_runs_sync_and_async_hooks_in_reverse(self) -> None:
        state = ShutdownState()
        order: list[str] = []

        async def async_hook() -> None:
            order.append("async")

        def sync_hook() -> None:
            order.append("sync")

        state.register_cleanup(async_hook)
        state.register_cleanup(sync_hook)

        hooks_total, completed, failed = await state.cleanup()

        assert hooks_total == 2
        assert completed == 2
        assert failed == 0
        # reverse registration order: sync then async
        assert order == ["sync", "async"]

    @pytest.mark.anyio
    async def test_cleanup_hook_failure_does_not_block_others(self) -> None:
        state = ShutdownState()
        order: list[str] = []

        def bad_hook() -> None:
            raise RuntimeError("cleanup failed")

        def good_hook() -> None:
            order.append("good")

        state.register_cleanup(bad_hook)
        state.register_cleanup(good_hook)

        hooks_total, completed, failed = await state.cleanup()

        assert hooks_total == 2
        assert completed == 1
        assert failed == 1
        assert order == ["good"]

    @pytest.mark.anyio
    async def test_register_after_complete_raises(self) -> None:
        state = ShutdownState()
        await state.shutdown()

        with pytest.raises(ShutdownError, match="cannot register cleanup"):
            state.register_cleanup(lambda: None)


class TestShutdownLifecycle:
    @pytest.mark.anyio
    async def test_shutdown_returns_stats(self) -> None:
        state = ShutdownState(drain_timeout_s=2.0)
        ran: list[str] = []

        async def work() -> None:
            await asyncio.sleep(0.01)
            ran.append("work")

        def hook() -> None:
            ran.append("hook")

        state.track_task(asyncio.create_task(work()))
        state.register_cleanup(hook)

        stats = await state.shutdown()

        assert isinstance(stats, ShutdownStats)
        assert stats.tasks_total == 1
        assert stats.tasks_drained == 1
        assert stats.tasks_cancelled == 0
        assert stats.hooks_total == 1
        assert stats.hooks_completed == 1
        assert stats.hooks_failed == 0
        assert stats.timed_out is False
        assert state.is_complete is True
        assert state.is_ready is False
        assert ran == ["work", "hook"]

    @pytest.mark.anyio
    async def test_shutdown_is_idempotent(self) -> None:
        state = ShutdownState()
        hooks: list[int] = []
        state.register_cleanup(lambda: hooks.append(1))

        first = await state.shutdown()
        second = await state.shutdown()

        assert first.hooks_completed == 1
        assert second == ShutdownStats(
            tasks_total=0,
            tasks_drained=0,
            tasks_cancelled=0,
            hooks_total=0,
            hooks_completed=0,
            hooks_failed=0,
            timed_out=False,
        )
        assert hooks == [1]

    @pytest.mark.anyio
    async def test_wait_for_signal_and_completion(self) -> None:
        state = ShutdownState()

        async def waiter() -> None:
            await state.wait_for_signal()
            await state.shutdown()

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0)
        assert state.trigger() is True
        await state.wait_for_completion()
        await task
        assert state.is_complete is True


class TestSingleton:
    def test_get_returns_same_instance(self) -> None:
        a = get_shutdown_state()
        b = get_shutdown_state()
        assert a is b

    def test_reset_creates_new_instance(self) -> None:
        a = get_shutdown_state()
        reset_shutdown_state()
        b = get_shutdown_state()
        assert a is not b
