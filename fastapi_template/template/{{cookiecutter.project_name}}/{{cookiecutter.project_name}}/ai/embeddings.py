from typing import Protocol


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


def get_embedding_provider(provider: str) -> EmbeddingProvider:
    """
    Resolve an embedding provider by name.

    Hash/scripted doubles live in ``tests/_fakes.py`` only (gold kill-list).
    """
    if provider in {"fastembed", "local"}:
        try:
            from {{cookiecutter.project_name}}.ai.providers.fastembed_provider import (
                FastEmbedProvider,
            )
        except ImportError as exc:
            raise ValueError(
                "provider 'fastembed' needs the fastembed package; "
                "install the vector extra or use ScriptedEmbeddingProvider in tests",
            ) from exc
        return FastEmbedProvider()

    raise ValueError(
        f"embedding provider {provider!r} is not configured; "
        f"wire an adapter or use tests/_fakes.ScriptedEmbeddingProvider",
    )
