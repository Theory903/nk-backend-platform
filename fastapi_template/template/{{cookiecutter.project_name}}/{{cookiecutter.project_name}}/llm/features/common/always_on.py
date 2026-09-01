"""Always-on digest scheduling via Taskiq when available."""

from __future__ import annotations

from {{cookiecutter.project_name}}.llm.features.common.research import research_outline

_digest_task = None


def _get_digest_task():
    global _digest_task
    if _digest_task is not None:
        return _digest_task
    from {{cookiecutter.project_name}}.tkq import broker

    @broker.task
    async def run_digest(topic: str) -> str:
        return await research_outline(f"Daily digest: {topic}", sections=3)

    _digest_task = run_digest
    return _digest_task


async def enqueue_digest(topic: str) -> str:
    """Queue a digest task or run inline when Taskiq is unavailable."""
    try:
        task_fn = _get_digest_task()
        queued = await task_fn.kiq(topic)
        return f"digest queued: {queued.task_id}"
    except ImportError:
        outline = await research_outline(f"Daily digest: {topic}", sections=3)
        return f"digest ready (inline):\n{outline}"


__all__ = ["enqueue_digest"]
