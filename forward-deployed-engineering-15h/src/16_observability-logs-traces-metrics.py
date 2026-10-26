# %% [markdown]
# # 16 · Observing a customer system: logs, traces and metrics
#
# Level L3 · Part 2 · core · ~30 min · builds on 14
#
# Needs Docker with Compose v2 (`docker compose version`), about 2 GB of free RAM and ports 8160 to 8162 free. Cells tagged `needs-docker` start containers. They run in notebook order, all together, when Docker is enabled. When they are skipped, each prints a skip message and the checks after them print the recorded output from the last real run, labelled as such.
#
# Time: about 30 minutes. The Collector hop is the part most likely to be cut if time runs short; the lesson still teaches it.

# %% [markdown]
# ## Goal
#
# By the end you can add structured logs, a trace and a latency metric to the Basket Bazaar triage service, find one slow request from its log line, and name the hop that made it slow.

# %% [markdown]
# ## Why it matters
#
# A customer says "triage was slow around lunch". Without observability you have a log of plain text lines, no request id and no timings per step. You guess, or you add prints and redeploy. Two requests at once make the guess worse, because their lines mix.
#
# The next cell shows that problem with invented numbers. It is plain Python, no Docker yet.

# %%
import random

random.seed(16)  # invented numbers, the same on every run
steps = ["token ok", "orders fetched", "label done"]
lines = [f"{step} in {random.randint(5, 900)} ms" for _ in range(2) for step in steps]  # two requests, interleaved
print("\n".join(lines))
print("Two requests ran at once. Which 'orders fetched' line was slow for BB-1002? The text does not say.")

# %% [markdown]
# - **Without it:** plain text lines with no request id. A slow request cannot be told apart from a fast one, and the customer gets a guess.
# - **With it:** every log line carries a trace id, every request is a trace of timed steps, and a metric counts the slow ones over time.
# - **When you don't need it:** a demo on your own laptop with one request at a time. A customer system with real traffic needs it.

# %% [markdown]
# ## The idea
#
# Three signals answer three questions. A **structured log** is one JSON line per event: what happened, to which order, how long it took. A **trace** is the timeline of one request: each step is a **span** with a start and a duration, and all spans share one **trace id**. A **metric** counts many requests: how many were slower than one second this hour. Each distinct label value (such as the route) is its own counted **series**.
#
# **OpenTelemetry** is the standard library that creates spans. Spans leave the app in **OTLP** (the OpenTelemetry wire format). The **Collector** receives OTLP and forwards it, so the app does not need to know which tool the customer uses; it stores nothing. **Jaeger** stores and shows traces. **Prometheus** stores metrics.
#
# Analogy: a parcel service. The scan log is the log, the route of one parcel is the trace, and the on-time percentage for the day is the metric.

# %% [markdown]
# ## Picture
#
# The triage service sends spans to the Collector, which passes them to Jaeger. Prometheus scrapes the metric from the service (it fetches `/metrics` on a timer). Only the triage service has a port open to us.

# %% [markdown]
# ```mermaid
# flowchart LR
#     A[Analyst or script on the laptop] -->|localhost:8160| T
#     subgraph net[Customer network, Compose project]
#         T[triage service 1.2.0] -->|http://erp:8000| E[erp: customer API, lab]
#         T -->|"spans, OTLP (the OpenTelemetry wire format)"| C[OTel Collector]
#         C --> J[Jaeger: traces]
#         P[Prometheus: metrics] -->|scrapes /metrics| T
#     end
# ```

# %% [markdown]
# ## Before you start
#
# Run the setup cell first. It loads the settings from `../.env` (names and yes/no only; no values are printed) and creates the folders this lesson writes to. Lesson 14 must be finished: this lesson reuses its mock customer API and its Dockerfile pattern.

# %%
import json, os, shutil, subprocess, sys, time
from pathlib import Path

import httpx

sys.path.insert(0, "..")
from tut_env import is_set, load

load()
DOCKER_RAN = False  # set to True by the cells tagged needs-docker
RUN_LOG = {}        # the real output of each Docker step, saved for the recording
STACK = "tut-forward-deployed-engineering-15h-16"  # one Compose project name for this lesson only
COMPOSE = ["docker", "compose", "-p", STACK, "-f", "../infra/compose/observability-16.yml", "--env-file", "../.env"]
TRIAGE, JAEGER, PROM = "http://localhost:8160", "http://localhost:8161", "http://localhost:8162"
REC = json.loads(Path("../data/recorded/16.json").read_text())
for folder in ["../apps/16", "../infra/compose/observability", "../data/16"]:
    Path(folder).mkdir(parents=True, exist_ok=True)

print("docker on PATH:", bool(shutil.which("docker")))
print("lesson 13 settings set:", all(is_set(n) for n in ["ERP_SIGNING_KEY", "ERP_READER_CLIENT_SECRET", "ERP_CREDIT_BOT_CLIENT_SECRET"]))

# %% [markdown]
# Next, the helpers. They run Compose for this lesson's project, poll a web address until it has an answer (never a fixed sleep), and pick the live output of this run or the recorded output.

# %%
def compose(*args, extra=None):
    """Run docker compose for this lesson's project. extra sets variables for this call only."""
    return subprocess.run([*COMPOSE, *args], capture_output=True, text=True, timeout=900,
                          env={**os.environ, **(extra or {})})


def tail(text, n=8):
    return "\n".join(text.strip().splitlines()[-n:])


def wait_for(check, timeout=90, every=2):
    """Call check() until it returns something true, or stop at the timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = check()
        if value:
            return value
        time.sleep(every)
    raise TimeoutError(f"nothing after {timeout} s")


def from_run(key):
    """The live output of this run, or the recorded output when Docker was skipped."""
    if DOCKER_RAN:
        return RUN_LOG[key]
    print("(recorded output: Docker was not run in this build)")
    return REC[key]


def log_events(text):
    """Structured log lines as dicts. Compose prefixes each line; the JSON starts at the first brace."""
    return [json.loads(line[line.index("{"):]) for line in text.splitlines() if "{" in line]

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the service code (version 1.2.0)
#
# The service is lesson 14's triage service plus three things. **Structured logs** (`structlog`) write one JSON line per request, with the trace id from the current span. **Spans** (OpenTelemetry) time the request, the customer API calls and the labelling step. **A latency histogram** (`prometheus-client`) counts requests into time buckets (under 0.05 s, under 0.1 s, ...) for each route and outcome.
#
# The service calls no model in this lesson, so the trace crosses the customer API call. Tracing the model call itself is only previewed in At work below, where a model call would get the same kind of span with model-specific attributes.

# %%
%%writefile ../apps/16/triage_service.py
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

# %% [markdown]
# ### Step 2: the lab customer API that is sometimes slow
#
# The customer API is lesson 13's mock, unchanged. This small wrapper makes every third `/orders` call wait `ERP_SLOW_MS` milliseconds, as a flaky customer system would. The triage service cannot see this in its own code. Only the trace can show it.

# %%
%%writefile ../apps/16/erp_slow_lab.py
"""Lab customer API: the lesson 13 mock, with every third /orders call slowed by ERP_SLOW_MS (invented, lab only)."""
import asyncio
import itertools
import os

from customer_api import app  # the lesson 13 mock, copied into the image next to this file

SLOW_MS = int(os.environ.get("ERP_SLOW_MS", "0"))
orders_calls = itertools.count(1)


@app.middleware("http")
async def every_third_orders_call_waits(request, call_next):
    if request.url.path == "/orders" and SLOW_MS and next(orders_calls) % 3 == 0:
        await asyncio.sleep(SLOW_MS / 1000)  # the customer's system is slow on this call
    return await call_next(request)

# %% [markdown]
# The image needs these pinned packages. The two instrumentation packages hook FastAPI and httpx, so every request and every call gets a span with no extra code.


# %%
%%writefile ../apps/16/requirements.txt
fastapi==0.162.0
uvicorn==0.54.0
pyjwt==2.15.1
httpx==0.28.1
structlog==26.1.0
prometheus-client==0.26.0
opentelemetry-sdk==1.45.1
opentelemetry-exporter-otlp-proto-http==1.45.1
opentelemetry-instrumentation-fastapi==0.66b1
opentelemetry-instrumentation-httpx==0.66b1

# %% [markdown]
# The Dockerfile is lesson 14's recipe with these packages. The ERP image also copies the lesson 13 mock next to the lab wrapper.


# %%
%%writefile ../apps/16/Dockerfile
# One recipe for both lab services. APP_FILE picks the code that runs as service:app.
FROM python:3.12.13-slim
WORKDIR /app
COPY 16/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY 13/customer_api.py /app/customer_api.py
ARG APP_FILE
COPY ${APP_FILE} /app/service.py
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]

# %% [markdown]
# ### Step 3: the observability parts and the Compose file
#
# Three small configs: the Collector receives spans on port 4318 and forwards them to Jaeger; Jaeger stores the traces in memory and serves its UI; Prometheus scrapes the triage service's `/metrics` every 5 seconds. The Compose file starts them with the lesson 14 customer environment. Image tags are pinned; none is `latest`.
#
# Paths in the start command (`-f`, `--env-file ../.env`) resolve from the folder you run Compose in, which is the notebooks folder here. `build.context` resolves from the Compose file's own folder.

# %%
%%writefile ../infra/compose/observability/otel-collector.yaml
# OpenTelemetry Collector: receives spans from the triage service and forwards them to Jaeger.
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
processors:
  batch: {}
exporters:
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true  # inside the lab's private Compose network only
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/jaeger]

# %% [markdown]
# Jaeger reads its settings from a file (v2 needs one). It stores spans in memory and serves the UI on port 8161.


# %%
%%writefile ../infra/compose/observability/jaeger.yaml
# Jaeger v2: receives OTLP from the Collector, keeps traces in memory (lab), serves the UI and query API.
service:
  extensions: [jaeger_storage, jaeger_query]
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [jaeger_storage_exporter]
extensions:
  jaeger_query:
    storage:
      traces: memstore
  jaeger_storage:
    backends:
      memstore:
        memory:
          max_traces: 100000
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
exporters:
  jaeger_storage_exporter:
    trace_storage: memstore

# %% [markdown]
# Prometheus scrapes the metric from the service every 5 seconds.


# %%
%%writefile ../infra/compose/observability/prometheus.yml
# Prometheus: scrapes the triage service's /metrics every 5 seconds (lab).
global:
  scrape_interval: 5s
scrape_configs:
  - job_name: triage
    metrics_path: /metrics
    static_configs:
      - targets: ["triage:8000"]

# %% [markdown]
# The Compose file wires the five services together. Only the triage service (8160) and the two UIs (8161, 8162) are open to the laptop.


# %%
%%writefile ../infra/compose/observability-16.yml
# Customer environment with observability for lesson 16 (lab, invented data). Started from the notebook with
# docker compose -p <project> -f <this file> --env-file ../.env up -d --build --wait
# -f and --env-file resolve from the folder Compose runs in (the notebooks folder), not from this file's folder.
services:
  erp:
    build:
      context: ../../apps
      dockerfile: 16/Dockerfile
      args:
        APP_FILE: 16/erp_slow_lab.py
    image: bb-erp-lab:16
    environment:
      ERP_SIGNING_KEY: ${ERP_SIGNING_KEY}
      ERP_READER_CLIENT_SECRET: ${ERP_READER_CLIENT_SECRET}
      ERP_CREDIT_BOT_CLIENT_SECRET: ${ERP_CREDIT_BOT_CLIENT_SECRET}
      ERP_SLOW_MS: ${ERP_SLOW_MS:-1500}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 10
  triage:
    build:
      context: ../../apps
      dockerfile: 16/Dockerfile
      args:
        APP_FILE: 16/triage_service.py
    image: bb-triage:${TRIAGE_TAG:-1.2.0}
    environment:
      ERP_URL: http://erp:8000
      ERP_READER_CLIENT_ID: ${ERP_READER_CLIENT_ID:-bb-orders-reader}
      ERP_READER_CLIENT_SECRET: ${ERP_READER_CLIENT_SECRET}
      OTEL_EXPORTER_OTLP_ENDPOINT: ${OTEL_EXPORTER_OTLP_ENDPOINT:-http://otel-collector:4318}
    ports:
      - "8160:8000"
    depends_on:
      erp:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 10
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.163.2
    command: ["--config=/etc/otel/config.yaml"]
    volumes:
      - ./observability/otel-collector.yaml:/etc/otel/config.yaml:ro
  jaeger:
    image: jaegertracing/jaeger:2.22.0
    command: ["--config=/jaeger/config.yaml"]
    volumes:
      - ./observability/jaeger.yaml:/jaeger/config.yaml:ro
    ports:
      - "8161:16686"
  prometheus:
    image: prom/prometheus:v3.15.1
    volumes:
      - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "8162:9090"

# %% [markdown]
# ### Step 4: start the stack and call the service
#
# `up --build --wait` builds the two images, starts every service and waits for the two healthy ones. The Collector, Jaeger and Prometheus have no health check in their images, so the next cell polls their web addresses until each answers.

# %% tags=["needs-docker"]
DOCKER_RAN = True
up = compose("up", "-d", "--build", "--wait", extra={"TRIAGE_TAG": "1.2.0"})
assert up.returncode == 0, tail(up.stderr, 12)
wait_for(lambda: all(httpx.get(u, timeout=5).status_code == 200 for u in [f"{JAEGER}/", f"{PROM}/-/ready"]))
ps = compose("ps", "--format", "table {{.Service}}\t{{.Status}}")
RUN_LOG["up"] = tail(ps.stdout + ps.stderr, 8)
print(RUN_LOG["up"])

# %% [markdown]
# If Docker was skipped, this shows the start output recorded from the last real run.

# %%
if not DOCKER_RAN:
    print(from_run("up"))

# %% [markdown]
# Now send eight requests. The customer API waits 1.5 seconds on its third and sixth `/orders` call, so two of the eight triage requests are slow. The label is the answer; the timings are in the logs.

# %% tags=["needs-docker"]
DOCKER_RAN = True
lines = []
for order_id in ["BB-1000", "BB-1001", "BB-1002", "BB-1003"] * 2:
    r = httpx.get(f"{TRIAGE}/triage/{order_id}", timeout=20)
    lines.append(f"{order_id} {r.status_code} {r.json().get('label', r.text[:40])}")
RUN_LOG["requests"] = "\n".join(lines)
print(RUN_LOG["requests"])

# %% [markdown]
# Check the eight answers: the live ones, or the recorded ones.


# %%
if not DOCKER_RAN:
    print(from_run("requests"))

# %% [markdown]
# ### Step 5: find the slow request in the logs
#
# The service writes one JSON line per request. The line holds the order, the outcome, the time in milliseconds and the trace id. This cell fetches the service's log lines (tagged cell), then the next cell filters them. A line with `duration_ms` of 1000 or more is slow.

# %% tags=["needs-docker"]
DOCKER_RAN = True
logs = compose("logs", "triage", "--no-color")
RUN_LOG["logs"] = "\n".join(line[line.index("{"):] for line in logs.stdout.splitlines() if "{" in line)

# %% [markdown]
# Filter the lines. A `duration_ms` of 1000 or more is slow.


# %%
events = log_events(from_run("logs"))
slow = [e for e in events if e.get("duration_ms", 0) >= 1000]
for e in slow:
    print({k: e[k] for k in ("order_id", "outcome", "duration_ms", "trace_id")})
print(f"{len(slow)} slow of {len(events)} requests")
slow_id = slow[0]["trace_id"]  # the first slow request; the trace step opens its trace

# %% [markdown]
# ### Step 6: open the trace of the slow request
#
# The trace id from the log line is the key. Jaeger keeps every span with that id. The next tagged cell asks Jaeger for the spans of the first slow request. Spans arrive a few seconds after the request, so the cell waits until the four expected spans are there.

# %% tags=["needs-docker"]
DOCKER_RAN = True


def fetch_spans(trace_id: str) -> list[dict]:
    """Spans of one trace from Jaeger's query API: name, ms and URL. 'http send' (0 ms bookkeeping) is left out."""
    r = httpx.get(f"{JAEGER}/api/traces/{trace_id}", timeout=10)
    if r.status_code != 200:
        return []
    out = []
    for s in r.json()["data"][0]["spans"]:
        tags = {t["key"]: t["value"] for t in s.get("tags", [])}  # the URL tag name depends on the semconv version
        url = tags.get("url.full") or tags.get("http.url") or tags.get("http.target") or ""
        if "http send" not in s["operationName"]:
            out.append({"span": s["operationName"], "ms": round(s["duration"] / 1000, 1), "url": str(url)})
    return out


RUN_LOG["trace"] = json.dumps(wait_for(lambda: (s := fetch_spans(slow_id)) and len(s) >= 4 and s))

# %% [markdown]
# Print the spans with their times.


# %%
spans = json.loads(from_run("trace"))
for s in spans:
    print(f"{s['ms']:>9.1f} ms  {s['span']:<24} {s['url']}")

# %% [markdown]
# Read it from the top. The first line, `GET /triage/{order_id}`, is the whole request: the server span, the span the triage service opens for the request it received. `POST` is the token call to the customer API and `GET` is the orders call; these are client spans, named by the HTTP method, and the URL column shows where each one went. The orders call holds nearly all the time, so the slow part is in the customer's system; `triage.label`, our own labelling step, takes about 0 ms. The trace tells you which hop to look at before anyone opens code.

# %% [markdown]
# ### Step 7: the same story in a metric
#
# The histogram counts every request. Prometheus stores it, and one query counts the requests that took more than one second. The tagged cell waits until Prometheus has scraped all eight requests.

# %% tags=["needs-docker"]
DOCKER_RAN = True


def prom_value(query: str) -> float:
    r = httpx.get(f"{PROM}/api/v1/query", params={"query": query}, timeout=10).json()
    return float(r["data"]["result"][0]["value"][1]) if r["data"]["result"] else 0.0


def current_counts() -> dict:
    # Histogram buckets are cumulative: bucket le="1.0" counts every request up to 1 s, so total minus that bucket is the count over 1 s.
    return {"requests": prom_value("sum(triage_request_seconds_count)"),
            "over_1s": prom_value('sum(triage_request_seconds_count) - sum(triage_request_seconds_bucket{le="1.0"})')}


RUN_LOG["metric"] = json.dumps(wait_for(lambda: (c := current_counts())["requests"] >= 8 and c))

# %% [markdown]
# Print the two counts from Prometheus.


# %%
metric = json.loads(from_run("metric"))
print(f"requests counted: {metric['requests']:.0f}, slower than 1 s: {metric['over_1s']:.0f}")
print(f"log lines over 1 s: {len(slow)}; metric over 1 s: {metric['over_1s']:.0f}; the metric has no trace id, only counts")

# %% [markdown]
# ## At work
#
# - **Telemetry goes to the customer's collector, not yours.** Customer security teams set where spans and logs may go, often through an egress proxy. → lesson 15 (restricted network), lesson 17 (runbooks and incidents).
# - **Keep metric labels to a few values.** Route and outcome are safe; an order id creates one series per order. → lesson 18 (cost and latency budgets).
# - **Log ids, not customer data.** Logs and traces leave the customer's system on the support path, so they carry order ids, never names, emails or tokens. → lesson 13 (secrets), lesson 27 (security reviews).
# - **For model calls, add the same spans.** Record the model id, token counts, latency and a prompt version on each call; the GenAI attribute names are still in development, so check them before you pin them. You meet model calls inside agent workflows in lesson 19, where you can add these spans.

# %% [markdown]
# ## Common mistakes
#
# **Mistake 1: parsing the Compose log line as JSON.** Compose puts the service name in front of each line. The fix is to start at the first brace, as the helper does.

# %% tags=["raises-exception"]
line = 'triage-1  | {"event": "triage_done", "duration_ms": 1502}'  # a line as docker compose logs prints it
event = json.loads(line)

# %% [markdown]
# The fix: cut the prefix before the JSON.

# %%
event = json.loads(line[line.index("{"):])
print(event["duration_ms"])

# %% [markdown]
# **Mistake 2: the order id as a metric label.** The label is the route, never the order id. Each distinct label value is a new series (one counted line, see The idea) that Prometheus stores and graphs. One label per order blows up storage and makes queries slow.

# %%
orders_per_day = 50_000  # invented
buckets = 7
print(f"label by route: {buckets} series. Label by order id: {orders_per_day * buckets:,} series a day")

# %% [markdown]
# **Mistake 3: a trace that stops at the edge of the service.** The httpx instrumentation adds the trace header to each call it makes. A hand-made client that skips the instrumentation sends no header, so the other side starts a new trace with no link to ours. The fix is to inject the header yourself. The next cell shows both versions. It needs no Docker and sends nothing.

# %%
import httpx
from opentelemetry.propagate import inject
from opentelemetry.sdk.trace import TracerProvider

url = "http://erp:8000/orders"  # the lab customer API, inside the Compose network
plain = httpx.Request("GET", url)  # a hand-made request: no instrumentation runs
print("plain client sends traceparent:", "traceparent" in plain.headers)

tracer = TracerProvider().get_tracer("demo")  # in-process only, nothing is exported
headers = {}
with tracer.start_as_current_span("triage.call"):
    inject(headers)  # writes the W3C traceparent header of the current span
fixed = httpx.Request("GET", url, headers=headers)
print("with inject sends traceparent:", "traceparent" in fixed.headers)

# %% [markdown]
# ## Try it
#
# Write `slowest_spans` to return the names of the top slowest spans in a trace, slowest first. Use it on the sample below, which is invented.

# %%
# your code here
def slowest_spans(spans: list[dict], top: int = 2) -> list[str]:
    """Names of the top slowest spans, slowest first."""
    return []  # your code here


sample = [{"span": "GET /triage/{order_id}", "ms": 1530.2}, {"span": "triage.label", "ms": 0.4},
          {"span": "GET", "ms": 1500.1}, {"span": "POST", "ms": 9.8}]
print(slowest_spans(sample))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def slowest_spans(spans: list[dict], top: int = 2) -> list[str]:
    """Names of the top slowest spans, slowest first."""
    return [s["span"] for s in sorted(spans, key=lambda s: s["ms"], reverse=True)[:top]]


print(slowest_spans(sample))

# %% [markdown]
# ## Tear down
#
# Stop and remove this lesson's containers and network. The images stay. The live output of this run is saved to `../data/16/` so the recording can be refreshed.


# %%
if not DOCKER_RAN:
    print("nothing to remove: Docker was not run")

# %% [markdown]
# With Docker, the next cell stops the stack and removes its containers and network.

# %% tags=["needs-docker"]
DOCKER_RAN = True
down = compose("down", "--remove-orphans")
RUN_LOG["down"] = tail(down.stderr + down.stdout, 4) or "stack removed; images kept"
Path("../data/16/run_log.json").write_text(json.dumps(RUN_LOG, indent=1))
print(RUN_LOG["down"])

# %% [markdown]
# ## Recap
#
# - **Structured log**: one JSON line per event, with the trace id on it, so a line can be matched to its request.
# - **Trace and span**: a trace is one request's timeline; each span is a timed step. The customer API call is a span of its own.
# - **Metric**: a histogram counts requests by route and outcome; keep the labels few.
# - **The slow request** was found in three places: its log line (the trace id), its trace (the time was in the customer API call) and the metric (how often it happens).
# - **OpenTelemetry Collector** receives spans and forwards them, so the app does not depend on the tool.
# - Go deeper: the restricted network the traces must leave through is lesson 15; the alert and the on-call steps are lesson 17.

# %% [markdown]
# **Interview:** "A customer says triage was slow yesterday. What do you look at first?" Strong answer: the metric for the shape (which route, how many requests, since when); then one slow request's log line and its trace id; then the trace, to find the hop with the time; and only then the code.
