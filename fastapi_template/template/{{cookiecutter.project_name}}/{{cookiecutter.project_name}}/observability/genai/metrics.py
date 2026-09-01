"""GenAI cost and latency metrics (P19)."""

from __future__ import annotations


def record_completion_latency(
    *,
    provider: str,
    model: str,
    capability: str,
    duration_s: float,
) -> None:
    """Record LLM latency without duplicating token counters."""
    try:
        from {{cookiecutter.project_name}}.operations.metrics import record_llm_latency

        record_llm_latency(
            provider=provider,
            capability=capability,
            model=model,
            duration_s=duration_s,
        )
    except Exception:
        pass


def record_genai_completion(
    *,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    duration_s: float = 0.0,
    capability: str = "chat",
) -> None:
    """Record LLM completion tokens, cost, and latency."""
    try:
        from {{cookiecutter.project_name}}.operations.metrics import (
            record_llm_latency,
            record_llm_usage,
        )

        record_llm_usage(
            provider=provider,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        if duration_s > 0:
            record_llm_latency(
                provider=provider,
                capability=capability,
                model=model,
                duration_s=duration_s,
            )
    except Exception:
        pass


def record_tool_invoke(
    *,
    tool_name: str,
    duration_s: float,
    outcome: str,
) -> None:
    """Record tool invocation latency and outcome."""
    try:
        from {{cookiecutter.project_name}}.operations.metrics import record_genai_tool

        record_genai_tool(
            tool_name=tool_name,
            duration_s=duration_s,
            outcome=outcome,
        )
    except Exception:
        pass


def record_agent_step(
    *,
    runtime_mode: str,
    outcome: str = "success",
) -> None:
    """Increment agent step counter for Prometheus when available."""
    try:
        from {{cookiecutter.project_name}}.operations.metrics import agent_steps_total

        agent_steps_total.inc(
            agent_type=runtime_mode,
            outcome=outcome,
        )
    except Exception:
        pass


__all__ = [
    "record_agent_step",
    "record_completion_latency",
    "record_genai_completion",
    "record_tool_invoke",
]
