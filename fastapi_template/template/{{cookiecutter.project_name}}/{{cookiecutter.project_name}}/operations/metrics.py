"""
Platform metrics with Prometheus backing and safe no-op fallback.

Design goals:

- Prometheus is optional.
- Application code never imports prometheus_client directly.
- Metrics are registered once.
- Metric operations are safe when Prometheus is unavailable.
- Typed wrappers provide a stable platform API.
- Labels are explicit to reduce accidental cardinality explosions.
- Metrics can be exported through a standard /metrics endpoint.

Production guidance:

    Good labels:
        method
        route
        status
        provider
        outcome
        direction

    Dangerous high-cardinality labels (never use these):
        user_id
        org_id
        request_id
        trace_id
        email
        arbitrary URL / raw path with IDs
        exception message
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)
_KNOWN_QUEUE_TASKS = frozenset(
    {
        "deliver_webhook",
        "relay_outbox",
        "webhook_delivery",
    }
)


def _queue_task_label(task: str) -> str:
    """Map untrusted task names to a bounded metric label set."""
    return task if task in _KNOWN_QUEUE_TASKS else "other"


# ---------------------------------------------------------------------------
# Optional Prometheus dependency
# ---------------------------------------------------------------------------

try:
    from prometheus_client import (
        REGISTRY as _DEFAULT_REGISTRY,
        CollectorRegistry,
        Counter as _PcCounter,
        Gauge as _PcGauge,
        Histogram as _PcHistogram,
        generate_latest,
        multiprocess,
    )

    HAS_PROMETHEUS = True

except ImportError:
    CollectorRegistry = Any  # type: ignore[misc,assignment]
    _DEFAULT_REGISTRY = None  # type: ignore[assignment]
    _PcCounter = Any  # type: ignore[misc,assignment]
    _PcGauge = Any  # type: ignore[misc,assignment]
    _PcHistogram = Any  # type: ignore[misc,assignment]
    generate_latest = None  # type: ignore[assignment]
    multiprocess = None  # type: ignore[assignment]

    HAS_PROMETHEUS = False


# ---------------------------------------------------------------------------
# No-op implementation
# ---------------------------------------------------------------------------


class _NoOpMetric:
    """
    Zero-cost metric implementation when Prometheus is unavailable.

    Methods intentionally mirror prometheus_client metric handles.
    """

    __slots__ = ()

    def labels(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> _NoOpMetric:
        return self

    def inc(
        self,
        amount: float = 1.0,
    ) -> None:
        return None

    def dec(
        self,
        amount: float = 1.0,
    ) -> None:
        return None

    def set(
        self,
        value: float,
    ) -> None:
        return None

    def observe(
        self,
        value: float,
    ) -> None:
        return None

    def time(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> _NoOpTimer:
        return _NoOpTimer()


class _NoOpTimer:
    """
    No-op context manager returned by Histogram.time().
    """

    __slots__ = ()

    def __enter__(self) -> _NoOpTimer:
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> bool:
        return False


# ---------------------------------------------------------------------------
# Duplicate registration helpers
# ---------------------------------------------------------------------------


def _is_duplicate_registration_error(exc: BaseException) -> bool:
    """
    True for prometheus_client duplicate-registration failures.

    Covers:
    - ValueError (documented API)
    - DuplicateTimeseries (current client)
    - AlreadyRegistered (legacy name, if present)
    """
    name = type(exc).__name__
    if name in {"DuplicateTimeseries", "AlreadyRegistered"}:
        return True

    if isinstance(exc, ValueError):
        message = str(exc).lower()
        return "duplicat" in message or "already" in message

    return False


def _lookup_existing_collector(
    *,
    name: str,
    registry: CollectorRegistry | None,
) -> Any | None:
    """
    Best-effort lookup of an already-registered collector by metric name.
    """
    if not HAS_PROMETHEUS:
        return None

    target = registry if registry is not None else _DEFAULT_REGISTRY
    names_map = getattr(target, "_names_to_collectors", None)
    if not isinstance(names_map, dict):
        return None

    return names_map.get(name)


def _create_or_reuse(
    factory: Any,
    *,
    name: str,
    description: str,
    label_names: tuple[str, ...],
    registry: CollectorRegistry | None,
    **extra: Any,
) -> Any:
    """
    Create a Prometheus metric, reusing an existing collector on re-import.

    On duplicate registration: look up the existing collector when possible;
    otherwise log a warning and fall back to ``_NoOpMetric`` so reload does
    not crash the process.
    """
    kwargs: dict[str, Any] = dict(extra)

    if registry is not None:
        kwargs["registry"] = registry

    try:
        return factory(
            name,
            description,
            labelnames=label_names,
            **kwargs,
        )
    except Exception as exc:
        if not _is_duplicate_registration_error(exc):
            raise

        existing = _lookup_existing_collector(name=name, registry=registry)
        if existing is not None:
            logger.debug(
                "Reusing existing Prometheus metric %r after duplicate registration",
                name,
            )
            return existing

        logger.warning(
            "Duplicate Prometheus metric registration for %r; "
            "falling back to no-op metric",
            name,
            exc_info=True,
        )
        return _NoOpMetric()


# ---------------------------------------------------------------------------
# Base metric
# ---------------------------------------------------------------------------


class _MetricBase:
    """
    Common functionality for all platform metrics.
    """

    __slots__ = (
        "_labels",
        "_impl",
        "_multiprocess_mode",
    )

    def __init__(
        self,
        *,
        name: str,
        description: str,
        label_names: tuple[str, ...] = (),
        registry: CollectorRegistry | None = None,
        multiprocess_mode: str | None = None,
    ) -> None:
        self._labels = label_names
        self._multiprocess_mode = multiprocess_mode

        if HAS_PROMETHEUS:
            self._impl = self._create_metric(
                name=name,
                description=description,
                label_names=label_names,
                registry=registry,
                multiprocess_mode=multiprocess_mode,
            )
        else:
            self._impl = _NoOpMetric()

    def _create_metric(
        self,
        *,
        name: str,
        description: str,
        label_names: tuple[str, ...],
        registry: CollectorRegistry | None,
        multiprocess_mode: str | None,
    ) -> Any:
        raise NotImplementedError

    def _validate_labels(
        self,
        labels: dict[str, str],
    ) -> None:
        """
        Validate supplied label names.

        Failing early is preferable to silently producing broken metrics.
        """
        expected = set(self._labels)
        supplied = set(labels)

        missing = expected - supplied
        unexpected = supplied - expected

        if missing:
            raise ValueError(
                f"missing metric labels: {sorted(missing)}"
            )

        if unexpected:
            raise ValueError(
                f"unexpected metric labels: {sorted(unexpected)}"
            )

    def labels(
        self,
        **labels: str,
    ) -> Any:
        """
        Return a labeled Prometheus metric handle.

        For no-op metrics this returns a no-op handle.
        """
        self._validate_labels(labels)

        if not self._labels:
            return self._impl

        return self._impl.labels(**labels)


# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------


class NkCounter(_MetricBase):
    """
    Monotonically increasing counter.

    Examples:

        requests
        errors
        events
        tokens
    """

    __slots__ = ()

    def _create_metric(
        self,
        *,
        name: str,
        description: str,
        label_names: tuple[str, ...],
        registry: CollectorRegistry | None,
        multiprocess_mode: str | None,
    ) -> Any:
        return _create_or_reuse(
            _PcCounter,
            name=name,
            description=description,
            label_names=label_names,
            registry=registry,
        )

    def inc(
        self,
        amount: float = 1.0,
        /,
        **labels: str,
    ) -> None:
        if self._labels:
            self._validate_labels(labels)
            self._impl.labels(**labels).inc(amount)
        else:
            if labels:
                self._validate_labels(labels)

            self._impl.inc(amount)


# ---------------------------------------------------------------------------
# Gauge
# ---------------------------------------------------------------------------


class NkGauge(_MetricBase):
    """
    Gauge for values that can increase or decrease.

    Examples:

        active sessions
        queue depth
        connected workers
        memory usage
    """

    __slots__ = ()

    def _create_metric(
        self,
        *,
        name: str,
        description: str,
        label_names: tuple[str, ...],
        registry: CollectorRegistry | None,
        multiprocess_mode: str | None,
    ) -> Any:
        kwargs = (
            {"multiprocess_mode": multiprocess_mode}
            if multiprocess_mode is not None
            else {}
        )
        return _create_or_reuse(
            _PcGauge,
            name=name,
            description=description,
            label_names=label_names,
            registry=registry,
            **kwargs,
        )

    def set(
        self,
        value: float,
        /,
        **labels: str,
    ) -> None:
        if self._labels:
            self._validate_labels(labels)
            self._impl.labels(**labels).set(value)
        else:
            if labels:
                self._validate_labels(labels)

            self._impl.set(value)

    def inc(
        self,
        amount: float = 1.0,
        /,
        **labels: str,
    ) -> None:
        if self._labels:
            self._validate_labels(labels)
            self._impl.labels(**labels).inc(amount)
        else:
            if labels:
                self._validate_labels(labels)

            self._impl.inc(amount)

    def dec(
        self,
        amount: float = 1.0,
        /,
        **labels: str,
    ) -> None:
        if self._labels:
            self._validate_labels(labels)
            self._impl.labels(**labels).dec(amount)
        else:
            if labels:
                self._validate_labels(labels)

            self._impl.dec(amount)


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


class NkHistogram(_MetricBase):
    """
    Histogram for distributions such as:

        request latency
        database latency
        queue latency
        payload size
    """

    __slots__ = ("_buckets",)

    DEFAULT_BUCKETS = (
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    )

    def __init__(
        self,
        *,
        name: str,
        description: str,
        buckets: tuple[float, ...] = DEFAULT_BUCKETS,
        label_names: tuple[str, ...] = (),
        registry: CollectorRegistry | None = None,
        multiprocess_mode: str | None = None,
    ) -> None:
        self._buckets = buckets

        super().__init__(
            name=name,
            description=description,
            label_names=label_names,
            registry=registry,
            multiprocess_mode=multiprocess_mode,
        )

    def _create_metric(
        self,
        *,
        name: str,
        description: str,
        label_names: tuple[str, ...],
        registry: CollectorRegistry | None,
        multiprocess_mode: str | None,
    ) -> Any:
        return _create_or_reuse(
            _PcHistogram,
            name=name,
            description=description,
            label_names=label_names,
            registry=registry,
            buckets=self._buckets,
        )

    def observe(
        self,
        value: float,
        /,
        **labels: str,
    ) -> None:
        if self._labels:
            self._validate_labels(labels)
            self._impl.labels(**labels).observe(value)
        else:
            if labels:
                self._validate_labels(labels)

            self._impl.observe(value)

    @contextmanager
    def time(
        self,
        **labels: str,
    ) -> Iterator[Any]:
        """
        Measure execution time.

        Example:

            with http_request_duration.time(
                method="GET",
                path="/users/{user_id}",
            ):
                ...
        """
        if self._labels:
            self._validate_labels(labels)
            timer = self._impl.labels(**labels).time()
        else:
            if labels:
                self._validate_labels(labels)

            timer = self._impl.time()

        with timer:
            yield timer


# ---------------------------------------------------------------------------
# Optional dedicated registry
# ---------------------------------------------------------------------------


def create_registry() -> CollectorRegistry | None:
    """
    Create an isolated Prometheus registry.

    Useful for:

    - unit tests
    - isolated applications
    - multi-tenant metric exporters

    Returns None when Prometheus is unavailable.
    """
    if not HAS_PROMETHEUS:
        return None

    return CollectorRegistry()


# ---------------------------------------------------------------------------
# Platform metrics
# ---------------------------------------------------------------------------

http_requests_total = NkCounter(
    name="nk_http_requests_total",
    description=(
        "Total HTTP requests by HTTP method, route and status code."
    ),
    label_names=(
        "method",
        "path",
        "status",
    ),
)


http_request_duration = NkHistogram(
    name="nk_http_request_duration_seconds",
    description="HTTP request latency distribution.",
    label_names=(
        "method",
        "path",
    ),
)


active_sessions = NkGauge(
    name="nk_active_sessions",
    description="Currently active user sessions.",
)


outbox_pending = NkGauge(
    name="nk_outbox_pending_count",
    description="Unsent outbox rows awaiting relay.",
)


llm_tokens_total = NkCounter(
    name="nk_llm_tokens_total",
    description="LLM tokens consumed by provider and direction.",
    label_names=(
        "provider",
        "direction",
    ),
)


llm_cost_usd_total = NkCounter(
    name="nk_llm_cost_usd_total",
    description="Estimated LLM cost in USD by provider.",
    label_names=(
        "provider",
    ),
)


llm_request_duration = NkHistogram(
    name="nk_llm_request_duration_seconds",
    description="LLM completion latency by provider and capability.",
    label_names=(
        "provider",
        "capability",
        "model",
    ),
)


genai_tool_duration = NkHistogram(
    name="nk_genai_tool_duration_seconds",
    description="Tool invocation latency for agent runs.",
    label_names=(
        "tool",
        "outcome",
    ),
)


genai_tool_invocations_total = NkCounter(
    name="nk_genai_tool_invocations_total",
    description="Tool invocations by tool name and outcome.",
    label_names=(
        "tool",
        "outcome",
    ),
)


agent_steps_total = NkCounter(
    name="nk_agent_steps_total",
    description="Agent execution steps by agent type and outcome.",
    label_names=(
        "agent_type",
        "outcome",
    ),
)


# ---------------------------------------------------------------------------
# Additional platform metrics
# ---------------------------------------------------------------------------

db_queries_total = NkCounter(
    name="nk_db_queries_total",
    description="Database queries by operation and outcome.",
    label_names=(
        "operation",
        "outcome",
    ),
)


db_query_duration = NkHistogram(
    name="nk_db_query_duration_seconds",
    description="Database query latency distribution.",
    label_names=(
        "operation",
    ),
)


cache_operations_total = NkCounter(
    name="nk_cache_operations_total",
    description="Cache operations by operation and outcome.",
    label_names=(
        "operation",
        "outcome",
    ),
)


queue_jobs_total = NkCounter(
    name="nk_queue_jobs_total",
    description="Background jobs by task and outcome.",
    label_names=(
        "task",
        "outcome",
    ),
)


queue_job_duration = NkHistogram(
    name="nk_queue_job_duration_seconds",
    description="Background job execution latency.",
    label_names=(
        "task",
    ),
)

worker_heartbeat = NkGauge(
    name="nk_worker_heartbeat",
    description="Whether the background worker is alive and accepting work.",
    multiprocess_mode="liveall",
)

queue_enqueues_total = NkCounter(
    name="nk_queue_enqueues_total",
    description="Task enqueue attempts by task and outcome.",
    label_names=(
        "task",
        "outcome",
    ),
)


queue_depth = NkGauge(
    name="nk_queue_depth",
    description="Current background queue depth.",
    label_names=(
        "queue",
    ),
)

dlq_messages = NkGauge(
    name="nk_dlq_messages",
    description="Current dead-letter queue depth.",
    label_names=("queue",),
)


auth_attempts_total = NkCounter(
    name="nk_auth_attempts_total",
    description="Authentication attempts by method and outcome.",
    label_names=(
        "method",
        "outcome",
    ),
)


auth_lockouts_total = NkCounter(
    name="nk_auth_lockouts_total",
    description="Authentication account lockouts.",
)


webhook_deliveries_total = NkCounter(
    name="nk_webhook_deliveries_total",
    description="Webhook deliveries by outcome.",
    label_names=(
        "outcome",
    ),
)


webhook_delivery_duration = NkHistogram(
    name="nk_webhook_delivery_duration_seconds",
    description="Webhook delivery latency.",
)


rate_limit_rejections_total = NkCounter(
    name="nk_rate_limit_rejections_total",
    description="Requests rejected by rate limiting.",
    label_names=(
        "scope",
    ),
)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_metrics() -> bytes:
    """
    Export registered metrics using Prometheus exposition format.

    Safe no-op when prometheus_client is not installed.
    """
    if not HAS_PROMETHEUS:
        return b"# prometheus_client not installed\n"

    assert generate_latest is not None

    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        assert multiprocess is not None
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)

    return generate_latest()


# ---------------------------------------------------------------------------
# ASGI / FastAPI helper
# ---------------------------------------------------------------------------


def metrics_content_type() -> str:
    """
    Return the Prometheus exposition content type.
    """
    if not HAS_PROMETHEUS:
        return "text/plain; version=0.0.4"

    return (
        "text/plain; version=0.0.4; "
        "charset=utf-8; "
        "escaping=underscores"
    )


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def record_http_request(
    *,
    method: str,
    path: str,
    status: int,
    duration_s: float,
) -> None:
    """
    Record a completed HTTP request.

    Prefer FastAPI route templates (e.g. ``/users/{user_id}``) over raw
    request URLs so ``path`` labels stay low-cardinality.
    """
    status_label = str(status)

    http_requests_total.inc(
        method=method,
        path=path,
        status=status_label,
    )

    http_request_duration.observe(
        duration_s,
        method=method,
        path=path,
    )


def record_llm_usage(
    *,
    provider: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """
    Record LLM token and cost consumption.
    """
    if prompt_tokens > 0:
        llm_tokens_total.inc(
            prompt_tokens,
            provider=provider,
            direction="input",
        )

    if completion_tokens > 0:
        llm_tokens_total.inc(
            completion_tokens,
            provider=provider,
            direction="output",
        )

    if cost_usd > 0:
        llm_cost_usd_total.inc(
            cost_usd,
            provider=provider,
        )


def record_llm_latency(
    *,
    provider: str,
    capability: str,
    model: str,
    duration_s: float,
) -> None:
    """Record LLM completion latency for GenAI observability."""
    if duration_s <= 0:
        return
    llm_request_duration.observe(
        duration_s,
        provider=provider,
        capability=capability,
        model=model,
    )


def record_genai_tool(
    *,
    tool_name: str,
    duration_s: float,
    outcome: str,
) -> None:
    """Record agent tool invocation latency and outcome."""
    genai_tool_invocations_total.inc(
        tool=tool_name,
        outcome=outcome,
    )
    if duration_s > 0:
        genai_tool_duration.observe(
            duration_s,
            tool=tool_name,
            outcome=outcome,
        )


def record_auth_attempt(
    *,
    method: str,
    success: bool,
) -> None:
    """
    Record an authentication attempt.
    """
    auth_attempts_total.inc(
        method=method,
        outcome="success" if success else "failure",
    )


def record_queue_job(
    *,
    task: str,
    outcome: str,
    duration_s: float | None = None,
) -> None:
    """
    Record background task execution.
    """
    queue_task = _queue_task_label(task)
    queue_jobs_total.inc(
        task=queue_task,
        outcome=outcome,
    )

    if duration_s is not None:
        queue_job_duration.observe(
            duration_s,
            task=queue_task,
        )


def record_queue_enqueue(
    *,
    task: str,
    outcome: str,
) -> None:
    """Record a task enqueue outcome using bounded task names."""
    queue_enqueues_total.inc(
        task=_queue_task_label(task),
        outcome=outcome,
    )


def set_worker_heartbeat(
    alive: bool,
) -> None:
    """Set the process-local worker liveness gauge."""
    worker_heartbeat.set(1 if alive else 0)


def mark_worker_process_dead(pid: int | None = None) -> None:
    """Remove this process from live multiprocess gauges on graceful exit."""
    if not HAS_PROMETHEUS or multiprocess is None:
        return
    # Taskiq workers do not go through __main__ multiproc setup; skip cleanup
    # when the shared metrics directory is unset to avoid PathLike TypeError.
    if not (
        os.getenv("PROMETHEUS_MULTIPROC_DIR")
        or os.getenv("prometheus_multiproc_dir")  # noqa: SIM112
    ):
        return
    multiprocess.mark_process_dead(pid or os.getpid())


__all__ = [
    "HAS_PROMETHEUS",
    "NkCounter",
    "NkGauge",
    "NkHistogram",
    "active_sessions",
    "agent_steps_total",
    "auth_attempts_total",
    "auth_lockouts_total",
    "cache_operations_total",
    "create_registry",
    "db_queries_total",
    "db_query_duration",
    "dlq_messages",
    "export_metrics",
    "http_request_duration",
    "http_requests_total",
    "genai_tool_duration",
    "genai_tool_invocations_total",
    "llm_cost_usd_total",
    "llm_request_duration",
    "llm_tokens_total",
    "metrics_content_type",
    "outbox_pending",
    "queue_depth",
    "queue_enqueues_total",
    "queue_job_duration",
    "queue_jobs_total",
    "rate_limit_rejections_total",
    "record_auth_attempt",
    "record_genai_tool",
    "record_http_request",
    "record_llm_latency",
    "record_llm_usage",
    "record_queue_job",
    "record_queue_enqueue",
    "mark_worker_process_dead",
    "set_worker_heartbeat",
    "worker_heartbeat",
    "webhook_deliveries_total",
    "webhook_delivery_duration",
]
