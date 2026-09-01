"""Self-improving loop exports (P30)."""

from {{cookiecutter.project_name}}.research.self_improving.contracts import (
    CanaryDecision,
    ImprovementProposal,
    PipelineRun,
    TelemetrySignal,
)
from {{cookiecutter.project_name}}.research.self_improving.pipeline import (
    SelfImprovingPipeline,
    build_self_improving_pipeline,
)
from {{cookiecutter.project_name}}.research.self_improving.telemetry import (
    TelemetryBridge,
    build_telemetry_bridge,
)

__all__ = [
    "CanaryDecision",
    "ImprovementProposal",
    "PipelineRun",
    "SelfImprovingPipeline",
    "TelemetryBridge",
    "TelemetrySignal",
    "build_self_improving_pipeline",
    "build_telemetry_bridge",
]
