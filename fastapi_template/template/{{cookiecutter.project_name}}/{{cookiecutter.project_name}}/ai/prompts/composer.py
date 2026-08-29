"""Prompt composition from reusable parts."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.prompts.models import (
    PromptMessage,
    PromptTemplate,
    PromptVariable,
    build_prompt,
)
from {{cookiecutter.project_name}}.ai.prompts.resolver import PromptResolver


class PromptComposer:
    """
    Compose a prompt from named part references.

    Prefer composition over inheritance — parts stay independently versioned.
    """

    def __init__(self, resolver: PromptResolver) -> None:
        self._resolver = resolver

    def compose(
        self,
        name: str,
        parts: list[str],
        *,
        version: int = 1,
        separator: str = "\n\n",
        description: str = "",
        tags: set[str] | None = None,
    ) -> PromptTemplate:
        """
        Resolve each part ref and concatenate messages in order.

        Example parts: ``["identity:v3", "safety@stable", "task:v12"]``
        Use ``:vN`` or ``@alias`` — numeric ``@3`` is not a valid alias.
        """
        if not parts:
            raise ValueError("parts must not be empty")

        messages: list[PromptMessage] = []
        variables: dict[str, PromptVariable] = {}
        part_meta: list[dict[str, object]] = []

        for ref in parts:
            prompt, _variant = self._resolver.resolve(ref)
            if messages and separator:
                # Keep role boundaries: append separator to previous message
                # when stitching same-role consecutive parts.
                prev = messages[-1]
                first = prompt.messages[0] if prompt.messages else None
                if first and prev.role == first.role:
                    messages[-1] = PromptMessage(
                        role=prev.role,
                        content=prev.content + separator + first.content,
                    )
                    messages.extend(prompt.messages[1:])
                else:
                    messages.extend(prompt.messages)
            else:
                messages.extend(prompt.messages)

            for variable in prompt.variables:
                variables.setdefault(variable.name, variable)
            part_meta.append(
                {
                    "ref": ref,
                    "name": prompt.name,
                    "version": prompt.version,
                    "checksum": prompt.checksum,
                }
            )

        return build_prompt(
            name,
            version,
            messages=tuple(messages),
            variables=tuple(variables.values()),
            description=description or f"composed from {len(parts)} parts",
            tags=tags or {"composed"},
            metadata={"parts": part_meta},
        )
