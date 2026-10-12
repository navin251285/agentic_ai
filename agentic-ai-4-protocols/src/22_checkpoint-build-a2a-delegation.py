# %% [markdown]
# # 22 · Checkpoint (Build, part 2): two A2A agents and a delegating orchestrator
# Level L3 · Part 4 · professional · ~120 min · builds on 09, 17, 18, 19

# %% [markdown]
# ## Goal
# By the end you have one working ops desk for Trackr. An AG-UI orchestrator delegates triage to lesson 18's triage-agent and a fix proposal to a new fix-agent, both over A2A. It then stops before `close_issue`, and a person decides. A cancel leaves issue 12 open. An approve on a new thread closes it. Every requirement below is checked by a printed PASS or FAIL.

# %% [markdown]
# ## Why it matters
# Without this build, each part works alone. The orchestrator would hold the triage and fix code itself, so every new team means new code in the orchestrator. Its write would also run the moment the model asks, and nobody would see the change first. This checkpoint joins three protocols in one flow: MCP for the data and the write, A2A for the two agents, and AG-UI for the person. It also shows the pause, the one step that must not be skipped.
#
# The cell below shows the unsafe loop: the model asks for a close and the write runs at once.

# %%
unsafe_pick = {"name": "close_issue", "args": {"issue_id": 12}}   # what a model might return, no model run here
print("without a gate: the write runs for", unsafe_pick, "and nobody is asked first")

# %% [markdown]
# ## The idea
# The ops desk is one orchestrator with three kinds of help. Trackr over MCP holds the data and performs the one write. Two agents over A2A each judge one job: triage-agent labels issues, and fix-agent proposes a fix. The orchestrator's model chooses which help to use. The gate node sits in front of `close_issue`, and it calls `interrupt()`, so the run stops and the person answers over AG-UI.
#
# Analogy: a support desk with a database, two specialist consultants and a manager. The consultants write reports. The manager reads them, proposes an action and waits for the owner's sign-off before the database changes.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant P as Person (AG-UI client)
#   participant O as Orchestrator (AG-UI)
#   participant T as Trackr (MCP)
#   participant A as triage-agent (A2A)
#   participant F as fix-agent (A2A)
#   P->>O: Triage 4, 9, 12, 15 and fix 12
#   O->>A: classify (one message)
#   O->>F: propose_fix 12
#   A-->>O: artifact: labels
#   F-->>O: artifact: fix proposal
#   O-->>P: interrupt: Close issue 12?
#   P->>O: resume: cancelled (issue 12 stays open)
#   P->>O: new thread: the fix is approved, close 12
#   O-->>P: interrupt: Close issue 12?
#   P->>O: resume: approved
#   O->>T: close_issue 12 (MCP write)
# ```

# %% [markdown]
# ## Requirements
# The build is done when the ship check (step 11) prints PASS for every line.
# - [ ] **R1.** Both agents are found from their cards over A2A. The triage artifact has one line per issue asked for (4, 9, 12, 15).
# - [ ] **R2.** The fix proposal comes back, and issue 12 is still open. Nothing changed before a person decided.
# - [ ] **R3.** The first run ends paused: the interrupt asks "Close issue 12?" and names `close_issue`.
# - [ ] **R4.** A cancelled resume on the same thread leaves issue 12 open, and the run says it was cancelled.
# - [ ] **R5.** An approved resume on a new thread closes issue 12. The run finishes without another interrupt.
# - [ ] **R6.** At most 5 model calls: the orchestrator twice on thread A, once on thread B, and one each for the two agents.
#
# **Make it yours.** Add a third team's agent as a new skill on the same card pattern. The gate and the checks stay the same.

# %% [markdown]
# ## Build it
# ### 1. Setup and the Trackr connection
# The notebook reuses the Trackr server from lesson 03, the triage-agent from lesson 18, and the approval gate idea from lesson 19. The ports come from this lesson's range, 8220 to 8229. The model is set later, in step 6.

# %%
import sys, json, socket, asyncio
from pathlib import Path
sys.path.insert(0, "..")                       # so llm_setup and llm_replay import
import llm_replay                              # the model cell starts it; the ship check and the stop use it
import httpx, uvicorn                          # the local A2A and AG-UI servers and clients use them
TRACKR = Path("../apps/03/trackr_server.py").resolve()
TRIAGE_FILE = Path("../apps/18/batch_triage_agent.py").resolve()
assert TRACKR.exists(), "run lesson 03 first: it writes the Trackr server"
assert TRIAGE_FILE.exists(), "run lesson 18 first: it writes the triage-agent"
Path("../apps/22").mkdir(parents=True, exist_ok=True)   # the fix-agent and orchestrator files go here
sys.path[:0] = [str(Path("../apps/22").resolve()), str(TRIAGE_FILE.parent)]
AGUI_PORT, TRIAGE_PORT, FIX_PORT = 8221, 8223, 8224
print("Trackr:", TRACKR.name, "| AG-UI", AGUI_PORT, "| triage-agent", TRIAGE_PORT, "| fix-agent", FIX_PORT)

# %% [markdown]
# The helper below keeps one MCP connection open across cells, as lessons 18 and 19 did. Trackr is a subprocess, so its data lives in that process. Issue 12 is open when the process starts.

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
trackr = await held.start(StdioServerParameters(command=sys.executable, args=[str(TRACKR)]))
open_rows = (await trackr.call_tool("search_issues", {"text": ""})).structured_content["result"]
print("open issues:", len(open_rows), "| 12 open:", any(r["id"] == 12 for r in open_rows))
issue_12 = next(r for r in open_rows if r["id"] == 12)
print("issue 12:", issue_12["title"], "| severity:", issue_12["severity"])
critical = [r["id"] for r in open_rows if r["severity"] == "critical"]
print("open critical issues:", critical, "(Trackr keeps no dates, so the highest id is the newest)")

# %% [markdown]
# ### 2. The fix-agent: one new A2A agent
# The fix-agent is a new file. It has the same parts as the triage-agent from lesson 18: a card, an executor and an app. It proposes a fix for one issue in one model call, and it never writes to Trackr. Its skill name is `propose_fix`.

# %%
%%writefile ../apps/22/fix_agent.py
"""Lesson 22: fix-agent. It reads one 'id: title' line and proposes a fix in ONE model call. It changes nothing in Trackr."""
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette

LLM = None   # the notebook sets a real model here; None means the scripted fallback

# %% [markdown]
# The card advertises one skill, `propose_fix`. It follows the same card pattern as the triage-agent.

# %%
%%writefile -a ../apps/22/fix_agent.py

def build_card(port: int) -> AgentCard:
    return AgentCard(
        name="fix-agent",
        description="Proposes a fix for one Trackr issue. It does not change Trackr.",
        version="1.0.0",
        supported_interfaces=[AgentInterface(url=f"http://127.0.0.1:{port}/",
                                             protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[AgentSkill(id="propose_fix", name="Propose a fix",
                           description="Reads one 'id: title' line and answers with a short fix proposal.",
                           tags=["fix"], examples=["12: TLS certificate expires in 9 days"],
                           input_modes=["text/plain"], output_modes=["text/plain"])],
    )

async def propose(line: str) -> tuple[str, str]:
    if LLM is None:   # no model: a fixed text, labelled 'scripted' in the artifact name
        return f"{line.split(':')[0]}: scripted proposal (no model): renew the certificate and check the renewal job.", "scripted"
    prompt = ("You are a careful engineer. Propose a fix for the issue below in two sentences. "
              "Say what to change and how to check it. Do not claim it is done.\n" + line)
    reply = await LLM.ainvoke(prompt)          # one model call for this issue
    return reply.text.strip(), "model"

# %% [markdown]
# The executor answers one task from the queue. The app serves the card and the JSON-RPC endpoint.

# %%
%%writefile -a ../apps/22/fix_agent.py

class FixExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:       # the Task must exist before any status update
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        answer, source = await propose(get_message_text(context.message).strip())
        await updater.add_artifact(parts=[new_text_part(answer)], name=source)
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

def build_app(card: AgentCard) -> Starlette:
    handler = DefaultRequestHandler(agent_executor=FixExecutor(),
                                    task_store=InMemoryTaskStore(), agent_card=card)
    return Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")])

# %% [markdown]
# ### 3. Serve both A2A agents and find them from their cards
# One helper serves an ASGI app as a task of this notebook's loop. It waits for a probe URL. For an A2A agent the probe is the card. The triage-agent is the lesson 18 module, unchanged. The client reads each card and makes an A2A client from it. It never imports either agent's code.
#
# `llm_replay` records every httpx call made after it starts, local ones included. Only the model calls belong in the recording, so the client below sends its local calls through httpx's own socket transport, kept before recording starts.

# %%
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
import batch_triage_agent, fix_agent
print("a2a client and both agent modules imported")

# %% [markdown]
# `SocketTransport` is httpx's socket transport, called directly. The recorder skips it, so the local A2A and AG-UI calls really run in a replay. The model's own HTTP calls use the normal transport, so they are still recorded and replayed. The recorder replaces `handle_async_request` when it starts, so we save the original first.

# %%
_SOCKET_CALL = httpx.AsyncHTTPTransport.handle_async_request   # kept before llm_replay.start(): the recorder wraps this method

class SocketTransport(httpx.AsyncBaseTransport):
    """httpx's socket transport, called directly, so the recorder does not record or replay this local call."""
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request):
        return await _SOCKET_CALL(self.inner, request)

    async def aclose(self):
        await self.inner.aclose()

print("local calls use", SocketTransport.__name__, "via the saved", _SOCKET_CALL.__qualname__, "and are not recorded")

# %% [markdown]
# `Server` serves one ASGI app as a task of this notebook's loop. It answers only after the probe path returns 200.

# %%
class Server:
    """One ASGI app served as a task of this notebook's event loop. probe is a path that answers 200 when it is up."""
    def __init__(self, app, port: int, probe: str):
        self.port, self.url, self.probe = port, f"http://127.0.0.1:{port}", probe
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    async def start(self, timeout: float = 15.0) -> "Server":
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", self.port)) != 0, f"port {self.port} is already in use"
        self.task = asyncio.create_task(self.server.serve())
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with httpx.AsyncClient(timeout=1) as http:
            while loop.time() < deadline:
                try:
                    if (await http.get(self.url + self.probe)).status_code == 200:
                        return self
                except httpx.TransportError:
                    pass                       # not up yet
                await asyncio.sleep(0.1)
        raise RuntimeError(f"{self.url}{self.probe} did not answer in time")

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task

# %% [markdown]
# `a2a_client_for` reads a card and makes an A2A client from it. The orchestrator never sees the agent's code.

# %%
async def a2a_client_for(url: str):
    """Read the card at url, then make a client from it. Returns (card, client)."""
    http = httpx.AsyncClient(transport=SocketTransport(), timeout=60)
    card = await A2ACardResolver(http, url).get_agent_card()
    return card, await create_client(agent=card, client_config=ClientConfig(streaming=False, httpx_client=http))

triage_server = await Server(batch_triage_agent.build_app(batch_triage_agent.build_card(TRIAGE_PORT)),
                             TRIAGE_PORT, "/.well-known/agent-card.json").start()
fix_server = await Server(fix_agent.build_app(fix_agent.build_card(FIX_PORT)),
                          FIX_PORT, "/.well-known/agent-card.json").start()
triage_card, triage_client = await a2a_client_for(triage_server.url)
fix_card, fix_client = await a2a_client_for(fix_server.url)
for card in (triage_card, fix_card):
    print("found:", card.name, "| skills:", [s.id for s in card.skills])

# %% [markdown]
# `ask_agent` sends one message and waits for the Task. It returns the artifact text, which is the answer. The orchestrator will call it from its tools.

# %%
async def ask_agent(client, text: str) -> str:
    request = SendMessageRequest(message=new_text_message(text, role=Role.ROLE_USER))
    task = None
    async for chunk in client.send_message(request):
        if chunk.WhichOneof("payload") == "task":
            task = chunk.task
    assert TaskState.Name(task.status.state) == "TASK_STATE_COMPLETED", task.status
    return get_artifact_text(task.artifacts[0])

# %% [markdown]
# ### 4. The orchestrator: two delegation tools, one MCP write, one gate
# The orchestrator is a LangGraph graph behind AG-UI. Its tools are `classify_issues` and `propose_fix` (both delegate over A2A) and `close_issue` (an MCP write). The `act` node runs the first two. The `gate` node runs before `close_issue`, and it calls `interrupt()`. The first part of the file holds the tools and the state.

# %%
%%writefile ../apps/22/orchestrator.py
"""Lesson 22: the Trackr ops orchestrator. An AG-UI agent. It delegates triage and fixes over A2A,
and it pauses for a person before close_issue, the one write (an MCP tool)."""
from typing import Annotated, TypedDict
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

LLM = None           # the notebook sets a real model; None means the scripted path
CALL_TRACKR = None   # async (tool_name, args) -> result: the MCP connection to Trackr
CALL_TRIAGE = None   # async (text) -> artifact text: the A2A call to triage-agent
CALL_FIX = None      # async (text) -> artifact text: the A2A call to fix-agent

SYSTEM = ("You are the Trackr ops desk. Use classify_issues for triage and propose_fix for a fix. "
          "When the person asks for both, ask for both in one reply. Once a fix has been proposed for an issue, "
          "call close_issue for that issue, alone in its reply. A request to close an issue is answered with the "
          "close_issue call, not with text. The desk pauses before it runs, and a person decides.")

async def issue_lines(ids: list[int]) -> str:
    rows = await CALL_TRACKR("search_issues", {"text": ""})
    by_id = {row["id"]: row["title"] for row in rows}
    return "\n".join(f"{i}: {by_id[i]}" for i in ids if i in by_id)

# %% [markdown]
# The three tools are the only calls the model can make. Two delegate over A2A, and one writes to Trackr over MCP.

# %%
%%writefile -a ../apps/22/orchestrator.py

@tool
async def classify_issues(issue_ids: list[int]) -> str:
    """Send open Trackr issues to triage-agent (A2A). It labels each one bug, feature or question. Use it for judgement."""
    return await CALL_TRIAGE(await issue_lines(issue_ids))

@tool
async def propose_fix(issue_id: int) -> str:
    """Ask fix-agent (A2A) to propose a fix for one open issue. It changes nothing in Trackr."""
    return await CALL_FIX(await issue_lines([issue_id]))

@tool
async def close_issue(issue_id: int) -> str:
    """Close one open Trackr issue (an MCP write). Only after a person has approved the change."""
    issue = await CALL_TRACKR("close_issue", {"issue_id": issue_id})
    return f"issue {issue['id']} is now {issue['status']}"

TOOLS = {t.name: t for t in (classify_issues, propose_fix, close_issue)}

# %% [markdown]
# The second part adds the graph. It reads the same tools, and it uses the gate. The file grows in four cells, each appended to the same file: the state, the model node, the gate with its two paths, and the routers with the graph.

# %%
%%writefile -a ../apps/22/orchestrator.py

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from ag_ui_langgraph import LangGraphAgent

class State(TypedDict):
    messages: Annotated[list, add_messages]

def last_human(state: State) -> str:
    return next(m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage))

def scripted_picks(state: State) -> list[dict]:
    """No-model stand-in: the same three picks the model is expected to make. Labelled in the output."""
    if "approved" in last_human(state) or any(isinstance(m, ToolMessage) for m in state["messages"]):
        return [{"name": "close_issue", "args": {"issue_id": 12}, "id": "scripted_close"}]
    return [{"name": "classify_issues", "args": {"issue_ids": [4, 9, 12, 15]}, "id": "scripted_triage"},
            {"name": "propose_fix", "args": {"issue_id": 12}, "id": "scripted_fix"}]

# %% [markdown]
# The model node asks the model which tools to call. Without a model it returns the scripted picks.

# %%
%%writefile -a ../apps/22/orchestrator.py

async def agent(state: State):
    if LLM is None:
        return {"messages": [AIMessage(content="", tool_calls=scripted_picks(state))]}
    reply = await LLM.bind_tools(list(TOOLS.values())).ainvoke([SystemMessage(SYSTEM), *state["messages"]])
    return {"messages": [reply]}                       # one model call per pass through this node

async def act(state: State):
    """Run the delegation tools the model chose. Each result becomes a ToolMessage."""
    out = []
    for call in state["messages"][-1].tool_calls:
        text = await TOOLS[call["name"]].ainvoke(call["args"])     # classify_issues or propose_fix
        out.append(ToolMessage(content=text, tool_call_id=call["id"]))
    return {"messages": out}

# %% [markdown]
# The gate is the approval step. It calls `interrupt()`, so the run pauses until a person resumes it.

# %%
%%writefile -a ../apps/22/orchestrator.py

def gate(state: State):
    call = state["messages"][-1].tool_calls[0]
    # Nothing before interrupt() may have side effects: on resume this node starts again from the top.
    decision = interrupt({"reason": "tool_call", "tool": call["name"], "args": call["args"],
                          "tool_call_id": call["id"], "message": f"Close issue {call['args']['issue_id']}?"})
    if isinstance(decision, dict) and decision.get("approve") is True:
        return {}
    # A cancelled resume arrives as a sentinel dict, so only an explicit approve counts as yes.
    return {"messages": [ToolMessage(content="cancelled by the person: close_issue did not run",
                                     tool_call_id=call["id"])]}

async def close(state: State):
    call = state["messages"][-1].tool_calls[0]
    return {"messages": [ToolMessage(content=await TOOLS["close_issue"].ainvoke(call["args"]),
                                     tool_call_id=call["id"])]}

def stop(state: State):   # app text, not model text: the person cancelled
    return {"messages": [AIMessage(content="Cancelled: the issue stays open.")]}

# %% [markdown]
# The routers pick the next node. `build_graph` wires the nodes and the checkpointer.

# %%
%%writefile -a ../apps/22/orchestrator.py

def route_after_agent(state: State):
    calls = state["messages"][-1].tool_calls
    if not calls:
        return END
    return "gate" if any(c["name"] == "close_issue" for c in calls) else "act"

def route_after_gate(state: State):
    return "stop" if isinstance(state["messages"][-1], ToolMessage) else "close"

def build_graph():
    g = StateGraph(State)
    for name, fn in [("agent", agent), ("act", act), ("gate", gate), ("close", close), ("stop", stop)]:
        g.add_node(name, fn)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_after_agent, ["act", "gate", END])
    g.add_edge("act", "agent")                       # the model reads the delegated answers, then decides again
    g.add_conditional_edges("gate", route_after_gate, ["close", "stop"])
    g.add_edge("close", END)                         # the close result is the answer: no extra model call
    g.add_edge("stop", END)
    return g.compile(checkpointer=MemorySaver())     # paused state is kept per thread id

def make_agent() -> LangGraphAgent:
    return LangGraphAgent(name="trackr-ops", graph=build_graph(), emit_interrupt_outcome=True)

# %% [markdown]
# ### 5. Wire the orchestrator and serve its AG-UI endpoint
# The notebook gives the orchestrator three functions. One calls Trackr over MCP. The other two call the A2A clients. Then it serves the app on the AG-UI port and waits for the health route.

# %%
import orchestrator
from fastapi import FastAPI
from ag_ui_langgraph import add_langgraph_fastapi_endpoint

async def call_trackr(name: str, args: dict):
    reply = await trackr.call_tool(name, args)
    if reply.is_error:
        raise RuntimeError(reply.content[0].text)
    return reply.structured_content.get("result", reply.structured_content)   # an Issue is not wrapped

async def triage_text(text: str) -> str:
    return await ask_agent(triage_client, text)

async def fix_text(text: str) -> str:
    return await ask_agent(fix_client, text)

orchestrator.CALL_TRACKR, orchestrator.CALL_TRIAGE, orchestrator.CALL_FIX = call_trackr, triage_text, fix_text
app = FastAPI()
add_langgraph_fastapi_endpoint(app, orchestrator.make_agent(), "/agent")
endpoint = await Server(app, AGUI_PORT, "/agent/health").start()
print("endpoint up:", endpoint.url + "/agent", "| routes:", [r.path for r in app.routes if r.path.startswith("/agent")])

# %% [markdown]
# ### 6. The model (`needs-llm`)
# Five model calls in this lesson, planned before the run. Thread A: the orchestrator picks the two tools (call 1), triage-agent classifies (call 2), fix-agent proposes (call 3), and the orchestrator picks `close_issue` after reading both answers (call 4). Thread B: the orchestrator picks `close_issue` (call 5). The cancel and the approve run no further model calls. The model is shared by all three agents.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm_replay.start("22_checkpoint-build-a2a-delegation")   # first: record or replay this notebook's model calls
llm = get_llm()                                # Gemini by default; the notebook budget is 5 calls
batch_triage_agent.LLM = fix_agent.LLM = orchestrator.LLM = llm
print("model set for the orchestrator, triage-agent and fix-agent")

# %% [markdown]
# If the model cell was skipped, each agent keeps its scripted path. The labels and proposals come from fixed rules, and the output says so.

# %%
if orchestrator.LLM is None:
    print("no model here: all three agents use the scripted path (outputs say 'scripted' or 'no model')")
else:
    print("model active: the orchestrator, triage-agent and fix-agent all call the model")

# %% [markdown]
# ### 7. An AG-UI client that reads the stream and the pause
# The client is plain `httpx`, as in lessons 10 and 19. `run_agui` sends one run. A question starts a run. A resume sends a `resume` list. `show` prints the tool calls, their results and the pause.

# %%
async def run_agui(thread_id: str, run_id: str, question: str | None = None, resume: list | None = None):
    messages = [] if question is None else [{"id": "u-" + run_id, "role": "user", "content": question}]
    payload = {"threadId": thread_id, "runId": run_id, "state": {}, "tools": [], "context": [],
               "forwardedProps": {}, "messages": messages}
    if resume is not None:
        payload["resume"] = resume
    events = []
    async with httpx.AsyncClient(transport=SocketTransport(), timeout=180) as http:
        async with http.stream("POST", endpoint.url + "/agent", json=payload,
                               headers={"Accept": "text/event-stream"}) as reply:
            async for line in reply.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: "):]))
    return events

# %% [markdown]
# These helpers read the stream. The final `MESSAGES_SNAPSHOT` is the complete record of the run.

# %%
def paused_on(events: list) -> list:
    finished = [e for e in events if e["type"] == "RUN_FINISHED"]
    return (finished[-1].get("outcome") or {}).get("interrupts", []) if finished else []

def final_messages(events: list) -> list:
    """The last MESSAGES_SNAPSHOT holds the whole conversation: tool results and the final text."""
    snaps = [e for e in events if e["type"] == "MESSAGES_SNAPSHOT"]
    return snaps[-1]["messages"] if snaps else []

def show(events: list) -> None:
    for m in final_messages(events):
        if m["role"] == "tool":
            print("  tool result ->", str(m.get("content")).replace("\n", " | ")[:110])
        elif m["role"] == "assistant" and m.get("content"):
            print("[answer]", m["content"])
    for e in events:
        if e["type"] == "RUN_ERROR":
            print("!! run error:", e.get("message"))
        if e["type"] == "RUN_FINISHED":
            ids = paused_on([e])
            print(f"== paused for a person: {ids[0]['message']}" if ids else "== run finished")

async def open_ids() -> list[int]:
    return [r["id"] for r in (await trackr.call_tool("search_issues", {"text": ""})).structured_content["result"]]

# %% [markdown]
# ### 8. Run A: triage and a fix proposal, then the pause
# Thread A asks for triage of four issues, a fix for issue 12 (the newest critical one), and then a close. Step 1 printed the open critical issues. Issue 12 has the highest id of them, which is what 'newest' means here, because Trackr keeps no dates. The run stops before `close_issue` runs. The printed trace shows the two delegations and the pause.

# %%
QUESTION_A = ("Triage open issues 4, 9, 12 and 15. Propose a fix for issue 12, the newest critical issue. "
              "When both answers are back, call the close_issue tool for issue 12 as your next step, "
              "so a person can approve it. Do not reply with text instead of that tool call: "
              "the desk pauses at that call.")
events_a = await run_agui("t-a", "run-a1", question=QUESTION_A)
show(events_a)
paused_a = paused_on(events_a)
open_after_a = 12 in await open_ids()        # read now: later steps change Trackr
print("open after run A:", open_after_a, "(True means issue 12 is still open)")

# %% [markdown]
# ### 9. Cancel: resume thread A with `cancelled`
# The person says no. The same thread resumes with `cancelled`. The gate writes a cancelled result, and the run ends with the app's text. No model call is made.

# %%
events_cancel = await run_agui("t-a", "run-a2",
                               resume=[{"interruptId": paused_a[0]["id"], "status": "cancelled"}])
show(events_cancel)
open_after_cancel = 12 in await open_ids()   # read now, before the approve closes it
print("issue 12 still open after the cancel:", open_after_cancel)

# %% [markdown]
# ### 10. Approve: a new thread closes issue 12
# A new thread asks for the close. The model picks `close_issue` (call 5), and the gate pauses again. The approve resume runs the write. The close result is the answer, so the run ends.

# %%
events_b1 = await run_agui("t-b", "run-b1", question="The fix for issue 12 is approved. Close issue 12.")
paused_b = paused_on(events_b1)
show(events_b1)
events_b2 = await run_agui("t-b", "run-b2",
                           resume=[{"interruptId": paused_b[0]["id"], "status": "resolved", "payload": {"approve": True}}])
show(events_b2)
print("issue 12 open after the approve:", 12 in await open_ids(), "(False means it was closed)")

# %% [markdown]
# ### 11. Ship check: every requirement, ticked
# Each line checks one requirement from the list at the top. The checks read the streams and Trackr, not the model's words.

# %%
open_at_end = 12 in await open_ids()        # True would mean the approve did not close issue 12
results = [str(m.get("content")) for m in final_messages(events_a) if m["role"] == "tool"]
triage_out = next((r for r in results if "15:" in r), "")
checks = {
    "R1": triage_card.name == "triage-agent" and fix_card.name == "fix-agent"
          and len(triage_out.splitlines()) == 4,
    "R2": len(results) >= 2 and open_after_a,
    "R3": bool(paused_a) and paused_a[0].get("message") == "Close issue 12?",
    "R4": open_after_cancel and any("Cancelled" in str(m.get("content")) for m in final_messages(events_cancel)),
    "R5": not open_at_end and not paused_on(events_b2),
    "R6": llm_replay.calls() <= 5,
}
for name, ok in checks.items():
    print(name, "PASS" if ok else "FAIL")

# %% [markdown]
# ### 12. Stop everything and save the recording
# Stop the endpoint and the two agents, close the Trackr connection, and save the recording if a model ran.

# %%
await endpoint.stop()
await triage_server.stop()
await fix_server.stop()
await triage_client.close()
await fix_client.close()
await held.close()
llm_replay.stop()
print("lesson 22 done: MCP for data and the write, A2A for two agents, AG-UI for the person")

# %% [markdown]
# ## At work
# - Production desks put every write behind an approval step and record who approved it. The endpoint that carries the approval needs its own security → lesson 31b.
# - A delegate agent from another team is trusted only after its signed card checks out. Until then the orchestrator should not call it → lesson 37.
# - The paused thread here lives in memory and is lost on restart. Real approvals outlive the process, so the state goes into a database → lesson 32.
# - One request crosses AG-UI, A2A and MCP. One trace id across the three is how the team finds the hop that failed → lesson 28.

# %% [markdown]
# ## Reference solution
# The checks above print the results to match. Expected output, in order:
# - R1 to R6: each prints PASS. The triage artifact has four lines, one per id.
# - The first run stops on `Close issue 12?`, and issue 12 is still open.
# - The cancel run prints the app's cancelled text, and issue 12 is still open.
# - The approve run closes issue 12, and the final run has no interrupt.
#
# The hidden cell below states the same expectations as asserts. A wrong result stops the notebook here.

# %% tags=["solution"]
assert all(checks.values()), checks
assert paused_a[0].get("message") == "Close issue 12?"
assert open_after_a and open_after_cancel, "issue 12 must stay open until the approve"
assert not open_at_end, "the approve closes issue 12"
print("reference checks hold: all six requirements")

# %% [markdown]
# ## Key terms
# - **checkpoint (build)** — a lesson that joins the part's pieces into one working system and checks each requirement with a printed PASS or FAIL.
# - **delegation tool** — a tool in the orchestrator's list whose code hands a task to another agent over A2A and returns the artifact as the tool result.
# - **approval gate** — the node in front of a write that calls `interrupt()`, so the run pauses until a person resumes it.
# - **resume entry** — the item the client sends to answer a pause: the interrupt id, `resolved` with a payload or `cancelled`.
