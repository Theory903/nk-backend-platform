"""Tests for metrics: counters, histograms, gauges, export, helpers."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from {{cookiecutter.project_name}}.operations.metrics import (
    HAS_PROMETHEUS,
    NkCounter,
    NkGauge,
    NkHistogram,
    create_registry,
    export_metrics,
    metrics_content_type,
    record_auth_attempt,
    record_http_request,
    record_llm_usage,
    record_queue_job,
)


class TestNoOpAndRegistryIsolation:
    def test_operations_never_raise_without_or_with_prometheus(self) -> None:
        registry = create_registry()
        counter = NkCounter(
            name="test_noop_counter",
            description="noop counter",
            registry=registry,
        )
        gauge = NkGauge(
            name="test_noop_gauge",
            description="noop gauge",
            registry=registry,
        )
        hist = NkHistogram(
            name="test_noop_hist",
            description="noop hist",
            registry=registry,
        )

        counter.inc()
        counter.inc(2.0)
        gauge.set(1.0)
        gauge.inc()
        gauge.dec()
        hist.observe(0.01)
        with hist.time():
            pass

    def test_create_registry_none_when_prometheus_absent(self) -> None:
        if HAS_PROMETHEUS:
            assert create_registry() is not None
        else:
            assert create_registry() is None


class TestLabelValidation:
    def test_missing_label_raises(self) -> None:
        counter = NkCounter(
            name="test_labels_missing",
            description="labeled",
            label_names=("method", "status"),
            registry=create_registry(),
        )
        with pytest.raises(ValueError, match="missing"):
            counter.inc(method="GET")

    def test_unexpected_label_raises(self) -> None:
        counter = NkCounter(
            name="test_labels_unexpected",
            description="labeled",
            label_names=("method",),
            registry=create_registry(),
        )
        with pytest.raises(ValueError, match="unexpected"):
            counter.inc(method="GET", status="200")


class TestNkCounter:
    def test_inc_without_labels(self) -> None:
        counter = NkCounter(
            name="test_counter_nolabels",
            description="A test counter",
            registry=create_registry(),
        )
        counter.inc()
        counter.inc(5.0)

    def test_inc_with_labels(self) -> None:
        counter = NkCounter(
            name="test_counter_labels",
            description="A labeled counter",
            label_names=("method", "status"),
            registry=create_registry(),
        )
        counter.inc(method="GET", status="200")
        counter.inc(3.0, method="POST", status="201")


class TestNkHistogram:
    def test_observe_without_labels(self) -> None:
        hist = NkHistogram(
            name="test_hist_nolabels",
            description="A test histogram",
            registry=create_registry(),
        )
        hist.observe(0.05)
        hist.observe(0.15)

    def test_observe_with_labels(self) -> None:
        hist = NkHistogram(
            name="test_hist_labels",
            description="Labeled histogram",
            label_names=("method",),
            registry=create_registry(),
        )
        hist.observe(0.1, method="GET")

    def test_time_context_manager(self) -> None:
        hist = NkHistogram(
            name="test_hist_timer",
            description="Timer test",
            registry=create_registry(),
        )
        with hist.time():
            pass


class TestNkGauge:
    def test_set_inc_dec(self) -> None:
        gauge = NkGauge(
            name="test_gauge",
            description="A test gauge",
            registry=create_registry(),
        )
        gauge.set(10)
        gauge.inc(5)
        gauge.dec(3)


class TestExportFormat:
    def test_export_returns_bytes(self) -> None:
        result = export_metrics()
        assert isinstance(result, bytes)

    def test_metrics_content_type_is_str(self) -> None:
        assert isinstance(metrics_content_type(), str)

    @pytest.mark.skipif(not HAS_PROMETHEUS, reason="prometheus_client not installed")
    def test_export_contains_registered_metrics(self) -> None:
        from {{cookiecutter.project_name}}.operations import metrics as m

        _ = m.http_requests_total
        _ = m.http_request_duration
        result = export_metrics()
        text = result.decode()
        assert "# HELP" in text or "# TYPE" in text


class TestRecordHelpers:
    def test_record_helpers_do_not_raise(self) -> None:
        record_http_request(
            method="GET",
            path="/users/{user_id}",
            status=200,
            duration_s=0.012,
        )
        record_llm_usage(
            provider="openai",
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=0.001,
        )
        record_auth_attempt(method="password", success=True)
        record_auth_attempt(method="password", success=False)
        record_queue_job(task="relay_outbox", outcome="success", duration_s=0.2)
        record_queue_job(task="relay_outbox", outcome="failure")


class TestDuplicateConstruction:
    def test_duplicate_construction_does_not_crash(self) -> None:
        registry = create_registry()
        first = NkCounter(
            name="test_dup_counter",
            description="first",
            registry=registry,
        )
        second = NkCounter(
            name="test_dup_counter",
            description="second",
            registry=registry,
        )
        first.inc()
        second.inc(2.0)


class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_200(self) -> None:
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from {{cookiecutter.project_name}}.web.api.monitoring.views import (
            router as monitoring_router,
        )

        app = FastAPI()
        app.include_router(monitoring_router, prefix="/api")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/metrics")
            assert resp.status_code == 200
            assert isinstance(resp.content, bytes)

    @pytest.mark.asyncio
    async def test_metrics_middleware_handles_included_router(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from fastapi import APIRouter, FastAPI
        from httpx import ASGITransport, AsyncClient

        from {{cookiecutter.project_name}}.web.middleware import metrics
        from {{cookiecutter.project_name}}.web.middleware.metrics import (
            PrometheusMetricsMiddleware,
        )

        record_request = Mock()
        monkeypatch.setattr(metrics, "record_http_request", record_request)

        router = APIRouter()

        @router.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.add_middleware(PrometheusMetricsMiddleware)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        record_request.assert_called_once()
        request_metrics = record_request.call_args.kwargs
        assert request_metrics["method"] == "GET"
        assert request_metrics["path"] == "/health"
        assert request_metrics["status"] == 200
        assert request_metrics["duration_s"] >= 0
