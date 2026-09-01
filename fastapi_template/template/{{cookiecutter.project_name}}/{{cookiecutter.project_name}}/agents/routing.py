"""Runtime mode selection — routing ladder (P3)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.agents.types import RuntimeMode


def resolve_runtime_mode(
    mode: RuntimeMode | str,
    *,
    task: str,
    tool_count: int = 0,
    multi_agent: bool = False,
    prefer_graph: bool = False,
) -> RuntimeMode:
    """
    Map AUTO → concrete runtime.

    Ladder (roadmap):
        simple Q&A / tool loop → LoopRuntime
        workflow / checkpointing → GraphRuntime (when prefer_graph)
        multi-agent → SupervisorRuntime
    """
    if isinstance(mode, str):
        normalized = mode.strip().lower() or RuntimeMode.AUTO
        try:
            mode = RuntimeMode(normalized)
        except ValueError as exc:
            raise ValueError(f"unknown runtime mode: {mode!r}") from exc

    if mode is not RuntimeMode.AUTO:
        return mode

    if multi_agent:
        return RuntimeMode.SUPERVISOR
    if prefer_graph and tool_count > 0:
        return RuntimeMode.GRAPH
    return RuntimeMode.LOOP


def runtime_mode_for_task(
    task: str,
    *,
    tool_count: int = 0,
) -> RuntimeMode:
    """Heuristic AUTO resolution from task text alone."""
    text = task.lower()
    multi_agent = any(
        phrase in text
        for phrase in (
            "team of agents",
            "multi-agent",
            "supervisor",
            "delegate to",
            "workers:",
        )
    )
    prefer_graph = "workflow" in text or "checkpoint" in text
    return resolve_runtime_mode(
        RuntimeMode.AUTO,
        task=task,
        tool_count=tool_count,
        multi_agent=multi_agent,
        prefer_graph=prefer_graph,
    )


__all__ = ["resolve_runtime_mode", "runtime_mode_for_task"]
