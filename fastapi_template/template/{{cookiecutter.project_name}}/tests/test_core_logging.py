"""Tests for structured JSON logging with trace_id propagation."""
import json
import logging
import sys

import pytest

from {{cookiecutter.project_name}}.core import logging as logging_mod
from {{cookiecutter.project_name}}.core.logging import (
    JsonFormatter,
    TextFormatter,
    clear_trace_context,
    configure_logging,
    get_logger,
    set_trace_context,
    trace_context,
    trace_id_var,
    request_id_var,
    org_id_var,
    user_id_var,
)


@pytest.fixture(autouse=True)
def _clean_context_and_logging():
    clear_trace_context()
    logging_mod._configured = False
    root = logging.getLogger()
    for handler in root.handlers[:]:
        if getattr(handler, "name", None) == "platform-structured":
            root.removeHandler(handler)
            handler.close()
    yield
    clear_trace_context()
    logging_mod._configured = False
    for handler in root.handlers[:]:
        if getattr(handler, "name", None) == "platform-structured":
            root.removeHandler(handler)
            handler.close()


class TestJsonFormatter:
    def test_valid_json_output(self) -> None:
        formatter = JsonFormatter(environment="test")
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello world", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["environment"] == "test"

    def test_includes_service_and_version(self) -> None:
        formatter = JsonFormatter(
            environment="prod",
            service="api",
            version="1.2.3",
        )
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="msg", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["service"] == "api"
        assert parsed["version"] == "1.2.3"

    def test_includes_trace_id_when_set(self) -> None:
        set_trace_context(trace_id="abc123")
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="msg", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["trace_id"] == "abc123"

    def test_trace_id_empty_when_not_set(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="msg", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert "trace_id" not in parsed

    def test_includes_org_and_user_context(self) -> None:
        set_trace_context(org_id="org_1", user_id="usr_2")
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="msg", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["org_id"] == "org_1"
        assert parsed["user_id"] == "usr_2"

    def test_extra_fields_serialized(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="msg", args=(), exc_info=None,
        )
        record.custom_field = {"nested": True}
        parsed = json.loads(formatter.format(record))
        assert parsed["custom_field"]["nested"] is True

    def test_exception_included(self) -> None:
        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="t.py",
                lineno=1, msg="failed", args=(), exc_info=sys.exc_info(),
            )
        parsed = json.loads(formatter.format(record))
        assert parsed["exception"]["type"] == "ValueError"
        assert "test error" in parsed["exception"]["message"]
        assert "traceback" in parsed["exception"]


class TestConfigureLogging:
    def test_json_format_produces_parseable_output(self) -> None:
        configure_logging(
            level="DEBUG",
            log_format="json",
            environment="test",
            service="svc",
            version="0.1.0",
            force=True,
        )
        root = logging.getLogger()
        handler = next(
            h for h in root.handlers if h.name == "platform-structured"
        )
        assert isinstance(handler.formatter, JsonFormatter)
        record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="t.py",
            lineno=1, msg="verify", args=(), exc_info=None,
        )
        parsed = json.loads(handler.formatter.format(record))
        assert parsed["service"] == "svc"
        assert parsed["version"] == "0.1.0"

    def test_text_format_human_readable(self) -> None:
        configure_logging(level="DEBUG", log_format="text", force=True)
        root = logging.getLogger()
        handler = next(
            h for h in root.handlers if h.name == "platform-structured"
        )
        assert isinstance(handler.formatter, TextFormatter)

    def test_level_filtering(self) -> None:
        configure_logging(level="WARNING", log_format="json", force=True)
        root = logging.getLogger()
        assert root.level == logging.WARNING
        logger = get_logger("test_filter")
        assert not logger.isEnabledFor(logging.DEBUG)
        assert not logger.isEnabledFor(logging.INFO)
        assert logger.isEnabledFor(logging.WARNING)

    def test_idempotent_without_force(self) -> None:
        configure_logging(level="INFO", log_format="json", force=True)
        root = logging.getLogger()
        before = [h for h in root.handlers if h.name == "platform-structured"]
        assert len(before) == 1
        configure_logging(level="DEBUG", log_format="text")
        after = [h for h in root.handlers if h.name == "platform-structured"]
        assert len(after) == 1
        assert after[0] is before[0]
        assert isinstance(after[0].formatter, JsonFormatter)

    def test_force_replaces_handlers(self) -> None:
        configure_logging(level="INFO", log_format="json", force=True)
        configure_logging(level="DEBUG", log_format="text", force=True)
        root = logging.getLogger()
        structured = [
            h for h in root.handlers if h.name == "platform-structured"
        ]
        assert len(structured) == 1
        assert isinstance(structured[0].formatter, TextFormatter)

    def test_invalid_level_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid log level"):
            configure_logging(level="NOPE", force=True)

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="log_format"):
            configure_logging(log_format="xml", force=True)


class TestContextPropagation:
    def test_set_and_clear(self) -> None:
        set_trace_context(
            trace_id="t1", request_id="r1", org_id="o1", user_id="u1",
        )
        assert trace_id_var.get() == "t1"
        assert request_id_var.get() == "r1"
        assert org_id_var.get() == "o1"
        assert user_id_var.get() == "u1"
        clear_trace_context()
        assert trace_id_var.get() == ""
        assert request_id_var.get() == ""

    def test_set_multiple_fields(self) -> None:
        set_trace_context(
            trace_id="multi", request_id="req", org_id="org", user_id="usr",
        )
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="msg", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["trace_id"] == "multi"
        assert parsed["request_id"] == "req"
        assert parsed["org_id"] == "org"
        assert parsed["user_id"] == "usr"

    def test_trace_context_restores_previous(self) -> None:
        set_trace_context(trace_id="outer", request_id="req-outer")
        with trace_context(trace_id="inner", org_id="org-inner"):
            assert trace_id_var.get() == "inner"
            assert request_id_var.get() == "req-outer"
            assert org_id_var.get() == "org-inner"
        assert trace_id_var.get() == "outer"
        assert request_id_var.get() == "req-outer"
        assert org_id_var.get() == ""

    def test_trace_context_restores_on_exception(self) -> None:
        set_trace_context(trace_id="before")
        with pytest.raises(RuntimeError):
            with trace_context(trace_id="boom"):
                assert trace_id_var.get() == "boom"
                raise RuntimeError("fail")
        assert trace_id_var.get() == "before"


class TestTextFormatter:
    def test_includes_trace_prefix(self) -> None:
        set_trace_context(trace_id="abcdef0123456789zzzz")
        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="hello", args=(), exc_info=None,
        )
        output = formatter.format(record)
        assert "[trace=abcdef0123456789]" in output
        assert "hello" in output
        assert record.msg == "hello"
