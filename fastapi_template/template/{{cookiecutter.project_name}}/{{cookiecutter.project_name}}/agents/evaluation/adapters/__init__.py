"""Evaluation adapter registry (P15)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.agents.evaluation.adapters.base import AdapterInfo, EvalAdapter
from {{cookiecutter.project_name}}.agents.evaluation.adapters.deepeval import DeepEvalAdapter
from {{cookiecutter.project_name}}.agents.evaluation.adapters.harness import HarnessEvalAdapter
from {{cookiecutter.project_name}}.agents.evaluation.adapters.native import NativeAdapter
from {{cookiecutter.project_name}}.agents.evaluation.adapters.promptfoo import PromptfooAdapter
from {{cookiecutter.project_name}}.agents.evaluation.adapters.ragas import RagasAdapter

_ADAPTERS: dict[str, type[EvalAdapter]] = {
    "native": NativeAdapter,
    "harness": HarnessEvalAdapter,
    "ragas": RagasAdapter,
    "deepeval": DeepEvalAdapter,
    "promptfoo": PromptfooAdapter,
}


def list_adapters() -> list[AdapterInfo]:
    """Return metadata for all registered adapters."""
    items: list[AdapterInfo] = []
    for cls in _ADAPTERS.values():
        items.append(cls().info())
    return items


def get_adapter(name: str) -> EvalAdapter:
    """Instantiate an adapter by name."""
    key = name.strip().lower()
    cls = _ADAPTERS.get(key)
    if cls is None:
        known = ", ".join(sorted(_ADAPTERS))
        raise KeyError(f"unknown eval adapter {name!r}; choose from: {known}")
    return cls()


__all__ = ["get_adapter", "list_adapters"]
