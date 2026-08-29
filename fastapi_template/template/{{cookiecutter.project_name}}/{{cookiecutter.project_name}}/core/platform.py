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


class ObservabilityConfig(BaseModel):
    """Observability feature configuration."""

    prometheus: bool = False
    opentelemetry: bool = False
    sentry: bool = False


class PlatformConfig(BaseModel):
    """Validated representation of the platform manifest."""

    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
    )

    project: str
    profile: str = ""
    providers: ProvidersConfig = Field(
        default_factory=ProvidersConfig,
    )
    modules: dict[str, bool] = Field(
        default_factory=dict,
    )
    observability: ObservabilityConfig = Field(
        default_factory=ObservabilityConfig,
    )

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
    "ObservabilityConfig",
    "PlatformConfig",
    "ProvidersConfig",
    "get_platform_config",
    "manifest_path",
    "reload_platform_config",
    "validate_platform_config",
]