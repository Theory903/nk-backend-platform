"""Gateway routing for LLM providers.

Provides task-aware model routing with ordered fallbacks.

The router is intentionally provider-agnostic. The rest of the platform
depends only on ChatModel, while provider-specific construction stays here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from {{cookiecutter.project_name}}.ai.llm import ChatModel
from {{cookiecutter.project_name}}.settings import settings


@dataclass(frozen=True, slots=True)
class Route:
    """Model route and ordered fallback providers."""

    provider: str
    model: str
    fallback: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("route provider cannot be empty")

        if not self.model.strip():
            raise ValueError("route model cannot be empty")


class ModelRouter:
    """
    Task-aware LLM router.

    Routing:
        task -> primary provider/model -> ordered fallbacks

    Example:

        router = ModelRouter(
            routes={
                "fast": Route(
                    provider="openai",
                    model="gpt-4.1-mini",
                    fallback=(
                        ("anthropic", "claude-haiku"),
                    ),
                ),
                "reasoning": Route(
                    provider="openai",
                    model="o3",
                ),
            }
        )
    """

    __slots__ = (
        "_routes",
        "_lock",
    )

    def __init__(
        self,
        routes: dict[str, Route] | None = None,
    ) -> None:
        default = Route(
            provider=str(
                getattr(
                    settings,
                    "llm_provider",
                    "ollama",
                )
            ),
            model=str(
                getattr(
                    settings,
                    "llm_model",
                    "llama3.2",
                )
            ),
        )

        configured = (
            dict(routes)
            if routes is not None
            else {
                "default": default,
                "reasoning": default,
                "fast": default,
            }
        )

        if "default" not in configured:
            configured["default"] = default

        self._routes = self._validate_routes(
            configured
        )
        self._lock = Lock()

    @property
    def routes(self) -> dict[str, Route]:
        """Return a defensive copy of configured routes."""
        with self._lock:
            return dict(self._routes)

    def for_task(
        self,
        task: str = "default",
    ) -> Route:
        """Resolve the route for a task."""
        task = task.strip() or "default"

        with self._lock:
            return self._routes.get(
                task,
                self._routes["default"],
            )

    def model_for(
        self,
        task: str = "default",
    ) -> ChatModel:
        """
        Construct the primary model, falling back in order on failure.
        """
        route = self.for_task(task)

        attempts = [
            (route.provider, route.model),
            *route.fallback,
        ]

        errors: list[str] = []

        for provider, model in attempts:
            try:
                return self._create_model(
                    provider=provider,
                    model=model,
                )
            except Exception as exc:
                errors.append(
                    f"{provider}/{model}: "
                    f"{type(exc).__name__}: {exc}"
                )

        raise RuntimeError(
            f"all model routes failed for task "
            f"{task!r}: "
            + " | ".join(errors)
        )

    @staticmethod
    def _create_model(
        *,
        provider: str,
        model: str,
    ) -> ChatModel:
        """
        Construct the configured ChatModel.

        Provider-specific implementation stays behind the LLM abstraction.
        """
        return ChatModel(
            model=model,
            provider=provider,
            api_key=getattr(
                settings,
                "llm_api_key",
                None,
            ),
            api_base=getattr(
                settings,
                "llm_api_base",
                None,
            ),
        )

    @staticmethod
    def _validate_routes(
        routes: dict[str, Route],
    ) -> dict[str, Route]:
        validated: dict[str, Route] = {}

        for name, route in routes.items():
            name = name.strip()

            if not name:
                raise ValueError(
                    "route name cannot be empty"
                )

            if not isinstance(route, Route):
                raise TypeError(
                    f"route {name!r} must be a Route"
                )

            validated[name] = route

        return validated


_router: ModelRouter | None = None
_router_lock = Lock()


def get_router() -> ModelRouter:
    """Return the process-wide model router."""
    global _router

    if _router is None:
        with _router_lock:
            if _router is None:
                _router = ModelRouter()

    return _router


__all__ = [
    "ModelRouter",
    "Route",
    "get_router",
]