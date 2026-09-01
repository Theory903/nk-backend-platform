"""Multi-agent supervisor runtime (P3)."""

from __future__ import annotations

import re

from {{cookiecutter.project_name}}.ai.gateway.router import get_router
from {{cookiecutter.project_name}}.ai.llm import Message
from {{cookiecutter.project_name}}.agents.budgets import Budget
from {{cookiecutter.project_name}}.agents.guardrails import Guardrails
from {{cookiecutter.project_name}}.agents.loop import LoopRuntime
from {{cookiecutter.project_name}}.agents.runtime import CancellationToken
from {{cookiecutter.project_name}}.agents.security import SecurityPipeline
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.agents.types import AgentResult, RuntimeMode, WorkerSpec
from {{cookiecutter.project_name}}.platform.contracts import Scope


_DEFAULT_WORKERS = (
    WorkerSpec(
        name="researcher",
        capability="fast",
        system_prompt="You are a researcher. Gather facts and cite sources briefly.",
    ),
    WorkerSpec(
        name="executor",
        capability="chat",
        system_prompt="You are an executor. Produce a concise deliverable.",
    ),
)


def _parse_subtasks(plan_text: str, *, max_tasks: int = 4) -> list[str]:
    lines = [line.strip() for line in plan_text.splitlines() if line.strip()]
    numbered = [
        re.sub(r"^\d+[\).\s-]+", "", line).strip()
        for line in lines
        if re.match(r"^\d+[\).\s-]", line)
    ]
    if numbered:
        return numbered[:max_tasks]
    bullets = [
        re.sub(r"^[-*•]\s+", "", line).strip()
        for line in lines
        if line.startswith(("-", "*", "•"))
    ]
    if bullets:
        return bullets[:max_tasks]
    if len(lines) <= max_tasks:
        return lines
    return [plan_text.strip()]


class SupervisorRuntime:
    """Planner + worker delegation + synthesis."""

    __slots__ = (
        "_tools",
        "_workers",
        "_scope",
        "_guardrails",
        "_budget",
        "_security",
        "_cancellation",
    )

    def __init__(
        self,
        tools: ToolRegistry,
        *,
        workers: list[WorkerSpec] | None = None,
        scope: Scope,
        guardrails: Guardrails | None = None,
        budget: Budget | None = None,
        security: SecurityPipeline | None = None,
        cancellation: CancellationToken | None = None,
        gateway: Any | None = None,
        recorder: Any | None = None,
    ) -> None:
        if scope is None:
            raise ValueError("scope is required for supervisor execution")
        self._tools = tools
        self._workers = tuple(workers or _DEFAULT_WORKERS)
        if not self._workers:
            raise ValueError("at least one worker is required")
        self._scope = scope
        self._guardrails = guardrails or Guardrails()
        self._budget = budget or Budget(max_steps=20)
        self._security = security or SecurityPipeline()
        self._cancellation = cancellation
        self._gateway = gateway
        self._recorder = recorder

    def _check_cancelled(self) -> None:
        if self._cancellation is not None and self._cancellation.cancelled:
            from {{cookiecutter.project_name}}.agents.runtime import RuntimeCancelled

            raise RuntimeCancelled("supervisor runtime cancelled")

    async def run(self, task: str) -> AgentResult:
        task = task.strip()
        if not task:
            raise ValueError("task cannot be empty")

        self._check_cancelled()
        router = get_router()
        planner = router.model_for_capability("reasoning")
        plan_reply = await planner.complete(
            [
                Message(
                    role="system",
                    content=(
                        "Decompose the user goal into numbered subtasks "
                        "(max 4). Output only the list."
                    ),
                ),
                Message(role="user", content=task),
            ],
            tools=[],
        )
        subtasks = _parse_subtasks(plan_reply.content or task)
        trace: list[tuple[str, ...]] = [("plan", str(len(subtasks)))]
        worker_outputs: list[str] = []
        total_steps = 0

        for index, subtask in enumerate(subtasks):
            self._check_cancelled()
            worker = self._workers[index % len(self._workers)]
            worker_model = router.model_for_capability(worker.capability)
            loop = LoopRuntime(
                worker_model,
                self._tools,
                scope=self._scope,
                guardrails=self._guardrails,
                budget=Budget(max_steps=min(8, self._budget.max_steps)),
                system_prompt=worker.system_prompt,
                security=self._security,
                cancellation=self._cancellation,
                gateway=self._gateway,
                recorder=self._recorder,
            )
            result = await loop.run(subtask)
            total_steps += result.steps
            trace.append(("worker", worker.name))
            worker_outputs.append(f"## {worker.name}\n{result.content or ''}")

        self._check_cancelled()
        synthesizer = router.model_for_capability("reasoning")
        synthesis = await synthesizer.complete(
            [
                Message(
                    role="system",
                    content="Synthesize worker outputs into one final answer.",
                ),
                Message(
                    role="user",
                    content=(
                        f"Goal:\n{task}\n\nWorker outputs:\n"
                        + "\n\n".join(worker_outputs)
                    ),
                ),
            ],
            tools=[],
        )
        trace.append(("final",))
        return AgentResult(
            content=synthesis.content,
            trace=trace,
            transcript=[
                Message(role="user", content=task),
                Message(role="assistant", content=synthesis.content),
            ],
            steps=total_steps + 1,
            runtime_mode=RuntimeMode.SUPERVISOR,
        )


__all__ = ["SupervisorRuntime"]
