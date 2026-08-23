from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

MANIFEST_FILENAME = "platform.yaml"


class ProvidersConfig(BaseModel):
    api_type: str = "rest"
    database: str = "none"
    orm: str = "none"
    ci: str = "none"


class ObservabilityConfig(BaseModel):
    prometheus: bool = False
    opentelemetry: bool = False
    sentry: bool = False


class PlatformConfig(BaseModel):
    """
    Typed view of platform.yaml: profile, providers and module switches.
    """

    project: str
    profile: str = ""
    providers: ProvidersConfig = ProvidersConfig()
    modules: dict[str, bool] = {}
    observability: ObservabilityConfig = ObservabilityConfig()

    def module_enabled(self, name: str) -> bool:
        return self.modules.get(name, False)


def manifest_path() -> Path:
    return Path(__file__).resolve().parents[2] / MANIFEST_FILENAME


@lru_cache(maxsize=1)
def get_platform_config(path: str | None = None) -> PlatformConfig:
    """
    Load and cache the platform manifest as a typed config.
    """
    target = Path(path) if path else manifest_path()
    raw: dict[str, Any] = yaml.safe_load(target.read_text()) or {}
    return PlatformConfig.model_validate(raw)
