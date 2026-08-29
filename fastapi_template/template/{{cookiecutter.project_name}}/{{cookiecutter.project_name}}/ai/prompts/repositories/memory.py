"""In-memory prompt repository for development and tests."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.prompts.exceptions import PromptVersionExistsError
from {{cookiecutter.project_name}}.ai.prompts.models import (
    PromptAlias,
    PromptEvaluation,
    PromptExperiment,
    PromptTemplate,
)


class MemoryPromptRepository:
    """Process-local immutable prompt store."""

    def __init__(self) -> None:
        self._prompts: dict[str, dict[int, PromptTemplate]] = {}
        self._aliases: dict[tuple[str, str], PromptAlias] = {}
        self._experiments: dict[str, PromptExperiment] = {}
        self._evaluations: dict[tuple[str, int], list[PromptEvaluation]] = {}

    async def save(self, prompt: PromptTemplate) -> None:
        self.save_sync(prompt)

    async def get(self, name: str, version: int) -> PromptTemplate | None:
        return self.get_sync(name, version)

    async def latest(self, name: str) -> PromptTemplate | None:
        return self.latest_sync(name)

    async def list_versions(self, name: str) -> list[int]:
        return sorted(self._prompts.get(name, {}))

    async def list_names(self) -> list[str]:
        return sorted(self._prompts)

    async def set_alias(self, alias: PromptAlias) -> None:
        self.set_alias_sync(alias)

    async def get_alias(self, name: str, alias: str) -> PromptAlias | None:
        return self.get_alias_sync(name, alias)

    async def save_experiment(self, experiment: PromptExperiment) -> None:
        self.save_experiment_sync(experiment)

    async def get_experiment(self, name: str) -> PromptExperiment | None:
        return self.get_experiment_sync(name)

    async def save_evaluation(self, evaluation: PromptEvaluation) -> None:
        key = (evaluation.prompt_name, evaluation.version)
        self._evaluations.setdefault(key, []).append(evaluation)

    async def latest_evaluation(
        self,
        prompt_name: str,
        version: int,
    ) -> PromptEvaluation | None:
        items = self._evaluations.get((prompt_name, version), [])
        return items[-1] if items else None

    def save_sync(self, prompt: PromptTemplate) -> None:
        bucket = self._prompts.setdefault(prompt.name, {})
        if prompt.version in bucket:
            raise PromptVersionExistsError(
                f"prompt '{prompt.name}' version {prompt.version} already exists"
            )
        bucket[prompt.version] = prompt.snapshot()

    def replace_sync(self, prompt: PromptTemplate) -> None:
        """Allow lifecycle/status updates only — content checksum must match."""
        from {{cookiecutter.project_name}}.ai.prompts.models import compute_checksum

        bucket = self._prompts.get(prompt.name)
        existing = bucket.get(prompt.version) if bucket else None
        if existing is None:
            raise KeyError(
                f"prompt '{prompt.name}' version {prompt.version} not found"
            )
        incoming_checksum = compute_checksum(
            prompt.name,
            prompt.version,
            prompt.messages,
            prompt.variables,
            model=prompt.model,
            provider=prompt.provider,
            temperature=prompt.temperature,
            max_tokens=prompt.max_tokens,
        )
        if incoming_checksum != existing.checksum:
            raise PromptVersionExistsError(
                f"cannot replace '{prompt.name}' v{prompt.version}: content is immutable"
            )
        # Preserve stored checksum; only status/description/tags/metadata may change.
        bucket[prompt.version] = PromptTemplate(
            name=existing.name,
            version=existing.version,
            messages=existing.messages,
            variables=existing.variables,
            status=prompt.status,
            description=prompt.description,
            tags=prompt.tags,
            model=existing.model,
            provider=existing.provider,
            temperature=existing.temperature,
            max_tokens=existing.max_tokens,
            metadata=dict(prompt.metadata),
            created_at=existing.created_at,
            created_by=existing.created_by,
            checksum=existing.checksum,
        )

    def get_sync(self, name: str, version: int) -> PromptTemplate | None:
        prompt = self._prompts.get(name, {}).get(version)
        return prompt.snapshot() if prompt else None

    def latest_sync(self, name: str) -> PromptTemplate | None:
        versions = self._prompts.get(name)
        if not versions:
            return None
        return versions[max(versions)].snapshot()

    def list_prompts_sync(self) -> dict[str, list[int]]:
        return {name: sorted(versions) for name, versions in self._prompts.items()}

    def set_alias_sync(self, alias: PromptAlias) -> None:
        self._aliases[(alias.name, alias.alias)] = alias

    def get_alias_sync(self, name: str, alias: str) -> PromptAlias | None:
        return self._aliases.get((name, alias))

    def save_experiment_sync(self, experiment: PromptExperiment) -> None:
        total = sum(v.weight for v in experiment.variants)
        if experiment.variants and abs(total - 1.0) > 1e-6:
            from {{cookiecutter.project_name}}.ai.prompts.exceptions import PromptExperimentError

            raise PromptExperimentError(
                f"experiment '{experiment.name}' weights must sum to 1.0, got {total}"
            )
        self._experiments[experiment.name] = experiment

    def get_experiment_sync(self, name: str) -> PromptExperiment | None:
        return self._experiments.get(name)

    def experiments_for_sync(
        self,
        prompt_name: str,
        environment: str,
    ) -> list[PromptExperiment]:
        return [
            exp
            for exp in self._experiments.values()
            if exp.active
            and exp.prompt_name == prompt_name
            and exp.environment == environment
        ]
