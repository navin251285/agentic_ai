# %% [markdown]
# # 19 · Human approval over AG-UI: interrupts and resume
# Level L3 · Part 4 · professional · ~35 min · builds on 10, 18

# %% [markdown]
# ## Goal
# By the end you have an AG-UI endpoint whose agent stops before `close_issue`. The run ends with `RUN_FINISHED` and an **interrupt** outcome. Approving resumes the same thread and closes issue 9. Cancelling on a second thread leaves issue 17 open. You can say what the client sends to resume, and why a 200 status and a `RUN_FINISHED` event do not, on their own, mean the job is done.

# %% [markdown]
# ## Why it matters
# Without a pause, the agent runs `close_issue` the moment the model picks it. A person can only see the result afterwards. The cell below shows that loop. It writes out the call by hand, shaped like a model's choice, so no model runs here. One write happens before anyone can say no.

# %%
import sys, json
from pathlib import Path
sys.path.insert(0, "..")                       # so llm_setup and llm_replay import
TRACKR = Path("../apps/03/trackr_server.py").resolve()
assert TRACKR.exists(), "run lesson 03 first: it writes the Trackr server"
Path("../apps/19").mkdir(parents=True, exist_ok=True)   # the agent module goes here
sys.path.insert(0, str(Path("../apps/19").resolve()))
PORT = 8191                                    # fixed localhost port for this lesson (8190-8199)
QUESTION = "Close issue 9, the pricing page typo is fixed."
SECOND_QUESTION = "Close issue 17, the profile page is fast now."
print("Trackr:", TRACKR.name, "| endpoint port", PORT)

# %% [markdown]
# Trackr is a subprocess, and its data lives in that process. The helper below keeps one MCP connection open across cells, as lesson 18 did. Trackr has no reopen tool, so each demo starts its own Trackr process. A closed issue stays closed in that process.

# %%
import asyncio
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

async def open_ids(client: Client) -> list[int]:
    reply = await client.call_tool("search_issues", {"text": ""})
    return [row["id"] for row in reply.structured_content["result"]]

TRACKR_PARAMS = StdioServerParameters(command=sys.executable, args=[str(TRACKR)])
print("helpers ready: a held Trackr connection and open_ids()")

# %% [markdown]
# The naive loop runs the write at once. Read the two printed lines: issue 9 is gone, and no person was asked.

# %%
naive = HeldClient()
naive_trackr = await naive.start(TRACKR_PARAMS)
print("open before:", 9 in await open_ids(naive_trackr))
call = {"name": "close_issue", "args": {"issue_id": 9}}   # a fixed call, shaped like a model's choice
await naive_trackr.call_tool(call["name"], call["args"])  # runs at once: no pause, no question
print("open after:", 9 in await open_ids(naive_trackr), "| writes before a person saw it: 1")
await naive.close()


# %% [markdown]
# ## The idea
# An approval is a **pause in the run**, not a question in the chat. The server ends the run early with `RUN_FINISHED`. Its outcome is `interrupt`, and it lists what the run waits for: an id, a reason and a message. The stream closes, and the agent's state is saved on the thread.
#
# The screen shows approve and cancel buttons. The client then starts a new run on the same `threadId`, with a `resume` list. The list needs one entry per open interrupt. Each entry is `resolved` (with a payload) or `cancelled`. The agent continues from its saved state.
#
# Analogy: a two-person rule for a bank transfer. The clerk fills in the form and it waits in a tray. Nobody holds the room open. The manager's signature sends it on, and the form carries the same reference number.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant U as Client (httpx)
#   participant E as /agent endpoint (LangGraph)
#   participant T as Trackr (MCP)
#   U->>E: POST run 1 (thread t-9)
#   E-->>U: RUN_STARTED
#   E->>E: model call 1 picks close_issue(9)
#   E-->>U: RUN_FINISHED, outcome interrupt, id int-...
#   Note over U: the person clicks Approve
#   U->>E: POST run 2 (thread t-9), resume resolved
#   E->>T: close_issue(9)
#   E-->>U: TOOL_CALL_RESULT, text, RUN_FINISHED success
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. The wire shapes: an interrupt out, a resume in
# No server and no model are needed for this step. The first cell builds the `RUN_FINISHED` event that pauses the run, and prints it as the frame the client receives. The second cell reads a resume body and checks it parses. Note the camelCase names on the wire and the snake_case attributes in Python.

# %%
from ag_ui.core import Interrupt, RunAgentInput, RunFinishedEvent, RunFinishedInterruptOutcome
from ag_ui.encoder import EventEncoder
enc = EventEncoder(accept="text/event-stream")
pause = RunFinishedEvent(thread_id="t-9", run_id="run-1",
    outcome=RunFinishedInterruptOutcome(type="interrupt", interrupts=[
        Interrupt(id="int-9", reason="tool_call", message="Close issue 9?", tool_call_id="call_1")]))
print(enc.encode(pause), end="")

# %% [markdown]
# The client's answer names the same thread and a new run. It also names the interrupt id from the pause. The next cell checks that the body parses.

# %%
resume_body = {"threadId": "t-9", "runId": "run-2", "state": {}, "tools": [], "context": [],
               "forwardedProps": {}, "messages": [],
               "resume": [{"interruptId": "int-9", "status": "resolved", "payload": {"approve": True}}]}
resumed = RunAgentInput.model_validate(resume_body)
print("same thread:", resumed.thread_id == pause.thread_id, "| new run:", resumed.run_id != pause.run_id,
      "| resume:", resumed.resume[0].interrupt_id, resumed.resume[0].status, resumed.resume[0].payload)

# %% [markdown]
# ### 2. The tool and the graph: the pause sits in front of the write
# The agent is a LangGraph graph. The model chooses `close_issue`, and a `gate` node calls `interrupt()` before the tool runs. The file below is the whole agent. Read the gate node: it is the only place a person can stop the write. `ag-ui-langgraph` turns the pause into the interrupt outcome, because `emit_interrupt_outcome=True`. The graph keeps the paused state per thread id, so a resume on the same thread continues it.


# %%
%%writefile ../apps/19/approval_agent.py
"""Lesson 19: a LangGraph agent that asks a person before it closes an issue.
The gate node calls interrupt(). ag-ui-langgraph turns that pause into RUN_FINISHED with an interrupt outcome."""
import re
from typing import Annotated, TypedDict
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from ag_ui_langgraph import LangGraphAgent

LLM = None           # the notebook sets a real model; None means the scripted path
CALL_TRACKR = None   # the notebook sets: async def (tool_name, args) -> dict (Trackr's result)

@tool
async def close_issue(issue_id: int) -> str:
    """Close one open Trackr issue by id. Only close an issue when the person asked for it."""
    issue = await CALL_TRACKR("close_issue", {"issue_id": issue_id})
    return f"issue {issue['id']} is now {issue['status']}"

class State(TypedDict):
    messages: Annotated[list, add_messages]

def last_human(state: State) -> str:
    return next(m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage))

async def agent(state: State):
    if LLM is None:   # scripted stand-in: the issue number from the question, labelled in the output
        issue = int(re.search(r"\d+", last_human(state)).group())
        call = {"name": "close_issue", "args": {"issue_id": issue}, "id": "scripted_1"}
        return {"messages": [AIMessage(content="", tool_calls=[call])]}
    return {"messages": [await LLM.bind_tools([close_issue]).ainvoke(state["messages"])]}   # model call

def gate(state: State):
    call = state["messages"][-1].tool_calls[0]
    # Nothing before interrupt() may have side effects: on resume this node starts again from the top.
    decision = interrupt({"reason": "tool_call", "tool": call["name"], "args": call["args"], "tool_call_id": call["id"],
                          "message": f"Close issue {call['args']['issue_id']}?"})
    if isinstance(decision, dict) and decision.get("approve") is True:
        return {}
    # A cancelled resume arrives as a sentinel dict, so only an explicit approve counts as yes.
    return {"messages": [ToolMessage(content="cancelled by the person: close_issue did not run",
                                     tool_call_id=call["id"])]}

async def close(state: State):
    call = state["messages"][-1].tool_calls[0]
    return {"messages": [ToolMessage(content=await close_issue.ainvoke(call["args"]), tool_call_id=call["id"])]}

async def answer(state: State):
    if LLM is None:
        return {"messages": [AIMessage(content="Issue closed. (scripted text, no model)")]}
    return {"messages": [await LLM.ainvoke(state["messages"])]}   # model call

def stop(state: State):   # app text, not model text: the person cancelled
    return {"messages": [AIMessage(content="Cancelled: the issue stays open.")]}

def route_after_agent(state: State):
    return "gate" if state["messages"][-1].tool_calls else END

def route_after_gate(state: State):
    return "stop" if isinstance(state["messages"][-1], ToolMessage) else "close"

def build_graph():
    g = StateGraph(State)
    for name, fn in [("agent", agent), ("gate", gate), ("close", close), ("answer", answer), ("stop", stop)]:
        g.add_node(name, fn)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_after_agent, ["gate", END])
    g.add_conditional_edges("gate", route_after_gate, ["close", "stop"])
    g.add_edge("close", "answer")
    g.add_edge("answer", END)
    g.add_edge("stop", END)
    return g.compile(checkpointer=MemorySaver())   # the paused state is kept per thread id

def make_agent() -> LangGraphAgent:
    # emit_interrupt_outcome=True: the pause is sent as RUN_FINISHED with outcome "interrupt"
    return LangGraphAgent(name="trackr-approval", graph=build_graph(), emit_interrupt_outcome=True)

# %% [markdown]
# ### 3. Start a fresh Trackr, the endpoint and the model
# The notebook sets two things on the module: the Trackr call that the tool uses, and the model. The endpoint is a FastAPI app with one route, `/agent`. It runs in this notebook's event loop, as lesson 18's agent did. The helper polls the health route until it answers.

# %%
import socket
import httpx, uvicorn
from fastapi import FastAPI
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
import approval_agent

held = HeldClient()
trackr = await held.start(TRACKR_PARAMS)      # a fresh Trackr: issues 9 and 17 are open again

async def call_trackr(name: str, args: dict):
    reply = await trackr.call_tool(name, args)
    if reply.is_error:
        raise RuntimeError(reply.content[0].text)
    return reply.structured_content.get("result", reply.structured_content)   # an Issue is not wrapped

approval_agent.CALL_TRACKR = call_trackr
app = FastAPI()
add_langgraph_fastapi_endpoint(app, approval_agent.make_agent(), "/agent")
print("agent wired: Trackr call set, endpoint routes:", [r.path for r in app.routes if r.path.startswith("/agent")])

# %% [markdown]
# The helper below serves the app in this notebook's loop and waits for the health route. Nothing in it is specific to approvals.

# %%
class EndpointServer:
    """One ASGI app served as a task of this notebook's event loop."""
    def __init__(self, app, port: int):
        self.port, self.url = port, f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    async def start(self, timeout: float = 15.0) -> "EndpointServer":
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", self.port)) != 0, f"port {self.port} is already in use"
        self.task = asyncio.create_task(self.server.serve())
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with httpx.AsyncClient(timeout=1) as http:
            while loop.time() < deadline:
                try:
                    if (await http.get(self.url + "/agent/health")).status_code == 200:
                        return self
                except httpx.TransportError:
                    pass                       # not up yet
                await asyncio.sleep(0.1)
        raise RuntimeError("the endpoint did not answer /agent/health in time")

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task

# %% [markdown]
# Start the endpoint on the port from step 1. The helper waits until the health route answers.

# %%
endpoint = await EndpointServer(app, PORT).start()
print("approval endpoint is up at", endpoint.url + "/agent")

# %% [markdown]
# The model is the course's default. The approval agent makes **three** model calls in this lesson. Run 1 picks `close_issue` (call 1). Approving run 2 writes the answer (call 2). Run 3 picks `close_issue` on the second thread (call 3). The cancel run makes no call after the resume. The recorder stops at a fourth call.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("19_ag-ui-human-approval", max_calls=3)
approval_agent.LLM = llm
print("model set for the approval agent")

# %% [markdown]
# If the model cell was skipped, the agent keeps the scripted path. The scripted path takes the issue number from the question, and its answer text says so.

# %%
if approval_agent.LLM is None:
    print("no model here: the agent keeps the scripted path (answers say 'no model')")

# %% [markdown]
# ### 4. A client that reads the stream and the pause
# The client is plain `httpx`, as in lesson 10. `stream_run` sends one run. A new question starts a run with a `question`. A resume sends an empty `messages` list and a `resume` list. `show` prints each event, including the interrupt that ends a paused run.

# %%
async def stream_run(thread_id: str, run_id: str, question: str | None = None, resume: list | None = None):
    messages = [] if question is None else [{"id": "u-" + run_id, "role": "user", "content": question}]
    payload = {"threadId": thread_id, "runId": run_id, "state": {}, "tools": [], "context": [],
               "forwardedProps": {}, "messages": messages}
    if resume is not None:
        payload["resume"] = resume
    events = []
    async with httpx.AsyncClient(timeout=120) as http:
        async with http.stream("POST", endpoint.url + "/agent", json=payload,
                               headers={"Accept": "text/event-stream"}) as reply:
            status = reply.status_code
            async for line in reply.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: "):]))
    return status, events

# %% [markdown]
# `show` prints the stream as a short live view. It skips the adapter's `RAW`, `STEP_*` and `STATE_SNAPSHOT` events. The answer comes from the final `MESSAGES_SNAPSHOT`, when the text was not streamed.

# %%
def show(events) -> None:
    streamed = any(e["type"] == "TEXT_MESSAGE_CONTENT" for e in events)
    for e in events:
        kind = e["type"]
        if kind == "RUN_STARTED": print("== run started")
        elif kind == "TOOL_CALL_START": print(f"[tool] {e['toolCallName']}", end="")
        elif kind == "TOOL_CALL_ARGS": print(" " + e["delta"], end="")
        elif kind == "TOOL_CALL_RESULT": print(" -> " + e["content"])
        elif kind == "TEXT_MESSAGE_CONTENT": print(e["delta"], end="", flush=True)
        elif kind == "MESSAGES_SNAPSHOT" and not streamed and e["messages"][-1]["role"] == "assistant" \
                and e["messages"][-1].get("content"):
            print(f"[answer] {e['messages'][-1]['content']}")
        elif kind == "RUN_ERROR": print(f"\n!! run error ({e['code']}): {e['message']}")
        elif kind == "RUN_FINISHED":
            ids = [i["id"] for i in (e.get("outcome") or {}).get("interrupts", [])]
            print(f"\n== run paused for a person: interrupts {ids}" if ids else "\n== run finished")

# %% [markdown]
# ### 5. Run 1: the agent stops before the write
# The client asks to close issue 9. The model picks `close_issue`, and the gate node pauses the run. The last event is `RUN_FINISHED` with an interrupt outcome. The stream closes there. Issue 9 is still open.

# %%
status, paused_events = await stream_run("t-9", "run-1", QUESTION)
print("HTTP status:", status)
show(paused_events)
last = paused_events[-1]
assert last["type"] == "RUN_FINISHED" and last["outcome"]["type"] == "interrupt", last
interrupt_id = last["outcome"]["interrupts"][0]["id"]
print("interrupt:", interrupt_id, "| reason:", last["outcome"]["interrupts"][0]["reason"])
print("issue 9 still open:", 9 in await open_ids(trackr))

# %% [markdown]
# ### 6. Run 2: approve on the same thread
# The screen sends a new run with the same `threadId`, a new `runId` and one `resume` entry. The entry names the interrupt id from run 1. Its status is `resolved`, with the payload the gate reads. The agent continues, closes issue 9, and writes the answer (model call 2).

# %%
status, approved_events = await stream_run("t-9", "run-2", resume=[
    {"interruptId": interrupt_id, "status": "resolved", "payload": {"approve": True}}])
show(approved_events)
assert approved_events[-1]["type"] == "RUN_FINISHED"
print("issue 9 open after approval:", 9 in await open_ids(trackr))

# %% [markdown]
# ### 7. Replay the same approval
# A client that loses its connection may send the same resume again. The spec says a resume must be safe to replay. Send the same body with a new `runId`. Read the counts: if the replay added no messages to the thread, the write did not run twice.

# %%
status, replay_events = await stream_run("t-9", "run-3", resume=[
    {"interruptId": interrupt_id, "status": "resolved", "payload": {"approve": True}}])
def thread_size(events) -> int:   # messages on the thread, from its last snapshot
    return next(len(e["messages"]) for e in reversed(events) if e["type"] == "MESSAGES_SNAPSHOT")
before, after = thread_size(approved_events), thread_size(replay_events)
print("last event:", replay_events[-1]["type"], "| issue 9 open:", 9 in await open_ids(trackr),
      "| thread messages before and after the replay:", before, after)

# %% [markdown]
# ### 8. Cancel on a second thread
# Now a different question on thread `t-17`. The agent pauses again (model call 3). The client answers `cancelled`. A cancelled entry has no payload. The gate does not run the write, and the stop node writes a line of app text, not model text. Issue 17 stays open.

# %%
status, paused_17 = await stream_run("t-17", "run-4", SECOND_QUESTION)
show(paused_17)
assert paused_17[-1]["outcome"]["type"] == "interrupt", paused_17[-1]
interrupt_17 = paused_17[-1]["outcome"]["interrupts"][0]["id"]

# %% [markdown]
# The client answers on the same thread, with the `cancelled` status and no payload.

# %%
status, cancelled_events = await stream_run("t-17", "run-5", resume=[
    {"interruptId": interrupt_17, "status": "cancelled"}])
show(cancelled_events)
print("issue 17 still open:", 17 in await open_ids(trackr))

# %% [markdown]
# ## At work
# - Production copilots pause before a write that cannot be undone, such as a close, a refund or a delete. The pause is stored with the thread, not held open on a connection. A restart must not lose it, so the state store has to be durable → lesson 32.
# - A resumed run can be sent twice, after a dropped connection or a double click. The write must still happen once. Production systems give each write a key, so a repeat is a no-op → lesson 23a.
# - The approval arrives from the client, so the server must check who approved and what was approved before it resumes the run → lesson 31b.
# - A2A agents use the same idea when they need input: the task stops in an input-required state and the caller answers the same task → lesson 09.

# %% [markdown]
# ## What just happened
# - The model chose `close_issue`, and the gate node stopped the run before the tool ran. The run ended with `RUN_FINISHED` and the interrupt outcome, and the stream closed.
# - Approving sent a new run on the same thread, with a resolved entry for the same interrupt id. The gate returned the payload, and the tool ran once.
# - Cancelling sent a cancelled entry. The gate wrote a tool message saying the call did not run, and the stop node wrote the closing line. Issue 17 stayed open.
# - The model made three calls: one for each choice, and one to write the answer after the approval. The cancel run made none after the resume.

# %% [markdown]
# ## Common mistakes
# **Reading `RUN_FINISHED` as "the job is done".** A paused run also ends with `RUN_FINISHED`. The check below passes for run 1, although issue 9 is still open:

# %%
assert paused_events[-1]["type"] == "RUN_FINISHED"       # the wrong check: passes
print("wrong check passed: the paused run also ends with RUN_FINISHED")

# %% [markdown]
# The right check reads the outcome. A run is done only when the outcome is `success`. An `interrupt` means the run waits for a person. The function below raises for the paused run:

# %% tags=["raises-exception"]
def require_done(events: list[dict]) -> str:
    last = events[-1]
    if last["type"] != "RUN_FINISHED":
        raise RuntimeError(f"run failed: last event is {last['type']}")
    outcome = last.get("outcome") or {}
    if outcome.get("type") == "interrupt":
        raise RuntimeError(f"waiting for a person: {outcome['interrupts'][0]['id']}")
    return "run finished"

require_done(paused_events)      # run 1: RUN_FINISHED, but a person must answer first

# %% [markdown]
# Fix: call the check on the events of the approved run. It returns, because that run finished.

# %%
print(require_done(approved_events))

# %% [markdown]
# **Sending a resume with an id the thread does not hold.** The server does not refuse it. The run ends with `RUN_FINISHED`, and nothing ran. The cell sends an approval for `int-wrong` on thread `t-9`, which has no open interrupt:

# %%
status, wrong_events = await stream_run("t-9", "run-8", resume=[
    {"interruptId": "int-wrong", "status": "resolved", "payload": {"approve": True}}])
print("last event:", wrong_events[-1]["type"], "| messages on the thread:", thread_size(wrong_events))

# %% [markdown]
# The check below reads the thread. A resume that ran adds messages to it. This one adds none, so it raises:

# %% tags=["raises-exception"]
def require_new_messages(before: list[dict], after: list[dict]) -> None:
    if thread_size(after) == thread_size(before):
        raise RuntimeError("the resume matched no open interrupt: the run finished, and nothing ran")

require_new_messages(approved_events, wrong_events)

# %% [markdown]
# Fix: take the interrupt id from the paused run's `RUN_FINISHED` and send exactly that id. Check the events of the run you resume, not only the status.

# %% [markdown]
# ## Try it
# Build the resume body that cancels interrupt `int-17` on thread `t-17`, for run `run-9`. Validate it with `RunAgentInput.model_validate` and print the interrupt id, the status and the payload. No server and no model are needed.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
body = {"threadId": "t-17", "runId": "run-9", "messages": [], "state": {}, "tools": [], "context": [],
        "forwardedProps": {}, "resume": [{"interruptId": "int-17", "status": "cancelled"}]}
parsed = RunAgentInput.model_validate(body)
print(parsed.resume[0].interrupt_id, parsed.resume[0].status, parsed.resume[0].payload)

# %% [markdown]
# ## Key terms
# - **interrupt outcome** — the `RUN_FINISHED` outcome `interrupt`: the run stopped, and it lists the interrupts a person must answer.
# - **interrupt** — one open question in that outcome, with an id, a reason and a message. The id is what a resume must name.
# - **resume entry** — one `resume` item in the next `RunAgentInput`: an interrupt id, a status (`resolved` or `cancelled`) and an optional payload.
# - **resume on the same thread** — the next run uses the same `threadId` and a new `runId`. The saved state of the paused run is what continues.
# - **emit_interrupt_outcome** — the `LangGraphAgent` option that sends a LangGraph pause as the interrupt outcome instead of a plain finish.

# %% [markdown]
# Stop the endpoint and Trackr. Then tell the recorder the lesson is done.

# %%
import llm_replay
await endpoint.stop()
await held.close()           # closes the Trackr connection and stops the subprocess
llm_replay.stop()            # saves the recording if a model ran; a no-op otherwise
print("lesson 19 done: a pause is a finished run with an interrupt; a resume continues the same thread")

