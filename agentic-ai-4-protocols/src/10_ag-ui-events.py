# %% [markdown]
# # 10 · AG-UI: streaming an agent to the user's screen
# Level L2 · Part 2 · core · ~35 min · builds on 05

# %% [markdown]
# ## Goal
# By the end you have a `/agent` endpoint that streams one real model run as AG-UI events, and a client that prints them as a live terminal view: a `count_open` tool call, then the answer. You can name the events in their order and say why the stream ends with `RUN_FINISHED` or `RUN_ERROR`.

# %% [markdown]
# ## The idea
# A chat screen cannot wait for a whole answer. AG-UI is the protocol between the agent's server and the user's screen. The client POSTs one `RunAgentInput`: a thread id, a run id and the messages. The server replies with a stream of **events**, one `data:` line each (HTTP with Server-Sent Events, SSE: the server keeps one response open and sends `data:` lines). Each event has a type, such as `RUN_STARTED`, and related events share an id, so the screen knows which text or tool call each one belongs to.
#
# AG-UI says what happened and in what order. It does not say how the screen looks. A run has no rewind: if the connection drops, the client starts a new run.
#
# Analogy: a live sports feed. Each message says what just happened, and the scoreboard is drawn from them. If the feed drops, you do not resume mid-match. You read the next match.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant U as Client (httpx)
#   participant E as /agent endpoint
#   participant M as Model
#   participant T as Trackr (MCP)
#   U->>E: POST RunAgentInput
#   E-->>U: RUN_STARTED
#   E->>M: which tool? (model call 1)
#   M-->>E: tool call count_open(team)
#   E-->>U: TOOL_CALL_START, ARGS, END
#   E->>T: count_open(team)
#   T-->>E: 3
#   E-->>U: TOOL_CALL_RESULT
#   E->>M: write the answer (model call 2, streamed)
#   M-->>E: text chunks
#   E-->>U: TEXT_MESSAGE_START, CONTENT..., END
#   E-->>U: RUN_FINISHED
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set up the example
# The running example is Trackr's chat: a person asks how many issues a team has open. Trackr is the lesson 03 server, still in `../apps/03`. The first cell sets the paths, the port and the question. It also imports `llm_replay`, so the last cell can always stop the recorder.

# %%
import sys, json
from pathlib import Path
sys.path.insert(0, "..")                       # so llm_setup and llm_replay import
import llm_replay
Path("../apps/10").mkdir(parents=True, exist_ok=True)   # the endpoint file goes here
sys.path.insert(0, str(Path("../apps/10").resolve()))
TRACKR = Path("../apps/03/trackr_server.py").resolve()
assert TRACKR.exists(), "run lesson 03 first: it writes the Trackr server"
PORT = 9110                                    # fixed localhost port for this lesson
QUESTION = "How many open issues does the web team have?"
print("Trackr:", TRACKR.name, "| endpoint port", PORT)

# %% [markdown]
# ### 2. The request: one RunAgentInput
# The client sends a `RunAgentInput`. On the wire its fields are camelCase: `threadId`, `runId`, `messages`, `state`, `tools`, `context` and `forwardedProps`. The SDK model reads them and gives you snake_case attributes. The cell below builds the body and checks it parses.

# %%
from ag_ui.core import RunAgentInput
body = {
    "threadId": "thread-1", "runId": "run-1",
    "messages": [{"id": "u1", "role": "user", "content": QUESTION}],
    "state": {}, "tools": [], "context": [], "forwardedProps": {},
}
run_input = RunAgentInput.model_validate(body)
print(run_input.thread_id, run_input.run_id, "|", run_input.messages[0].role, "|", run_input.messages[0].content)

# %% [markdown]
# ### 3. Events on the wire: one `data:` line each
# The server does not send one JSON answer. It sends events in order. `EventEncoder` turns each event into one Server-Sent Events frame: the text `data:` followed by the event's JSON and a blank line. The cell below encodes a tiny run with no model. Read the order: start, text, end, finish.

# %%
from ag_ui.core import (RunStartedEvent, TextMessageStartEvent, TextMessageContentEvent,
                        TextMessageEndEvent, RunFinishedEvent, RunFinishedSuccessOutcome)
from ag_ui.encoder import EventEncoder
enc = EventEncoder(accept="text/event-stream")
print("content type:", enc.get_content_type())
tiny_run = [
    RunStartedEvent(thread_id="thread-1", run_id="run-1"),
    TextMessageStartEvent(message_id="m1", role="assistant"),
    TextMessageContentEvent(message_id="m1", delta="Hello"),
    TextMessageEndEvent(message_id="m1"),
    RunFinishedEvent(thread_id="thread-1", run_id="run-1", outcome=RunFinishedSuccessOutcome(type="success")),
]
for event in tiny_run:
    print(enc.encode(event), end="")

# %% [markdown]
# The text of one message is split into events that share a `messageId`: one start, any number of content deltas, one end. The same idea applies to tool calls, which share a `toolCallId`. The cell below groups the events by `messageId`.

# %%
from collections import defaultdict
by_message = defaultdict(list)
for e in tiny_run:
    if hasattr(e, "message_id"):
        by_message[e.message_id].append(e.type.value)
print(dict(by_message))

# %% [markdown]
# ### 4. Write the endpoint
# The endpoint is a FastAPI app in `../apps/10/agui_app.py`. Read it top to bottom once. `run_events` is an async generator: each `yield` sends one event to the client as soon as it exists. The model call and the Trackr tool call happen between the events. If something fails after the stream has started, the generator sends `RUN_ERROR` instead of raising. The module has three settings that the notebook sets: the Trackr config, the model and a switch that forces a failure.

# %%
%%writefile ../apps/10/agui_app.py
"""Lesson 10: the Trackr AG-UI endpoint. POST /agent reads RunAgentInput and streams AG-UI events over SSE."""
import json, uuid, warnings
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)   # the beta notice is noise here
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain.mcp import MCPAdapter
from langchain_core.messages import AIMessage, HumanMessage
from ag_ui.core import (RunAgentInput, RunStartedEvent, RunFinishedEvent, RunErrorEvent,
    RunFinishedSuccessOutcome, TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent,
    ToolCallStartEvent, ToolCallArgsEvent, ToolCallEndEvent, ToolCallResultEvent)
from ag_ui.encoder import EventEncoder

TRACKR_CONFIG = {}   # the notebook sets {"mcpServers": {"trackr": {...}}}
LLM = None           # the notebook sets a real model; None means the scripted path
FAIL = False         # the notebook sets True to show RUN_ERROR
ENC = EventEncoder(accept="text/event-stream")
TEAMS = ("web", "api", "mobile", "infra")

def scripted_team(text: str) -> str:
    return next((t for t in TEAMS if t in text.lower()), "web")

async def answer_deltas(messages, team: str, count: str):
    """The answer, in pieces. The scripted path splits a fixed sentence; the model streams its own chunks."""
    if LLM is None:
        for word in f"The {team} team has {count} open issues.".split(" "):
            yield word + " "
        return
    async for chunk in LLM.astream(messages):          # model call 2
        if chunk.text:
            yield chunk.text

async def run_events(inp: RunAgentInput):
    yield ENC.encode(RunStartedEvent(thread_id=inp.thread_id, run_id=inp.run_id))
    try:
        if FAIL:
            raise RuntimeError("the model host did not answer (set on purpose)")
        question = inp.messages[-1].content
        async with MCPAdapter(TRACKR_CONFIG) as adapter:
            by_name = {t.name: t for t in await adapter.list_tools()}
            if LLM is None:
                ai = AIMessage(content="", tool_calls=[{"name": "count_open", "id": "call_1",
                               "args": {"team": scripted_team(question)}}])
            else:
                ai = await LLM.bind_tools(list(by_name.values())).ainvoke([HumanMessage(question)])  # model call 1
            messages, team, count = [HumanMessage(question), ai], "web", "?"
            for call in ai.tool_calls:
                yield ENC.encode(ToolCallStartEvent(tool_call_id=call["id"], tool_call_name=call["name"]))
                yield ENC.encode(ToolCallArgsEvent(tool_call_id=call["id"], delta=json.dumps(call["args"])))
                yield ENC.encode(ToolCallEndEvent(tool_call_id=call["id"]))
                result = await by_name[call["name"]].ainvoke(call)      # the real Trackr server runs here
                messages.append(result)
                team, count = call["args"]["team"], result.text      # the tool's text, e.g. "3"
                yield ENC.encode(ToolCallResultEvent(message_id=str(uuid.uuid4()), tool_call_id=call["id"], content=count))
            msg_id = str(uuid.uuid4())
            yield ENC.encode(TextMessageStartEvent(message_id=msg_id, role="assistant"))
            async for delta in answer_deltas(messages, team, count):
                yield ENC.encode(TextMessageContentEvent(message_id=msg_id, delta=delta))
            yield ENC.encode(TextMessageEndEvent(message_id=msg_id))
        yield ENC.encode(RunFinishedEvent(thread_id=inp.thread_id, run_id=inp.run_id,
                                          outcome=RunFinishedSuccessOutcome(type="success")))
    except Exception as exc:       # the status is already 200, so the failure travels as an event
        yield ENC.encode(RunErrorEvent(message=str(exc), code="run_failed"))

app = FastAPI()

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/agent")
async def agent(inp: RunAgentInput):
    return StreamingResponse(run_events(inp), media_type=ENC.get_content_type(),
                             headers={"X-Accel-Buffering": "no"})   # tells nginx not to hold the stream

# %% [markdown]
# The cell above saved the file. The next cell imports the endpoint and gives it the Trackr config. The endpoint starts Trackr as a subprocess for each run, so the tool call is real even when no model is set.

# %%
import socket, threading, time
import httpx, uvicorn
import agui_app
agui_app.TRACKR_CONFIG = {"mcpServers": {"trackr": {"command": sys.executable, "args": [str(TRACKR)]}}}
print("endpoint module loaded | model set:", agui_app.LLM is not None)

# %% [markdown]
# ### 5. Start the endpoint and poll its health
# The endpoint runs in a thread of this notebook, so a model set in this process is used by the endpoint. The helper polls `/health` until the server answers, instead of sleeping for a fixed time. The port check comes first, so a stale server fails clearly.

# %%
class ServerThread:
    """One ASGI app in a thread of this notebook (the model calls stay in this process)."""
    def __init__(self, app, port: int):
        self.url = f"http://127.0.0.1:{port}"
        self.port = port
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self, timeout: float = 15.0) -> "ServerThread":
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", self.port)) != 0, f"port {self.port} is already in use"
        self.thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if httpx.get(self.url + "/health", timeout=1).status_code == 200:
                    return self
            except httpx.TransportError:
                pass                              # not up yet
            time.sleep(0.1)
        raise RuntimeError("the endpoint did not answer /health in time")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

# %% [markdown]
# The class is in place. The next cell starts the endpoint with it, on the port from step 1.

# %%
endpoint = ServerThread(agui_app.app, PORT).start()
print("AG-UI endpoint is up at", endpoint.url + "/agent")

# %% [markdown]
# ### 6. A terminal client reads the stream
# The client is plain `httpx`. It POSTs the body, reads the `data:` lines as they arrive and parses each JSON. It does not import the SDK, so it could be written in any language. `stream_run` returns the HTTP status and the list of events. `show` prints them as a small live view: the tool call, then the answer as it streams.

# %%
async def stream_run(question: str, run_id: str):
    payload = {"threadId": "thread-1", "runId": run_id, "state": {}, "tools": [], "context": [],
               "forwardedProps": {}, "messages": [{"id": "u-" + run_id, "role": "user", "content": question}]}
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
# The helper below prints the events as the live view. It handles each event type the endpoint sends.

# %%
def show(events) -> None:
    for e in events:
        kind = e["type"]
        if kind == "RUN_STARTED":
            print("== run started")
        elif kind == "TOOL_CALL_START":
            print(f"[tool] {e['toolCallName']}", end="")
        elif kind == "TOOL_CALL_ARGS":
            print(" " + e["delta"], end="")
        elif kind == "TOOL_CALL_RESULT":
            print(" -> " + e["content"])
        elif kind == "TEXT_MESSAGE_CONTENT":
            print(e["delta"], end="", flush=True)
        elif kind == "RUN_ERROR":
            print(f"\n!! run error ({e['code']}): {e['message']}")
        elif kind == "RUN_FINISHED":
            print("\n== run finished")

# %% [markdown]
# ### 7. One run with the scripted path (no model)
# This run needs no key. With no model set, the endpoint asks Trackr for `count_open` with the team it finds in the question, and writes a fixed sentence. The tool call is real, so the events show a real result. The printed line says `answered by: scripted`, so you know no model wrote the answer.

# %%
status, events = await stream_run(QUESTION, "run-1")
print("HTTP status:", status, "| answered by:", "model" if agui_app.LLM is not None else "scripted")
show(events)
types = [e["type"] for e in events]
assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED", types
assert types.index("TOOL_CALL_START") < types.index("TEXT_MESSAGE_START")

# %% [markdown]
# ### 8. Give the endpoint a real model (`needs-llm`)
# This cell gets the course's default model and sets it on the endpoint. `get_llm` starts the recording, or the replay, for this lesson. A run makes two model calls: the first chooses the tool from Trackr's tool list, the second streams the answer. The budget is two calls. If the cell is skipped, the endpoint keeps the scripted path and the next cells still run.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("10_ag-ui-events", max_calls=2)
agui_app.LLM = llm
print("model set for the AG-UI endpoint")

# %% [markdown]
# If the model cell was skipped, the endpoint keeps the scripted path, and the next cells still run.

# %%
if agui_app.LLM is None:
    print("no model here: the endpoint keeps the scripted path (answered by 'scripted')")

# %% [markdown]
# ### 9. The same question, answered by the model
# The client code is unchanged. Only the endpoint's source of words changed. Read the tool events first: the tool name and its arguments came from the model's choice. Then the text arrives in pieces, as the model streams it.

# %%
status, events = await stream_run(QUESTION, "run-2")
print("HTTP status:", status, "| answered by:", "model" if agui_app.LLM is not None else "scripted")
show(events)
types = [e["type"] for e in events]
assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED", types

# %% [markdown]
# ### 10. Failures: a 200 can still end in RUN_ERROR
# Once the stream has started, the status code is already 200. It cannot change to 500. So a failure during the run is sent as a `RUN_ERROR` event, and the client must read the last event. The switch below forces a failure before the model is called, then turns it off again.

# %%
agui_app.FAIL = True
try:
    status, events = await stream_run(QUESTION, "run-3")
finally:
    agui_app.FAIL = False
print("HTTP status:", status, "| last event:", events[-1]["type"], "|", events[-1]["message"])
assert status == 200 and events[-1]["type"] == "RUN_ERROR"
failed_status, failed_events = status, events   # kept for the common mistakes below

# %% [markdown]
# A request that is wrong before the stream starts gets a normal HTTP error instead. Here `messages` is missing. FastAPI rejects the body with `422`, and no event is sent at all.

# %%
bad = {"threadId": "thread-4", "runId": "run-4", "state": {}, "tools": [], "context": [], "forwardedProps": {}}
reply = httpx.post(endpoint.url + "/agent", json=bad, headers={"Accept": "text/event-stream"})
print("status:", reply.status_code, "| body mentions:", "messages" in reply.text)

# %% [markdown]
# ## At work
# - Production chat UIs (CopilotKit-style front ends, Slack and Teams bots) draw tool cards and text as the events arrive, rather than waiting for the whole answer. Keep the stream free of proxy buffering, or users see nothing until the end → lesson 32.
# - AG-UI has no resumption. A dropped stream is a new run with a new `runId`, so a retry can repeat a tool call. Production systems make tool calls idempotent (safe to repeat) with keys → lesson 23a.
# - A run can also end by asking the user something: it finishes with an interrupt outcome and resumes after the answer → lesson 19.
# - The endpoint runs a model and tools with the user's data, so it must check who the user is and where the request came from before the first event → lesson 31b.

# %% [markdown]
# ## What just happened
# - The client sent one `RunAgentInput`. The server answered with an ordered list of events, and each event was sent before the next step ran.
# - The tool call showed up as three events (start, args, end) and then a result, all with one `toolCallId`. The text showed up as start, content deltas and end, all with one `messageId`.
# - The run ended with `RUN_FINISHED` on success, or `RUN_ERROR` on failure. The HTTP status was 200 in both cases, so the status alone says nothing about the run.
# - Two model calls happened in the model run: one to choose the tool, one to stream the answer. The scripted run made none.

# %% [markdown]
# ## Common mistakes
# **Sending a body without `messages`.** The request is refused before any event. Calling `raise_for_status()` turns the `422` into an exception:

# %% tags=["raises-exception"]
reply = httpx.post(endpoint.url + "/agent", json=bad, headers={"Accept": "text/event-stream"})
reply.raise_for_status()           # 422: messages is required; no stream was started

# %% [markdown]
# Fix: send every required field, as the `RunAgentInput` model lists them.
#
# **Judging a run by its HTTP status.** A stream that ends in `RUN_ERROR` still returns 200, so the status alone says nothing. The run from step 10 shows it. The wrong check passes:

# %%
assert failed_status == 200                    # the wrong check: passes
print("wrong check passed, but the last event was", failed_events[-1]["type"])

# %% [markdown]
# The right check reads the events. A run is done only when its last event is `RUN_FINISHED`; a missing `RUN_FINISHED` or any `RUN_ERROR` is a failed run. The cell below defines that check and calls it on the failed run, so it raises:

# %% tags=["raises-exception"]
def check_run(types: list[str]) -> str:
    if types[-1] != "RUN_FINISHED":
        raise RuntimeError(f"run failed: last event is {types[-1]}")
    return "run finished"

check_run([e["type"] for e in failed_events])     # the run from step 10: HTTP 200, but RUN_ERROR

# %% [markdown]
# Fix: call the check on the event types of a good run. The events from the encoder cell in step 3 are such a run, so this passes with no server and no model.

# %%
print(check_run([e.type.value for e in tiny_run]))

# %% [markdown]
# **Retrying a dropped stream by asking for the same events again.** `Last-Event-ID` is the SSE header a client uses to ask a server to resume from where it dropped. AG-UI has no resumption, so no such request exists. A retry is a new run: send a new `runId` and let the agent start over. Repeating a tool call is then the agent's problem, which lesson 23a covers.

# %% [markdown]
# ## Try it
# Encode two more events with `EventEncoder`, without a server and without a model. First a `TOOL_CALL_RESULT` for tool call `call_9`, with message id `m9` and content `3`. Then a `RUN_ERROR` with message `timeout` and code `timeout`. Print both lines, the `data:` frames as the client would receive them.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **AG-UI** — the protocol between an agent's server and the user's screen: an ordered stream of events, plus approval interrupts (lesson 19).
# - **RunAgentInput** — the request body a client POSTs to start a run: thread id, run id, messages, state, tools, context and forwarded props.
# - **Run** — one execution of the agent, from `RUN_STARTED` to `RUN_FINISHED` or `RUN_ERROR`. It has a run id and cannot be resumed.
# - **Event** — one typed message in the stream, such as `TOOL_CALL_START` or `TEXT_MESSAGE_CONTENT`. Related events share an id.
# - **EventEncoder** — the `ag_ui.encoder` class that turns an event into one SSE frame for the negotiated content type.
# - **HTTP+SSE binding** — the AG-UI transport: a POST returns `text/event-stream`, with one `data:` frame per event.
# - **RUN_ERROR** — the event that ends a run that failed after its stream started. The HTTP status stays 200.

# %% [markdown]
# Stop the endpoint and tell the recorder the lesson is done.

# %%
endpoint.stop()
llm_replay.stop()        # saves the recording if a model ran; a no-op otherwise
print("lesson 10 done: the run is a stream of events; a failure is an event, not a status code")
