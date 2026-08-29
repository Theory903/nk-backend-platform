"""Application-facing prompt registry and service.

Owns prompt identity, versions, aliases, experiments, and rendering.
LangChain (or any other framework) may consume RenderedPrompt.messages —
it does not own governance.
"""

from __future__ import annotations

from typing import Any

from {{cookiecutter.project_name}}.ai.prompts.composer import PromptComposer
from {{cookiecutter.project_name}}.ai.prompts.evaluator import PromptEvaluator
from {{cookiecutter.project_name}}.ai.prompts.exceptions import (
    PromptNotFoundError,
    PromptRenderError,
    PromptVersionExistsError,
)
from {{cookiecutter.project_name}}.ai.prompts.lifecycle import transition
from {{cookiecutter.project_name}}.ai.prompts.models import (
    PromptAlias,
    PromptEvaluation,
    PromptExperiment,
    PromptMessage,
    PromptSelector,
    PromptStatus,
    PromptTemplate,
    PromptVariable,
    PromptVariant,
    RenderedPrompt,
    build_prompt,
)
from {{cookiecutter.project_name}}.ai.prompts.renderer import render_prompt
from {{cookiecutter.project_name}}.ai.prompts.repositories.memory import MemoryPromptRepository
from {{cookiecutter.project_name}}.ai.prompts.resolver import PromptResolver


class PromptRegistry:
    """
    Sync facade used by application code and existing tests.

    Backed by an in-memory repository with immutable versions, aliases,
    experiments, typed variables, and structured messages.
    """

    def __init__(self, repository: MemoryPromptRepository | None = None) -> None:
        self._repo = repository or MemoryPromptRepository()
        self._resolver = PromptResolver(self._repo)
        self._composer = PromptComposer(self._resolver)
        self._evaluator = PromptEvaluator()

    @property
    def repository(self) -> MemoryPromptRepository:
        return self._repo

    def register(
        self,
        name: str,
        template: str | None = None,
        *,
        version: int = 1,
        variables: set[str] | frozenset[str] | tuple[PromptVariable, ...] | None = None,
        messages: tuple[PromptMessage, ...] | list[PromptMessage] | None = None,
        status: PromptStatus = "draft",
        description: str = "",
        tags: set[str] | frozenset[str] | None = None,
        model: str | None = None,
        provider: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> PromptTemplate:
        """
        Register an immutable prompt version.

        Prefer ``messages=`` for multi-role prompts. Legacy ``template=``
        strings become a single user message.
        """
        prompt = build_prompt(
            name,
            version,
            template=template,
            messages=messages,
            variables=variables,
            status=status,
            description=description,
            tags=tags,
            model=model,
            provider=provider,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata,
            created_by=created_by,
        )
        self._repo.save_sync(prompt)
        return prompt

    def render(
        self,
        name: str,
        *,
        version: int | None = None,
        selector: PromptSelector | None = None,
        **kwargs: Any,
    ) -> str:
        """Render a prompt to a flat string (legacy-compatible)."""
        return self.render_full(name, version=version, selector=selector, **kwargs).text

    def render_full(
        self,
        name: str,
        *,
        version: int | None = None,
        selector: PromptSelector | None = None,
        **kwargs: Any,
    ) -> RenderedPrompt:
        """Resolve + validate + render, returning full metadata."""
        try:
            prompt, variant = self._resolver.resolve(
                name,
                selector=selector,
                version=version,
            )
        except PromptNotFoundError as exc:
            # Preserve KeyError for callers/tests that expect it.
            raise KeyError(str(exc)) from exc
        return render_prompt(prompt, kwargs, variant=variant)

    def resolve(
        self,
        ref: str,
        *,
        context: dict[str, Any] | None = None,
        selector: PromptSelector | None = None,
        version: int | None = None,
    ) -> RenderedPrompt:
        """
        Primary API: resolve aliases/experiments and render.

        Example::

            rendered = registry.resolve(
                "rag_answer@production",
                context={"query": q, "context": docs},
            )
        """
        try:
            prompt, variant = self._resolver.resolve(
                ref,
                selector=selector,
                version=version,
            )
        except PromptNotFoundError as exc:
            raise KeyError(str(exc)) from exc
        return render_prompt(prompt, context or {}, variant=variant)

    def set_alias(self, name: str, alias: str, version: int) -> PromptAlias:
        """Point an alias (production, candidate, stable, …) at a version."""
        if self._repo.get_sync(name, version) is None:
            raise KeyError(f"prompt '{name}' version {version} not found")
        record = PromptAlias(name=name, alias=alias, version=version)
        self._repo.set_alias_sync(record)
        return record

    def register_experiment(self, experiment: PromptExperiment) -> PromptExperiment:
        self._repo.save_experiment_sync(experiment)
        return experiment

    def promote(
        self,
        name: str,
        version: int,
        *,
        to_status: PromptStatus,
        alias: str | None = None,
        evaluation: PromptEvaluation | None = None,
    ) -> PromptTemplate:
        """
        Transition lifecycle and optionally publish an alias.

        When ``evaluation`` is provided, thresholds must pass before promotion.
        """
        prompt = self._repo.get_sync(name, version)
        if prompt is None:
            raise KeyError(f"prompt '{name}' version {version} not found")
        if evaluation is not None:
            self._evaluator.require_pass(evaluation)
        updated = transition(prompt, to_status)
        # Content stays immutable; only lifecycle metadata is replaced.
        self._repo.replace_sync(updated)
        if alias:
            self.set_alias(name, alias, version)
        return updated

    def compose(
        self,
        name: str,
        parts: list[str],
        *,
        version: int = 1,
        **kwargs: Any,
    ) -> PromptTemplate:
        """Compose and register a new immutable prompt from part refs."""
        prompt = self._composer.compose(name, parts, version=version, **kwargs)
        self._repo.save_sync(prompt)
        return prompt

    def get(self, name: str, version: int | None = None) -> PromptTemplate:
        if version is None:
            prompt = self._repo.latest_sync(name)
        else:
            prompt = self._repo.get_sync(name, version)
        if prompt is None:
            available = ", ".join(self.list_prompts())
            raise KeyError(f"prompt '{name}' not found; available: [{available}]")
        return prompt

    def list_prompts(self) -> dict[str, list[int]]:
        """Return all registered prompt names and their available versions."""
        return self._repo.list_prompts_sync()


class PromptService:
    """Async service wrapping PromptRegistry for repository-backed apps."""

    def __init__(self, registry: PromptRegistry | None = None) -> None:
        self.registry = registry or PromptRegistry()

    async def resolve(
        self,
        ref: str,
        *,
        context: dict[str, Any] | None = None,
        selector: PromptSelector | None = None,
    ) -> RenderedPrompt:
        return self.registry.resolve(ref, context=context, selector=selector)

    async def save(self, prompt: PromptTemplate) -> None:
        await self.registry.repository.save(prompt)


_registry: PromptRegistry | None = None


def get_prompt_registry() -> PromptRegistry:
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry


__all__ = [
    "PromptRegistry",
    "PromptService",
    "PromptTemplate",
    "PromptMessage",
    "PromptVariable",
    "PromptAlias",
    "PromptVariant",
    "PromptExperiment",
    "PromptSelector",
    "RenderedPrompt",
    "PromptRenderError",
    "PromptNotFoundError",
    "PromptVersionExistsError",
    "get_prompt_registry",
]
