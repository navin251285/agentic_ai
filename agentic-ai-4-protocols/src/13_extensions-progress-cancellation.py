# %% [markdown]
# # 13 · Extensions, progress and cancellation
# Level L3 · Part 3 · professional · ~30 min · builds on 07

# %% [markdown]
# ## Goal
# By the end you run a 20-second Trackr reindex on a worker that reports progress. You opt in to an extension and see the extra detail, and without it you see the plain progress. You cancel the reindex by closing the response stream, and the worker log shows that the handler stopped. A real model starts the reindex with one call.

# %% [markdown]
# ## Why it matters
# Without progress, a 20-second tool call is 20 seconds of silence. The host cannot draw a bar, and it cannot tell a slow job from a stuck one. Without cancellation, the host that closes its connection leaves the server working for a user who has gone. Without an extension mechanism, every new feature must be in the core spec, or it breaks the clients that do not know it.
#
# The cell below is the silent version: one request, one reply, nothing in between.

# %%
import time

def reindex_plain(steps=3):
    """The plain version: the client gets nothing until the last batch is done."""
    client_saw = []                      # what the client has received so far
    for batch in range(1, steps + 1):
        time.sleep(0.5)                  # one batch of work, no message sent
    client_saw.append(f"result: {steps} batches done")
    return client_saw

t0 = time.monotonic()
messages = reindex_plain()
print(messages, f"| after {time.monotonic() - t0:.1f} s")

# %% [markdown]
# The client sees one message, after the whole job. Trackr's real reindex has 20 batches of one second. This lesson adds two things: progress events while the job runs, and a way to stop the job early. You do not need either for a call that takes under a second, or for a host with no screen to update. You need cancellation as soon as a call can run for minutes.

# %% [markdown]
# ## The idea
# An **extension** is a feature outside the core spec. Its id has a vendor prefix, such as `example.trackr/progress-detail`. A client opts in by naming the id in its capabilities. A server lists the ids it supports in `server/discover`. Extensions are off by default, and a server that meets a client without the opt-in does the plain thing. That is **graceful degradation**.
#
# **Progress**: the client sends a `progressToken` in `_meta`, and the server may send `notifications/progress` on the open stream.
#
# **Cancellation over HTTP** is closing the response stream. The server sees the disconnect and cancels the handler, and the handler must stop work. `notifications/cancelled` is for stdio only.
#
# Analogy: a print shop. Progress is the counter on the job slip. Cancelling takes the job back, and the press must stop. An extension is a rush option on the form, which only shops that know it act on.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant H as Host
#   participant W as Trackr reindex worker
#   H->>W: tools/call reindex_issues (_meta: opt-in + progressToken)
#   W-->>H: notifications/progress 1 of 20
#   W-->>H: notifications/progress 2 of 20
#   H-->>W: closes the response stream (this is the cancel)
#   Note over W: handler is cancelled, logs "stopped at batch 2", does no more work
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. The worker: one slow tool and one opt-in extension
# This worker is a small Trackr server with two tools: `reindex_issues`, which takes about 20 seconds, and `reindex_status`, which reads the count. It is its own server, not the lesson 03 server, because an extension is set when the server is built. The `ProgressDetail` extension has no tools of its own. It exists so the server advertises its id. The reindex adds a message to each progress event only when the client named the id. The handler logs its start and its stop, so the log shows what happened.

# %%
from pathlib import Path
Path("../apps/13").mkdir(parents=True, exist_ok=True)

# %% [markdown]
# The worker file is written next. Its folder exists now.

# %%
%%writefile ../apps/13/trackr_reindex_worker.py
"""Trackr reindex worker (lesson 13): one slow tool, one opt-in extension, progress and cancellation.

The handler logs when it starts, when it reports and when it stops, so the worker log shows cancellation."""
import sys
from typing import Literal
import anyio
from mcp.server import MCPServer
from mcp.server.extension import Extension
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings

DETAIL_ID = "example.trackr/progress-detail"   # vendor prefix / name: an opt-in extension
STEPS = 20                                     # 20 batches of one second each: about 20 seconds
INDEX = {}                                     # team -> batches done in the latest reindex (this worker's memory)
Team = Literal["web", "api", "mobile", "infra"]

class ProgressDetail(Extension):
    """Off unless the client declares DETAIL_ID. When it is on, progress messages name the batch."""
    identifier = DETAIL_ID

mcp = MCPServer("Trackr reindex", extensions=[ProgressDetail()])

def detail_on(ctx: Context) -> bool:
    caps = ctx.client_capabilities
    return bool(caps and caps.extensions and DETAIL_ID in caps.extensions)

@mcp.tool(title="Reindex a team's issues")
async def reindex_issues(team: Team, ctx: Context) -> str:
    """Rebuild the search index for one team's issues in 20 batches. Takes about 20 seconds."""
    detail = detail_on(ctx)
    INDEX[team] = 0
    finished = False
    print(f"start {team} (detail extension {'on' if detail else 'off'})", file=sys.stderr, flush=True)
    try:
        for step in range(1, STEPS + 1):
            await anyio.sleep(1)
            INDEX[team] = step
            message = f"indexed batch {step} of {STEPS} for {team}" if detail else None
            await ctx.report_progress(step, STEPS, message)
        finished = True
        return f"{team} reindexed: {STEPS} batches"
    finally:
        if finished:
            print(f"finished {team}", file=sys.stderr, flush=True)
        else:
            print(f"stopped {team} at batch {INDEX[team]} of {STEPS}: handler exited, no more work",
                  file=sys.stderr, flush=True)

@mcp.tool(title="Reindex status")
def reindex_status(team: Team) -> str:
    """How many batches the latest reindex of this team has finished."""
    return f"{team}: {INDEX.get(team, 0)} of {STEPS} batches"

PORT = int(sys.argv[1])   # the notebook passes the port
SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[f"127.0.0.1:{PORT}", f"localhost:{PORT}"],
)

if __name__ == "__main__":
    # json_response=False: tool replies stream as text/event-stream, so progress can arrive first
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=False, transport_security=SECURITY)

# %% [markdown]
# The notebook starts the worker on port 8130 and writes its log to `../apps/13/worker.log`. The worker is ready when `server/discover` answers.

# %%
import atexit, subprocess, sys, time
import httpx
PORT = 8130
URL = f"http://127.0.0.1:{PORT}/mcp"
logf = open("../apps/13/worker.log", "w")   # closed in the cleanup cell
proc = subprocess.Popen([sys.executable, str(Path("../apps/13/trackr_reindex_worker.py").resolve()), str(PORT)],
                        stdout=logf, stderr=subprocess.STDOUT)
def stop_worker():
    if proc.poll() is None:
        proc.terminate()
_ = atexit.register(stop_worker)
print("worker starting on port", PORT, "| log: ../apps/13/worker.log")

# %% [markdown]
# ### 2. The helpers: each request carries its own opt-in
# Every request has its own `_meta`, as in lesson 07. The opt-in is an entry in `clientCapabilities`, and it is sent only on the requests that want it. A `progressToken` asks for progress. `open_call` returns an open stream. Use it in a `with` block: leaving the block closes the connection, and the server treats that as a cancel.

# %%
import json
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"
DETAIL_ID = "example.trackr/progress-detail"
PLAIN_META = {VERSION_KEY: "2026-07-28", CAPS_KEY: {}}
OPT_IN_META = {VERSION_KEY: "2026-07-28", CAPS_KEY: {"extensions": {DETAIL_ID: {}}}}
BASE_HEADERS = {"Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": "2026-07-28"}

def body(method, params=None, meta=PLAIN_META, req_id=1):
    """A JSON-RPC request. The version and capabilities ride in params._meta."""
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": {**(params or {}), "_meta": meta}}

def open_call(name, arguments, meta, token=None):
    """Open a tools/call stream. The progress token asks for progress events on it."""
    meta = {**meta, "progressToken": token} if token else meta
    payload = body("tools/call", {"name": name, "arguments": arguments}, meta=meta, req_id=5)
    headers = {**BASE_HEADERS, "Mcp-Method": "tools/call", "Mcp-Name": name}
    return httpx.stream("POST", URL, json=payload, headers=headers, timeout=30)

def events(response):
    """Yield each JSON message on an open stream (the SSE 'data:' lines)."""
    for line in response.iter_lines():
        if line.startswith("data:"):
            yield json.loads(line[len("data:"):].strip())

print("helpers ready: body, open_call, events")

# %% [markdown]
# ### 3. Wait until the worker answers
# The cell polls `server/discover` for up to 20 seconds. If the worker does not start, the cell prints its log.

# %%
deadline = time.monotonic() + 20
while True:
    try:
        httpx.post(URL, json=body("server/discover"), headers={**BASE_HEADERS, "Mcp-Method": "server/discover"}, timeout=5)
        break
    except httpx.ConnectError:
        if proc.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("the worker did not start: read ../apps/13/worker.log")
        time.sleep(0.2)
print("worker is up on port", PORT)

# %% [markdown]
# ### 4. The extension is advertised, and off by default
# `server/discover` lists the extensions the server supports. The server offers the id. A client that does not name it in its own capabilities is not in the extension.

# %%
r = httpx.post(URL, json=body("server/discover"), headers={**BASE_HEADERS, "Mcp-Method": "server/discover"}, timeout=10)
advertised = r.json()["result"]["capabilities"].get("extensions", {})
print("server advertises:", sorted(advertised))
print("this client opted in:", DETAIL_ID in PLAIN_META[CAPS_KEY].get("extensions", {}))

# %% [markdown]
# ### 5. Graceful degradation: the same tool with and without the opt-in
# The host asks for the same reindex twice and reads only the first progress event. Each time it then closes the stream. Both clients get progress, so the plain client still sees progress. Only the client that opted in gets the batch name in the message.

# %%
def first_progress(meta, token):
    """Read the first progress event, then leave the block, which closes the stream."""
    with open_call("reindex_issues", {"team": "web"}, meta, token) as resp:
        for msg in events(resp):
            if msg.get("method") == "notifications/progress":
                return msg["params"]
    return None

plain = first_progress(PLAIN_META, "plain-1")
detail = first_progress(OPT_IN_META, "detail-1")
print("without opt-in:", int(plain["progress"]), "of", int(plain["total"]), "| message:", plain.get("message"))
print("with opt-in:   ", int(detail["progress"]), "of", int(detail["total"]), "| message:", detail.get("message"))

# %% [markdown]
# ### 6. Cancel by closing the stream
# On HTTP, cancelling is one act: close the stream. The host reads three progress events, then leaves the `with` block. The server sees the disconnect and cancels the handler. The count should stop where the handler was. The cell reads the count now, waits 2.5 seconds and reads it again.

# %%
def status():
    r = httpx.post(URL, json=body("tools/call", {"name": "reindex_status", "arguments": {"team": "web"}}, req_id=9),
                   headers={**BASE_HEADERS, "Mcp-Method": "tools/call", "Mcp-Name": "reindex_status"}, timeout=10)
    return r.json()["result"]["structuredContent"]["result"]

log_path = Path("../apps/13/worker.log")

def stop_lines():
    """The handler's stop lines in the worker log."""
    return [line for line in log_path.read_text().splitlines() if "stopped" in line]

def wait_for_stop(count_before):
    """Wait up to 5 s for one more stop line than count_before, then return the newest one."""
    deadline = time.monotonic() + 5
    while len(stop_lines()) <= count_before and time.monotonic() < deadline:
        time.sleep(0.2)
    return stop_lines()[-1]

# %% [markdown]
# Now the cancel itself. The host opens the stream, reads three progress events, and leaves the `with` block.

# %%
stops_before = len(stop_lines())
seen = 0
with open_call("reindex_issues", {"team": "web"}, OPT_IN_META, "cancel-1") as resp:
    for msg in events(resp):
        if msg.get("method") == "notifications/progress":
            seen += 1
            print("progress", int(msg["params"]["progress"]), "of 20:", msg["params"]["message"])
            if seen == 3:
                break   # leaving the block closes the stream: this is the cancel
print("stream closed after", seen, "progress events")
before = status()
time.sleep(2.5)
after = status()
print("right after the close:", before, "| 2.5 s later:", after, "| stopped:", before == after)

# %% [markdown]
# The worker log is the proof on the server side. The handler wrote a line when it stopped. The cell waits up to five seconds for that line, because the server may take a moment to notice the close.

# %%
print(wait_for_stop(stops_before))

# %% [markdown]
# ### 7. A real model starts the reindex (`needs-llm`)
# The host lists the tools from the worker, and the model chooses one. The model is called once. Its answer is a tool call, not a written reply. The host then runs that call with the opt-in and progress on, reads two events, and closes the stream. Below the model cell is a labelled stand-in for a skipped model.
#
# The setup cell lists the tools through the LangChain adapter. The adapter is beta, so its warning is muted.

# %%
import logging, warnings
from contextlib import AsyncExitStack
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)  # the adapter is still beta
logging.getLogger("httpx").setLevel(logging.WARNING)
from langchain.mcp import MCPAdapter
from langchain_core.messages import AIMessage, HumanMessage
import sys
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
import llm_replay
QUESTION = HumanMessage("Reindex the web team's issues. Start it now.")
stack = AsyncExitStack()   # closed in the cleanup cell
adapter = await stack.enter_async_context(MCPAdapter({"mcpServers": {"trackr": {"url": URL}}}))
tools = {t.name: t for t in await adapter.list_tools()}
assert "reindex_issues" in tools
print("tools the model sees:", sorted(tools))
llm = None   # filled by the model cell; stays None if that cell is skipped

# %% [markdown]
# The model is called once, with the tool list. It must answer with a tool call.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("13_extensions-progress-cancellation", max_calls=1)
ask = await llm.bind_tools(list(tools.values())).ainvoke([QUESTION])
print("model asks for:", [(c["name"], c["args"]) for c in ask.tool_calls])

# %% [markdown]
# If the model cell was skipped, a labelled stand-in takes its place.

# %%
if llm is None:   # fallback: the model cell was skipped
    ask = AIMessage(content="", tool_calls=[{"name": "reindex_issues", "args": {"team": "web"}, "id": "scripted_1"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in ask.tool_calls])

# %% [markdown]
# The model part is done, so stop the replay layer here. It saves the model's recording and hands the wire back to plain HTTP. It buffers streamed responses, and the next cell needs to read the stream live.

# %%
llm_replay.stop()

# %% [markdown]
# The host runs the call the model asked for. It keeps the opt-in and the progress token, reads two events and closes the stream.

# %%
call = ask.tool_calls[0]
stops_before = len(stop_lines())
seen = []
with open_call(call["name"], call["args"], OPT_IN_META, "model-1") as resp:
    for msg in events(resp):
        if msg.get("method") == "notifications/progress":
            seen.append(msg["params"])
            print("progress", int(seen[-1]["progress"]), "of 20:", seen[-1].get("message"))
            if len(seen) == 2:
                break   # closing the stream cancels the job the model started
print("host closed the stream after", len(seen), "progress events")
print(wait_for_stop(stops_before))

# %% [markdown]
# ### 8. Clean up
# The adapter closes, the worker stops and the log file closes.

# %%
await stack.aclose()
stop_worker()
proc.wait(timeout=10)
logf.close()
print("worker stopped")

# %% [markdown]
# ## At work
# - **Long calls need a stream that stays alive.** Proxies and clients cut idle connections (the Python client's read timeout is 300 s, and an `httpx2` client without a timeout falls back to 5 s). Progress events keep the stream busy. A job longer than a stream should move to a Task (→ lesson 13a).
# - **A cancelled job must stop.** Teams log stops and check them, as here, because a handler that ignores cancellation keeps writing after the user left. Production hardening is in lessons 32 and 33.
# - **Extensions let a server add features without breaking old clients.** The server lists ids in discovery and clients opt in. Trace context travels in `_meta` the same way (→ lesson 28).

# %% [markdown]
# ## What just happened
# The reindex ran as a stream. The server added a progress event for each batch. The extension added a batch name to those events, but only for the client that named it. When the host closed the stream, the server noticed, cancelled the handler, and the log recorded the stop. The count did not move after that. The model made one call, and the host did the rest over the wire.

# %% [markdown]
# ## Common mistakes
# **Mistake 1: treating the extension as always on.** A client that did not opt in has no `extensions` entry for the id. Looking the key up directly fails. Check for the id first, or use `.get`.

# %% tags=["raises-exception"]
client_caps = {"extensions": {}}          # a client that did not opt in
print(client_caps["extensions"][DETAIL_ID])

# %% [markdown]
# The fix is to check first. A missing id means the extension is off, and the plain behaviour applies.

# %%
print("opted in?", DETAIL_ID in client_caps.get("extensions", {}))

# %% [markdown]
# **Mistake 2: sending `notifications/cancelled` over HTTP.** The server accepts the POST and ignores it. The job keeps running. On HTTP, close the stream. **Mistake 3: expecting progress without a token.** The server sends progress only when the request carries a `progressToken`. Without one, the reply is just the result.

# %% [markdown]
# ## Try it
# A client can name the extension, leave it out, or send `extensions: null`. Write `detail_is_on(client_caps)` so that it returns True only when the client named `DETAIL_ID` under `extensions`. It must not crash when the key is missing or `None`.

# %%
# your code here
def detail_is_on(client_caps):
    """True only when client_caps names DETAIL_ID under extensions. Handle a missing key or None."""
    pass

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def detail_is_on(client_caps):
    extensions = (client_caps or {}).get("extensions") or {}
    return DETAIL_ID in extensions

print(detail_is_on({"extensions": {DETAIL_ID: {}}}), detail_is_on({}), detail_is_on({"extensions": None}))

# %% [markdown]
# ## Key terms
# - **Extension** — an opt-in feature outside the core spec, named by a vendor-prefixed id and negotiated in capabilities.
# - **Graceful degradation** — a server does the plain thing when the client did not opt in.
# - **Progress token** — an opaque value in `_meta` that asks for `notifications/progress` events.
# - **Cancellation by closing the stream** — on HTTP the client cancels a request by closing its response stream; the server must stop the handler.
