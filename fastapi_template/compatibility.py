"""Central compatibility rules for generated AI Stack capabilities."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi_template.config import GeneratorConfig


@dataclass(frozen=True)
class CompatibilityIssue:
    """A configuration error with an actionable correction."""

    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


class CompatibilityError(ValueError):
    """Raised when selected capabilities cannot be generated safely."""

    def __init__(self, issues: list[CompatibilityIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(
            "incompatible project options: " + "; ".join(str(issue) for issue in self.issues)
        )


def check_compatibility(config: GeneratorConfig) -> list[CompatibilityIssue]:
    """Return all cross-layer incompatibilities for a resolved config."""
    issues: list[CompatibilityIssue] = []
    caps = config.capabilities

    if config.api_type not in {"rest", "graphql"}:
        issues.append(CompatibilityIssue("api_type", "choose rest or graphql"))

    if config.database == "none" and config.orm != "none":
        issues.append(
            CompatibilityIssue("orm", "an ORM requires a configured database"),
        )
    if config.database != "none" and config.orm == "none":
        issues.append(
            CompatibilityIssue("database", "a configured database requires an ORM"),
        )

    if caps.vector and config.database != "postgresql":
        issues.append(
            CompatibilityIssue(
                "vector",
                "the native vector path requires PostgreSQL with pgvector",
            ),
        )
    if caps.rag and not caps.llm:
        issues.append(CompatibilityIssue("rag", "RAG requires an LLM provider"))
    if caps.rag and not caps.vector:
        issues.append(CompatibilityIssue("rag", "RAG requires vector storage"))
    if caps.rag and config.database != "postgresql":
        issues.append(
            CompatibilityIssue(
                "rag",
                "the native hybrid RAG path requires PostgreSQL metadata and FTS",
            ),
        )
    if caps.agents and not caps.llm:
        issues.append(CompatibilityIssue("agents", "agents require an LLM provider"))
    if caps.agents and config.database == "none" and config.storage.cache == "none":
        issues.append(
            CompatibilityIssue(
                "agents",
                "restart-safe agents require a database or explicit shared state store",
            ),
        )
    if caps.agents and config.storage.cache != "redis":
        issues.append(
            CompatibilityIssue(
                "agents",
                "generated agent persistence requires the shared Redis state store",
            ),
        )
    if caps.graphrag and not caps.agents:
        issues.append(
            CompatibilityIssue("graphrag", "GraphRAG requires the agent/runtime module"),
        )
    if caps.graphrag and not caps.rag:
        issues.append(
            CompatibilityIssue("graphrag", "GraphRAG requires the traditional RAG path"),
        )
    if caps.audit and config.database == "none":
        issues.append(
            CompatibilityIssue("audit", "audit records require a durable database"),
        )
    if caps.audit and config.storage.cache != "redis":
        issues.append(
            CompatibilityIssue(
                "audit",
                "generated audit persistence requires the shared Redis sink",
            ),
        )
    if caps.idempotency and config.database == "none" and config.storage.cache == "none":
        issues.append(
            CompatibilityIssue(
                "idempotency",
                "durable idempotency requires a database or explicit cache store",
            ),
        )
    if caps.idempotency and config.storage.cache != "redis":
        issues.append(
            CompatibilityIssue(
                "idempotency",
                "generated production idempotency requires the shared Redis store",
            ),
        )
    if (
        config.modules.get("users")
        and not config.modules.get("migrations")
        and not config.modules.get("redis")
    ):
        issues.append(
            CompatibilityIssue(
                "users",
                "identity requires migrations or Redis for durable stores",
            ),
        )
    if (
        config.storage.checkpoints != "none"
        and config.storage.cache == "none"
        and config.storage.metadata == "none"
    ):
        issues.append(
            CompatibilityIssue(
                "checkpoints",
                "checkpoint storage requires a shared cache or durable state provider",
            ),
        )

    return issues


def validate_compatibility(config: GeneratorConfig) -> None:
    """Raise one deterministic error for incompatible options."""
    issues = check_compatibility(config)
    if issues:
        raise CompatibilityError(issues)


__all__ = [
    "CompatibilityError",
    "CompatibilityIssue",
    "check_compatibility",
    "validate_compatibility",
]
