"""Logs and traces for the triage app (step 3, lesson 16).

- Logs: one JSON object per line, with the trace id of the request when there is one, so a log line
  can be matched to its trace. Lesson 16 does this with structlog; this app keeps the standard
  logging module the other files already use, and adds the same trace-id field.
- Traces: one span per step of a triage (the request, the two model calls, the check, the store).
  Spans are written to a JSON-lines file here; lesson 16 sends them to a collector in Compose.

Message text is never logged and never put in a span: the customer's words stay out of both.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

SERVICE_NAME = "bb-triage"
LOGGER_NAME = "delivery_triage"


class JsonFormatter(logging.Formatter):
    """One JSON object per log line. Extra fields come in through logger.info(..., extra={"fields": {...}})."""

    def format(self, record: logging.LogRecord) -> str:
        event: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            event["trace_id"] = format(context.trace_id, "032x")
        event.update(getattr(record, "fields", {}) or {})
        if record.exc_info:
            event["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "unknown"
        return json.dumps(event, default=str)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Send the app's own log lines to stdout as JSON. Safe to call more than once."""
    logger = logging.getLogger(LOGGER_NAME)
    if not any(getattr(h, "_triage_json", False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler._triage_json = True  # marks our handler so a second call does not add another
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(level)
    return logger


def _span_line(span: ReadableSpan) -> dict[str, Any]:
    context = span.get_span_context()
    parent = span.parent
    return {
        "name": span.name,
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
        "parent_id": format(parent.span_id, "016x") if parent else None,
        "duration_ms": round((span.end_time - span.start_time) / 1_000_000, 3),
        "status": span.status.status_code.name,
        "attributes": dict(span.attributes or {}),
    }


class JsonLinesSpanExporter(SpanExporter):
    """Appends each finished span to a file as one JSON line."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def export(self, spans: Any) -> SpanExportResult:
        text = "".join(json.dumps(_span_line(span), default=str) + "\n" for span in spans)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(text)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


class Telemetry:
    """One tracer provider per app. It is not set as the global provider, so tests can build many apps."""

    def __init__(self, trace_file: Path) -> None:
        self.provider = TracerProvider(
            resource=Resource.create({"service.name": SERVICE_NAME}),
        )
        # SimpleSpanProcessor writes each span before the request answers, so the file is up to date.
        self.provider.add_span_processor(SimpleSpanProcessor(JsonLinesSpanExporter(trace_file)))
        self.tracer = self.provider.get_tracer(LOGGER_NAME)
