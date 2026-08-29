"""Prompt subsystem exceptions."""

from __future__ import annotations


class PromptError(Exception):
    """Base error for the prompt subsystem."""


class PromptRenderError(PromptError, ValueError):
    """Raised when variable validation or rendering fails."""


class PromptNotFoundError(PromptError, KeyError):
    """Raised when a prompt name/version cannot be resolved."""


class PromptVersionExistsError(PromptError):
    """Raised when registering an immutable version that already exists."""


class PromptLifecycleError(PromptError):
    """Raised for illegal lifecycle transitions."""


class PromptExperimentError(PromptError):
    """Raised when experiment configuration is invalid."""
