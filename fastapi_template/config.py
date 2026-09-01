"""Typed generator configuration and AI Stack capability resolution."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fastapi_template.input_model import BuilderContext


def _as_bool(value: Any) -> bool:
    """Normalize values coming from Click, Cookiecutter, or YAML."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled", ""}:
            return False
    return bool(value)


class CapabilityConfig(BaseModel):
    """Resolved capability switches shared by generator and templates."""

    model_config = ConfigDict(extra="allow")

    llm: bool = False
    vector: bool = False
    rag: bool = False
    agents: bool = False
    graphrag: bool = False
    audit: bool = False
    idempotency: bool = False


class StorageConfig(BaseModel):
    """Storage roles required by the generated application."""

    model_config = ConfigDict(extra="allow")

    metadata: str = "none"
    vectors: str = "none"
    lexical: str = "none"
    objects: str = "none"
    cache: str = "none"
    queue: str = "none"
    checkpoints: str = "none"


class FrameworkConfig(BaseModel):
    """Framework metadata recorded in the generated contract."""

    version: str = "1.x"


class ScaleConfig(BaseModel):
    """Earned deployment stage for the generated service."""

    stage: Literal["S0", "S1", "S2", "S3", "S4", "S5", "S6"] = "S0"


class DeployConfig(BaseModel):
    """Deployment topology switches derived from profile capabilities."""

    path_split_stream: bool = False


class GeneratorConfig(BaseModel):
    """One typed, resolved representation of BuilderContext."""

    model_config = ConfigDict(extra="allow")

    project_name: str
    profile: str | None = None
    use_case: str | None = None
    api_type: Literal["rest", "graphql"] = "rest"
    database: str = "none"
    orm: str = "none"
    ci: str = "none"
    capabilities: CapabilityConfig = Field(default_factory=CapabilityConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    framework: FrameworkConfig = Field(default_factory=FrameworkConfig)
    scale: ScaleConfig = Field(default_factory=ScaleConfig)
    deploy: DeployConfig = Field(default_factory=DeployConfig)
    observability: dict[str, bool] = Field(default_factory=dict)
    modules: dict[str, bool] = Field(default_factory=dict)
    runtime_plane: Literal["runtime"] = "runtime"
    control_plane: Literal["generated-metadata"] = "generated-metadata"

    @model_validator(mode="after")
    def _derive_capabilities(self) -> "GeneratorConfig":
        """Keep module and capability views consistent."""
        for name, enabled in self.capabilities.model_dump().items():
            self.modules.setdefault(name, enabled)
        return self

    @classmethod
    def from_context(cls, context: BuilderContext) -> "GeneratorConfig":
        """Resolve a BuilderContext into the canonical typed contract."""
        values = context.dict()
        modules = {
            key.removeprefix("enable_"): _as_bool(value)
            for key, value in values.items()
            if key.startswith("enable_")
        }
        modules["users"] = _as_bool(values.get("add_users"))
        modules["migrations"] = _as_bool(values.get("enable_migrations"))
        modules["redis"] = _as_bool(values.get("enable_redis"))
        modules["taskiq"] = _as_bool(values.get("enable_taskiq"))
        modules["gunicorn"] = _as_bool(values.get("gunicorn"))

        capabilities = CapabilityConfig(
            llm=_as_bool(values.get("enable_llm")),
            vector=_as_bool(values.get("enable_vector")),
            rag=_as_bool(values.get("enable_rag_traditional")),
            agents=_as_bool(values.get("enable_agents")),
            graphrag=_as_bool(values.get("enable_graphrag")),
            audit=_as_bool(values.get("enable_audit")),
            idempotency=_as_bool(values.get("enable_idempotency")),
        )
        database = str(values.get("db") or "none")
        has_database = database != "none"
        has_redis = _as_bool(values.get("enable_redis"))
        has_taskiq = _as_bool(values.get("enable_taskiq"))
        has_vector = capabilities.vector
        profile = values.get("profile")
        default_stage = {
            "minimal": "S0",
            "saas": "S1",
            "ai-saas": "S2",
            "agentic": "S3",
            "fintech": "S2",
        }.get(str(profile), "S0")
        stage = str(values.get("scale_stage") or default_stage).upper()
        if stage not in {"S0", "S1", "S2", "S3", "S4", "S5", "S6"}:
            stage = default_stage
        path_split_stream = capabilities.agents and stage in {
            "S2",
            "S3",
            "S4",
            "S5",
            "S6",
        }

        return cls(
            project_name=str(values.get("project_name") or "project"),
            profile=values.get("profile"),
            use_case=values.get("use_case"),
            api_type=str(values.get("api_type") or "rest"),
            database=database,
            orm=str(values.get("orm") or "none"),
            ci=str(values.get("ci_type") or "none"),
            capabilities=capabilities,
            modules=modules,
            framework=FrameworkConfig(
                version=str(values.get("framework_version") or "1.x"),
            ),
            scale=ScaleConfig(stage=stage),
            deploy=DeployConfig(path_split_stream=path_split_stream),
            observability={
                "prometheus": _as_bool(values.get("prometheus_enabled")),
                "opentelemetry": _as_bool(values.get("otlp_enabled")),
                "sentry": _as_bool(values.get("sentry_enabled")),
            },
            storage=StorageConfig(
                metadata=database if has_database else "none",
                vectors="pgvector"
                if has_vector and database == "postgresql"
                else ("external" if has_vector else "none"),
                lexical="postgresql-fts"
                if capabilities.rag and database == "postgresql"
                else ("external" if capabilities.rag else "none"),
                objects="local" if _as_bool(values.get("add_users")) else "none",
                cache="redis" if has_redis else "none",
                queue="taskiq" if has_taskiq else "none",
                # Checkpoints are durable runtime state, not an ephemeral cache.
                checkpoints=database if capabilities.agents and has_database else "none",
            ),
            runtime_plane="runtime",
            control_plane="generated-metadata",
        )


def resolve_config(context: BuilderContext) -> GeneratorConfig:
    """Return the canonical typed configuration for a builder context."""
    return GeneratorConfig.from_context(context)


__all__ = [
    "CapabilityConfig",
    "DeployConfig",
    "FrameworkConfig",
    "GeneratorConfig",
    "ScaleConfig",
    "StorageConfig",
    "resolve_config",
]
