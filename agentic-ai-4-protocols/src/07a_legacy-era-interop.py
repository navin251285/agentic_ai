# %% [markdown]
# # 07a · Talking to legacy servers (2025-11-25 and older)
# Level L2 · Part 2 · professional · ~35 min · builds on 07

# %% [markdown]
# ## Goal
# By the end you connect to two kinds of Trackr server from one notebook. One still uses the `initialize` handshake and `Mcp-Session-Id` (2025-11-25). One speaks 2026-07-28. You pin the old era with `mode="legacy"`, you see why a legacy session breaks when its requests reach a different worker, and you see the stateless legacy leg that fixes it. A real model uses the old and the modern server in one conversation, two calls at most.

# %% [markdown]
# ## Why it matters
# Many MCP servers still speak 2025-11-25. A client that knows only the new core cannot reach them, so you keep two stacks. A legacy server that scales out keeps its sessions in one process's memory.
#
# | Without legacy support | What breaks | What the era-aware client gives you |
# |---|---|---|
# | A client that only sends `_meta` | An old server answers `initialize` only, so the client cannot connect | One `Client(url)` probes the server and falls back to `initialize` |
# | Two workers behind a load balancer | A legacy session made on worker A is unknown on worker B: `404 Session not found` | Sticky routing, or the stateless legacy leg |
# | A stateless legacy leg | Server-to-client calls (elicitation, sampling) have no channel back to the client | Use modern elicitation (lesson 12), which works on both eras |
#
# Skip this when every client speaks 2026-07-28. Use it when a client you do not control still speaks the old handshake.

# %% [markdown]
# ## The idea
# The old era begins with an `initialize` request. The server keeps a session for the client and names it with `Mcp-Session-Id`. The 2026-07-28 era has no handshake: each request carries its version in `_meta`.
#
# One endpoint serves both. `Client(url)` probes with `server/discover` first and falls back to `initialize` only if the server does not answer in the new era. `mode="legacy"` skips the probe and forces the handshake.
#
# Analogy: a hotel with an old check-in desk and a new kiosk. The desk gives you a key card that only that desk can find. The kiosk gives a booking code that any desk can read.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   OC[Old client: mode=legacy] -->|initialize, then Mcp-Session-Id| A[Worker A :8781 sticky]
#   OC -.->|same session on another worker| B[Worker B :8782 sticky]
#   B -.->|404 Session not found| OC
#   NC[Modern client: auto probe] -->|_meta: 2026-07-28| B
#   OC2[Old client, stateless leg] -->|no session kept| C[Worker C :8783 stateless]
#   OC2 -->|same request| D[Worker D :8784 stateless]
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Check the lesson 03 server and write the legacy worker
# A worker is the lesson 03 Trackr server on a port from the command line. Its one argument, `sticky` or `stateless`, sets how the legacy leg keeps sessions. The first cell checks that the server exists. The next cell writes the worker file.

# %%
from pathlib import Path
TRACKR_DIR = Path("../apps/03").resolve()
assert (TRACKR_DIR / "trackr_server.py").exists(), "run lesson 03 first: it writes the Trackr server"
Path("../apps/07a").mkdir(parents=True, exist_ok=True)
print("Trackr server found: ../apps/03/trackr_server.py")

# %% [markdown]
# The worker keeps the security settings from lesson 06. The one new setting is `stateless_http`. It is `False` for `sticky`, so legacy sessions live in the worker's memory. It is `True` for `stateless`, so the legacy leg keeps no session.

# %%
%%writefile ../apps/07a/legacy_worker.py
"""Trackr legacy-leg worker (lesson 07a): the lesson 03 server on 127.0.0.1, one worker per port.

argv: PORT, then "sticky" (default: HTTP sessions live in this process) or
"stateless" (stateless_http=True: the legacy leg keeps no session in memory)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03"))  # the lesson 03 server
from mcp.server.transport_security import TransportSecuritySettings
from trackr_server import mcp

PORT = int(sys.argv[1])
STATELESS = len(sys.argv) > 2 and sys.argv[2] == "stateless"
SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[f"127.0.0.1:{PORT}", f"localhost:{PORT}"],
)

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True,
            stateless_http=STATELESS, transport_security=SECURITY)

# %% [markdown]
# ### 2. Start four workers and wait until each answers
# Workers A and B are sticky. Workers C and D are stateless. Each is its own process with its own memory. The notebook polls each one with a legacy `initialize`. It gives up after 20 seconds and reads the worker log if a worker does not start.

# %%
import atexit, subprocess, sys, time
import httpx
PORTS = {"A": 8781, "B": 8782, "C": 8783, "D": 8784}
MODE = {"A": "sticky", "B": "sticky", "C": "stateless", "D": "stateless"}
URL = {w: f"http://127.0.0.1:{p}/mcp" for w, p in PORTS.items()}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "lesson-07a", "version": "1.0"}}}
WORKER = str(Path("../apps/07a/legacy_worker.py").resolve())
procs, logs = {}, {}
for w, port in PORTS.items():
    logs[w] = open(f"../apps/07a/worker_{w}.log", "w")   # closed in the cleanup cell
    procs[w] = subprocess.Popen([sys.executable, WORKER, str(port), MODE[w]], stdout=logs[w], stderr=subprocess.STDOUT)
atexit.register(lambda: [p.poll() is None and p.terminate() for p in procs.values()])
for w in PORTS:
    deadline = time.monotonic() + 20
    while True:
        try:
            httpx.post(URL[w], json=INIT, headers={"Accept": "application/json, text/event-stream"}, timeout=10)
            break
        except httpx.ConnectError:
            if procs[w].poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"worker {w} did not start: read ../apps/07a/worker_{w}.log")
            time.sleep(0.2)
    print(f"worker {w} ({MODE[w]}) is up on port {PORTS[w]}")

# %% [markdown]
# ### 3. Era probing: the same server, two eras
# `Client(url)` uses the default `mode="auto"`. It asks the server in the new era first. Worker B answers, so the client negotiates 2026-07-28. `mode="legacy"` skips that question and runs the `initialize` handshake. Both clients list the same tools.

# %%
from mcp import Client
async with Client(URL["B"]) as modern:
    print("auto probe     -> protocol", modern.protocol_version, "| tools:", len((await modern.list_tools()).tools))
async with Client(URL["A"], mode="legacy") as old:
    print("mode='legacy'  -> protocol", old.protocol_version, "| tools:", len((await old.list_tools()).tools))

# %% [markdown]
# ### 4. The legacy handshake on the wire
# The SDK did the handshake for you above. Here is the same exchange by hand with `httpx`, so you can see what the header and the session are. The `initialize` request has no version header and no session. The reply carries `Mcp-Session-Id`. Every later request repeats the session and the version. The client then sends `notifications/initialized`, which the server answers with `202`.

# %%
def legacy_post(worker, payload, session=None, version=True):
    """One POST in the legacy era. The version header and the session id go on every request after initialize."""
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if version:
        headers["MCP-Protocol-Version"] = "2025-11-25"
    if session:
        headers["Mcp-Session-Id"] = session
    return httpx.post(URL[worker], json=payload, headers=headers, timeout=10)

reply = legacy_post("A", INIT, version=False)
session_a = reply.headers["mcp-session-id"]
print("initialize on A:", reply.status_code, "| protocol", reply.json()["result"]["protocolVersion"],
      "| session id received:", bool(session_a))
note = legacy_post("A", {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_a)
print("notifications/initialized on A:", note.status_code)

# %% [markdown]
# ### 5. A sticky session cannot follow the request to another worker
# Now send `tools/list` with the session from worker A, first to A and then to B. A knows the session. B has never seen it, because the session is a plain entry in A's memory. B answers `404 Session not found`. A load balancer must send every request of one legacy session to the same worker. That is sticky routing.

# %%
same = legacy_post("A", {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_a)
other = legacy_post("B", {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_a)
print("tools/list on A (the session's worker):", same.status_code)
print("tools/list on B (another worker):      ", other.status_code, "|", other.text.strip()[:80])

# %% [markdown]
# ### 6. The stateless legacy leg: no session to find
# With `stateless_http=True` the legacy leg keeps no session. Worker C's `initialize` returns no `Mcp-Session-Id`. So any worker can answer the next request. Send `tools/list` to D, which never saw the `initialize`. It answers `200`. You trade away server-to-client calls on this leg: a legacy elicitation or sampling request has no back channel to the client.

# %%
init_c = legacy_post("C", INIT, version=False)
print("initialize on C: status", init_c.status_code, "| session header:", "mcp-session-id" in init_c.headers)
on_d = legacy_post("D", {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
print("tools/list on D (no session, never initialized there):", on_d.status_code,
      "| tools:", len(on_d.json()["result"]["tools"]))

# %% [markdown]
# ### 7. A real model uses the old and the modern server (`needs-llm`)
# The host keeps one conversation. It has two tools: one that counts on the old server (a legacy session on worker A) and one that counts on the modern server (worker B, the 2026-07-28 client). The model never learns the protocol era. It only sees the tool names.
#
# The setup cell wraps each server as a LangChain tool. Each tool call opens its own client, so no connection stays open between cells. The model cell asks which tools to call. It may ask for both counts in one turn.

# %%
import logging, sys
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
import llm_replay
logging.getLogger("httpx").setLevel(logging.WARNING)

class TeamArgs(BaseModel):
    team: str

QUESTION = HumanMessage("How many open issues does the web team have on the old server, and on the modern one? Use the tools.")
llm = None   # filled by the model cell; stays None if that cell is skipped
def as_tool(prefix, url, mode):
    """A LangChain tool that sends count_open to one server. The model sees only the name."""
    async def run(team: str) -> str:
        async with Client(url, mode=mode) as client:   # one client per call
            result = await client.call_tool("count_open", {"team": team})
        return str(result.structured_content["result"])
    return StructuredTool.from_function(coroutine=run, name=f"{prefix}_count_open", args_schema=TeamArgs,
                                        description=f"Count open issues for one team on the {prefix} server.")

tools = [as_tool("old", URL["A"], "legacy"), as_tool("modern", URL["B"], "auto")]
by_name = {t.name: t for t in tools}
print("tools for the model:", sorted(by_name))

# %% [markdown]
# The model cell asks which tools to call. This is the first of two model calls in the lesson.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("07a_legacy-era-interop", max_calls=2)
first = await llm.bind_tools(tools).ainvoke([QUESTION])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model cell was skipped, scripted calls stand in for the model's first reply. The stand-in is labelled.

# %%
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[
        {"name": "old_count_open", "args": {"team": "web"}, "id": "scripted_1"},
        {"name": "modern_count_open", "args": {"team": "web"}, "id": "scripted_2"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# The host runs each call on the server it names. The old call opens a legacy session on A. The modern call goes to B.

# %%
results = []
for c in first.tool_calls:
    result = await by_name[c["name"]].ainvoke(c)
    results.append(result)
    print(f"{c['name']} -> {result.content}")

# %% [markdown]
# The model reads both results and writes its answer. This is its second and last call (`needs-llm`).

# %% tags=["needs-llm"]
final = await llm.bind_tools(tools).ainvoke([QUESTION, first, *results])
print("answer:", final.text)

# %% [markdown]
# Without a model there is no written answer, so the fallback prints what the servers returned.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). The servers said:", [r.content for r in results])

# %% [markdown]
# ### 8. Handle the version error
# A server that does not support a version answers with JSON-RPC error `-32022`. The spec calls it `UnsupportedProtocolVersionError`. The SDK raises it as `MCPError`, and the code is the constant `UNSUPPORTED_PROTOCOL_VERSION`. Its `data.supported` lists the versions the server speaks. `Client` handles this inside its own probe, so you rarely see it. When you call the wire yourself, check the code and retry with a shared version.

# %%
from mcp_types import UNSUPPORTED_PROTOCOL_VERSION
from mcp.shared.exceptions import MCPError
print("code:", UNSUPPORTED_PROTOCOL_VERSION, "| class:", MCPError.__name__)

# %% [markdown]
# Now send a `server/discover` with an unknown version to worker B. The reply is a JSON error, and `data.supported` names what B speaks.

# %%
modern_req = {"jsonrpc": "2.0", "id": 3, "method": "server/discover",
              "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2099-01-01",
                                   "io.modelcontextprotocol/clientCapabilities": {}}}}
reply = httpx.post(URL["B"], json=modern_req, timeout=10,
                   headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
                            "MCP-Protocol-Version": "2099-01-01", "Mcp-Method": "server/discover"})
err = reply.json().get("error", {})
print("status:", reply.status_code, "| code:", err.get("code"), "| supported:", err.get("data", {}).get("supported"))
print("a client that speaks 2026-07-28 retries with:", err["data"]["supported"][0])

# %% [markdown]
# ## At work
# - Old servers stay in production for a long time, so gateways and clients keep both eras working during a deprecation window. MCP's deprecation policy keeps a deprecated feature for at least 12 months before removal → lesson 40.
# - Legacy sessions live in process memory. Teams either route every legacy request of one session to the same replica, or run the legacy leg stateless and accept that server-to-client calls stop → lesson 23.
# - A stateless legacy leg removes the back channel for elicitation and sampling. Use the modern elicitation flow, which works on both eras → lesson 12.

# %% [markdown]
# ## What just happened
# - One server answered two eras. The old client got `2025-11-25` after `mode="legacy"`. The default client probed and got `2026-07-28`.
# - The legacy session was an entry in worker A's memory. Worker B answered `404 Session not found` for it.
# - The stateless legacy leg issued no session. Worker D answered a request it had never seen the `initialize` for.
# - The model used two tools, one per server, in two calls. The host decided which server answered each call. The model never saw the protocol era.
# - An unknown version got error `-32022` with the versions the server supports. The client retries with one that both sides speak.

# %% [markdown]
# ## Common mistakes
# Pinning the old era with a version string. `mode` takes `"legacy"`, `"auto"`, or a 2026 version. A 2025 string is rejected on purpose, with a hint:

# %% tags=["raises-exception"]
async with Client(URL["A"], mode="2025-11-25") as wrong:   # raises ValueError: use mode="legacy"
    pass

# %% [markdown]
# Fix: write `mode="legacy"` for any 2025 or older server.
#
# Sending a legacy request with no session. A sticky worker needs the `Mcp-Session-Id` from its own `initialize`. Without it the worker refuses the request with `400 Missing session ID`:

# %%
no_session = legacy_post("A", {"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}})
print("status:", no_session.status_code, "|", no_session.json()["error"]["message"])

# %% [markdown]
# Fix: run `initialize` first on the same worker, keep the session id it returns, and send that id on every request. Or use the stateless leg, which needs no session.

# %% [markdown]
# ## Try it
# Using `legacy_post`, send `tools/list` with no session to worker C (stateless) and to worker A (sticky). Print both status codes. Then say in one sentence why the two workers answer differently. No model is needed.

# %%
# your code here
# Hint: legacy_post("C", {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}}) and the same for "A".

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
for w in ["C", "A"]:
    r = legacy_post(w, {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}})
    print(f"worker {w}: status {r.status_code}")
print("C is stateless: no session is needed. A is sticky: it refuses a request without the session it issued.")

# %% [markdown]
# Clean up: stop the four workers, and tell the recorder the lesson is done. This cell runs last.

# %%
for p in procs.values():
    p.terminate()
for p in procs.values():
    p.wait(timeout=10)
for f in logs.values():
    f.close()
llm_replay.stop()
print("workers stopped | lesson 07a done")

# %% [markdown]
# ## Key terms
# - **protocol era** — a generation of MCP: 2025-11-25 uses a handshake and a session; 2026-07-28 uses per-request `_meta`.
# - **era probing** — `Client(url)` in `mode="auto"` asks in the new era first, then falls back to the handshake.
# - **mode="legacy"** — the `Client` option that skips the probe and runs the `initialize` handshake.
# - **legacy session handshake** — the `initialize` request, the `Mcp-Session-Id` the server returns, and `notifications/initialized`.
# - **sticky session** — a legacy session kept in one worker's memory. Its requests must reach that worker, or the worker answers `404 Session not found`.
# - **stateless_http** — the server setting that keeps no legacy session. Any worker can answer, but server-to-client calls on that leg have no back channel.
# - **serving legacy clients** — a server that answers both eras, with sticky routing or the stateless leg for old clients.
