"""FastEmbed-backed dense embeddings (real ONNX path when installed)."""

from __future__ import annotations


class FastEmbedProvider:
    """Default local embedding provider using fastembed bge-small."""

    dimensions = 384

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "fastembed is not installed; add the vector dependency group",
            ) from exc
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, text: str) -> list[float]:
        vectors = list(self._model.embed([text]))
        return [float(x) for x in vectors[0]]
