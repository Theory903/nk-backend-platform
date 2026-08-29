"""Alias / environment / experiment resolution."""

from __future__ import annotations

import re

from {{cookiecutter.project_name}}.ai.prompts.exceptions import PromptNotFoundError
from {{cookiecutter.project_name}}.ai.prompts.experiments import assign_variant
from {{cookiecutter.project_name}}.ai.prompts.models import (
    PromptSelector,
    PromptTemplate,
)
from {{cookiecutter.project_name}}.ai.prompts.repositories.memory import MemoryPromptRepository

_REF_RE = re.compile(
    r"^(?P<name>[a-zA-Z_][\w-]*)"
    r"(?:@(?P<alias>[a-zA-Z_][\w-]*))?"
    r"(?::v?(?P<version>\d+))?$"
)


def parse_prompt_ref(ref: str) -> tuple[str, str | None, int | None]:
    """
    Parse refs like:
      rag_answer
      rag_answer@production
      rag_answer@latest
      rag_answer:17
      rag_answer:v17
    """
    match = _REF_RE.match(ref.strip())
    if not match:
        raise PromptNotFoundError(f"invalid prompt reference: {ref!r}")
    version = int(match.group("version")) if match.group("version") else None
    return match.group("name"), match.group("alias"), version


class PromptResolver:
    """Resolve a prompt reference to an immutable PromptTemplate."""

    def __init__(self, repository: MemoryPromptRepository) -> None:
        self._repo = repository

    def resolve(
        self,
        ref: str,
        *,
        selector: PromptSelector | None = None,
        version: int | None = None,
    ) -> tuple[PromptTemplate, str | None]:
        """
        Return (prompt, variant_id).

        Resolution order:
          1. Explicit version argument or :N in ref
          2. @alias (production, stable, candidate, latest, …)
          3. Active experiment for environment + subject_id
          4. Latest version
        """
        selector = selector or PromptSelector()
        name, alias, ref_version = parse_prompt_ref(ref)
        pinned = version if version is not None else ref_version
        variant_id: str | None = None

        if pinned is not None:
            prompt = self._repo.get_sync(name, pinned)
            if prompt is None:
                raise PromptNotFoundError(
                    f"prompt '{name}' version {pinned} not found"
                )
            return prompt, None

        if alias and alias not in {"latest"}:
            record = self._repo.get_alias_sync(name, alias)
            if record is None:
                raise PromptNotFoundError(
                    f"alias '{name}@{alias}' not found"
                )
            prompt = self._repo.get_sync(name, record.version)
            if prompt is None:
                raise PromptNotFoundError(
                    f"alias '{name}@{alias}' points to missing version {record.version}"
                )
            return prompt, None

        if selector.subject_id:
            for experiment in self._repo.experiments_for_sync(
                name,
                selector.environment,
            ):
                chosen = assign_variant(experiment, selector.subject_id)
                prompt = self._repo.get_sync(chosen.prompt_name, chosen.version)
                if prompt is None:
                    raise PromptNotFoundError(
                        f"experiment '{experiment.name}' variant "
                        f"'{chosen.id}' points to missing "
                        f"{chosen.prompt_name}:v{chosen.version}"
                    )
                return prompt, chosen.id

        prompt = self._repo.latest_sync(name)
        if prompt is None:
            available = ", ".join(self._repo.list_prompts_sync())
            raise PromptNotFoundError(
                f"prompt '{name}' not found; available: [{available}]"
            )
        return prompt, variant_id
