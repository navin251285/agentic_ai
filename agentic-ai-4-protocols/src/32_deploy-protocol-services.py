# %% [markdown]
# # 32 · Deploying protocol services
# Level L5 · Part 6 · professional · ~40 min · builds on 09, 10, 28

# %% [markdown]
# ## Goal
# By the end you can serve Trackr's MCP and A2A services from one ASGI app with a health route. You can run two replicas that share one durable task store, keep an A2A stream alive while one replica restarts, put both behind a proxy that does not buffer streams, and collect expired tasks.

# %% [markdown]
# ## Why it matters
# Lessons 08 to 10 run the agent in one process with an in-memory task store. A second process serving the same agent breaks five things:
#
# | Without this lesson | With this lesson |
# |---|---|
# | Restart the process and every task is gone. | Both replicas share one store; a restart loses nothing. |
# | Replica B has never heard of a task that replica A runs. | Any replica reads or streams the task from the shared event log. |
# | A default proxy holds SSE frames until the stream ends. | `proxy_buffering off` and `X-Accel-Buffering: no` send each frame as it is written. |
# | The app sees the proxy as the client and `http` as the scheme. | Proxy headers give the real client and scheme. |
# | Finished tasks pile up forever. | A sweep deletes finished tasks older than a time to live (TTL). |
#
# The cell below shows the first break: a task saved in one in-memory store is invisible in another.
# %%
import asyncio
from a2a.server.context import ServerCallContext
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import Task, TaskState, TaskStatus

replica_1, replica_2 = InMemoryTaskStore(), InMemoryTaskStore()
task = Task(id="t-1", context_id="c-1", status=TaskStatus(state=TaskState.TASK_STATE_WORKING))
await replica_1.save(task, context=ServerCallContext())
print("replica 1 sees t-1:", await replica_1.get("t-1", context=ServerCallContext()) is not None)
print("replica 2 sees t-1:", await replica_2.get("t-1", context=ServerCallContext()) is not None)

# %% [markdown]
# ## The idea
# A deployed agent is an ASGI app. One object answers the health probe, mounts the A2A agent under `/a2a`, and mounts MCP at `/mcp`. Each replica is one copy of that app. A proxy in front spreads requests over the replicas and passes the real client address and scheme. The replicas share a task store: the SDK's versioned database store keeps the tasks, and its event log lets any replica stream a task whose work runs on another. The SDK does not delete old tasks, so a sweep does that. AG-UI (lesson 10) is not mounted or run in this lesson.
#
# An analogy: two counters in one shop share one order book. A customer can walk up to either counter, and the order is the same at both.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   C[client] --> P[proxy: nginx]
#   P --> A[replica a]
#   P --> B[replica b]
#   A --> DB[(tasks.db: tasks and event log)]
#   B --> DB
#   S[sweep: delete old finished tasks] --> DB
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set up the example
# The running example is the triage of issue 4, as in lesson 09. The notebook starts its recording with the lesson name first. The recorder matches every HTTP call made by its own process, so the notebook's local calls run in a child process (`probe.py`). The cell below sets the three ports for this lesson, 8320 (proxy), 8321 and 8322 (replicas), and a fresh task database. Nothing here calls a model.

# %%
import os, sys, json, time, shutil, subprocess, threading, queue, statistics
from pathlib import Path
import httpx
sys.path.insert(0, "..")                          # llm_setup, llm_replay, tut_env
import llm_replay
from tut_env import env
llm_replay.start("32_deploy-protocol-services")

NB = Path.cwd()                                   # the notebooks folder
DATA = Path("../data/32"); DATA.mkdir(parents=True, exist_ok=True)
APPS = Path("../apps/32"); APPS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(APPS.resolve()))           # the files this lesson writes
DB_FILE = (DATA / "tasks.db").resolve()
DB_FILE.unlink(missing_ok=True)                   # a fresh store for this run
ISSUES = Path("../data/trackr_05b_issues.json").resolve()
ISSUE = next(i for i in json.loads(ISSUES.read_text()) if i["id"] == 4)
PROXY, PORT_A, PORT_B = 8320, 8321, 8322          # ports for lesson 32 (progress.py --ports 32)
PROXY_URL, A_URL, B_URL = (f"http://127.0.0.1:{p}" for p in (PROXY, PORT_A, PORT_B))
DB_URL = f"sqlite+aiosqlite:///{DB_FILE}"
print(ISSUE["title"], "| proxy", PROXY, "| replicas", PORT_A, PORT_B)

# %% [markdown]
# ### 2. Write the service files
# Each file is short, so you can read it in full. `trackr_store.py` holds the shared store and the sweep. `trackr_triage.py` is the executor: one classification, then six status updates, so a stream has time to be interrupted. `trackr_mcp.py` holds the MCP tool and its host and origin checks. `trackr_asgi.py` is the app that ties them together. The next two files start a replica as a process, and make the notebook's own local calls and read a stream in child processes.

# %%
%%writefile ../apps/32/trackr_store.py
"""Lesson 32: the task store two replicas share, and the sweep that collects expired tasks."""
import time
from datetime import datetime, timezone
from a2a.server.cluster import DatabaseTaskEventStream, VersionedDatabaseTaskStore
from a2a.server.models import TaskModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import create_async_engine

TERMINAL = {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"}

def make_engine(url: str):
    """One engine per process. A SQLite file is safe for several processes on one host."""
    return create_async_engine(url, connect_args={"timeout": 30})

def make_stores(engine):
    """The versioned task store, and the event log that lets any replica stream any task."""
    return VersionedDatabaseTaskStore(engine), DatabaseTaskEventStream(engine)

async def collect_expired(engine, ttl_s: float, now: float | None = None, dry_run: bool = False) -> list[str]:
    """Delete finished tasks not updated for ttl_s seconds. Returns their ids (dry_run: no delete)."""
    cutoff = datetime.fromtimestamp((now or time.time()) - ttl_s, tz=timezone.utc).replace(tzinfo=None)
    async with engine.begin() as conn:
        rows = (await conn.execute(select(TaskModel.id, TaskModel.status)
                                   .where(TaskModel.last_updated < cutoff))).all()
        expired = [row.id for row in rows if (row.status or {}).get("state") in TERMINAL]
        if expired and not dry_run:
            await conn.execute(delete(TaskModel).where(TaskModel.id.in_(expired)))
    return expired

# %% [markdown]
# `trackr_triage.py` is the executor of one replica: one classification with the model, then six status updates, then the artifact.
# %%
%%writefile ../apps/32/trackr_triage.py
"""Lesson 32: the triage executor of one replica. One real model call classifies the issue, then six
status updates give a stream time to be interrupted, then the artifact. TRACKR_MODEL=off uses keywords."""
import asyncio, os
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, TaskState

LABELS = ("bug", "feature", "question")
MODEL = None                                      # trackr_asgi sets this when TRACKR_MODEL=on
REPLICA = os.environ.get("TRACKR_REPLICA", "a")
STEPS = 6
STEP_DELAY_S = float(os.environ.get("TRACKR_STEP_DELAY_S", "1.0"))

def build_card(url: str) -> AgentCard:
    skill = AgentSkill(id="classify_issue", name="Classify an issue", description="Answers bug, feature or question.",
                       tags=["triage"], examples=["App crashes on start"], input_modes=["text/plain"], output_modes=["text/plain"])
    return AgentCard(name="triage-agent", description="Classifies a Trackr issue.", version="1.2.0",
                     supported_interfaces=[AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0")],
                     capabilities=AgentCapabilities(streaming=True, push_notifications=False),
                     default_input_modes=["text/plain"], default_output_modes=["text/plain"], skills=[skill])

def scripted_label(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("crash", "error", "fails", "does nothing")):
        return "bug"
    return "feature" if any(w in t for w in ("add", "support", "would be nice")) else "question"

async def classify(text: str) -> tuple[str, str]:
    if MODEL is None:
        return scripted_label(text), "scripted"
    reply = await MODEL.ainvoke("Classify this Trackr issue as exactly one word: bug, feature or question.\nIssue: " + text)
    word = (reply.text.strip().lower().split() or [""])[0].strip(".,:")
    return (word if word in LABELS else "unknown"), "model"

class TriageExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        label, source = await classify(get_message_text(context.message))
        for step in range(1, STEPS + 1):
            await asyncio.sleep(STEP_DELAY_S)
            note = f"step {step}/{STEPS} on replica {REPLICA}"
            await updater.update_status(TaskState.TASK_STATE_WORKING, message=updater.new_agent_message([new_text_part(note)]))
        await updater.add_artifact(parts=[new_text_part(f"{label}, handled by replica {REPLICA}")], name=source)
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

# %% [markdown]
# `trackr_mcp.py` is the MCP tool. Its Streamable HTTP app refuses a host or origin that is not listed.
# %%
%%writefile ../apps/32/trackr_mcp.py
"""Lesson 32: Trackr's MCP tool, served by the same ASGI app as the A2A agent (mounted at /mcp)."""
import json, os
from pathlib import Path
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

ISSUES = json.loads(Path(os.environ["TRACKR_ISSUES"]).read_text(encoding="utf-8"))

def mcp_app(hosts: list[str], origins: list[str]):
    """The Streamable HTTP app. Host and Origin are checked: a request for another host is refused."""
    server = MCPServer("Trackr", version="1.0.0", log_level="WARNING")

    @server.tool()
    def count_open(team: str) -> int:
        """Count the open issues of one team."""
        return sum(1 for i in ISSUES if i["team"] == team and i["status"] == "open")

    security = TransportSecuritySettings(allowed_hosts=[*hosts, *(h + ":*" for h in hosts)], allowed_origins=origins)
    return server.streamable_http_app(json_response=True, transport_security=security)

# %% [markdown]
# `trackr_asgi.py` is the app: the health route, the A2A mount, the MCP mount, the proxy-header and host checks, and the stream header.
# %%
%%writefile ../apps/32/trackr_asgi.py
"""Lesson 32: Trackr as one ASGI app. /healthz for probes, /whoami to see the proxy headers,
/a2a for the triage-agent, /mcp for the tool. Run it with uvicorn --proxy-headers."""
import contextlib, os
from fastapi import FastAPI, Request
from sqlalchemy import text
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from tut_env import env
import trackr_triage
from trackr_mcp import mcp_app
from trackr_store import make_engine, make_stores

REPLICA = os.environ.get("TRACKR_REPLICA", "a")
PUBLIC_URL = env("TRACKR_PUBLIC_URL", "http://localhost:8320")
HOSTS = os.environ.get("TRACKR_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
MODEL_ON = os.environ.get("TRACKR_MODEL", "off") == "on"
CASSETTE = "32_deploy-protocol-services"

engine = make_engine(env("TRACKR_DB_URL", "sqlite+aiosqlite:///tasks.db"))
tasks, events = make_stores(engine)
card = trackr_triage.build_card(PUBLIC_URL + "/a2a/")
handler = DefaultRequestHandler(agent_executor=trackr_triage.TriageExecutor(), task_store=tasks,
                                agent_card=card, event_stream=events)
a2a_app = Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")])
mcp = mcp_app(HOSTS, [PUBLIC_URL])

@contextlib.asynccontextmanager
async def lifespan(app):
    await tasks.initialize()                      # the mounted apps' lifespans do not run here,
    await events.initialize()                     # so the start-up work is done in this one
    if MODEL_ON:
        import llm_replay
        from llm_setup import get_llm
        llm_replay.start(CASSETTE)
        trackr_triage.MODEL = get_llm(max_calls=1)
    async with mcp.router.lifespan_context(mcp):
        yield
    if MODEL_ON:
        llm_replay.stop()
    await engine.dispose()

class SseNoBuffer:
    """Adds X-Accel-Buffering: no to every event stream, so a proxy that honours it sends frames at once."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if headers.get("content-type", "").startswith("text/event-stream"):
                    headers["X-Accel-Buffering"] = "no"
            await send(message)
        await self.app(scope, receive, send_with_header)

app = FastAPI(lifespan=lifespan, title="Trackr replica")

@app.get("/healthz")
async def healthz():
    async with engine.connect() as conn:          # ready only when the shared store answers
        await conn.execute(text("select 1"))
    return {"status": "ok", "replica": REPLICA}

@app.get("/whoami")
async def whoami(request: Request):
    return {"scheme": request.url.scheme, "client": request.client.host,
            "host": request.headers.get("host"), "forwarded_proto": request.headers.get("x-forwarded-proto")}

app.mount("/a2a", a2a_app)
app.mount("/", mcp)                               # last: /mcp and everything not matched above
app.add_middleware(SseNoBuffer)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=HOSTS)

# %% [markdown]
# `replica_proc.py` starts one replica as a uvicorn process, waits for it and stops it. It is the no-Docker path.
# %%
%%writefile ../apps/32/replica_proc.py
"""Lesson 32: start, wait for and stop one Trackr replica as a uvicorn process (the no-Docker path)."""
import os, subprocess, sys
from pathlib import Path

APPS = Path(__file__).resolve().parent
TOPIC = APPS.parent.parent                    # the topic folder (tut_env, llm_setup, llm_replay, data)

def start(name: str, port: int, *, db_url: str, issues: str, model_on: bool) -> subprocess.Popen:
    env = {**os.environ, "TRACKR_REPLICA": name, "TRACKR_PUBLIC_URL": f"http://127.0.0.1:{port}",
           "TRACKR_DB_URL": db_url, "TRACKR_ISSUES": issues, "TRACKR_ALLOWED_HOSTS": "localhost,127.0.0.1",
           "TRACKR_MODEL": "on" if model_on else "off", "TRACKR_STEP_DELAY_S": "1.0",
           "TUT_CASSETTE_DIR": str((TOPIC / "data" / "llm_cassettes").resolve()),
           "PYTHONPATH": os.pathsep.join([str(TOPIC), str(APPS)])}
    cmd = [sys.executable, "-m", "uvicorn", "trackr_asgi:app", "--host", "127.0.0.1", "--port", str(port),
           "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1", "--log-level", "warning"]
    return subprocess.Popen(cmd, cwd=str(APPS), env=env)

def wait_url(url: str, timeout: float = 30.0) -> None:
    """Poll a URL until it answers 200 (probe.py polls, so the recorder does not see the calls)."""
    subprocess.run([sys.executable, str(APPS / "probe.py"), "wait", url, "--timeout", str(timeout)],
                   check=True, capture_output=True, text=True)

def stop(proc: subprocess.Popen) -> None:
    proc.terminate()                              # uvicorn runs the lifespan shutdown on SIGTERM
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()

# %% [markdown]
# `probe.py` makes the notebook's own local calls in a child process, so the recorder does not match them.
# %%
%%writefile ../apps/32/probe.py
"""Lesson 32: the notebook's own network calls, made from a child process. The lesson recorder (llm_replay)
matches every HTTP call of the process it runs in, so local calls must not run there. Each command prints
JSON, or exits 1 with the error when the service answers an error."""
import argparse, asyncio, json, statistics, sys, time
import httpx

def wait(url: str, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return {"ready": url}
        except httpx.TransportError:
            pass                                  # not up yet: poll again, no fixed sleep
        time.sleep(0.2)
    raise RuntimeError(f"{url} did not answer within {timeout:.0f} s")

def get(url: str, headers: list[str]) -> dict:
    r = httpx.get(url, headers=dict(h.split(": ", 1) for h in headers), timeout=10)
    r.raise_for_status()
    return r.json()

async def mcp(url: str, tool: str, args: str) -> dict:
    from mcp import Client
    async with Client(url) as client:
        return (await client.call_tool(tool, json.loads(args))).structured_content

async def task(base: str, task_id: str) -> dict:
    from a2a.client import A2ACardResolver, ClientConfig, create_client
    from a2a.types import GetTaskRequest, TaskState
    async with httpx.AsyncClient(timeout=30) as http:
        card = await A2ACardResolver(http, base + "/a2a").get_agent_card()
    card.supported_interfaces[0].url = base + "/a2a/"   # call the URL we were given (proxy or replica)
    client = await create_client(agent=card, client_config=ClientConfig(streaming=False))
    t = await client.get_task(GetTaskRequest(id=task_id, history_length=0))
    text = t.artifacts[0].parts[0].text if t.artifacts else ""
    return {"state": TaskState.Name(t.status.state).removeprefix("TASK_STATE_"), "artifact": text,
            "classified_by": t.artifacts[0].name if t.artifacts else ""}

def latency(url: str, n: int) -> dict:
    with httpx.Client() as c:
        times = []
        for _ in range(n):
            t0 = time.perf_counter(); c.get(url); times.append((time.perf_counter() - t0) * 1000)
    return {"median_ms": statistics.median(times)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wait"); w.add_argument("url"); w.add_argument("--timeout", type=float, default=30)
    g = sub.add_parser("get"); g.add_argument("url"); g.add_argument("--header", action="append", default=[])
    m = sub.add_parser("mcp"); m.add_argument("url"); m.add_argument("tool"); m.add_argument("args")
    t = sub.add_parser("task"); t.add_argument("base"); t.add_argument("task_id")
    lat = sub.add_parser("latency"); lat.add_argument("url"); lat.add_argument("n", type=int)
    a = ap.parse_args()
    try:
        if a.cmd == "wait":
            out = wait(a.url, a.timeout)
        elif a.cmd == "get":
            out = get(a.url, a.header)
        elif a.cmd == "mcp":
            out = asyncio.run(mcp(a.url, a.tool, a.args))
        elif a.cmd == "task":
            out = asyncio.run(task(a.base, a.task_id))
        else:
            out = latency(a.url, a.n)
    except Exception as exc:                      # the caller sees the error and a non-zero exit
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(out))

# %% [markdown]
# `stream_client.py` sends one message, or subscribes to a task, and prints each event. It runs in its own process too.
# %%
%%writefile ../apps/32/stream_client.py
"""Lesson 32: send one A2A message, or subscribe to a task, and print each event as a JSON line.
It runs in its own process: a stream opened inside the notebook is cut by its recorder (see lesson 09)."""
import asyncio, json, sys
import httpx
from google.protobuf.json_format import MessageToDict
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest, SubscribeToTaskRequest

async def main(base_url: str, text: str, task_id: str) -> None:
    async with httpx.AsyncClient(timeout=60) as http:
        card = await A2ACardResolver(http, base_url).get_agent_card()
    card.supported_interfaces[0].url = base_url.rstrip("/") + "/"   # call the URL we were given (the proxy or a replica)
    client = await create_client(agent=card, client_config=ClientConfig(streaming=True))
    if task_id:
        stream = client.subscribe(SubscribeToTaskRequest(id=task_id))
    else:
        stream = client.send_message(SendMessageRequest(message=new_text_message(text, role=Role.ROLE_USER)))
    async for event in stream:
        print(json.dumps(MessageToDict(event)), flush=True)

asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))

# %% [markdown]
# ### 3. Health, mounts and the proxy headers (replica a, one process)
# A replica is one uvicorn process: `uvicorn trackr_asgi:app --proxy-headers`. The helper starts replica a on port 8321 with the model off, so this step makes no model call. The health route checks the shared store, not just that the process is alive. The agent card, the A2A mount and the MCP mount all answer under one port.

# %%
import replica_proc
PROBE = [sys.executable, str(APPS / "probe.py")]
def probe(*args: str) -> dict:
    """A local call made by probe.py in a child process (see the note in step 1). Raises on an error."""
    out = subprocess.run([*PROBE, *args], capture_output=True, text=True, cwd=str(NB))
    if out.returncode:
        raise RuntimeError(out.stderr.strip())
    return json.loads(out.stdout)

store_args = dict(db_url=DB_URL, issues=str(ISSUES), model_on=False)
proc_a = replica_proc.start("a", PORT_A, **store_args)
replica_proc.wait_url(f"{A_URL}/healthz")
print("healthz:", probe("get", f"{A_URL}/healthz"))
card_json = probe("get", f"{A_URL}/a2a/.well-known/agent-card.json")
print("agent card:", card_json["name"], "at", card_json["supportedInterfaces"][0]["url"])

# %% [markdown]
# The next cell calls the MCP tool through the same port. `Client` from the `mcp` package talks Streamable HTTP. The tool is the same kind as lesson 03's, now served behind `/mcp` in the ASGI app.

# %%
print("count_open(web) over /mcp:", probe("mcp", f"{A_URL}/mcp", "count_open", '{"team": "web"}')["result"])

# %% [markdown]
# ### 4. Proxy headers: what the app sees
# The client below sends `X-Forwarded-Proto: https` and a forwarded client address, the way a TLS-terminating proxy does. The replica runs with `--forwarded-allow-ips 127.0.0.1`, so it trusts those headers from that address only. The app reports `https` and the forwarded client. Without `--proxy-headers`, the usual result is `http` and the proxy's own address. This lesson does not run that case.

# %%
seen = probe("get", f"{A_URL}/whoami", "--header", "X-Forwarded-Proto: https", "--header", "X-Forwarded-For: 203.0.113.9")
print("app sees:", seen)

# %% [markdown]
# ### 5. Model setup (`needs-llm`)
# This cell turns the model on for the replicas. Each replica then makes its classification call through `llm_replay`, so the recording replays with no key. The notebook makes one model call in total. If the cell is skipped, the replicas use the keyword rule and say so.

# %% tags=["needs-llm"]
MODEL_ON = True
print("model on for the replicas: one classification call, recorded once and replayed after that")

# %% [markdown]
# The next cell reads the switch back and prints it, so the run log shows whether the replicas will call the model.
# %%
MODEL_ON = globals().get("MODEL_ON", False)
print("model:", "on, replayed from the recording" if MODEL_ON else "off, the keyword rule runs")

# %% [markdown]
# ### 6. A stream that survives a replica restart
# Now the two replicas run with the model setting above. The client opens a stream on replica a, which runs the task. Halfway through, replica b is restarted, and the stream on a keeps going. A second client then subscribes to the same task on the restarted replica b. Replica b did not run the task, so it reads the task from the shared event log.

# %%
replica_proc.stop(proc_a)                         # restart both with the model setting from step 5
proc_a = replica_proc.start("a", PORT_A, **{**store_args, "model_on": MODEL_ON})
proc_b = replica_proc.start("b", PORT_B, **{**store_args, "model_on": MODEL_ON})
replica_proc.wait_url(f"{A_URL}/healthz"); replica_proc.wait_url(f"{B_URL}/healthz")

# %% [markdown]
# `open_stream` runs `stream_client.py` in its own process and returns its events as a queue. `drain` reads that queue until the stream ends. No helper calls a model.
# %%
def open_stream(base_url: str, text: str = "", task_id: str = ""):
    """Run stream_client.py in its own process. Returns the process and a queue of parsed events."""
    cmd = [sys.executable, str(APPS / "stream_client.py"), base_url + "/a2a", text, task_id]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, cwd=str(NB))
    events_q: queue.Queue = queue.Queue()
    def pump():
        for line in proc.stdout:
            events_q.put(json.loads(line))
        events_q.put(None)
    threading.Thread(target=pump, daemon=True).start()
    return proc, events_q

def drain(events_q: queue.Queue, timeout: float = 90.0) -> list[dict]:
    out = []
    while (item := events_q.get(timeout=timeout)) is not None:
        out.append(item)
    return out

# %% [markdown]
# `state_of` reads the state from a task snapshot or a status update, and `task_id_of` reads the task id. The stream cells below use them to compare the two streams.
# %%
def state_of(event: dict) -> str | None:
    if "task" in event:
        return event["task"]["status"]["state"]
    if "statusUpdate" in event:
        return event["statusUpdate"]["status"]["state"]
    return None

def task_id_of(event: dict) -> str | None:
    return event.get("task", {}).get("id") or event.get("statusUpdate", {}).get("taskId")

# %% [markdown]
# The client opens the stream on replica a and reads the first event. Then replica b is restarted while a's stream keeps going. Once b answers, b subscribes to the same task.
# %%
stream_proc, q = open_stream(A_URL, ISSUE["title"])
first = q.get(timeout=90)
TASK_ID = task_id_of(first)
print("stream on a, task", TASK_ID[:8], "| first event:", state_of(first))
replica_proc.stop(proc_b)                          # restart replica b while a's stream runs
proc_b = replica_proc.start("b", PORT_B, **{**store_args, "model_on": MODEL_ON})
replica_proc.wait_url(f"{B_URL}/healthz")
b_stream, b_q = open_stream(B_URL, task_id=TASK_ID)   # replica b subscribes to a task that replica a runs
events_b = drain(b_q)
events_a = [first] + drain(q)
states_a = [state_of(e) for e in events_a if state_of(e)]
states_b = [state_of(e) for e in events_b if state_of(e)]
print("states on a's stream:", [s.removeprefix("TASK_STATE_") for s in dict.fromkeys(states_a)])
print("states on b's stream:", [s.removeprefix("TASK_STATE_") for s in dict.fromkeys(states_b)])

# %% [markdown]
# Both streams have ended, and replica b is up again. Next, read the task through the restarted replica b. The answer comes from the shared store, not from memory. The `probe.py task` command reads the task with a plain request, so it needs no stream.

# %%
task_b = probe("task", B_URL, TASK_ID)                 # GetTask over A2A, from a child process
print("replica b reads the task:", task_b["state"], "|", task_b["artifact"], "| classified by:", task_b["classified_by"])
replica_proc.stop(proc_a)
replica_proc.stop(proc_b)
print("both replicas stopped; the task stays in", DB_FILE.name)

# %% [markdown]
# ### 7. Docker: nginx in front of two replicas (`needs-docker`)
# This cell builds the image, starts nginx and the two replicas with `docker compose`, and waits for the proxy to answer. The compose file sets each replica's public URL to its own port, so the agent card in this lab names the replica, not the proxy. Round-robin shows both replicas answering through the proxy. The proxy adds a small, measured latency. The cell then restarts replica b, reads the task again through the proxy, and stops the stack.

# %% tags=["needs-docker"]
DOCKER_RAN = False
COMPOSE = ["docker", "compose", "-p", "tut-agentic-ai-4-protocols-32", "-f", str(Path("../infra/32/docker-compose.yml").resolve())]
BUILD = DATA / "build"
shutil.rmtree(BUILD, ignore_errors=True); BUILD.mkdir(parents=True)
for f in APPS.glob("*.py"):
    shutil.copy(f, BUILD)
for f in ("tut_env.py",):
    shutil.copy(Path("../" + f), BUILD)
shutil.copy(ISSUES, BUILD / "issues.json")
shutil.copy(Path("../infra/32/Dockerfile"), BUILD / "Dockerfile")
print("build folder:", sorted(f.name for f in BUILD.iterdir()))
# %% [markdown]
# `timed_stream` sends one new task through a base URL and notes when each event arrives. The run cell below calls it through the proxy.
# %%
def timed_stream(base: str, text: str) -> list[tuple[float, str | None]]:
    """One new A2A message through base/a2a. Returns (seconds since the client started, state) per event."""
    t0 = time.monotonic()
    sp = subprocess.Popen([sys.executable, str(APPS / "stream_client.py"), base + "/a2a", text, ""],
                          stdout=subprocess.PIPE, text=True, cwd=str(NB))
    arrivals = [(time.monotonic() - t0, state_of(json.loads(line))) for line in sp.stdout]
    sp.wait()
    if not arrivals:
        raise RuntimeError("the stream sent no events")
    return arrivals

# %% [markdown]
# The run cell starts the stack, measures it, times one new stream through the proxy, and always stops the stack, even when a step fails. The replicas have the model off, so the keyword rule classifies the new task and no model call is made. If the proxy held the frames, the first event would arrive with the last. The stream client calls the URL it was given, not the URL on the agent card, so the stream goes through the proxy.
#
# The proxy setting that matters for streams is in `infra/32/nginx.conf`:
#
# ```nginx
# proxy_buffering off;
# ```
#
# The app also adds `X-Accel-Buffering: no` to every event stream, so a proxy that reads that header sends frames at once too.
# %% tags=["needs-docker"]
try:
    subprocess.run([*COMPOSE, "up", "-d", "--build"], check=True, capture_output=True, text=True)
    DOCKER_RAN = True
    for url in (A_URL, B_URL, PROXY_URL):          # `up` returns before the apps listen: poll each replica, then the proxy
        replica_proc.wait_url(f"{url}/healthz")
    names = [probe("get", f"{PROXY_URL}/healthz")["replica"] for _ in range(6)]
    print("replicas answering through the proxy (round-robin):", names)
    direct_ms = probe("latency", f"{A_URL}/healthz", "200")["median_ms"]
    proxy_ms = probe("latency", f"{PROXY_URL}/healthz", "200")["median_ms"]
    print(f"median /healthz: direct {direct_ms:.1f} ms, through the proxy {proxy_ms:.1f} ms, added {proxy_ms - direct_ms:.1f} ms")
    subprocess.run([*COMPOSE, "restart", "trackr-b"], check=True, capture_output=True, text=True)
    replica_proc.wait_url(f"{B_URL}/healthz"); replica_proc.wait_url(f"{PROXY_URL}/healthz")
    task_via_proxy = probe("task", PROXY_URL, TASK_ID)
    print("after restarting trackr-b, the task through the proxy:", task_via_proxy["state"])
    arrivals = timed_stream(PROXY_URL, ISSUE["title"])     # the clock includes the client's own start-up
    first_s, last_s = arrivals[0][0], arrivals[-1][0]
    states = list(dict.fromkeys(s.removeprefix("TASK_STATE_") for _, s in arrivals if s))
    print(f"stream through the proxy: first event after {first_s:.1f} s, last after {last_s:.1f} s, states {states}")
    RECORDED = {"replicas_via_proxy": names, "direct_ms": direct_ms, "proxy_ms": proxy_ms,
                "task_via_proxy": task_via_proxy["state"], "first_event_s": round(first_s, 1), "last_event_s": round(last_s, 1)}
    if os.environ.get("TUT_SAVE_RECORDED") == "1":          # the writer saves a real run for the fallback
        (Path("../data/recorded") / "32.json").write_text(json.dumps(RECORDED, indent=2))
finally:
    subprocess.run([*COMPOSE, "down"], capture_output=True, text=True)
    print("stack stopped")

# %% [markdown]
# The next cell prints the saved Docker output when the Docker cell was skipped, so the proxy numbers still appear on this page.
# %%
# Fallback for a skipped Docker cell: the output of a real run, saved by the writer.
if not globals().get("DOCKER_RAN", False):
    rec = json.loads((Path("../data/recorded/32.json")).read_text())
    print("recorded output (Docker cell skipped here):")
    print("replicas through the proxy:", rec["replicas_via_proxy"])
    print(f"median /healthz: direct {rec['direct_ms']:.1f} ms, through the proxy {rec['proxy_ms']:.1f} ms, added {rec['proxy_ms'] - rec['direct_ms']:.1f} ms")
    print("after restarting trackr-b, the task through the proxy:", rec["task_via_proxy"])
    print(f"stream through the proxy: first event after {rec['first_event_s']} s, last after {rec['last_event_s']} s")

# %% [markdown]
# ### 8. Expired tasks are collected
# A finished task is kept until its TTL ends. The sweep compares `last_updated` with the cutoff and deletes only finished tasks. A dry run shows what would go. Here the TTL is one hour. The second run pretends that two hours have passed, so every finished task from this run is collected.

# %%
from trackr_store import make_engine, collect_expired
from sqlalchemy import text as sql
engine = make_engine(DB_URL)
async def count_tasks() -> int:
    async with engine.connect() as conn:
        return (await conn.execute(sql("select count(*) from tasks"))).scalar_one()
print("tasks before:", await count_tasks())
print("dry run now, TTL 1 h:", await collect_expired(engine, 3600, dry_run=True))
later = time.time() + 7200
print("dry run two hours later:", await collect_expired(engine, 3600, now=later, dry_run=True))
deleted = await collect_expired(engine, 3600, now=later)
print("deleted two hours later:", deleted, "| tasks after:", await count_tasks())
await engine.dispose()

# %% [markdown]
# ## At work
# - **Health probes.** Kubernetes and cloud load balancers call a health route and drain a replica that fails it. `/healthz` checks the shared store, so it fails when the replica cannot serve.
# - **Proxies and streams.** A default proxy holds SSE frames, so an A2A or AG-UI stream looks frozen. Fix it with `proxy_buffering off` and `X-Accel-Buffering: no`. This lesson checks an A2A stream through the proxy. AG-UI is not deployed here; lesson 31b covers securing an AG-UI endpoint.
# - **Durable task stores.** A task store in memory loses every task on restart. Production stores are databases (the SDK ships SQLAlchemy stores for SQLite, PostgreSQL and MySQL). Retries and idempotent writes for those tasks are in lesson 23a.
# - **Sweeps.** Nothing in the SDK deletes old tasks, so teams run a scheduled sweep like this one and keep an audit trail before deleting. → lesson 42 covers audit trails for agent protocols.

# %% [markdown]
# ## What just happened
# One ASGI app served the health route, the A2A agent and the MCP tool, with no change to the agent code from lesson 09. Two replicas read and wrote one store. A stream on replica a kept running when replica b restarted. Replica b then streamed the same task from the shared event log while a was still running it, and read the finished task from the store after its restart. The proxy headers told the app the real client. The sweep removed only finished tasks whose TTL had passed. The one model call happened in replica a, and the recording replays it with no key.

# %% [markdown]
# ## Common mistakes
# Trusting the Host header is the usual mistake. A client that sends a host name the app does not list is refused. This cell sends a request with the host `evil.example`, and the app answers 400. The probe sees the 400 and fails, so the cell stops with that error.

# %% tags=["raises-exception"]
proc_c = replica_proc.start("a", PORT_A, **store_args)
try:
    replica_proc.wait_url(f"{A_URL}/healthz")
    probe("get", f"{A_URL}/healthz", "--header", "Host: evil.example")   # the replica answers 400: probe fails
finally:
    replica_proc.stop(proc_c)

# %% [markdown]
# The fix is to list the public host names in `TRACKR_ALLOWED_HOSTS` and nothing else. Two other mistakes do not raise an error, so they only show in the results. The usual result of `proxy_buffering on` is that a stream arrives all at once, so step 7 times a stream through the proxy. The usual result of giving each replica its own SQLite file is that `GetTask` on the other replica returns not found, as step 1 shows for separate in-memory stores. This lesson runs neither broken setup.

# %% [markdown]
# ## Production checklist
# - The health route checks the store. The probe's timeout and failure count match the restart time.
# - The proxy turns buffering off for every stream path and trusts forwarded headers from listed addresses only.
# - `--forwarded-allow-ips` lists the proxy's address, never `*` on a public port.
# - TransportSecuritySettings and TrustedHostMiddleware list the real public host names only.
# - All replicas use one store URL from `.env` and the same image tag.
# - The sweep runs on a schedule, with a TTL that matches retention, and logs what it deletes.
# - A stream cut by a restart resumes by reading the task, not by guessing.
# - The image runs as a non-root user, and the store volume is owned by that user. The lab image runs as root so it can write the bind-mounted SQLite file.
# - SQLite is for one host, where processes share one file. PostgreSQL (or MySQL) is the multi-host store.

# %% [markdown]
# ## Try it
# A finished task should be kept for 24 hours after its last update. With `collect_expired` and a dry run, show that the sweep keeps a finished task now and collects it three days later. Step 8 emptied the store, so the setup cell first saves one finished task.

# %%
# Setup: save one finished task, stamped now, so the sweep has a task to look at.
from a2a.server.cluster import TaskVersion
from google.protobuf.timestamp_pb2 import Timestamp
from trackr_store import make_stores
engine = make_engine(DB_URL)                     # a new engine: step 8 disposed the first one
tasks, _ = make_stores(engine)
stamp = Timestamp(); stamp.GetCurrentTime()
done = Task(id="t-try", context_id="c-try", status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED, timestamp=stamp))
await tasks.save(done, prev_version=TaskVersion.MISSING, context=ServerCallContext())
print("saved one finished task:", done.id)

# %% [markdown]
# Your turn: the stub below reuses `engine` from the setup cell. It calls `collect_expired` twice with a dry run.

# %%
# your code here: with ttl_s = 24 * 3600, call collect_expired(engine, ttl_s, now=..., dry_run=True) twice.
# First use now=time.time(), then now=time.time() + 3 * 86400. Print both lists.

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
ttl_s = 24 * 3600
print("now:", await collect_expired(engine, ttl_s, now=time.time(), dry_run=True))
print("three days later:", await collect_expired(engine, ttl_s, now=time.time() + 3 * 86400, dry_run=True))
await engine.dispose()

# %% [markdown]
# **Tidy up.** The recorder stops last, so the recording is saved once, after every call.
# %%
llm_replay.stop()                                 # the recording is saved only when the recorder stops
print("recorder stopped; the notebook's own calls were made by probe.py")

# %% [markdown]
# ## Key terms
# - **ASGI app** — the Python interface a server such as uvicorn runs. Mounts put other apps under a path prefix.
# - **Health route** — a URL a probe calls. It returns 200 only when the replica can serve.
# - **Proxy headers** — `X-Forwarded-For` and `X-Forwarded-Proto`. The app trusts them only from listed proxy addresses.
# - **TrustedHostMiddleware** — refuses requests whose Host header is not in the allowed list.
# - **X-Accel-Buffering** — a response header that tells nginx not to buffer the response. Event streams need it.
# - **VersionedDatabaseTaskStore** — the SDK's SQL task store with a version per task. It lets replicas detect a concurrent write.
# - **DatabaseTaskEventStream** — the SDK's event log in the same database. A replica reads it to stream a task another replica runs.
# - **TTL sweep** — a scheduled delete of finished tasks older than a time to live.
