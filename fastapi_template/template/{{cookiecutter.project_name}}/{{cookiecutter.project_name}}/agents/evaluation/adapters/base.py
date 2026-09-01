"""Eval adapter contracts (P15)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from {{cookiecutter.project_name}}.agents.evaluation import EvalCase, EvalConfig, EvalReport, Runner


@dataclass(frozen=True, slots=True)
class AdapterInfo:
    """Metadata for a registered evaluation backend."""

    name: str
    description: str
    installed: bool
    install_hint: str | None = None


class EvalAdapter(ABC):
    """Pluggable evaluation backend."""

    install_hint: str | None = None

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def description(self) -> str:
        return self.name

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool: ...

    def info(self) -> AdapterInfo:
        return AdapterInfo(
            name=self.name,
            description=self.description,
            installed=self.is_available(),
            install_hint=self.install_hint,
        )

    @abstractmethod
    async def run(
        self,
        cases: Sequence[EvalCase],
        runner: Runner,
        *,
        config: EvalConfig | None = None,
        **kwargs: Any,
    ) -> EvalReport: ...


__all__ = ["AdapterInfo", "EvalAdapter"]
