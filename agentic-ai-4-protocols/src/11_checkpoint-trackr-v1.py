# %% [markdown]
# # 11 · Checkpoint: Trackr v1 — an MCP server, an A2A agent and a live UI
# Level L2 · Part 2 · core · ~90 min · builds on 07, 08, 10

# %% [markdown]
# ## Goal
# By the end you have run all three Trackr pieces together: the Trackr MCP server on stdio and on Streamable HTTP, the triage-agent over A2A, and the AG-UI chat endpoint whose model uses the MCP tools. You verified each one from Python, with five checks. This closes Part 2.

# %% [markdown]
# ## The idea
# Lessons 03, 06, 08 and 10 each built one piece. Trackr v1 wires them into one product. The team's chat asks Trackr for a count through MCP, the triage-agent classifies an issue over A2A, and the AG-UI endpoint streams the whole answer to the screen.
#
# The point of a checkpoint is the check, not the build. Each requirement gets a test that goes through every hop, and the test reads the answer that comes back. If one hop breaks, one check fails and says which one.
#
# Analogy: a pre-flight checklist. The pilot does not trust that each part was fitted well. Each item is checked before the plane leaves.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   U[Chat screen] -->|AG-UI POST /agent| E[AG-UI endpoint :9110]
#   E -->|model picks the tool| M[Model]
#   E -->|MCP over stdio| T[Trackr server]
#   E -->|MCP over HTTP :8766| T
#   C[Client code] -->|A2A SendMessage| A[triage-agent :9108]
#   A -->|one classification| M
# ```

# %% [markdown]
# ## Requirements
# Trackr v1 is done when every box is ticked. The ship check (step 11) prints this list with a tick for each check that passed.
# - [ ] **R1.** The Trackr MCP server runs over **stdio**. `count_open(web)` returns `3`.
# - [ ] **R2.** The same server runs over **Streamable HTTP** on port 8766. It gives the same answer.
# - [ ] **R3.** The **triage-agent** answers one A2A `SendMessage` with one label. Issue 4 ("App crashes when photo is rotated") is a `bug`.
# - [ ] **R4.** The **AG-UI chat** answers the web team question over stdio. The events show `count_open`, then the answer, then `RUN_FINISHED`.
# - [ ] **R5.** The same chat question over HTTP instead of stdio gives the same tool result.
#
# The model budget is 6 calls, 5 used: two for each chat run and one for the triage.

# %% [markdown]
# ## Build it
# ### 1. Set up the paths, the ports and the example
# The three pieces already exist as files from earlier lessons. This cell finds them and fails early if one is missing. It also fixes one port per piece and the example data. Port 8766 is the Trackr HTTP server, 9108 the triage-agent and 9110 the chat endpoint.

# %%
import sys, json, socket, subprocess, atexit
from pathlib import Path
sys.path.insert(0, "..")                       # so llm_setup and llm_replay import
import llm_replay
APPS = Path("../apps").resolve()
TRACKR = APPS / "03" / "trackr_server.py"      # Trackr over stdio (lesson 03)
TRACKR_HTTP = APPS / "06" / "trackr_http.py"   # Trackr over Streamable HTTP (lesson 06)
for needed in (TRACKR, TRACKR_HTTP, APPS / "08" / "triage_agent.py", APPS / "10" / "agui_app.py"):
    assert needed.exists(), f"missing {needed.name}: run lessons 03, 06, 08 and 10 first"
sys.path[:0] = [str(APPS / "08"), str(APPS / "10")]   # triage-agent and AG-UI modules
PORT_HTTP, PORT_TRIAGE, PORT_AGUI = 8766, 9108, 9110
QUESTION = "How many open issues does the web team have?"
ISSUE = next(i for i in json.loads(Path("../data/trackr_05b_issues.json").read_text()) if i["id"] == 4)
Path("../apps/11").mkdir(parents=True, exist_ok=True)
print("example issue:", ISSUE["id"], ISSUE["title"], "| ports:", PORT_HTTP, PORT_TRIAGE, PORT_AGUI)

# %% [markdown]
# Each server gets a fixed port. Before anything starts, the cell below checks that all three ports are free. A stale server from another run would otherwise answer in its place.

# %%
def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0

for port in (PORT_HTTP, PORT_TRIAGE, PORT_AGUI):
    assert port_free(port), f"port {port} is in use: stop the old server first"
print("all three ports are free")

# %% [markdown]
# The next cell defines one small class that runs an ASGI app in a thread, as lesson 10 did. `start` polls a path until it answers, so the notebook never sleeps for a fixed time.

# %%
import threading, time, uvicorn, httpx

class ServerThread:
    """One ASGI app in a thread of this notebook, so the model set here is the model the app uses."""
    def __init__(self, app, port: int):
        self.port, self.url = port, f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self, path: str = "/health", timeout: float = 15.0) -> "ServerThread":
        self.thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if httpx.get(self.url + path, timeout=1).status_code == 200:
                    return self
            except httpx.TransportError:
                pass                                   # not up yet
            time.sleep(0.1)
        raise RuntimeError(f"the server did not answer {path} in time")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

# %% [markdown]
# ### 2. R1: Trackr over stdio
# The host starts the server as a subprocess and talks to it over stdin and stdout. `MCPAdapter` does that from one config entry with a `command`. The check lists the tools and calls `count_open` for the web team. The answer must be `3`: issues 1, 9 and 17 are open for web. LangChain marks `langchain.mcp` as beta, so the notebook filters that warning out before it imports the adapter.

# %%
import warnings, logging
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)   # the adapter is still beta
from langchain.mcp import MCPAdapter
logging.getLogger("fastmcp").setLevel(logging.WARNING)
STDIO = {"mcpServers": {"trackr": {"command": sys.executable, "args": [str(TRACKR)]}}}
async with MCPAdapter(STDIO) as adapter:
    tools = {t.name: t for t in await adapter.list_tools()}
    stdio_count = await tools["count_open"].ainvoke({"name": "count_open", "args": {"team": "web"}, "id": "r1", "type": "tool_call"})
print("R1 tools over stdio:", sorted(tools))
print("R1 count_open(web) over stdio:", stdio_count.text)
assert stdio_count.text == "3"

# %% [markdown]
# ### 3. R2: the same server over Streamable HTTP
# The same file now runs as its own process on port 8766. The cell starts it and polls with a `server/discover` request until it answers, or gives up after 20 seconds. Its log goes to a file, so a failure can be read.

# %%
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {}}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
           "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "server/discover"}
URL_HTTP = f"http://127.0.0.1:{PORT_HTTP}/mcp"
trackr_log = open("../apps/11/trackr_http.log", "w")      # closed in the last cell
trackr_proc = subprocess.Popen([sys.executable, str(TRACKR_HTTP)], stdout=trackr_log, stderr=subprocess.STDOUT)
atexit.register(lambda: trackr_proc.poll() is None and trackr_proc.terminate())   # also if a cell fails
deadline = time.monotonic() + 20
while True:
    try:
        reply = httpx.post(URL_HTTP, json={"jsonrpc": "2.0", "id": 1, "method": "server/discover",
                                           "params": {"_meta": META}}, headers=HEADERS, timeout=5)
        break
    except httpx.ConnectError:
        if trackr_proc.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("Trackr HTTP did not start: read ../apps/11/trackr_http.log")
        time.sleep(0.2)
print("Trackr over HTTP answered:", reply.status_code, "| at", URL_HTTP)

# %% [markdown]
# The same adapter now takes a `url` instead of a `command`. Nothing else in the host changes. The check calls the same tool and compares the answers.

# %%
STREAM = {"mcpServers": {"trackr": {"url": URL_HTTP}}}
async with MCPAdapter(STREAM) as adapter:
    http_tools = {t.name: t for t in await adapter.list_tools()}
    http_count = await http_tools["count_open"].ainvoke({"name": "count_open", "args": {"team": "web"}, "id": "r2", "type": "tool_call"})
print("R2 count_open(web) over HTTP:", http_count.text)
assert http_count.text == stdio_count.text == "3"

# %% [markdown]
# ### 4. R3: the triage-agent, started as a server
# The triage-agent is the lesson 08 agent. Its card and its app come from the files in `../apps/08`. The notebook starts it on port 9108. Its health route is the card, so the start cell polls the card path.

# %%
import triage_card, triage_agent
card = triage_card.build_card(PORT_TRIAGE)
triage = ServerThread(triage_agent.build_app(card), PORT_TRIAGE).start("/.well-known/agent-card.json")
print("triage-agent is up at", triage.url, "| card:", card.name)

# %% [markdown]
# ### 5. R4 and R5: the AG-UI chat endpoint, with the Trackr config
# The chat endpoint from lesson 10 starts with the stdio config. The endpoint runs the MCP server for each chat, so a tool call is real even before a model is set. The next cell starts it on port 9110.

# %%
import agui_app
agui_app.TRACKR_CONFIG = STDIO
endpoint = ServerThread(agui_app.app, PORT_AGUI).start()
print("AG-UI endpoint is up at", endpoint.url + "/agent", "| model set:", agui_app.LLM is not None)

# %% [markdown]
# ### 6. Give the two agents a real model (`needs-llm`)
# One model serves both agents. `get_llm` picks it and starts the recording or the replay for this lesson. If this cell is skipped, both agents keep their scripted paths, and the checks still run. With no model the checks print `answered by: scripted` and the labels come from the keyword rules.

# %% tags=["needs-llm"]
import asyncio
from llm_setup import get_llm
llm = get_llm("11_checkpoint-trackr-v1", max_calls=6)

class ThreadModel:
    """The triage-agent runs in its own thread and event loop. An async model client stays tied to the
    loop it first ran in, so the triage calls the same model in a worker thread instead."""
    def __init__(self, model):
        self.model = model
    async def ainvoke(self, prompt: str):
        return await asyncio.to_thread(self.model.invoke, prompt)

triage_agent.LLM = ThreadModel(llm)    # the triage-agent's classify() awaits ainvoke
agui_app.LLM = llm                     # the chat endpoint runs in the notebook's loop
print("model set for the triage-agent (thread) and the AG-UI endpoint")

# %% [markdown]
# ### 7. Helpers for the chat checks
# The client is plain `httpx`, as in lesson 10. `stream_run` POSTs one `RunAgentInput` and collects the `data:` events. `summarize` pulls out the three things the checks read: the tool name, the tool result and the answer text. `check_run` fails unless the last event is `RUN_FINISHED`.

# %%
async def stream_run(question: str, run_id: str):
    payload = {"threadId": "thread-v1", "runId": run_id, "state": {}, "tools": [], "context": [],
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

def summarize(events) -> dict:
    starts = [e for e in events if e["type"] == "TOOL_CALL_START"]
    results = [e["content"] for e in events if e["type"] == "TOOL_CALL_RESULT"]
    answer = "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    return {"tool": starts[0]["toolCallName"] if starts else None,
            "result": results[0] if results else None, "answer": answer}

def check_run(types: list[str]) -> str:
    if types[-1] != "RUN_FINISHED":
        raise RuntimeError(f"run failed: last event is {types[-1]}")
    return "run finished"

# %% [markdown]
# ### 8. R4: the chat over stdio
# The browser would POST this. The check sends the question, then reads the events. It expects one `count_open` call with the answer `3`, then the text, then `RUN_FINISHED`. Up to two model calls run here.

# %%
status, events = await stream_run(QUESTION, "run-r4")
summary = summarize(events)
types = [e["type"] for e in events]
print("R4 HTTP", status, "| answered by:", "model" if agui_app.LLM is not None else "scripted")
print("R4 tool:", summary["tool"], "| result:", summary["result"])
print("R4 answer:", summary["answer"])
print("R4", check_run(types), "| events:", types[0], "...", types[-1])
assert status == 200 and summary["tool"] == "count_open" and summary["result"] == "3"
r4_ok = types.index("TOOL_CALL_START") < types.index("TEXT_MESSAGE_START") and check_run(types) == "run finished"

# %% [markdown]
# ### 9. R3 in use: the client calls the triage-agent directly
# The chat does not call the triage-agent. A separate client does. It reads the card, creates a client from it and sends one `SendMessage` with the issue title. The label comes back as an artifact. This is one model call at most.

# %%
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
async with httpx.AsyncClient(timeout=60) as http:
    found = await A2ACardResolver(http, triage.url).get_agent_card()
client = await create_client(agent=found, client_config=ClientConfig(streaming=False))
task = None
async for chunk in client.send_message(SendMessageRequest(message=new_text_message(ISSUE["title"], role=Role.ROLE_USER))):
    if chunk.WhichOneof("payload") == "task":
        task = chunk.task
artifact = task.artifacts[0]
label = get_artifact_text(artifact)
print("R3 state:", TaskState.Name(task.status.state), "| answered by:", artifact.name, "| label:", label)
assert TaskState.Name(task.status.state) == "TASK_STATE_COMPLETED" and label == "bug"
r3_ok = True

# %% [markdown]
# ### 10. R5: the same chat question over HTTP instead of stdio
# Only the config changes: the endpoint now reaches Trackr by URL. The check runs the same question and compares the tool result. The config is put back to stdio afterwards, even if the run fails.

# %%
agui_app.TRACKR_CONFIG = STREAM
try:
    status_c, events_c = await stream_run(QUESTION, "run-r5")
finally:
    agui_app.TRACKR_CONFIG = STDIO
summary_c = summarize(events_c)
print("R5 HTTP", status_c, "| tool:", summary_c["tool"], "| result:", summary_c["result"])
print("R5 answer:", summary_c["answer"])
assert status_c == 200 and summary_c["result"] == summary["result"] == "3"
r5_ok = check_run([e["type"] for e in events_c]) == "run finished"

# %% [markdown]
# ### 11. Ship check: every requirement, ticked
# The last check prints the requirement list. Each line is a check that already passed above. If one were false, the assert would stop the notebook.

# %%
checks = {
    "R1 Trackr over stdio: count_open(web) = 3": stdio_count.text == "3",
    "R2 Trackr over Streamable HTTP: the same answer": http_count.text == "3",
    "R3 triage-agent over A2A: one SendMessage, label bug": r3_ok,
    "R4 AG-UI chat over stdio: tool, text, RUN_FINISHED": r4_ok,
    "R5 the same chat over HTTP: the same tool result": r5_ok,
}
for name, ok in checks.items():
    print("[x]" if ok else "[ ]", name)
assert all(checks.values()), "a requirement failed"
print("Trackr v1 passes all five checks")

# %% [markdown]
# Stop the three pieces and tell the recorder the lesson is done. If an earlier cell failed, the Trackr HTTP process still stops at exit, because its cell registered that hook.

# %%
endpoint.stop()
triage.stop()
trackr_proc.terminate()
trackr_proc.wait(timeout=10)
trackr_log.close()
llm_replay.stop()        # saves the recording if a model ran; a no-op otherwise
print("stopped: AG-UI endpoint, triage-agent and Trackr HTTP | lesson 11 done")

# %% [markdown]
# ## At work
# - Teams ship one MCP server per system and expose it twice: over stdio for desktop hosts, and over Streamable HTTP (one `POST /mcp`, bound to localhost, Origin checked, 403 on failure) for shared use. Both must share one tool list, or the same question gets two answers. Proxies are covered in → lesson 32.
# - An A2A agent accepts work from other agents. Its Agent Card lists `securitySchemes` and `security`, so callers learn how to authenticate first. Without auth, anyone who reaches the URL can send it tasks. Securing it is in → lesson 37.
# - A chat across AG-UI, A2A and MCP is one request in three services. Teams send one OpenTelemetry trace id through every hop → lesson 28.
# - Before a release, teams run in-memory tests and the MCP Inspector in CI (`npx @modelcontextprotocol/inspector --cli <url> --transport http --method tools/list`, Node 22.19 or newer), then an end-to-end check like this one → lesson 27.

# %% [markdown]
# ## Reference solution
# <details><summary>Try the build first. Open this only to compare.</summary>
#
# The checks should print these results. A model may word the chat answer differently, but the tool result and the label must match:
#
# - R1: `count_open(web)` over stdio gives `3`.
# - R2: the same call over HTTP gives `3`.
# - R3: the state is `TASK_STATE_COMPLETED`, the artifact name is `model` (or `scripted` with no model), and the label is `bug`.
# - R4: the events start with `RUN_STARTED`, show `count_open` and its result `3`, then text, and end with `RUN_FINISHED`.
# - R5: the same as R4, through the HTTP server.
#
# Design choices to notice. The chat and the triage-agent are separate services: the chat calls Trackr for numbers, and the triage-agent classifies issues. The Trackr server is the same file in both transports, so the tool list cannot drift. Every check reads the final state, not the HTTP status alone.
# </details>

# %% [markdown]
# ## Key terms
# - **Trackr v1** — the first complete Trackr: the MCP server on two transports, a triage-agent over A2A, and an AG-UI chat endpoint that uses the MCP tools.
# - **end-to-end check** — a test that goes through every hop of one user request and reads the final answer, not the status of each hop.
# - **stdio transport** — the MCP transport where the host starts the server as a subprocess and talks over stdin and stdout (lesson 05b).
# - **Streamable HTTP** — the MCP transport for a server that is already running, reached by POST at `/mcp` (lesson 06).
# - **SendMessage** — the A2A request that starts or continues a task with one message (lesson 08).
# - **RUN_FINISHED** — the AG-UI event that marks a successful run; a run without it failed (lesson 10).
