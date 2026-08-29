import asyncio
import inspect
import logging
from typing import Any

from {{cookiecutter.project_name}}.workflows.definitions import Step, Workflow, WorkflowResult

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """Sequential executor with retries, compensation, and approval gates."""

    def __init__(
        self,
        approve_fn: Any | None = None,
    ) -> None:
        """
        :param approve_fn: async callable(step, ctx) -> bool for HITL gates.
        """
        self.approve_fn = approve_fn

    async def run(self, workflow: Workflow, initial_ctx: dict[str, Any] | None = None) -> WorkflowResult:
        errors = workflow.validate()
        if errors:
            return WorkflowResult(workflow_name=workflow.name, status="invalid", error="; ".join(errors))

        ctx: dict[str, Any] = dict(initial_ctx or {})
        completed: list[str] = []
        done_steps: list[Step] = []

        for step in workflow.steps:
            if step.requires_approval and self.approve_fn is not None:
                approved = await self.approve_fn(step, ctx)  # type: ignore[misc]
                if not approved:
                    await self._compensate(done_steps, ctx)
                    return WorkflowResult(
                        workflow_name=workflow.name,
                        status="rejected",
                        completed_steps=completed,
                        failed_step=step.name,
                        error=f"approval denied at step '{step.name}'",
                    )

            result = await self._execute_with_retry(step, ctx)
            if isinstance(result, Exception):
                await self._compensate(done_steps, ctx)
                return WorkflowResult(
                    workflow_name=workflow.name,
                    status="failed",
                    completed_steps=completed,
                    failed_step=step.name,
                    error=str(result),
                    outputs=ctx,
                )
            ctx[step.name] = result
            completed.append(step.name)
            done_steps.append(step)

        return WorkflowResult(
            workflow_name=workflow.name,
            status="completed",
            completed_steps=completed,
            outputs=ctx,
        )

    async def _execute_with_retry(self, step: Step, ctx: dict[str, Any]) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1 + step.max_retries):
            try:
                result = step.fn(ctx) if not inspect.iscoroutinefunction(step.fn) else await step.fn(ctx)
                return result
            except Exception as exc:
                last_exc = exc
                logger.warning("step '%s' attempt %d/%d failed: %s", step.name, attempt + 1, 1 + step.max_retries, exc)
                if attempt < step.max_retries:
                    await asyncio.sleep(0.1 * (attempt + 1))
        return last_exc

    async def _compensate(self, done_steps: list[Step], ctx: dict[str, Any]) -> None:
        for step in reversed(done_steps):
            if step.compensate is not None:
                try:
                    if inspect.iscoroutinefunction(step.compensate):
                        await step.compensate(ctx)
                    else:
                        step.compensate(ctx)
                except Exception as exc:
                    logger.error("compensation for '%s' failed: %s", step.name, exc)
