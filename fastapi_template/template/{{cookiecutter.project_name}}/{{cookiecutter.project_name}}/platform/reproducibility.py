"""Reproducibility manifest for generated runtime releases."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ReproducibilityManifest:
    """Stable inputs required to compare or reproduce a runtime."""

    config_version: str
    config_hash: str
    dependency_lock_hash: str
    model_versions: dict[str, str] = field(default_factory=dict)
    prompt_versions: dict[str, str] = field(default_factory=dict)
    tool_versions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_inputs(
        cls,
        *,
        config: dict[str, Any],
        lockfile: str,
        model_versions: dict[str, str] | None = None,
        prompt_versions: dict[str, str] | None = None,
        tool_versions: dict[str, str] | None = None,
    ) -> "ReproducibilityManifest":
        return cls(
            config_version=str(config.get("config_version", "1")),
            config_hash=hashlib.sha256(
                json.dumps(
                    config,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            ).hexdigest(),
            dependency_lock_hash=hashlib.sha256(
                lockfile.encode("utf-8")
            ).hexdigest(),
            model_versions=dict(model_versions or {}),
            prompt_versions=dict(prompt_versions or {}),
            tool_versions=dict(tool_versions or {}),
        )

    def fingerprint(self) -> str:
        """Hash all manifest inputs into one release fingerprint."""
        payload = {
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "dependency_lock_hash": self.dependency_lock_hash,
            "model_versions": self.model_versions,
            "prompt_versions": self.prompt_versions,
            "tool_versions": self.tool_versions,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


__all__ = ["ReproducibilityManifest"]
