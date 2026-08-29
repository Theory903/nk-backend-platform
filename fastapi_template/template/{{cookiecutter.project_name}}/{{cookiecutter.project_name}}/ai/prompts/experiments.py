"""Deterministic A/B assignment for prompt experiments."""

from __future__ import annotations

import hashlib

from {{cookiecutter.project_name}}.ai.prompts.exceptions import PromptExperimentError
from {{cookiecutter.project_name}}.ai.prompts.models import PromptExperiment, PromptVariant


def assign_variant(
    experiment: PromptExperiment,
    subject_id: str,
) -> PromptVariant:
    """
    Assign a subject to an experiment variant deterministically.

    Same (experiment, salt, subject) always maps to the same variant.
    """
    if not experiment.variants:
        raise PromptExperimentError(
            f"experiment '{experiment.name}' has no variants"
        )

    total = sum(v.weight for v in experiment.variants)
    if abs(total - 1.0) > 1e-6:
        raise PromptExperimentError(
            f"experiment '{experiment.name}' weights must sum to 1.0, got {total}"
        )

    key = f"{experiment.name}:{experiment.salt}:{subject_id}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF

    cumulative = 0.0
    for variant in experiment.variants:
        cumulative += variant.weight
        if bucket < cumulative:
            return variant
    return experiment.variants[-1]
