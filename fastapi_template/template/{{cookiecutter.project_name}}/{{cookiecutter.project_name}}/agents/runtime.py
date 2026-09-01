"""Bounded Observe → Reason → Act → Verify workflow runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from {{cookiecutter.project_name}}.platform.contracts import (
    Scope,
    ToolInvocation,
    ToolResult,
    WorkflowState,
    WorkflowStatus,
)
from {{cookiecutter.project_name}}.platform.state import StateStore


class RuntimeStep(StrEnum):
    OBSERVE = "observe"
    REASON = "reason"
    ACT = "act"
    VERIFY = "verify"


class RuntimeCancelled(RuntimeError):
    """Raised when an execution is cancelled between workflow steps."""


class RuntimeFailed(RuntimeError):
    """Raised when a bounded workflow cannot recover."""


class CheckpointStore(Protocol):
    async def save(self, state: WorkflowState) -> None: ...

    async def load(self, workflow_id: str) -> WorkflowState | None: ...

    async def claim_action(self, workflow_id: str, action_id: str) -> bool: ...


class InMemoryCheckpointStore:
    """Development checkpoint store with copy-on-write semantics."""

    def __init__(self) -> None:
        self._states: dict[str, WorkflowState] = {}
        self._claims: set[tuple[str, str]] = set()

    async def save(self, state: WorkflowState) -> None:
        self._states[str(state.workflow_id)] = state.model_copy(deep=True)

    async def load(self, workflow_id: str) -> WorkflowState | None:
        state = self._states.get(workflow_id)
        return state.model_copy(deep=True) if state is not None else None

    async def claim_action(self, workflow_id: str, action_id: str) -> bool:
        claim = (workflow_id, action_id)
        if claim in self._claims:
            return False
        self._claims.add(claim)
        return True


class StateCheckpointStore:
    """Bridge the agent checkpoint contract to the durable state protocol."""

    def __init__(self, store: StateStore, scope: Scope) -> None:
        self._store = store
        self._scope = scope

    async def save(self, state: WorkflowState) -> None:
        save_checkpoint = getattr(self._store, "save_checkpoint", None)
        if save_checkpoint is None:
            raise TypeError("configured state store does not support checkpoints")
        await save_checkpoint(state)

    async def load(self, workflow_id: str) -> WorkflowState | None:
        load_checkpoint = getattr(self._store, "load_checkpoint", None)
        if load_checkpoint is None:
            raise TypeError("configured state store does not support checkpoints")
        from uuid import UUID

        return await load_checkpoint(self._scope, UUID(workflow_id))

    async def claim_action(self, workflow_id: str, action_id: str) -> bool:
        claim = getattr(self._store, "claim_idempotency", None)
        if claim is None:
            raise TypeError("configured state store does not support action claims")
        return await claim(
            self._scope,
            f"workflow:{workflow_id}:action:{action_id}",
        )


class CancellationToken:
    """Cooperative cancellation shared by request and worker boundaries."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()


@dataclass(frozen=True, slots=True)
class RuntimeLimits:
    """Hard execution limits; no runtime may silently exceed them."""

    max_cycles: int = 10
    max_retries: int = 1

    def __post_init__(self) -> None:
        if self.max_cycles < 1:
            raise ValueError("max_cycles must be >= 1")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")


StepHandler = Callable[
    [WorkflowState, RuntimeStep],
    Awaitable[WorkflowState],
]
ApprovalHandler = Callable[[WorkflowState], Awaitable[bool]]
PostCondition = Callable[[WorkflowState], Awaitable[bool]]
ActionExecutor = Callable[[ToolInvocation], Awaitable[ToolResult]]


@dataclass
class BoundedRuntime:
    """Restartable state machine with checkpoint and side-effect guards."""

    scope: Scope
    handler: StepHandler
    limits: RuntimeLimits = field(default_factory=RuntimeLimits)
    checkpoints: CheckpointStore | None = None
    action_executor: ActionExecutor | None = None
    approval: ApprovalHandler | None = None
    post_condition: PostCondition | None = None
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    _completed_actions: set[str] = field(default_factory=set, init=False)

    async def run(
        self,
        *,
        state: WorkflowState | None = None,
        resume_workflow_id: str | None = None,
    ) -> WorkflowState:
        """Execute or resume a bounded workflow."""
        current = state
        if current is None and resume_workflow_id and self.checkpoints is not None:
            current = await self.checkpoints.load(resume_workflow_id)
        if current is None:
            current = WorkflowState(scope=self.scope)

        current = current.model_copy(deep=True)
        if current.scope != self.scope:
            raise RuntimeFailed("workflow checkpoint belongs to another scope")
        stored_actions = current.data.get("completed_action_ids", [])
        self._completed_actions.update(str(action_id) for action_id in stored_actions)
        current.status = WorkflowStatus.RUNNING

        for _ in range(self.limits.max_cycles):
            for step in RuntimeStep:
                self._check_cancelled()
                current.step = step.value
                current.revision += 1

                if step is RuntimeStep.ACT and current.pending_actions:
                    self._validate_action_scopes(current)
                    await self._approve(current)
                    current = await self._run_actions_once(current)
                    # Persist the idempotency barrier before invoking a
                    # side-effecting handler.  Production stores should make
                    # this claim atomic across workers.
                    await self._checkpoint(current)

                current = await self._call_with_retry(current, step)
                if current.scope != self.scope:
                    raise RuntimeFailed(
                        "workflow handler changed the execution scope",
                    )
                if step is RuntimeStep.ACT:
                    current.pending_actions = []
                if step is RuntimeStep.VERIFY and self.post_condition is not None:
                    if not await self.post_condition(current):
                        current.status = WorkflowStatus.FAILED
                        raise RuntimeFailed("workflow post-condition failed")
                await self._checkpoint(current)

            if current.status is WorkflowStatus.COMPLETED:
                return current
            current.status = WorkflowStatus.COMPLETED
            await self._checkpoint(current)
            return current

        current.status = WorkflowStatus.FAILED
        await self._checkpoint(current)
        raise RuntimeFailed("workflow exceeded max_cycles")

    async def _call_with_retry(
        self,
        state: WorkflowState,
        step: RuntimeStep,
    ) -> WorkflowState:
        for attempt in range(self.limits.max_retries + 1):
            try:
                return await self.handler(state, step)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # An ACT handler may have committed an external side effect
                # before raising. Never replay a claimed action automatically.
                if step is RuntimeStep.ACT:
                    state.status = WorkflowStatus.FAILED
                    raise RuntimeFailed(
                        "side-effect step failed; manual recovery is required",
                    ) from exc
                if attempt >= self.limits.max_retries:
                    state.status = WorkflowStatus.FAILED
                    raise RuntimeFailed(
                        f"{step.value} failed after {attempt + 1} attempts",
                    ) from exc
        raise AssertionError("unreachable")

    async def _run_actions_once(self, state: WorkflowState) -> WorkflowState:
        """Claim and execute actions, recording results for resume/inspection."""
        if state.pending_actions and self.action_executor is None:
            raise RuntimeFailed(
                "workflow has actions but no action executor is configured",
            )
        results = list(state.data.get("tool_results", []))
        for action in state.pending_actions:
            action_id = str(action.call_id)
            if not _scope_allows_action(self.scope, action.scope):
                raise RuntimeFailed(
                    f"action {action_id} belongs to another execution scope",
                )
            if not await self._claim_action(str(state.workflow_id), action_id):
                continue
            result = await self.action_executor(action)
            results.append(result.model_dump(mode="json"))
            self._completed_actions.add(action_id)
        state.data["completed_action_ids"] = sorted(self._completed_actions)
        state.data["tool_results"] = results
        state.pending_actions = []
        return state

    def _validate_action_scopes(self, state: WorkflowState) -> None:
        """Reject unauthorized actions before approval or execution."""
        for action in state.pending_actions:
            if not _scope_allows_action(self.scope, action.scope):
                raise RuntimeFailed(
                    f"action {action.call_id} belongs to another execution scope",
                )

    async def _claim_action(self, workflow_id: str, action_id: str) -> bool:
        if self.checkpoints is not None:
            claim_action = getattr(self.checkpoints, "claim_action", None)
            if callable(claim_action):
                return await claim_action(workflow_id, action_id)
        return action_id not in self._completed_actions

    async def _approve(self, state: WorkflowState) -> None:
        if self.approval is None:
            return
        state.status = WorkflowStatus.WAITING_APPROVAL
        if not await self.approval(state):
            state.status = WorkflowStatus.FAILED
            raise RuntimeFailed("workflow action rejected by approval policy")
        state.status = WorkflowStatus.RUNNING

    async def _checkpoint(self, state: WorkflowState) -> None:
        if self.checkpoints is not None:
            await self.checkpoints.save(state)

    def _check_cancelled(self) -> None:
        if self.cancellation.cancelled:
            raise RuntimeCancelled("workflow cancelled")


def _scope_allows_action(runtime_scope: Scope, action_scope: Scope) -> bool:
    """Require identity and tenant equality before any tool side effect."""
    return (
        runtime_scope.principal_id == action_scope.principal_id
        and runtime_scope.organization_id == action_scope.organization_id
        and (
            action_scope.project_id is None
            or action_scope.project_id == runtime_scope.project_id
        )
        and (
            action_scope.thread_id is None
            or action_scope.thread_id == runtime_scope.thread_id
        )
        and (
            action_scope.run_id is None
            or action_scope.run_id == runtime_scope.run_id
        )
    )


__all__ = [
    "BoundedRuntime",
    "ActionExecutor",
    "CancellationToken",
    "CheckpointStore",
    "InMemoryCheckpointStore",
    "RuntimeCancelled",
    "RuntimeFailed",
    "RuntimeLimits",
    "RuntimeStep",
    "PostCondition",
    "StateCheckpointStore",
]
