# %% [markdown]
# # 23a · Retries, idempotency and deadlines across protocols
# Level L4 · Part 5 · professional · ~35 min · builds on 09, 10, 18

# %% [markdown]
# ## Goal
# By the end you can make a retry safe when nothing resumes. You send a `create_issue` call with one idempotency key and see that the retry writes nothing. You retry an AG-UI run as a new run that keeps the same operation id. You send the same A2A `messageId` twice and get the stored answer without a second model call. You pass one absolute deadline through AG-UI, MCP and A2A. Step 4 shows an MCP call cancelled at the deadline, and step 8 shows the A2A hop stopping when the deadline passes.

# %% [markdown]
# ## Why it matters
# A call can finish on the server and still fail on the client: the reply is lost, and the client cannot tell whether the work happened. A plain retry then does it twice.
#
# | Without a plan (the naive way) | With it (this lesson) |
# |---|---|
# | The connection drops after `create_issue`. The retry opens a second issue. | The retry carries the same key. Trackr returns the first issue and writes nothing. |
# | An AG-UI stream drops. The client asks to resume from the last event. | The protocol has no resume. The client starts a new run with the same operation id. |
# | An A2A retry asks the model again and pays again. | The same `messageId` returns the stored answer. |
# | Each hop sets its own 30 s timeout. The user waits 90 s while the work runs on. | One absolute deadline goes down the chain, and each hop uses what is left. |
#
# Reads need none of this: searching twice is harmless.

# %% [markdown]
# ## The idea
# A retry is safe only when the repeated request has the same identity as the first one. Three rules follow. First, a write carries an **idempotency key**. The client makes the key once per user action, and the server stores it with the result. Second, a stream cannot be resumed, so a retry is a **new run** with a new run id, and the operation id stays the same. Third, a **deadline** is one absolute time, the moment the user stops waiting. Every hop reads it and works out what is left.
#
# Analogy: a restaurant order slip with a number. If the waiter sends the slip again, the kitchen sees the number and does not cook a second steak. A new slip for the same order cooks it twice.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant C as Client
#   participant O as Orchestrator (AG-UI)
#   participant T as Trackr (MCP)
#   participant A as triage-agent (A2A)
#   C->>O: run 1, opId X, deadline D
#   O->>T: create_issue, key X
#   T-->>O: issue 24
#   O-->>C: stream lost (no resume)
#   C->>O: run 2, new runId, opId X, deadline D
#   O->>T: create_issue, key X
#   T-->>O: issue 24, replayed
#   O->>A: messageId X:classify, deadline D
#   A-->>O: FAILED, deadline_exceeded
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### 1. Set up the paths and start Trackr with idempotency keys
# The first cell sets up folders, ports and logs. The ports are 9231 for the triage-agent and 9232 for the AG-UI endpoint. Both are from this lesson's range. The Trackr server is two new files: `trackr_data.py` holds the issues and the key store, and `trackr_keys.py` holds the MCP tools. It is lesson 03's Trackr with one change: `create_issue` takes an optional `idempotency_key`. It also has a slow tool that logs when the client cancels it.

# %%
import sys, time, socket, asyncio, json
from pathlib import Path
sys.path.insert(0, "..")                          # so llm_setup and llm_replay import
import llm_replay
llm_replay.start("23a_retries-and-idempotency")   # the notebook's file name, first code cell
llm = None                                        # set by the model cell in step 5; stays None if that cell is skipped
Path("../apps/23a").mkdir(parents=True, exist_ok=True)   # the three app files go here
Path("../data/23a").mkdir(parents=True, exist_ok=True)   # logs written at run time go here
sys.path.insert(0, str(Path("../apps/23a").resolve()))
TRACKR = Path("../apps/23a/trackr_keys.py").resolve()
LOG_TRACKR = Path("../data/23a/trackr_log.txt")
LOG_TRACKR.unlink(missing_ok=True)                 # a clean log for every run of this notebook
AGENT_PORT, ENDPOINT_PORT = 9231, 9232
print("ports: triage-agent", AGENT_PORT, "| AG-UI endpoint", ENDPOINT_PORT)

# %% [markdown]
# The data file holds the 20 issues from lesson 03 and the idempotency store. The store maps each key to the arguments and the issue of its first call.

# %%
%%writefile ../apps/23a/trackr_data.py
"""Lesson 23a: the Trackr data and the idempotency store. trackr_keys.py (the MCP server) uses them."""
import sys, time
from pathlib import Path
from typing_extensions import TypedDict

LOG = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("trackr_log.txt")
ROWS = """1 Login button does nothing on Safari|web|open|high
2 Signup email arrives twice|api|open|medium
3 Dark mode hides the save icon|web|closed|low
4 App crashes when photo is rotated|mobile|open|critical
5 Rate limiter blocks health checks|infra|open|high
6 Search ignores capital letters|api|open|low
7 Push notifications arrive late|mobile|open|medium
8 Disk alert fires every night at 2am|infra|closed|medium
9 Typo on the pricing page|web|open|low
10 Export to CSV drops the last row|api|open|high
11 Offline mode loses drafts|mobile|closed|high
12 TLS certificate expires in 9 days|infra|open|critical
13 Footer links open in the same tab|web|closed|low
14 Pagination returns duplicates|api|open|medium
15 Battery drain in background sync|mobile|open|high
16 Backups not copied to second region|infra|open|high
17 Profile page slow to load|web|open|medium
18 Webhook retries never stop|api|closed|medium
19 Tablet layout cuts off buttons|mobile|open|low
20 Log volume doubled since Monday|infra|open|medium"""
ISSUES = [{"id": int(h.split(" ", 1)[0]), "title": h.split(" ", 1)[1], "team": t, "status": st, "severity": sv}
          for h, t, st, sv in (line.split("|") for line in ROWS.splitlines())]
SEEN: dict[str, tuple[tuple, dict]] = {}          # idempotency key -> (arguments, issue) of the first call

class Created(TypedDict):
    id: int
    title: str
    team: str
    status: str
    severity: str
    replayed: bool

def note(text: str) -> None:
    with LOG.open("a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} trackr: {text}\n")

# %% [markdown]
# The MCP server itself is the second file. It imports the data and adds the four tools. The first tool is lesson 03's `count_open`. The second is `search_issues`. The third is `create_issue`, which now takes the key. The fourth is `slow_scan`, which is for the deadline step.

# %%
%%writefile ../apps/23a/trackr_keys.py
"""Lesson 23a: Trackr with an idempotency key on create_issue, and a slow tool that logs when it is cancelled."""
import asyncio, sys
from typing import Literal
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from trackr_data import ISSUES, SEEN, Created, LOG, note

Team = Literal["web", "api", "mobile", "infra"]
Severity = Literal["low", "medium", "high", "critical"]
mcp = MCPServer("Trackr")

@mcp.tool(title="Count open issues", annotations=ToolAnnotations(readOnlyHint=True))
def count_open(team: Team) -> int:
    """Count open Trackr issues for one team."""
    return sum(1 for i in ISSUES if i["team"] == team and i["status"] == "open")

@mcp.tool(title="Search open issues", annotations=ToolAnnotations(readOnlyHint=True))
def search_issues(text: str) -> list[dict]:
    """Find open issues whose title contains the text, in any letter case."""
    needle = text.lower()
    return [i for i in ISSUES if i["status"] == "open" and needle in i["title"].lower()]

@mcp.tool(title="Create an issue", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
def create_issue(title: str, team: Team, severity: Severity, idempotency_key: str | None = None) -> Created:
    """Open a new issue. With an idempotency_key, repeating the same call returns the first issue and writes nothing."""
    args = (title, team, severity)
    if idempotency_key is not None and idempotency_key in SEEN:
        first_args, issue = SEEN[idempotency_key]
        if first_args != args:
            raise ToolError(f"idempotency key {idempotency_key!r} was already used for other arguments")
        note(f"key {idempotency_key!r}: replayed, nothing written")
        return {**issue, "replayed": True}
    new = {"id": max(i["id"] for i in ISSUES) + 1, "title": title, "team": team, "status": "open", "severity": severity}
    ISSUES.append(new)
    if idempotency_key is not None:
        SEEN[idempotency_key] = (args, new)
    note(f"issue {new['id']} written")
    return {**new, "replayed": False}

@mcp.tool(title="Slow scan", annotations=ToolAnnotations(readOnlyHint=True))
async def slow_scan(seconds: float) -> str:
    """Scan the issues for some seconds. The server log says whether the scan finished or was cancelled."""
    note(f"scan of {seconds} s started")
    try:
        await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        note("scan CANCELLED: the caller gave up, so the work stopped")
        raise
    note("scan finished")
    return f"scanned {len(ISSUES)} issues"

if __name__ == "__main__":
    mcp.run()                                    # stdio; the log path comes from argv

# %% [markdown]
# The next cell starts the server as a subprocess and keeps one client open for the whole lesson. Every later step uses this one connection. That matters: the idempotency key is stored in the server's memory, so a second server would not know the first call.

# %%
from mcp import Client
from mcp.client.stdio import StdioServerParameters

class HeldClient:
    """One MCP connection that stays open across cells: it lives in its own task until close()."""
    async def start(self, params: StdioServerParameters) -> Client:
        self.ready, self.done = asyncio.Event(), asyncio.Event()
        self.task = asyncio.create_task(self._hold(params))
        await self.ready.wait()
        return self.client

    async def _hold(self, params: StdioServerParameters) -> None:
        async with Client(params) as client:
            self.client = client
            self.ready.set()
            await self.done.wait()

    async def close(self) -> None:
        self.done.set()
        await self.task

held = HeldClient()
trackr = await held.start(StdioServerParameters(command=sys.executable, args=[str(TRACKR), str(LOG_TRACKR)]))
print("Trackr tools:", sorted(t.name for t in (await trackr.list_tools()).tools))

# %% [markdown]
# ### 2. Without a key: a retry after a lost reply
# The first call below finishes on the server. Its reply never reaches us, so the code throws the result away. That is a dropped connection. Then the client does what most code does: it retries the same call. Search for the title afterwards and count the rows.

# %%
issue = {"title": "Export to PDF drops the header row", "team": "api", "severity": "medium"}
await trackr.call_tool("create_issue", issue)          # the reply is lost: we never read it
await trackr.call_tool("create_issue", issue)          # the naive retry, with no key
rows = await trackr.call_tool("search_issues", {"text": "Export to PDF"})
print("issues with that title:", len(rows.structured_content["result"]))   # 2: the retry duplicated the work

# %% [markdown]
# ### 3. With a key: the same retry writes nothing
# The client makes the key once for this user action, before the first call. The retry sends the same key. The server keeps the first result under that key, and a repeat returns it with `replayed: True`. The key is a plain string the client chooses, such as `op-` plus an id from the user's action. The model never chooses it.

# %%
args = {"title": "Login loop on Android 15", "team": "mobile", "severity": "high", "idempotency_key": "op-login-loop-android-1"}
first = await trackr.call_tool("create_issue", args)    # the reply is lost
again = await trackr.call_tool("create_issue", args)     # the retry: same key
print("first:", first.structured_content["id"], "| retry:", again.structured_content["id"],
      "| replayed:", again.structured_content["replayed"])
rows = await trackr.call_tool("search_issues", {"text": "Login loop"})
print("issues with that title:", len(rows.structured_content["result"]))

# %% [markdown]
# A key is only safe for the request it was made for. If the same key arrives with other arguments, the server must refuse it. Trackr does that with an error reply, not a silent write.

# %%
other = await trackr.call_tool("create_issue", {**args, "severity": "low"})
print("same key, other severity -> is_error:", other.is_error, "|", other.content[0].text)

# %% [markdown]
# ### 4. One deadline on the MCP hop
# A deadline is a fixed moment, in epoch milliseconds, stored as `deadline_ms`. Each hop computes `deadline_ms / 1000 - time.time()` and uses that as its timeout. The call below is a 30 s scan under a 10 s deadline. When the client gives up, the stdio transport sends a cancel, and the server stops the scan. The server log proves it.

# %%
DEADLINE_MS = int(time.time() * 1000) + 10_000          # one absolute deadline, 10 s from now
def remaining_s(deadline_ms: int) -> float:
    return deadline_ms / 1000 - time.time()
try:
    async with asyncio.timeout(remaining_s(DEADLINE_MS)):
        await trackr.call_tool("slow_scan", {"seconds": 30})
except TimeoutError:
    print("the MCP call gave up at the deadline")
for _ in range(50):                                     # the server logs just after the cancel arrives: poll, don't sleep
    if "CANCELLED" in LOG_TRACKR.read_text():
        break
    await asyncio.sleep(0.1)
print("server log, last line:", LOG_TRACKR.read_text().splitlines()[-1])

# %% [markdown]
# ### 5. A2A: the same messageId twice gives one answer
# The triage-agent is a new file. It has lesson 18's shape, with two additions. It stores its answer under the incoming `messageId`, so a second message with that id returns the stored answer and makes no model call. It also reads the deadline from the request metadata and stops when the deadline passes. It stores only successes, so a failed try can run again.

# %%
%%writefile ../apps/23a/triage_agent.py
"""Lesson 23a: triage-agent with messageId dedupe and a deadline. One model call per new messageId."""
import asyncio, time
from pathlib import Path
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette

LLM = None            # the notebook sets a real model; None gives a labelled stand-in
STALL_S = 0.0         # the notebook sets 30 for the deadline demo: a slow queue before the model
ANSWERS: dict[str, str] = {}   # messageId -> answer; only successes are stored

def build_card(port: int) -> AgentCard:
    return AgentCard(
        name="triage-agent", description="Classifies Trackr issues as bug, feature or question.", version="1.0.0",
        supported_interfaces=[AgentInterface(url=f"http://127.0.0.1:{port}/", protocol_binding="JSONRPC",
                                             protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"], default_output_modes=["text/plain"],
        skills=[AgentSkill(id="classify_issues", name="Classify issues", description="One line per issue.",
                           tags=["triage"], examples=["4: App crashes when photo is rotated"],
                           input_modes=["text/plain"], output_modes=["text/plain"])])

async def classify(text: str) -> tuple[str, str]:
    if LLM is None:
        return "\n".join(f"{line.split(':')[0]}: stand-in (no model)" for line in text.splitlines() if line.strip()), "stand-in"
    prompt = ("Classify each issue as exactly one word: bug, feature or question.\n"
              "Reply with one line per issue, in the form '<id>: <label>', and nothing else.\n" + text)
    reply = await LLM.ainvoke(prompt)
    return reply.text.strip(), "model"

class DedupeTriageExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        msg_id = context.message.message_id
        if msg_id in ANSWERS:                                  # seen before: return the stored answer
            await updater.add_artifact(parts=[new_text_part(ANSWERS[msg_id])], name="replayed")
            await updater.complete()
            return
        deadline_ms = context.metadata.get("deadlineMs")       # the absolute deadline from the caller
        budget = None if deadline_ms is None else deadline_ms / 1000 - time.time()
        try:
            async with asyncio.timeout(budget):
                await asyncio.sleep(STALL_S)
                answer, source = await classify(get_message_text(context.message))
        except TimeoutError:
            await updater.failed(updater.new_agent_message([new_text_part("deadline_exceeded before the model call")]))
            return
        ANSWERS[msg_id] = answer
        await updater.add_artifact(parts=[new_text_part(answer)], name=source)
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

def build_app(card: AgentCard) -> Starlette:
    handler = DefaultRequestHandler(agent_executor=DedupeTriageExecutor(),
                                    task_store=InMemoryTaskStore(), agent_card=card)
    return Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")])

# %% [markdown]
# The model cell comes first. It is the only real model call in step 5. The next cell serves the triage-agent and fetches its card the way lesson 18 did.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm()                                   # the real model, recorded once, replayed from data/llm_cassettes
print("model:", type(llm).__name__)

# %% [markdown]
# Two helpers serve an ASGI app as a task in this notebook's event loop. One loop runs the agents, the endpoint and the model. That keeps the model client in one loop, as lesson 18 did.

# %%
import httpx, uvicorn
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
import triage_agent

# %% [markdown]
# First a probe: it polls a URL until it answers 200. No fixed sleep, and a timeout with a clear error.

# %%
async def wait_for_probe(url: str, timeout: float = 15.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    async with httpx.AsyncClient(timeout=1) as http:
        while loop.time() < deadline:
            try:
                if (await http.get(url)).status_code == 200:
                    return
            except httpx.TransportError:
                pass                                   # not up yet
            await asyncio.sleep(0.1)
    raise RuntimeError(f"nothing answered {url} in time")

# %% [markdown]
# Then `Served` runs one ASGI app as a task of this notebook's loop. It refuses a port that is already taken.

# %%
class Served:
    def __init__(self, app, port: int, probe: str):
        self.port, self.url = port, f"http://127.0.0.1:{port}"
        self.probe_url = self.url + probe
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    async def start(self) -> "Served":
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", self.port)) != 0, f"port {self.port} is already in use"
        self.task = asyncio.create_task(self.server.serve())
        await wait_for_probe(self.probe_url)
        return self

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task

triage_agent.LLM = llm
agent = await Served(triage_agent.build_app(triage_agent.build_card(AGENT_PORT)), AGENT_PORT,
                     "/.well-known/agent-card.json").start()
async with httpx.AsyncClient(timeout=60) as http:
    found = await A2ACardResolver(http, agent.url).get_agent_card()
a2a_http = httpx.AsyncClient(timeout=60)          # the SDK's default 5 s is shorter than the deadline demo
a2a = await create_client(agent=found, client_config=ClientConfig(streaming=False, httpx_client=a2a_http))
print("found:", found.name, "| skills:", [s.id for s in found.skills])

# %% [markdown]
# Now the test. Send one batch of three issues with the message id `msg-batch-1`. Then send the same text again with the same `messageId`, as a retry would. Each send builds a new message object, so only the id is shared.

# %%
def batch(message_id: str) -> SendMessageRequest:
    msg = new_text_message("4: App crashes when photo is rotated\n9: Typo on the pricing page\n"
                           "15: Battery drain in background sync", role=Role.ROLE_USER)
    msg.message_id = message_id
    return SendMessageRequest(message=msg)

async def send(request: SendMessageRequest):
    task = None
    async for chunk in a2a.send_message(request):
        if chunk.WhichOneof("payload") == "task":
            task = chunk.task
    return task

for attempt in (1, 2):
    task = await send(batch("msg-batch-1"))
    artifact = task.artifacts[0]
    print(f"send {attempt}: {TaskState.Name(task.status.state)} | artifact '{artifact.name}'")
print(get_artifact_text(artifact))

# %% [markdown]
# ### 6. The orchestrator: one AG-UI endpoint, with the key and the deadline from the client
# The orchestrator is two new files. `orchestrator_tools.py` holds the two tools, and `orchestrator_app.py` holds the endpoint. It is lesson 10's endpoint with three changes. The client sends an operation id and an absolute deadline in `forwardedProps`. The model only chooses the tool and its arguments. The code adds the operation id as the idempotency key, and it passes the deadline to every hop. A missing model keeps the same shape with a labelled stand-in call.

# %%
%%writefile ../apps/23a/orchestrator_tools.py
"""Lesson 23a: the orchestrator's two tools. Each hop gets the same absolute deadline; the key is the client's opId."""
import asyncio, time
from typing import Literal
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from a2a.helpers import get_artifact_text, get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState

TRACKR = None         # the notebook sets the connected Trackr client, shared by every run
A2A = None            # the notebook sets an A2A client for triage-agent

class RunStop(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message

@tool
def create_issue(title: str, team: Literal["web", "api", "mobile", "infra"],
                 severity: Literal["low", "medium", "high", "critical"]) -> str:
    """Open a Trackr issue. Use it when the user asks to file or open a bug."""
    raise NotImplementedError("schema only: the orchestrator runs this tool itself")

@tool
def classify_issues(issue_ids: list[int]) -> str:
    """Send open Trackr issues to triage-agent, which labels each as bug, feature or question."""
    raise NotImplementedError("schema only: the orchestrator runs this tool itself")

def remaining_s(deadline_ms: int) -> float:
    return deadline_ms / 1000 - time.time()

async def within(factory, deadline_ms: int, what: str, grace: float = 0.0):
    if remaining_s(deadline_ms) <= 0:
        raise RunStop("deadline_exceeded", f"deadline passed before {what}")
    try:
        async with asyncio.timeout(remaining_s(deadline_ms) + grace):
            return await factory()
    except TimeoutError:
        raise RunStop("deadline_exceeded", f"deadline passed during {what}")

async def call_create(args: dict, op_id: str, deadline_ms: int) -> str:
    reply = await within(lambda: TRACKR.call_tool("create_issue", {**args, "idempotency_key": op_id}),
                         deadline_ms, "create_issue")
    if reply.is_error:
        raise RunStop("tool_failed", reply.content[0].text)
    issue = reply.structured_content
    return f"issue {issue['id']} " + ("already created (replayed)" if issue["replayed"] else "created")

async def call_classify(args: dict, op_id: str, deadline_ms: int) -> str:
    rows = await within(lambda: TRACKR.call_tool("search_issues", {"text": ""}), deadline_ms, "search_issues")
    by_id = {r["id"]: r["title"] for r in rows.structured_content["result"]}
    text = "\n".join(f"{i}: {by_id[i]}" for i in args["issue_ids"] if i in by_id)
    request = SendMessageRequest(message=new_text_message(text, role=Role.ROLE_USER))
    request.message.message_id = f"{op_id}:classify"     # stable across retries: the agent dedupes on it
    request.metadata.update({"deadlineMs": deadline_ms})  # the same absolute deadline, one hop further

    async def send_and_wait():
        task = None
        async for chunk in A2A.send_message(request):
            if chunk.WhichOneof("payload") == "task":
                task = chunk.task
        return task
    task = await within(send_and_wait, deadline_ms, "triage-agent", grace=5.0)  # the agent enforces the deadline
    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        detail = get_message_text(task.status.message) if task.status.HasField("message") else ""
        raise RunStop("deadline_exceeded" if detail.startswith("deadline_exceeded") else "a2a_failed", f"triage-agent: {detail}")
    return get_artifact_text(task.artifacts[0])

def stand_in(question: str) -> AIMessage:
    """No model: a fixed tool call stands in, so the keys and the deadline still run. Labelled in the notebook."""
    if "classify" in question.lower():
        return AIMessage(content="", tool_calls=[{"name": "classify_issues", "id": "standin_1", "args": {"issue_ids": [4, 9, 15]}}])
    return AIMessage(content="", tool_calls=[{"name": "create_issue", "id": "standin_1",
                     "args": {"title": "Photo upload fails on iOS 18", "team": "mobile", "severity": "high"}}])

TOOLS = [create_issue, classify_issues]
# %% [markdown]
# The endpoint file imports the tools and runs the stream. Its rules are unchanged from lesson 10: each `yield` is one event, and a failure is an event too.

# %%
%%writefile ../apps/23a/orchestrator_app.py
"""Lesson 23a: the Trackr orchestrator behind AG-UI. The client sends an opId and an absolute deadline."""
import json, uuid
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from ag_ui.core import (RunAgentInput, RunStartedEvent, RunFinishedEvent, RunErrorEvent, RunFinishedSuccessOutcome,
    ToolCallStartEvent, ToolCallArgsEvent, ToolCallEndEvent, ToolCallResultEvent)
from ag_ui.encoder import EventEncoder
from orchestrator_tools import TOOLS, RunStop, call_classify, call_create, remaining_s, stand_in

LLM = None            # the notebook sets a real model; None gives a labelled stand-in tool call
ENC = EventEncoder(accept="text/event-stream")

async def run_events(inp: RunAgentInput):
    yield ENC.encode(RunStartedEvent(thread_id=inp.thread_id, run_id=inp.run_id))
    props = inp.forwarded_props or {}
    op_id, deadline_ms = props["opId"], props["deadlineMs"]
    try:
        if remaining_s(deadline_ms) <= 0:
            raise RunStop("deadline_exceeded", "deadline passed before the model call")
        question = inp.messages[-1].content
        if LLM is None:
            ai = stand_in(question)
        else:
            ai = await LLM.bind_tools(TOOLS).ainvoke([HumanMessage(question)])
        for call in ai.tool_calls:
            yield ENC.encode(ToolCallStartEvent(tool_call_id=call["id"], tool_call_name=call["name"]))
            yield ENC.encode(ToolCallArgsEvent(tool_call_id=call["id"], delta=json.dumps(call["args"])))
            yield ENC.encode(ToolCallEndEvent(tool_call_id=call["id"]))
            if call["name"] == "create_issue":
                text = await call_create(call["args"], op_id, deadline_ms)
            else:
                text = await call_classify(call["args"], op_id, deadline_ms)
            yield ENC.encode(ToolCallResultEvent(message_id=str(uuid.uuid4()), tool_call_id=call["id"], content=text))
        yield ENC.encode(RunFinishedEvent(thread_id=inp.thread_id, run_id=inp.run_id,
                                          outcome=RunFinishedSuccessOutcome(type="success")))
    except RunStop as stop:                       # the status is already 200: the failure travels as RUN_ERROR
        yield ENC.encode(RunErrorEvent(message=stop.message, code=stop.code))
    except Exception as exc:                      # anything else is still an event, never a cut stream
        yield ENC.encode(RunErrorEvent(message=repr(exc), code="internal_error"))

app = FastAPI()

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/agent")
async def agent_endpoint(inp: RunAgentInput):
    return StreamingResponse(run_events(inp), media_type=ENC.get_content_type(),
                             headers={"X-Accel-Buffering": "no"})

# %% [markdown]
# The cell below connects the orchestrator to the Trackr client, the A2A client and the model, then starts the endpoint. The endpoint's health probe must answer before the lesson goes on.

# %%
import orchestrator_app, orchestrator_tools
orchestrator_tools.TRACKR, orchestrator_tools.A2A = trackr, a2a
orchestrator_app.LLM = llm
endpoint = await Served(orchestrator_app.app, ENDPOINT_PORT, "/health").start()
print("AG-UI endpoint:", endpoint.url + "/agent", "| model set:", llm is not None)

# %% [markdown]
# ### 7. Retry = a new run with the same operation id
# AG-UI has no resume. The client reads the stream until the tool result arrives, then the connection drops. The retry is a **new run**: a new `runId`, the same `threadId` and the same `opId`. The helper below POSTs one `RunAgentInput` and reads the `data:` lines as they arrive. It can stop after a named event, which is how this lesson drops the connection.

# %%
async def stream_run(question: str, run_id: str, op_id: str, deadline_ms: int, keep_until: str | None = None):
    payload = {"threadId": "thread-ops-1", "runId": run_id, "state": {}, "tools": [], "context": [],
               "forwardedProps": {"opId": op_id, "deadlineMs": deadline_ms},
               "messages": [{"id": "m-" + run_id, "role": "user", "content": question}]}
    events = []
    async with httpx.AsyncClient(timeout=60) as http:
        async with http.stream("POST", endpoint.url + "/agent", json=payload,
                               headers={"Accept": "text/event-stream"}) as reply:
            async for line in reply.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: "):]))
    if keep_until:          # the client keeps events up to this one; the rest counts as lost with the connection
        events = events[: next(i for i, e in enumerate(events) if e["type"] == keep_until) + 1]
    return events

# %% [markdown]
# Run 1 is cut after its tool result: the client keeps only the events up to that result. Run 2 is the retry, a new run with a new `runId` and the same `opId`.

# %%
QUESTION = "File a bug: 'Photo upload fails on iOS 18' for the mobile team, severity high."
OP = "op-photo-upload-1"                                   # made by the client once, when the user clicked "file bug"
LATER_MS = int(time.time() * 1000) + 60_000               # a deadline far enough away for these two runs
run1 = await stream_run(QUESTION, "run-1", OP, LATER_MS, keep_until="TOOL_CALL_RESULT")
print("run 1 kept:", [e["type"] for e in run1])
print("run 1 tool result:", next(e["content"] for e in run1 if e["type"] == "TOOL_CALL_RESULT"))
run2 = await stream_run(QUESTION, "run-2", OP, LATER_MS)
print("run 2 events:", [e["type"] for e in run2])
print("run 2 tool result:", next(e["content"] for e in run2 if e["type"] == "TOOL_CALL_RESULT"))

# %% [markdown]
# ### 8. One deadline across AG-UI, A2A and MCP
# This run asks for a classification. The orchestrator reads the titles over MCP, then sends the batch to triage-agent with the same deadline. The agent is slow before its model call, so the deadline arrives first. The agent stops, returns a failed Task that says where it stopped, and the AG-UI run ends with `RUN_ERROR` and the code `deadline_exceeded`.

# %%
triage_agent.STALL_S = 30.0                    # the slow queue, set for this run only
run3 = await stream_run("Classify issues 4, 9 and 15 as bug, feature or question.", "run-3", "op-classify-2",
                        int(time.time() * 1000) + 10_000)
triage_agent.STALL_S = 0.0
print("events:", [e["type"] for e in run3])
error = next(e for e in run3 if e["type"] == "RUN_ERROR")
print("RUN_ERROR code:", error["code"], "|", error["message"])

# %% [markdown]
# The same deadline was used on each hop: the MCP read (it finishes well inside the deadline), then the A2A send. The MCP cancel was shown in step 4; here the A2A hop stops. The agent's own check ended its work at the deadline, before any model call. The run ended at once after that.

# %% [markdown]
# ## At work
# - Stripe's API takes an `Idempotency-Key` header, rejects a reused key whose parameters differ, and prunes keys after at least 24 hours. Trackr uses the same rules in a tool argument. Its key store is in memory and is lost on restart. The A2A task store with expiry is in lesson 32.
# - Streams do not resume on the wire. AG-UI has no resume, and Streamable HTTP does not resume SSE, so production clients keep the operation id and start a new run. Each run's trace should carry that id → lesson 28.
# - Work that outlives one connection goes into an MCP Task with a `taskId`, polled with `pollIntervalMs`. Do not hold one request open for minutes → lesson 13a.
# - A gateway in front of many servers applies per-tool policy and rate limits, so one caller cannot tie up every hop → lesson 40.

# %% [markdown]
# ## What just happened
# - A lost reply plus a naive retry opened a duplicate issue. The same call with an idempotency key wrote once, and the repeat said `replayed`.
# - The MCP call with a 10 s deadline was cancelled by the client. The server log shows the scan stopped.
# - A2A messages with the same `messageId` returned the stored answer. The second send made no model call.
# - The AG-UI retry was a new run with a new `runId`. The operation id was the same, so the second run found the first issue.
# - One absolute deadline reached the agent through the AG-UI run, the orchestrator and the A2A metadata. The run ended with `deadline_exceeded`, and the A2A agent stopped its work.

# %% [markdown]
# ### What this does not solve
# A key only protects the operation it names. If the agent also sends an email, the email API needs its own key. A key store in memory is lost on restart, so a real one lives in a database with an expiry. A retry that changes the request, such as a new title, is a different operation and should get a new key. Work that takes minutes needs MCP Tasks (lesson 13a), not a retry loop. When an operation cannot be repeated at all, use a compensating action instead of a retry.

# %% [markdown]
# ## Common mistakes
# Reading a reply without checking `is_error` first. Here the same key comes back with another severity, so the server refuses it. The code reads `structured_content` on an error reply:

# %% tags=["raises-exception"]
bad = await trackr.call_tool("create_issue", {**args, "team": "web"})   # same key, other team: an error reply
print(bad.structured_content["id"])                                       # structured_content is None on an error

# %% [markdown]
# Fix: check `is_error` first, print `content[0].text`, and only then read `structured_content`. A second mistake is silent: making a new key on every attempt. `str(uuid.uuid4())` inside the retry loop turns each retry into a new request, so the key protects nothing. Make the key before the first attempt and reuse it.

# %% [markdown]
# ## Try it
# Make one keyed `create_issue` for the title `"Dark mode hides the save icon on Android"` with key `op-try-1`, team `web` and severity `low`. Send the same key again with the title `"Dark mode hides the save icon on iOS"`. Print the second reply's `is_error` and its text. Then count the issues whose title contains `"Dark mode hides the save icon"`. No model is needed.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
key_args = {"team": "web", "severity": "low", "idempotency_key": "op-try-1"}
ok = await trackr.call_tool("create_issue", {"title": "Dark mode hides the save icon on Android", **key_args})
changed = await trackr.call_tool("create_issue", {"title": "Dark mode hides the save icon on iOS", **key_args})
print("is_error:", changed.is_error, "|", changed.content[0].text)
rows = await trackr.call_tool("search_issues", {"text": "Dark mode hides the save icon"})
print("issues with that text:", len(rows.structured_content["result"]))   # 1: the second send wrote nothing

# %% [markdown]
# ## Key terms
# - **idempotency key** — a client-made id for one logical write. The server stores the first result under it, and a repeat returns that result without writing again.
# - **non-resumable stream** — an event stream that cannot continue from a position after a drop. The client starts a new request or run.
# - **retry as a new run** — the AG-UI rule: a dropped run is retried as a new run with a new run id and the same operation id.
# - **messageId dedupe** — an A2A agent that stores its answer under the incoming `messageId` and returns it for a repeat. The a2a-sdk 1.2.2 does not do this for you, so this lesson's agent does it itself.
# - **absolute deadline** — one fixed time (epoch milliseconds) passed to every hop. Each hop uses the time left, so the waits do not add up.

# %% [markdown]
# ## Clean up
# Stop the endpoint and the triage-agent, close the A2A client and the Trackr connection, and save the recording.

# %%
await endpoint.stop()
await agent.stop()
await a2a.close()
await a2a_http.aclose()
await held.close()                                        # closes the Trackr connection and stops the subprocess
llm_replay.stop()                                         # saves the recording if a model ran; a no-op otherwise
print("lesson 23a done: keys for writes, new runs for streams, one messageId for A2A, one deadline for every hop")
