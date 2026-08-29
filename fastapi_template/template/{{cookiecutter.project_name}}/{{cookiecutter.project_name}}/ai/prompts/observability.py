"""Observability helpers for rendered prompts."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from {{cookiecutter.project_name}}.ai.prompts.models import RenderedPrompt


def prompt_span_attributes(rendered: RenderedPrompt) -> dict[str, Any]:
    """Attributes safe to attach to an OTel/agent span."""
    attrs: dict[str, Any] = {
        "prompt.name": rendered.name,
        "prompt.version": rendered.version,
        "prompt.checksum": rendered.checksum,
    }
    if rendered.variant is not None:
        attrs["prompt.variant"] = rendered.variant
    if rendered.model is not None:
        attrs["prompt.model"] = rendered.model
    if rendered.provider is not None:
        attrs["prompt.provider"] = rendered.provider
    if rendered.input_tokens is not None:
        attrs["prompt.input_tokens"] = rendered.input_tokens
    return attrs


@contextmanager
def prompt_span(rendered: RenderedPrompt, name: str = "llm.generate") -> Generator[None, None, None]:
    """Wrap an LLM call with prompt identity attributes via agent_span."""
    try:
        from {{cookiecutter.project_name}}.agents.tracing import agent_span
    except ImportError:
        yield
        return

    with agent_span(name, **prompt_span_attributes(rendered)):
        yield
