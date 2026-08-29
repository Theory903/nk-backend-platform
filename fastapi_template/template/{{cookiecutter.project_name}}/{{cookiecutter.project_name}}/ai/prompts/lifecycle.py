"""Prompt lifecycle transitions."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.prompts.exceptions import PromptLifecycleError
from {{cookiecutter.project_name}}.ai.prompts.models import (
    ALLOWED_TRANSITIONS,
    PromptStatus,
    PromptTemplate,
)


def transition(prompt: PromptTemplate, new_status: PromptStatus) -> PromptTemplate:
    """Return a copy of the prompt with a validated lifecycle status."""
    allowed = ALLOWED_TRANSITIONS.get(prompt.status, frozenset())
    if new_status not in allowed:
        raise PromptLifecycleError(
            f"cannot transition '{prompt.name}:v{prompt.version}' "
            f"from {prompt.status!r} to {new_status!r}"
        )
    return prompt.with_status(new_status)
