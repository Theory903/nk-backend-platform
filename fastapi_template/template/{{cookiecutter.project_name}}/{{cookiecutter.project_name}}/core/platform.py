"""Typed, validated, production-grade platform manifest configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MANIFEST_FILENAME = "platform.yaml"


class ProvidersConfig(BaseModel):
    """Infrastructure/provider selections."""

    model_config = ConfigDict(extra="allow")

    api_type: str = "rest"
    database: str = "none"
    orm: str = "none"
    ci: str = "none"
    cache: str = "none"
    queue: str = "none"
    identity: str = "none"
    llm: str = "none"
    vector: str = "none"
    workflow: str = "none"


class FrameworkConfig(BaseModel):
    """Framework release metadata."""

    version: str = "1.x"


class ScaleConfig(BaseModel):
    """Deployment stage from the NK scale ladder."""

    stage: str = "S0"


class DeployConfig(BaseModel):
    """Deployment topology switches."""

    path_split_stream: bool = False
    compose: bool = True
    helm: bool = False


class ObservabilityConfig(BaseModel):
    """Observability feature configuration."""

    prometheus: bool = False
    opentelemetry: bool = False
    sentry: bool = False
    sampling_ratio: float = Field(default=0.1, ge=0.0, le=1.0)


class StackLayersConfig(BaseModel):
    """Six-layer AI Stack capability map."""

    model_config = ConfigDict(protected_namespaces=())

    compute: str = "external"
    model_development: str = "external"
    inference_serving: bool = False
    data_retrieval_protocols: bool = False
    orchestration_agents: bool = False
    applications_products: bool = True


class StackConfig(BaseModel):
    """Ownership and layer map for the generated platform."""

    layers: StackLayersConfig = Field(default_factory=StackLayersConfig)
    ownership: dict[str, str] = Field(default_factory=dict)


class RuntimeConfig(BaseModel):
    """Runtime-plane and generated control-plane boundary."""

    plane: str = "runtime"
    control_plane: str = "generated-metadata"
    workflow_state: bool = False
    durable_state: bool = False


class ProtocolConfig(BaseModel):
    """External protocol adapters enabled for the application."""

    mcp: bool = False
    a2a: bool = False


class AIConfig(BaseModel):
    """Model, gateway, and protocol capabilities."""

    enabled: bool = False
    model_gateway: bool = False
    model_routing: bool = False
    embeddings: bool = False
    protocols: ProtocolConfig = Field(default_factory=ProtocolConfig)


class KnowledgeConfig(BaseModel):
    """Knowledge lifecycle and retrieval capabilities."""

    enabled: bool = False
    ingestion: bool = False
    hybrid_retrieval: bool = False
    reranking: bool = False
    graph_retrieval: bool = False
    acl_filtering: bool = False
    freshness_tracking: bool = False


class AgentsConfig(BaseModel):
    """Bounded agent runtime capabilities."""

    enabled: bool = False
    bounded_runtime: bool = False
    checkpointing: bool = False
    approvals: bool = False
    multi_agent: bool = False


class StorageConfig(BaseModel):
    """Storage roles, kept separate even when one backend serves many roles."""

    metadata: str = "none"
    vectors: str = "none"
    lexical: str = "none"
    objects: str = "none"
    cache: str = "none"
    queue: str = "none"
    checkpoints: str = "none"


class EvaluationConfig(BaseModel):
    """Evaluation and release-gate capabilities."""

    enabled: bool = False
    golden_dataset: bool = False
    regression_gates: bool = False
    red_team: bool = False


class ReproducibilityConfig(BaseModel):
    """Versioning inputs needed to reproduce a generated runtime."""

    model_config = ConfigDict(protected_namespaces=())

    config_version: str = "1"
    lockfile: bool = True
    model_versions: bool = False
    prompt_versions: bool = False
    tool_versions: bool = False


class PlatformConfig(BaseModel):
    """Validated representation of the platform manifest."""

    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
        protected_namespaces=(),
    )

    project: str
    profile: str = ""
    use_case: str | None = None
    framework: FrameworkConfig = Field(default_factory=FrameworkConfig)
    scale: ScaleConfig = Field(default_factory=ScaleConfig)
    providers: ProvidersConfig = Field(
        default_factory=ProvidersConfig,
    )
    modules: dict[str, bool] = Field(
        default_factory=dict,
    )
    observability: ObservabilityConfig = Field(
        default_factory=ObservabilityConfig,
    )
    stack: StackConfig = Field(default_factory=StackConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    reproducibility: ReproducibilityConfig = Field(
        default_factory=ReproducibilityConfig,
    )
    deploy: DeployConfig = Field(default_factory=DeployConfig)

    def module_enabled(
        self,
        name: str,
    ) -> bool:
        """Return whether a platform module is enabled."""

        return self.modules.get(
            name,
            False,
        )

    def provider(
        self,
        name: str,
        default: str | None = None,
    ) -> str | None:
        """Resolve a provider by name."""

        value = getattr(
            self.providers,
            name,
            default,
        )

        return value

    def observability_enabled(
        self,
        name: str,
    ) -> bool:
        """Return whether an observability integration is enabled."""

        return bool(
            getattr(
                self.observability,
                name,
                False,
            )
        )

    def scale_at_least(self, stage: str) -> bool:
        """Return whether the configured stage has reached ``stage``."""
        order = {f"S{index}": index for index in range(7)}
        current = order.get(self.scale.stage.upper())
        requested = order.get(stage.upper())
        return current is not None and requested is not None and current >= requested


def manifest_path() -> Path:
    """Return the default platform manifest path."""

    return (
        Path(__file__)
        .resolve()
        .parents[2]
        / MANIFEST_FILENAME
    )


def _load_manifest(
    path: Path,
) -> dict[str, Any]:
    """Read and validate the raw YAML document."""

    if not path.exists():
        raise FileNotFoundError(
            f"platform manifest not found: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"platform manifest is not a file: {path}"
        )

    try:
        raw = yaml.safe_load(
            path.read_text(
                encoding="utf-8",
            )
        )
    except yaml.YAMLError as exc:
        raise ValueError(
            f"invalid YAML in platform manifest: {path}"
        ) from exc

    if raw is None:
        raise ValueError(
            f"platform manifest is empty: {path}"
        )

    if not isinstance(raw, dict):
        raise ValueError(
            "platform manifest root must be a mapping"
        )

    return raw


@lru_cache(maxsize=1)
def get_platform_config(
    path: str | None = None,
) -> PlatformConfig:
    """
    Load and cache the platform manifest.

    The cache is process-local and keyed by ``path``. With
    ``maxsize=1``, only the most recent path argument is retained;
    a different path displaces the previous entry. Tests or
    applications that need to reload the *default* manifest can call
    ``reload_platform_config()`` (clears the whole cache, then loads
    the default path only). For an arbitrary path, call
    ``validate_platform_config(path)`` or
    ``get_platform_config.cache_clear()`` then
    ``get_platform_config(path)``.
    """

    target = (
        Path(path).expanduser().resolve()
        if path
        else manifest_path()
    )

    raw = _load_manifest(target)

    try:
        return PlatformConfig.model_validate(
            raw
        )
    except ValidationError as exc:
        raise ValueError(
            f"invalid platform configuration: {target}"
        ) from exc


def reload_platform_config() -> PlatformConfig:
    """
    Clear the manifest cache and immediately reload the default path.

    Does not accept a custom path — use ``validate_platform_config(path)``
    when you need to re-validate a non-default manifest.
    """

    get_platform_config.cache_clear()
    return get_platform_config()


def validate_platform_config(
    path: str | None = None,
) -> PlatformConfig:
    """Validate a manifest without relying on a previous cached value."""

    get_platform_config.cache_clear()

    return get_platform_config(
        path
    )


__all__ = [
    "MANIFEST_FILENAME",
    "AIConfig",
    "AgentsConfig",
    "DeployConfig",
    "EvaluationConfig",
    "FrameworkConfig",
    "KnowledgeConfig",
    "ObservabilityConfig",
    "PlatformConfig",
    "ProvidersConfig",
    "ReproducibilityConfig",
    "RuntimeConfig",
    "ScaleConfig",
    "StackConfig",
    "StackLayersConfig",
    "StorageConfig",
    "get_platform_config",
    "manifest_path",
    "reload_platform_config",
    "validate_platform_config",
]