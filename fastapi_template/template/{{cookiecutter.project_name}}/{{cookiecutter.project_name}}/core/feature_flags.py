
"""Production feature-flag system with typed values, overrides, and caching."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any

from {{cookiecutter.project_name}}.core.platform import get_platform_config

class FeatureFlagError(RuntimeError):
    """Base feature-flag error."""

@dataclass(frozen=True, slots=True)
class FeatureFlag:
    """Resolved feature-flag definition."""

    name: str
    enabled: bool
    source: str
    metadata: dict[str, Any]

class FeatureFlags:
    """
    Central feature-flag resolver.

    Resolution precedence:

        environment
            ↓
        platform.yaml
            ↓
        module configuration
            ↓
        registered runtime override
            ↓
        requested default

    The registry is intentionally provider-agnostic so it can later be
    backed by Redis, LaunchDarkly, Unleash, a database, or another service.
    """

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        environment: str | None = None,
    ) -> None:
        self._config_path = (
            config_path
            or Path(__file__).resolve().parents[2]
            / "platform.yaml"
        )

        self._environment = (
            environment
            or os.getenv(
                "APP_ENV",
                "development",
            )
        )

        self._overrides: dict[str, bool] = {}
        self._lock = RLock()

        self._load.cache_clear()

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def is_enabled(
        self,
        flag: str,
        *,
        default: bool = False,
    ) -> bool:
        """Return whether a feature flag is enabled."""

        return self.resolve(
            flag,
            default=default,
        ).enabled

    def resolve(
        self,
        flag: str,
        *,
        default: bool = False,
    ) -> FeatureFlag:
        """Resolve a complete feature-flag definition."""

        name = self._normalize_name(
            flag
        )

        with self._lock:
            if name in self._overrides:
                return FeatureFlag(
                    name=name,
                    enabled=self._overrides[name],
                    source="runtime",
                    metadata={},
                )

        flags = self._load()

        if name in flags:
            value = flags[name]

            if isinstance(value, dict):
                enabled = self._coerce_bool(
                    value.get(
                        "enabled",
                        default,
                    )
                )

                return FeatureFlag(
                    name=name,
                    enabled=enabled,
                    source=str(
                        value.get(
                            "source",
                            "config",
                        )
                    ),
                    metadata=dict(
                        value.get(
                            "metadata",
                            {}
                        )
                    ),
                )

            return FeatureFlag(
                name=name,
                enabled=self._coerce_bool(
                    value
                ),
                source="config",
                metadata={},
            )

        return FeatureFlag(
            name=name,
            enabled=default,
            source="default",
            metadata={},
        )

    # ------------------------------------------------------------------
    # Runtime overrides
    # ------------------------------------------------------------------

    def set(
        self,
        flag: str,
        enabled: bool,
    ) -> None:
        """Set a process-local runtime override."""

        name = self._normalize_name(
            flag
        )

        with self._lock:
            self._overrides[name] = bool(
                enabled
            )

    def unset(
        self,
        flag: str,
    ) -> None:
        """Remove a runtime override."""

        name = self._normalize_name(
            flag
        )

        with self._lock:
            self._overrides.pop(
                name,
                None,
            )

    def clear_overrides(self) -> None:
        """Remove all runtime overrides."""

        with self._lock:
            self._overrides.clear()

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def all(
        self,
    ) -> dict[str, bool]:
        """Return all resolved flags."""

        flags = self._load()

        result = {
            name: self._coerce_bool(
                value.get(
                    "enabled",
                    False,
                )
                if isinstance(value, dict)
                else value
            )
            for name, value in flags.items()
        }

        with self._lock:
            result.update(
                self._overrides
            )

        return dict(
            sorted(result.items())
        )

    def names(self) -> list[str]:
        """Return feature names from config + overrides (not platform modules)."""

        names: set[str] = set()
        raw: dict = {}
        if self._config_path.exists():
            try:
                import yaml

                loaded = yaml.safe_load(
                    self._config_path.read_text(encoding="utf-8")
                )
                if isinstance(loaded, dict):
                    raw = loaded
            except (OSError, ValueError, yaml.YAMLError):
                raw = {}
        configured = raw.get("feature_flags", {})
        if isinstance(configured, dict):
            names.update(str(k) for k in configured)
        with self._lock:
            names.update(self._overrides)
        return sorted(names)

    def reload(self) -> None:
        """Invalidate cached configuration."""

        self._load.cache_clear()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @lru_cache(maxsize=1)
    def _load(
        self,
    ) -> dict[str, Any]:
        raw: dict[str, Any] = {}

        if self._config_path.exists():
            try:
                import yaml

                loaded = yaml.safe_load(
                    self._config_path.read_text(
                        encoding="utf-8"
                    )
                )

                if isinstance(
                    loaded,
                    dict,
                ):
                    raw = loaded

            except (
                OSError,
                ValueError,
                yaml.YAMLError,
            ):
                raw = {}

        result: dict[str, Any] = {}

        configured = raw.get(
            "feature_flags",
            {},
        )

        if isinstance(
            configured,
            dict,
        ):
            result.update(
                configured
            )

        cfg = get_platform_config()

        modules = getattr(
            cfg,
            "modules",
            {},
        )

        if isinstance(
            modules,
            dict,
        ):
            for name, value in modules.items():
                if isinstance(
                    value,
                    bool,
                ):
                    result.setdefault(
                        name,
                        value,
                    )

        environment_flags = raw.get(
            "environments",
            {},
        )

        if isinstance(
            environment_flags,
            dict,
        ):
            environment_config = (
                environment_flags.get(
                    self._environment,
                    {},
                )
            )

            if isinstance(
                environment_config,
                dict,
            ):
                result.update(
                    environment_config
                )

        return result

    # ------------------------------------------------------------------
    # Environment overrides
    # ------------------------------------------------------------------

    def _environment_value(
        self,
        name: str,
    ) -> bool | None:
        key = (
            "FEATURE_"
            + name.upper()
            .replace("-", "_")
            .replace(".", "_")
        )

        value = os.getenv(key)

        if value is None:
            return None

        return self._coerce_bool(
            value
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_name(
        name: str,
    ) -> str:
        normalized = name.strip()

        if not normalized:
            raise FeatureFlagError(
                "feature flag name must not be empty"
            )

        return normalized

    @staticmethod
    def _coerce_bool(
        value: Any,
    ) -> bool:
        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            int,
        ):
            return value != 0

        if isinstance(
            value,
            str,
        ):
            normalized = value.strip().lower()

            if normalized in {
                "1",
                "true",
                "yes",
                "on",
                "enabled",
            }:
                return True

            if normalized in {
                "0",
                "false",
                "no",
                "off",
                "disabled",
            }:
                return False

        raise FeatureFlagError(
            f"invalid feature flag value: {value!r}"
        )

_flags = FeatureFlags()

def is_enabled(
    flag: str,
    *,
    default: bool = False,
) -> bool:
    """Check whether a feature is enabled."""

    environment_value = _flags._environment_value(
        flag
    )

    if environment_value is not None:
        return environment_value

    return _flags.is_enabled(
        flag,
        default=default,
    )

def all_flags() -> dict[str, bool]:
    """Return all resolved feature flags."""

    result = _flags.all()

    for name in list(result):
        environment_value = (
            _flags._environment_value(
                name
            )
        )

        if environment_value is not None:
            result[name] = environment_value

    return result

def get_feature_flags() -> FeatureFlags:
    """Return the process-wide feature-flag service."""

    return _flags

__all__ = [
    "FeatureFlag",
    "FeatureFlagError",
    "FeatureFlags",
    "all_flags",
    "get_feature_flags",
    "is_enabled",
]
