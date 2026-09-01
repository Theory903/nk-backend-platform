"""Gateway routing for LLM providers.

Provides task-aware model routing with ordered fallbacks.

The router is intentionally provider-agnostic. The rest of the platform
depends only on ChatModel, while provider-specific construction stays here.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from threading import Lock

from {{cookiecutter.project_name}}.ai.llm import (
    AssistantReply,
    ChatModel,
    Message,
    ToolSpec,
    get_chat_model,
)
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


class ResilientChatModel:
    """Apply timeout, bounded retry, and ordered fallback at invocation time."""

    def __init__(
        self,
        models: list[ChatModel],
        *,
        identities: list[tuple[str, str]] | None = None,
        timeout_s: float = 30.0,
        retries: int = 1,
    ) -> None:
        if not models:
            raise ValueError("at least one model is required")
        self._models = models
        self._identities = identities or []
        self._last_identity: tuple[str, str] | None = None
        self._timeout_s = timeout_s
        self._retries = max(0, retries)

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AssistantReply:
        errors: list[str] = []
        for index, model in enumerate(self._models):
            for attempt in range(self._retries + 1):
                try:
                    result = await asyncio.wait_for(
                        model.complete(messages, tools),
                        timeout=self._timeout_s,
                    )
                    if index < len(self._identities):
                        self._last_identity = self._identities[index]
                    return result
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    if attempt < self._retries:
                        await asyncio.sleep(min(2.0, 0.25 * (2**attempt)) + random.random() / 10)
        raise RuntimeError("all model providers failed: " + " | ".join(errors))

    @property
    def last_identity(self) -> tuple[str, str] | None:
        """Return the provider/model that produced the last response."""
        return self._last_identity


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

        models: list[ChatModel] = []
        identities: list[tuple[str, str]] = []
        for provider, model in attempts:
            try:
                models.append(self._create_model(provider=provider, model=model))
                identities.append((provider, model))
            except Exception as exc:
                errors.append(
                    f"{provider}/{model}: "
                    f"{type(exc).__name__}: {exc}"
                )

        if not models:
            raise RuntimeError(
                f"all model routes failed for task {task!r}: "
                + " | ".join(errors)
            )
        return ResilientChatModel(
            models,
            identities=identities,
            timeout_s=float(getattr(settings, "llm_timeout_s", 30.0)),
            retries=int(getattr(settings, "llm_max_retries", 1)),
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
        return get_chat_model(provider, model=model)

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
    "ResilientChatModel",
    "get_router",
]