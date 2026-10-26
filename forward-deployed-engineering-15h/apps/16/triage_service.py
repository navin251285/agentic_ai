"""Basket Bazaar triage service, version 1.2.0 (lab, invented data): logs, a trace and a latency metric."""
import os
import time

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Histogram, generate_latest

VERSION = "1.2.0"
ERP_URL = os.environ["ERP_URL"]                        # the customer API, by its Compose service name
CLIENT_ID = os.environ["ERP_READER_CLIENT_ID"]
CLIENT_SECRET = os.environ["ERP_READER_CLIENT_SECRET"]  # injected from the secret store, never in the image

# Traces: spans go to the Collector named by OTEL_EXPORTER_OTLP_ENDPOINT (set in Compose).
provider = TracerProvider(resource=Resource.create({"service.name": "bb-triage", "service.version": VERSION}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("bb-triage")


def add_trace_id(_, __, event: dict) -> dict:
    """Put the current trace id on every log line, so a line can be matched to its trace.
    trace_id appears only inside a request span; a background task with no span has none."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event["trace_id"] = format(ctx.trace_id, "032x")
    return event


structlog.configure(processors=[structlog.processors.add_log_level, add_trace_id,
                                structlog.processors.TimeStamper(fmt="iso"),
                                structlog.processors.JSONRenderer()])
log = structlog.get_logger()
LATENCY = Histogram("triage_request_seconds", "Triage request time in seconds",
                    ["route", "outcome"], buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0))

app = FastAPI(title="Basket Bazaar triage", version=VERSION)
FastAPIInstrumentor.instrument_app(app, excluded_urls="metrics,health")  # one server span per request
HTTPXClientInstrumentor().instrument()                                   # one client span per call to the customer API


def erp_token() -> str:
    """Client credentials grant (lesson 13): exchange the account's secret for a short-lived token."""
    r = httpx.post(f"{ERP_URL}/oauth/token", auth=(CLIENT_ID, CLIENT_SECRET),
                   data={"grant_type": "client_credentials", "scope": "orders:read"}, timeout=5)
    r.raise_for_status()
    return r.json()["access_token"]


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/triage/{order_id}")
def triage(order_id: str):
    start, outcome = time.perf_counter(), "error"
    try:
        r = httpx.get(f"{ERP_URL}/orders", headers={"Authorization": f"Bearer {erp_token()}"}, timeout=5)
        if r.status_code != 200:
            log.error("erp_error", order_id=order_id, erp_status=r.status_code)
            raise HTTPException(502, detail=f"customer API returned {r.status_code}")
        order = next((o for o in r.json()["data"] if o["id"] == order_id), None)
        if order is None:
            raise HTTPException(404, detail="order not found")
        with tracer.start_as_current_span("triage.label") as span:
            label = "missing items" if order["lines_short"] else "complete"
            span.set_attribute("triage.label", label)
        outcome = "ok"
        return {"order_id": order_id, "label": label, "version": VERSION}
    finally:
        ms = (time.perf_counter() - start) * 1000
        LATENCY.labels(route="/triage", outcome=outcome).observe(ms / 1000)
        log.info("triage_done", order_id=order_id, outcome=outcome, duration_ms=round(ms))
