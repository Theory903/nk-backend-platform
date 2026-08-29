"""Production graceful-shutdown coordinator.

Shutdown sequence:

    signal
      ↓
    readiness = false
      ↓
    stop accepting new work
      ↓
    drain in-flight work
      ↓
    cancel remaining work
      ↓
    run cleanup hooks
      ↓
    complete shutdown

Designed for FastAPI lifespan, workers, DB pools, queues and brokers.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import signal
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

CleanupHook = Callable[[], Any]


class ShutdownError(RuntimeError):
    """Base shutdown error."""


@dataclass(frozen=True, slots=True)
class ShutdownStats:
    """Shutdown execution statistics."""

    tasks_total: int
    tasks_drained: int
    tasks_cancelled: int
    hooks_total: int
    hooks_completed: int
    hooks_failed: int
    timed_out: bool


class ShutdownState:
    """
    Coordinates graceful application shutdown.

    The object is intentionally independent of FastAPI. It can be used by
    HTTP servers, workers, schedulers and background consumers.
    """

    def __init__(
        self,
        *,
        drain_timeout_s: float = 30.0,
        cleanup_timeout_s: float = 15.0,
    ) -> None:
        if drain_timeout_s <= 0:
            raise ValueError(
                "drain_timeout_s must be greater than zero"
            )

        if cleanup_timeout_s <= 0:
            raise ValueError(
                "cleanup_timeout_s must be greater than zero"
            )

        self.drain_timeout_s = drain_timeout_s
        self.cleanup_timeout_s = cleanup_timeout_s

        self._shutting_down = False
        self._completed = False

        self._active_tasks: set[asyncio.Task[Any]] = set()
        self._cleanup_hooks: list[CleanupHook] = []

        self._signal_received = asyncio.Event()
        self._shutdown_complete = asyncio.Event()

        self._lock = Lock()

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    @property
    def is_ready(self) -> bool:
        """Readiness becomes false immediately when shutdown begins."""
        return not self._shutting_down

    @property
    def is_complete(self) -> bool:
        return self._completed

    def register_cleanup(
        self,
        hook: CleanupHook,
    ) -> CleanupHook:
        if self._completed:
            raise ShutdownError(
                "cannot register cleanup after shutdown completed"
            )

        if not callable(hook):
            raise TypeError(
                "cleanup hook must be callable"
            )

        with self._lock:
            self._cleanup_hooks.append(hook)

        return hook

    def track_task(
        self,
        task: asyncio.Task[Any],
    ) -> asyncio.Task[Any]:
        if task.done():
            return task

        self._active_tasks.add(task)

        task.add_done_callback(
            self._active_tasks.discard
        )

        return task

    def untrack_task(
        self,
        task: asyncio.Task[Any],
    ) -> None:
        self._active_tasks.discard(
            task
        )

    def trigger(
        self,
        *,
        reason: str = "signal",
    ) -> bool:
        with self._lock:
            if self._shutting_down:
                return False

            self._shutting_down = True

        logger.info(
            "graceful shutdown initiated: reason=%s",
            reason,
        )

        self._signal_received.set()

        return True

    async def wait_for_signal(self) -> None:
        await self._signal_received.wait()

    async def wait_for_completion(self) -> None:
        await self._shutdown_complete.wait()

    async def drain(
        self,
    ) -> tuple[int, int, bool]:
        pending = {
            task
            for task in self._active_tasks
            if not task.done()
        }

        total = len(pending)

        if not pending:
            return 0, 0, False

        logger.info(
            "draining %d in-flight tasks; timeout=%.1fs",
            total,
            self.drain_timeout_s,
        )

        done, remaining = await asyncio.wait(
            pending,
            timeout=self.drain_timeout_s,
            return_when=asyncio.ALL_COMPLETED,
        )

        if remaining:
            logger.warning(
                "%d tasks exceeded shutdown drain timeout",
                len(remaining),
            )

            for task in remaining:
                task.cancel()

            await self._await_cancelled(
                remaining
            )

        return (
            total,
            len(done),
            bool(remaining),
        )

    async def cleanup(
        self,
    ) -> tuple[int, int, int]:
        hooks = list(
            reversed(
                self._cleanup_hooks
            )
        )

        completed = 0
        failed = 0

        for hook in hooks:
            try:
                await asyncio.wait_for(
                    self._invoke_hook(hook),
                    timeout=self.cleanup_timeout_s,
                )
                completed += 1

            except asyncio.CancelledError:
                raise

            except Exception:
                failed += 1

                logger.exception(
                    "shutdown cleanup hook failed: %r",
                    hook,
                )

        return len(hooks), completed, failed

    async def shutdown(
        self,
    ) -> ShutdownStats:
        if self._completed:
            return ShutdownStats(
                tasks_total=0,
                tasks_drained=0,
                tasks_cancelled=0,
                hooks_total=0,
                hooks_completed=0,
                hooks_failed=0,
                timed_out=False,
            )

        self.trigger(
            reason="shutdown"
        )

        (
            tasks_total,
            tasks_drained,
            timed_out,
        ) = await self.drain()

        tasks_cancelled = max(
            0,
            tasks_total - tasks_drained,
        )

        (
            hooks_total,
            hooks_completed,
            hooks_failed,
        ) = await self.cleanup()

        self._completed = True
        self._shutdown_complete.set()

        stats = ShutdownStats(
            tasks_total=tasks_total,
            tasks_drained=tasks_drained,
            tasks_cancelled=tasks_cancelled,
            hooks_total=hooks_total,
            hooks_completed=hooks_completed,
            hooks_failed=hooks_failed,
            timed_out=timed_out,
        )

        logger.info(
            "graceful shutdown complete: %s",
            stats,
        )

        return stats

    @staticmethod
    async def _invoke_hook(
        hook: CleanupHook,
    ) -> None:
        result = hook()

        if inspect.isawaitable(result):
            await result

    @staticmethod
    async def _await_cancelled(
        tasks: set[asyncio.Task[Any]],
    ) -> None:
        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )


def install_signal_handlers(
    state: ShutdownState,
) -> None:
    loop = asyncio.get_running_loop()

    def handle_signal(
        sig: signal.Signals,
    ) -> None:
        logger.info(
            "received signal: %s",
            sig.name,
        )

        state.trigger(
            reason=sig.name
        )

    for sig in (
        signal.SIGTERM,
        signal.SIGINT,
    ):
        try:
            loop.add_signal_handler(
                sig,
                handle_signal,
                sig,
            )
        except (NotImplementedError, RuntimeError):
            logger.debug(
                "signal handler unavailable: %s",
                sig,
            )


_state: ShutdownState | None = None
_state_lock = Lock()


def get_shutdown_state(
    *,
    drain_timeout_s: float = 30.0,
    cleanup_timeout_s: float = 15.0,
) -> ShutdownState:
    global _state

    if _state is None:
        with _state_lock:
            if _state is None:
                _state = ShutdownState(
                    drain_timeout_s=drain_timeout_s,
                    cleanup_timeout_s=cleanup_timeout_s,
                )

    return _state


def reset_shutdown_state() -> None:
    global _state

    with _state_lock:
        _state = None


__all__ = [
    "CleanupHook",
    "ShutdownError",
    "ShutdownState",
    "ShutdownStats",
    "get_shutdown_state",
    "install_signal_handlers",
    "reset_shutdown_state",
]
