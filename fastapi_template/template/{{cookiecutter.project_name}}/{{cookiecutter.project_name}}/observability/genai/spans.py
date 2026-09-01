"""OTel GenAI semantic convention spans (P19).

Reference: OpenTelemetry semantic conventions for generative AI systems.
Instrumentation must never break agent or model execution.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


def _normalize_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            normalized[str(key)] = value
        else:
            normalized[str(key)] = str(value)
    return normalized


def _record_exception(span: Any, exc: BaseException) -> None:
    try:
        span.record_exception(exc)
        span.set_attribute("error.type", type(exc).__name__)
        from opentelemetry.trace import StatusCode

        span.set_status(StatusCode.ERROR, str(exc))
    except Exception:
        pass


@contextmanager
def genai_chat_span(
    *,
    system: str,
    model: str,
    capability: str = "chat",
    operation: str = "chat",
) -> Generator[dict[str, Any], None, None]:
    """Span around one LLM chat completion with GenAI attributes."""
    attrs = _normalize_attributes(
        {
            "gen_ai.operation.name": operation,
            "gen_ai.system": system,
            "gen_ai.request.model": model,
            "gen_ai.request.capability": capability,
        },
    )
    started = time.perf_counter()
    state: dict[str, Any] = {"duration_s": 0.0}

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("nk.genai")
        with tracer.start_as_current_span("gen_ai.chat", attributes=attrs) as span:
            try:
                yield state
            except Exception as exc:
                _record_exception(span, exc)
                raise
            finally:
                state["duration_s"] = time.perf_counter() - started
    except ImportError:
        try:
            yield state
        finally:
            state["duration_s"] = time.perf_counter() - started
    except Exception:
        if False:
            raise
        try:
            yield state
        finally:
            state["duration_s"] = time.perf_counter() - started


def set_chat_span_usage(
    span_state: dict[str, Any],
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    finish_reason: str | None = None,
) -> None:
    """Attach token usage to the active GenAI chat span when OTel is available."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if not span.is_recording():
            return
        if input_tokens:
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if output_tokens:
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        if finish_reason:
            span.set_attribute("gen_ai.response.finish_reasons", finish_reason)
        duration = span_state.get("duration_s")
        if duration:
            span.set_attribute("gen_ai.response.duration_s", duration)
    except Exception:
        pass


@contextmanager
def tool_invoke_span(
    *,
    tool_name: str,
    system: str = "nk.tools",
) -> Generator[dict[str, Any], None, None]:
    """Span around one tool invocation."""
    attrs = _normalize_attributes(
        {
            "gen_ai.tool.name": tool_name,
            "gen_ai.tool.type": "function",
            "gen_ai.system": system,
        },
    )
    started = time.perf_counter()
    state: dict[str, Any] = {"duration_s": 0.0}

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("nk.genai")
        with tracer.start_as_current_span("gen_ai.tool.invoke", attributes=attrs) as span:
            try:
                yield state
            except Exception as exc:
                _record_exception(span, exc)
                raise
            finally:
                state["duration_s"] = time.perf_counter() - started
                if span.is_recording():
                    span.set_attribute("gen_ai.tool.duration_s", state["duration_s"])
    except ImportError:
        try:
            yield state
        finally:
            state["duration_s"] = time.perf_counter() - started
    except Exception:
        if False:
            raise
        try:
            yield state
        finally:
            state["duration_s"] = time.perf_counter() - started


@contextmanager
def agent_run_span(
    *,
    runtime_mode: str = "loop",
    organization_id: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Span around one agent run."""
    attrs = _normalize_attributes(
        {
            "gen_ai.agent.name": "nk.agent",
            "gen_ai.agent.runtime_mode": runtime_mode,
            "gen_ai.agent.organization_id": organization_id,
        },
    )
    started = time.perf_counter()
    state: dict[str, Any] = {"duration_s": 0.0, "steps": 0}

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("nk.genai")
        with tracer.start_as_current_span("gen_ai.agent.run", attributes=attrs) as span:
            try:
                yield state
            except Exception as exc:
                _record_exception(span, exc)
                raise
            finally:
                state["duration_s"] = time.perf_counter() - started
                if span.is_recording():
                    span.set_attribute("gen_ai.agent.duration_s", state["duration_s"])
                    if state.get("steps"):
                        span.set_attribute("gen_ai.agent.steps", state["steps"])
    except ImportError:
        try:
            yield state
        finally:
            state["duration_s"] = time.perf_counter() - started
    except Exception:
        if False:
            raise
        try:
            yield state
        finally:
            state["duration_s"] = time.perf_counter() - started


__all__ = [
    "agent_run_span",
    "genai_chat_span",
    "set_chat_span_usage",
    "tool_invoke_span",
]
