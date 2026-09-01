"""Gateway routing for LLM providers.

Provides task-aware model routing with ordered fallbacks.

The router is intentionally provider-agnostic. The rest of the platform
depends only on ChatModel, while provider-specific construction stays here.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from threading import Lock

from {{cookiecutter.project_name}}.ai.gateway.budget import BudgetEnforcingChatModel
from {{cookiecutter.project_name}}.ai.gateway.capabilities import (
    CapabilitySpec,
    load_capability_routes,
    resolve_capability,
)
from {{cookiecutter.project_name}}.ai.gateway.semantic_cache import (
    CachedChatModel,
    get_completion_cache,
    get_semantic_embedder,
)
from {{cookiecutter.project_name}}.observability.genai.instrumentation import InstrumentedChatModel
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
    Capability-aware LLM router.

    Routing:
        capability -> primary provider/model -> ordered fallbacks

    Legacy task names (`default`, `reasoning`, `fast`) map to capabilities via
    ``ai/gateway/capabilities.yaml``.
    """

    __slots__ = (
        "_routes",
        "_aliases",
        "_lock",
    )

    def __init__(
        self,
        routes: dict[str, Route | CapabilitySpec] | None = None,
        *,
        task_aliases: dict[str, str] | None = None,
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

        if routes is None:
            try:
                specs, aliases = load_capability_routes()
                configured = {
                    name: Route(
                        provider=spec.provider,
                        model=spec.model,
                        fallback=spec.fallback,
                    )
                    for name, spec in specs.items()
                }
                self._aliases = aliases
            except Exception:
                configured = {
                    "chat": default,
                    "reasoning": default,
                    "fast": default,
                }
                self._aliases = {
                    "default": "chat",
                    "reasoning": "reasoning",
                    "fast": "fast",
                }
        else:
            configured = {}
            for name, route in routes.items():
                if isinstance(route, CapabilitySpec):
                    configured[name] = Route(
                        provider=route.provider,
                        model=route.model,
                        fallback=route.fallback,
                    )
                else:
                    configured[name] = route
            self._aliases = dict(task_aliases or {"default": "chat"})

        if "chat" not in configured:
            configured["chat"] = default

        self._routes = self._validate_routes(configured)
        self._lock = Lock()

    @property
    def routes(self) -> dict[str, Route]:
        """Return a defensive copy of configured capability routes."""
        with self._lock:
            return dict(self._routes)

    @property
    def task_aliases(self) -> dict[str, str]:
        with self._lock:
            return dict(self._aliases)

    @property
    def capabilities(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._routes.keys())

    def for_capability(
        self,
        capability: str = "chat",
    ) -> Route:
        """Resolve the route for a logical capability."""
        capability = capability.strip() or "chat"
        with self._lock:
            return self._routes.get(
                capability,
                self._routes["chat"],
            )

    def for_task(
        self,
        task: str = "default",
    ) -> Route:
        """Resolve the route for a legacy task alias."""
        capability = resolve_capability(task, self._aliases)
        return self.for_capability(capability)

    def model_for_capability(
        self,
        capability: str = "chat",
    ) -> ChatModel:
        """Construct a capability-bound model with fallback, cache, and budget."""
        route = self.for_capability(capability)
        return self._wrap_model(self._build_resilient(route), capability=capability)

    def model_for(
        self,
        task: str = "default",
    ) -> ChatModel:
        """Construct a model for a legacy task alias."""
        capability = resolve_capability(task, self._aliases)
        return self.model_for_capability(capability)

    def _build_resilient(self, route: Route) -> ResilientChatModel:
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
                "all model routes failed: " + " | ".join(errors)
            )
        return ResilientChatModel(
            models,
            identities=identities,
            timeout_s=float(getattr(settings, "llm_timeout_s", 30.0)),
            retries=int(getattr(settings, "llm_max_retries", 1)),
        )

    def _wrap_model(
        self,
        model: ChatModel,
        *,
        capability: str,
    ) -> ChatModel:
        wrapped: ChatModel = BudgetEnforcingChatModel(model, capability=capability)
        wrapped = InstrumentedChatModel(wrapped, capability=capability)
        cache = get_completion_cache()
        if cache is not None:
            wrapped = CachedChatModel(
                wrapped,
                cache,
                embedder=get_semantic_embedder(),
                capability=capability,
            )
        return wrapped

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
    "reset_router",
]


def reset_router() -> None:
    """Reset the process-wide router (tests)."""
    global _router
    with _router_lock:
        _router = None