# %% [markdown]
# # 28 · Observability: one trace across AG-UI, A2A and MCP
# Level L5 · Part 6 · professional · ~35 min · builds on 22, 27

# %% [markdown]
# ## Goal
# By the end, one request from a person, "triage issues 4, 9, 12 and 15, then close issue 12 after approval", has one trace id on every hop: the AG-UI request, the orchestrator, the A2A call to triage-agent and each MCP call to Trackr. You also count requests per tool from the HTTP headers alone, and measure what tracing costs on 200 `tools/call` requests.

# %% [markdown]
# ## Why it matters
# Without a shared id, the ops desk is four services and four logs. A person says "issue 12 closed, but triage said it was a question". To find out which triage call led to that close, you search four logs by time and guess which lines belong to the same run. The next cell shows the shape of that search. The lines are made up, to show the problem.

# %%
# Made-up log lines from four services. No line names the run, so the join is a guess.
logs = {
    "ag-ui": ["10:02:11.402 POST /agent thread=t-28", "10:02:14.980 POST /agent resume"],
    "orchestrator": ["10:02:11.410 picked classify_issues", "10:02:13.100 picked close_issue"],
    "triage-agent": ["10:02:12.007 classified 4 lines"],
    "trackr": ["10:02:12.300 tools/call search_issues", "10:02:15.200 tools/call close_issue"],
}
for service, lines in logs.items():
    for line in lines:
        print(f"{service:>12} | {line}")
print("shared ids across the four services:", 0)

# %% [markdown]
# With tracing, every hop writes the same trace id and its own timed span. One tree answers the question. The cost is small: each hop carries one extra header or `_meta` key. You don't need this for one process on your laptop, where a `print()` and a debugger are enough.

# %% [markdown]
# ## The idea
# A **trace** is the whole journey of one request. A **span** is one timed step in it, with a parent. Think of a parcel tracking number. Every depot scans the same number and adds its own scan. The W3C **traceparent** is that number in a label: `00-<trace id>-<parent span id>-01`. The caller writes it, and the callee reads it and starts a child span. MCP carries it in `_meta` under the reserved keys `traceparent`, `tracestate` and `baggage`. AG-UI and A2A are HTTP, so the same value travels as a header. Counting requests per tool is a separate job. It reads the `Mcp-Method` and `Mcp-Name` headers, so a gateway can do it without parsing the body.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   P[Person] -->|traceparent header| G[AG-UI endpoint]
#   G --> O[Orchestrator]
#   O -->|traceparent header| T[triage-agent over A2A]
#   O -->|_meta traceparent| M[Trackr over MCP]
# ```
# Drawn as the ideal chain. Step 10 shows what this version really prints: the orchestrator's spans hang under the person's span.

# %% [markdown]
# ## Step by step
# ### 1. Set up the imports and the service names
# The notebook reuses Trackr from lesson 03, triage-agent from lesson 18 and the orchestrator from lesson 22. No socket opens. Each local call goes through an in-process ASGI transport, so the ports below only name the services in cards and URLs.

# %%
import sys, json, time, asyncio, logging
from contextlib import asynccontextmanager
from pathlib import Path
sys.path.insert(0, "..")                         # llm_setup and llm_replay
import llm_replay                                # the model cell starts it
import httpx, httpx2
for noisy in ("httpx", "httpx2", "mcp", "a2a", "vcr", "google_genai", "google.genai", "httpcore"):   # keep stderr for our own log lines only
    logging.getLogger(noisy).setLevel(logging.WARNING)
logging.getLogger("ag_ui_langgraph").setLevel(logging.ERROR)   # its "OnToolEnd received non-ToolMessage" warning is expected here
APPS = Path("../apps").resolve()

for sub in ("03", "18", "22", "28"):             # Trackr, triage-agent, orchestrator, tracing helpers
    sys.path.insert(0, str(APPS / sub))
Path(APPS / "28").mkdir(parents=True, exist_ok=True)
AGUI_PORT, TRIAGE_PORT, TRACKR_PORT = 8280, 8281, 8282
AGUI_URL, TRIAGE_URL, TRACKR_URL = (f"http://127.0.0.1:{p}" for p in (AGUI_PORT, TRIAGE_PORT, TRACKR_PORT))
print("AG-UI", AGUI_URL, "| triage-agent", TRIAGE_URL, "| Trackr", TRACKR_URL, "(names only, no sockets)")

# %% [markdown]
# The local transports below run each service in-process through ASGI, and they are never recorded. llm_replay's recorder patches ASGITransport in httpx and httpx2. So each transport calls the original method, saved here before `llm_replay.start`. This is the same trick as lesson 22's `SocketTransport`. Only model calls are recorded.

# %%
_HTTPX_ASGI, _HTTPX2_ASGI = httpx.ASGITransport.handle_async_request, httpx2.ASGITransport.handle_async_request

class LocalASGI(httpx.AsyncBaseTransport):
    def __init__(self, app):
        self.inner = httpx.ASGITransport(app=app)
    async def handle_async_request(self, request):
        return await _HTTPX_ASGI(self.inner, request)

class LocalASGI2(httpx2.AsyncBaseTransport):
    def __init__(self, app):
        self.inner = httpx2.ASGITransport(app=app)
    async def handle_async_request(self, request):
        return await _HTTPX2_ASGI(self.inner, request)

# %% [markdown]
# ### 2. The tracing helpers, written to `apps/28/tracing.py`
# Four small pieces. `Meter` counts requests from headers. `TraceParent` opens a server span under the caller's traceparent header. `inject_headers` adds the current traceparent to an outgoing HTTP call. `stderr_logger` writes log lines to stderr with the trace id. Everything else is the OpenTelemetry API.

# %%
%%writefile ../apps/28/tracing.py
"""Lesson 28: tracing and metering helpers for the ops desk. Standard OpenTelemetry, no vendor."""
import logging, sys
from collections import Counter
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind

TRACER = trace.get_tracer("ops-desk")
CALLS = Counter()        # (Mcp-Method, Mcp-Name) -> requests, read from the headers only

def _headers(scope) -> dict:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}

class Meter:
    """ASGI middleware: counts each MCP request from its Mcp-Method and Mcp-Name headers. It never reads the body."""
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            h = _headers(scope)
            CALLS[(h.get("mcp-method", "?"), h.get("mcp-name", ""))] += 1
        await self.app(scope, receive, send)

class TraceParent:
    """ASGI middleware: one server span per HTTP request, a child of the caller's traceparent header."""
    def __init__(self, app, name):
        self.app, self.name = app, name
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        ctx = extract(_headers(scope))
        with TRACER.start_as_current_span(f"{self.name} {scope['method']} {scope['path']}",
                                          context=ctx, kind=SpanKind.SERVER):
            await self.app(scope, receive, send)

async def inject_headers(request):
    """httpx request hook: copy the current span's traceparent into the outgoing headers."""
    inject(request.headers)

class TraceIdFilter(logging.Filter):
    def filter(self, record):
        ctx = trace.get_current_span().get_span_context()
        record.trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else "-"
        return True

def stderr_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)          # stderr: never stdout, which a stdio server uses for protocol
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s trace=%(trace_id)s %(message)s"))
        h.addFilter(TraceIdFilter())
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log

# %% [markdown]
# ### 3. Trackr over Streamable HTTP, behind the meter
# Lesson 03's Trackr runs as a Streamable HTTP app, not over stdio, so its calls carry headers. Its lifespan (the session manager) and its client stay open across cells. `Held` keeps any async context manager open in its own task, as lesson 22 does for stdio.

# %%
import trackr_server                              # lesson 03's Trackr, unchanged
from tracing import Meter, TraceParent, CALLS, TRACER, TraceIdFilter, inject_headers, stderr_logger
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

class Held:
    """Keeps an async context manager open across notebook cells, in its own task."""
    async def open(self, make_cm):
        self.ready, self.done, self.error = asyncio.Event(), asyncio.Event(), None
        self.task = asyncio.create_task(self._hold(make_cm))
        await self.ready.wait()
        if self.error:
            raise self.error
        return self.value
    async def _hold(self, make_cm):
        try:
            async with make_cm() as value:
                self.value = value
                self.ready.set()
                await self.done.wait()
        except Exception as e:
            self.error = e
            self.ready.set()
    async def close(self):
        self.done.set()
        await self.task

# %% [markdown]
# The MCP app and its meter. The meter wraps the whole app, so it counts every request before the MCP code runs.

# %%
trackr_app = trackr_server.mcp.streamable_http_app(json_response=True)   # POST /mcp
metered = Meter(trackr_app)                       # counts by header before the MCP app runs

@asynccontextmanager
async def trackr_connection():
    async with trackr_app.router.lifespan_context(trackr_app):   # starts the session manager
        async with httpx2.AsyncClient(transport=LocalASGI2(metered), base_url=TRACKR_URL) as http:
            async with Client(streamable_http_client(f"{TRACKR_URL}/mcp", http_client=http)) as c:
                yield c

held = Held()
trackr = await held.open(trackr_connection)
rows = (await trackr.call_tool("search_issues", {"text": ""})).structured_content["result"]
print(len(rows), "open issues | issue 12 open:", any(r["id"] == 12 for r in rows))

# %% [markdown]
# ### 4. Baseline: 200 `tools/call` requests with tracing off
# Nothing has set a tracer provider yet, so OpenTelemetry uses its no-op tracer. The helper runs 20 warm-up calls, then times 200 calls and reports the average. The next step turns tracing on and runs the same loop.

# %%
async def time_calls(n: int) -> float:
    """Milliseconds per tools/call, averaged over n calls after 20 warm-up calls."""
    for _ in range(20):
        await trackr.call_tool("search_issues", {"text": ""})
    t0 = time.perf_counter()
    for _ in range(n):
        await trackr.call_tool("search_issues", {"text": ""})
    return (time.perf_counter() - t0) / n * 1000

off_ms = await time_calls(200)
print(f"tracing OFF: {off_ms:.2f} ms per tools/call over 200 calls")

# %% [markdown]
# ### 5. Turn tracing on and measure the cost
# The provider keeps finished spans in memory, so the notebook can print them. `BatchSpanProcessor` exports in a background thread, as a production setup does. A real service would send to a collector instead. Note that the MCP SDK already creates its own spans and injects `_meta.traceparent` once a provider exists; the "MCP send" spans with a server child in step 10 show it. The a2a-sdk does the same for its handlers. Set `OTEL_INSTRUMENTATION_A2A_SDK_ENABLED=false` to turn the a2a spans off.

# %%
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
on_ms = await time_calls(200)
exporter.clear()
print(f"tracing ON:  {on_ms:.2f} ms per tools/call over 200 calls | ratio {on_ms / off_ms:.2f}")

# %% [markdown]
# ### 6. The model (`needs-llm`)
# Three model calls in this notebook, planned before the run. The orchestrator picks `classify_issues` (call 1), triage-agent classifies the four lines in one call (call 2), and the orchestrator reads the answer and picks `close_issue` (call 3). The approve run makes no model call. The model is shared by the orchestrator and triage-agent.

# %% tags=["needs-llm"]
llm_replay.start("28_observability")              # first: record or replay this notebook's model calls
from llm_setup import get_llm
import batch_triage_agent, orchestrator           # lesson 18's triage-agent and lesson 22's orchestrator
llm = get_llm()                                   # Gemini by default; 3 calls in this notebook
batch_triage_agent.LLM = orchestrator.LLM = llm
print("model set for the orchestrator and triage-agent")

# %% [markdown]
# If this cell is skipped, both agents keep their scripted paths. Their outputs say 'scripted', and the run still ends at the same approval pause.

# %%
import batch_triage_agent, orchestrator           # ensures the modules load when the model cell is skipped
if orchestrator.LLM is None:
    print("no model: orchestrator and triage-agent use the scripted paths")
else:
    print("model active: orchestrator and triage-agent call the model")

def scripted_picks(state):   # no-model path for this lesson: triage, then close after the triage answer
    if any(isinstance(m, orchestrator.ToolMessage) for m in state["messages"]):
        return [{"name": "close_issue", "args": {"issue_id": 12}, "id": "scripted_close"}]
    return [{"name": "classify_issues", "args": {"issue_ids": [4, 9, 12, 15]}, "id": "scripted_triage"}]
orchestrator.scripted_picks = scripted_picks

# %% [markdown]
# ### 7. Serve triage-agent and the AG-UI endpoint, each behind a server span
# Each service is wrapped in `TraceParent`, so a request with a traceparent header becomes a child span. The two clients use `inject_headers`, so every request they send carries the current traceparent. The triage-agent and the AG-UI endpoint run in this process, as ASGI apps.

# %%
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
from fastapi import FastAPI
from ag_ui_langgraph import add_langgraph_fastapi_endpoint

triage_app = TraceParent(batch_triage_agent.build_app(batch_triage_agent.build_card(TRIAGE_PORT)), "triage-agent")
triage_http = httpx.AsyncClient(transport=LocalASGI(triage_app), base_url=TRIAGE_URL,
                                timeout=60, event_hooks={"request": [inject_headers]})
triage_card = await A2ACardResolver(triage_http, TRIAGE_URL).get_agent_card()
triage_client = await create_client(agent=triage_card,
                                    client_config=ClientConfig(streaming=False, httpx_client=triage_http))
agui = FastAPI()
add_langgraph_fastapi_endpoint(agui, orchestrator.make_agent(), "/agent")
agui_http = httpx.AsyncClient(transport=LocalASGI(TraceParent(agui, "ag-ui")), base_url=AGUI_URL,
                              timeout=180, event_hooks={"request": [inject_headers]})
print("found:", triage_card.name, "| AG-UI endpoint ready at", AGUI_URL + "/agent")

# %% [markdown]
# ### 8. Wire the orchestrator: stderr logs, spans per delegation, and Trackr over MCP
# `call_trackr` writes one stderr line per MCP call, with the trace id. `triage_text` opens a client span around the A2A call. The MCP SDK does the rest, so the `_meta` traceparent needs no code here. A `Capture` handler keeps the log records, so a check can read them later.

# %%
from opentelemetry.trace import SpanKind

log = stderr_logger("ops.orchestrator")
class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []
        self.addFilter(TraceIdFilter())
    def emit(self, record):
        self.records.append(record)
capture = Capture()
log.addHandler(capture)

async def ask_agent(client, text: str) -> str:
    request = SendMessageRequest(message=new_text_message(text, role=Role.ROLE_USER))
    task = None
    async for chunk in client.send_message(request):
        if chunk.WhichOneof("payload") == "task":
            task = chunk.task
    assert TaskState.Name(task.status.state) == "TASK_STATE_COMPLETED", task.status
    return get_artifact_text(task.artifacts[0])

# %% [markdown]
# The orchestrator's three hooks. MCP to Trackr writes one stderr line per call. A2A to triage-agent is one client span. The fix hook stops the run if it is ever called, because this lesson has no fix-agent.

# %%
async def call_trackr(name: str, args: dict):
    log.info("tools/call %s %s", name, args)          # one stderr line per MCP call
    reply = await trackr.call_tool(name, args)
    if reply.is_error:
        raise RuntimeError(reply.content[0].text)
    return reply.structured_content.get("result", reply.structured_content)

async def triage_text(text: str) -> str:
    with TRACER.start_as_current_span("delegate triage-agent (A2A)", kind=SpanKind.CLIENT):
        return await ask_agent(triage_client, text)

async def fix_text(_text: str) -> str:
    raise RuntimeError("this lesson has no fix-agent: the run triages and closes only")

orchestrator.CALL_TRACKR, orchestrator.CALL_TRIAGE, orchestrator.CALL_FIX = call_trackr, triage_text, fix_text
print("orchestrator wired: MCP to Trackr, A2A to triage-agent")

# %% [markdown]
# ### 9. One person, one trace: triage, the pause, and the approval
# The person's request runs inside one root span, so the pause and the approval share a trace. The request for the pause and the resume go through `run_agui`, the same client as lessons 19 and 22. The helpers read the stream. The question asks for the close alone, in its own reply: lesson 22's gate reads the first tool call of a reply, so a close mixed in with other calls would be read wrong.

# %%
async def run_agui(thread_id: str, run_id: str, question: str | None = None, resume: list | None = None):
    messages = [] if question is None else [{"id": "u-" + run_id, "role": "user", "content": question}]
    payload = {"threadId": thread_id, "runId": run_id, "state": {}, "tools": [], "context": [],
               "forwardedProps": {}, "messages": messages}
    if resume is not None:
        payload["resume"] = resume
    events = []
    async with agui_http.stream("POST", "/agent", json=payload, headers={"Accept": "text/event-stream"}) as reply:
        async for line in reply.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events

# %% [markdown]
# These helpers read the stream. The last `RUN_FINISHED` event says whether the run paused, and for what.

# %%
def paused_on(events: list) -> list:
    finished = [e for e in events if e["type"] == "RUN_FINISHED"]
    return (finished[-1].get("outcome") or {}).get("interrupts", []) if finished else []

def show(events: list) -> None:
    for e in events:
        if e["type"] == "MESSAGES_SNAPSHOT":
            for m in e["messages"]:
                if m["role"] == "assistant" and m.get("content"):
                    print("[answer]", m["content"])
                if m["role"] == "tool":
                    print("  tool result ->", str(m.get("content")).replace("\n", " | ")[:100])
        if e["type"] == "RUN_FINISHED":
            ids = paused_on([e])
            print(f"== paused for a person: {ids[0]['message']}" if ids else "== run finished")

# %% [markdown]
# The person's request, in one root span. The pause and the approval share its trace id.

# %%
QUESTION = ("Step 1: call classify_issues for open issues 4, 9, 12 and 15. Make no other tool call in that reply. "
            "Step 2: after its answer comes back, reply with ONE tool call only: close_issue with issue_id 12. "
            "close_issue goes alone in its own reply, with no other tool call in it, so a person can approve it. "
            "Do not reply with text instead of a tool call.")
with TRACER.start_as_current_span("person: triage and close issue 12", kind=SpanKind.CLIENT) as root:
    events_1 = await run_agui("t-28", "run-28a", question=QUESTION)
    show(events_1)
    paused = paused_on(events_1)
    events_2 = await run_agui("t-28", "run-28b",
                              resume=[{"interruptId": paused[0]["id"], "status": "resolved", "payload": {"approve": True}}])
    show(events_2)
trace_id = root.get_span_context().trace_id
print("one trace id for the whole request:", format(trace_id, "032x"))

# %% [markdown]
# ### 10. Read the one trace as a tree
# Flush the provider so every finished span is in the exporter. Then print the spans of that trace, indented by parent. Only the spans that name a hop are shown. The a2a-sdk's internal spans are skipped, and their children move up a level. In this version the agent run does not take the AG-UI span as its parent: the orchestrator's spans hang under the person's span. The trace id still joins them, and each parent link shows the hop.

# %%
provider.force_flush()
spans = [s for s in exporter.get_finished_spans() if s.context.trace_id == trace_id]
KEEP = ("person", "ag-ui", "orchestrator", "delegate", "triage-agent", "tools/call", "MCP send")
by_parent: dict = {}
for s in spans:
    by_parent.setdefault(s.parent.span_id if s.parent else None, []).append(s)

def walk(parent_id, depth: int) -> None:
    for s in sorted(by_parent.get(parent_id, []), key=lambda s: s.start_time):
        if s.name.startswith(KEEP):
            print("  " * depth + f"{s.name} [{s.kind.name}]")
            walk(s.context.span_id, depth + 1)
        else:
            walk(s.context.span_id, depth)

walk(None, 0)
print(len(spans), "spans in this trace")

# %% [markdown]
# ### 11. Logs, meters and the ship check
# The stderr lines above carry the same trace id as the tree. The meter counts the MCP requests by tool name from their headers. The checks below read the spans, the logs, the meter and the streams. None of them read the model's words.

# %%
print("log lines with this trace id:", sum(1 for r in capture.records if r.trace_id == format(trace_id, "032x")))
for (method, name), n in sorted(CALLS.items()):
    if method == "tools/call":
        print(f"tools/call {name}: {n} requests (counted from Mcp-Name, body not read)")
open_ids = [r["id"] for r in (await trackr.call_tool("search_issues", {"text": ""})).structured_content["result"]]
client_ids = {s.context.span_id for s in spans if s.kind == SpanKind.CLIENT}
mcp_server = [s for s in spans if s.kind == SpanKind.SERVER and s.name.startswith("tools/call")]
triage_server = [s for s in spans if s.name.startswith("triage-agent POST")]
ag_ui_server = [s for s in spans if s.name.startswith("ag-ui POST")]
checks = {
    "R1": bool(ag_ui_server) and bool(triage_server) and bool(mcp_server),
    "R2": any(s.parent and s.parent.span_id in client_ids for s in mcp_server),       # _meta carried the trace
    "R3": any(s.parent and s.parent.span_id in client_ids for s in triage_server),    # the header carried it
    "R4": on_ms / off_ms < 2.0,
    "R5": CALLS[("tools/call", "search_issues")] >= 440,                             # 2 x (20 warm-up + 200)
    "R6": sum(1 for r in capture.records if r.trace_id == format(trace_id, "032x")) >= 2,
    "R7": bool(paused) and paused[0].get("message") == "Close issue 12?" and 12 not in open_ids,
    "R8": llm_replay.calls() <= 5,
}
for name, ok in checks.items():
    print(name, "PASS" if ok else "FAIL")

# %% [markdown]
# ### 12. Stop everything and save the recording
# Close the clients and the held connection, then save the recording if a model ran.

# %%
await triage_client.close()
await triage_http.aclose()
await agui_http.aclose()
await held.close()
log.removeHandler(capture)
llm_replay.stop()
print("lesson 28 done: one trace, the header and _meta carried it, the meter counted by name")

# %% [markdown]
# ## At work
# - Gateways count calls per tool from the `Mcp-Method` and `Mcp-Name` headers, without parsing the body. Cloudflare and other gateways do this, and it is the cheapest meter to run → lesson 32.
# - Tracing every request costs storage and CPU. Production teams sample, and keep every error span → lesson 32.
# - On stdio, stdout is the protocol, so logs go to stderr. A stray `print()` corrupts the stream → lesson 05b.
# - The tool arguments may hold personal data. Log the tool name and an id, not the whole argument list, and keep the span attributes small → lesson 31b.

# %% [markdown]
# ## What just happened
# One person's request produced one trace. The AG-UI server span, the orchestrator's client spans, the triage-agent server span and the Trackr server spans all share the trace id. The MCP calls carried the id in `_meta`, and the A2A call carried it in a header. Tracing on added a small, measured cost per call, and the meter counted calls per tool without reading any body.

# %% [markdown]
# ## Common mistakes
# A root span has no parent, so `.parent` is `None`. Reading `.span_id` from it fails. This is the mistake people make when they walk the tree by hand.

# %% tags=["raises-exception"]
root_span = next(s for s in spans if s.name.startswith("person"))
print("parent span id:", root_span.parent.span_id)

# %% [markdown]
# Fix: check for `None` before you read the parent. A root span is the start of the trace.

# %%
root_span = next(s for s in spans if s.name.startswith("person"))
print("root span:", root_span.name, "| parent:", "none (a root)" if root_span.parent is None else root_span.parent.span_id)

# %% [markdown]
# ## Production checklist
# - Export spans to a collector (OTLP) with a sampling rule, not to memory as this notebook does.
# - Log the trace id on every line, and keep the same id in the span, so a log and a trace join.
# - Check the a2a-sdk telemetry switch and the MCP SDK defaults in your version before you rely on them.
# - Measure your own overhead on your own calls. One ratio on a laptop is not a benchmark.
# - Never put secrets or tokens in span attributes or in log lines.

# %% [markdown]
# ## Try it
# Count the spans in the trace by kind (SERVER, CLIENT, INTERNAL) and print the count for each kind.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
from collections import Counter
print(Counter(s.kind.name for s in spans))

# %% [markdown]
# ## Key terms
# - **trace** — the whole journey of one request across services, identified by one trace id.
# - **span** — one timed step in a trace, with a parent span and a kind (SERVER, CLIENT or INTERNAL).
# - **traceparent** — the W3C header or `_meta` key that carries the trace id and parent span id to the next hop.
# - **OpenTelemetry (OTel)** — the open standard and API for traces, metrics and logs; the SDK here keeps spans in memory.
# - **ASGI middleware** — a wrapper around an ASGI app that runs code before and after each request; `TraceParent` and `Meter` are two.
# - **metering** — counting requests per tool from headers such as `Mcp-Method` and `Mcp-Name`, without reading the body.
# - **tracing overhead** — the extra time per call that tracing adds; measure it on your own calls.
