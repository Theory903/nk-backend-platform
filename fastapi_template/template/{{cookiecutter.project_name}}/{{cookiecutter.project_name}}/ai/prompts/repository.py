"""Prompt persistence protocol."""

from __future__ import annotations

from typing import Protocol

from {{cookiecutter.project_name}}.ai.prompts.models import (
    PromptAlias,
    PromptEvaluation,
    PromptExperiment,
    PromptTemplate,
)


class PromptRepository(Protocol):
    """Persistence interface — memory, Postgres, Mongo, files, etc."""

    async def save(self, prompt: PromptTemplate) -> None:
        ...

    async def get(self, name: str, version: int) -> PromptTemplate | None:
        ...

    async def latest(self, name: str) -> PromptTemplate | None:
        ...

    async def list_versions(self, name: str) -> list[int]:
        ...

    async def list_names(self) -> list[str]:
        ...

    async def set_alias(self, alias: PromptAlias) -> None:
        ...

    async def get_alias(self, name: str, alias: str) -> PromptAlias | None:
        ...

    async def save_experiment(self, experiment: PromptExperiment) -> None:
        ...

    async def get_experiment(self, name: str) -> PromptExperiment | None:
        ...

    async def save_evaluation(self, evaluation: PromptEvaluation) -> None:
        ...

    async def latest_evaluation(
        self,
        prompt_name: str,
        version: int,
    ) -> PromptEvaluation | None:
        ...
