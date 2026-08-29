"""Safe prompt rendering via string.Formatter."""

from __future__ import annotations

import string
from typing import Any

from {{cookiecutter.project_name}}.ai.prompts.exceptions import PromptRenderError
from {{cookiecutter.project_name}}.ai.prompts.models import (
    PromptMessage,
    PromptTemplate,
    RenderedPrompt,
)
from {{cookiecutter.project_name}}.ai.prompts.validator import (
    redact_for_logging,
    validate_variables,
)


class SafeFormatter(string.Formatter):
    """Formatter that surfaces missing/invalid fields as PromptRenderError."""

    def get_field(self, field_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]):
        try:
            return super().get_field(field_name, args, kwargs)
        except (KeyError, AttributeError, IndexError) as exc:
            raise PromptRenderError(
                f"invalid prompt variable: {field_name}"
            ) from exc

    def get_value(self, key: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        try:
            return super().get_value(key, args, kwargs)
        except KeyError as exc:
            raise PromptRenderError(f"invalid prompt variable: {key}") from exc


_FORMATTER = SafeFormatter()


def render_text(template: str, values: dict[str, Any]) -> str:
    """Render a single template string with validated values."""
    try:
        return _FORMATTER.vformat(template, (), values)
    except PromptRenderError:
        raise
    except (ValueError, KeyError) as exc:
        raise PromptRenderError(str(exc)) from exc


def render_prompt(
    prompt: PromptTemplate,
    values: dict[str, Any],
    *,
    variant: str | None = None,
    allow_extra: bool = False,
) -> RenderedPrompt:
    """Validate inputs and render all messages into a RenderedPrompt."""
    normalized = validate_variables(prompt, values, allow_extra=allow_extra)
    rendered_messages = tuple(
        PromptMessage(role=m.role, content=render_text(m.content, normalized))
        for m in prompt.messages
    )
    return RenderedPrompt(
        name=prompt.name,
        version=prompt.version,
        messages=rendered_messages,
        variables=redact_for_logging(prompt, normalized),
        variant=variant,
        checksum=prompt.checksum,
        model=prompt.model,
        provider=prompt.provider,
        temperature=prompt.temperature,
        max_tokens=prompt.max_tokens,
        metadata={
            **prompt.metadata,
            "status": prompt.status,
            "tags": sorted(prompt.tags),
            "contains_secrets": any(v.secret or v.pii for v in prompt.variables),
        },
    )
