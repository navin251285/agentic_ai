# %% [markdown]
# # 07 · The stateless core of MCP 2026-07-28
# Level L2 · Part 2 · core · ~30 min · builds on 06

# %% [markdown]
# ## Goal
# By the end you run two Trackr workers on two ports. You send requests to them in turn and get the same answers. Each request carries its own protocol version. A request with an unknown version is refused with `-32022`, and you retry with a version both sides speak. You see that a worker's private memory is not shared state: the id a reply returns is a handle that works only on the worker that holds the record. A real model uses both workers in one conversation, two calls at most.

# %% [markdown]
# ## The idea
# The old protocol began with an `initialize` handshake. The server then kept a session for the client, keyed by `Mcp-Session-Id`, and only that worker could answer the next request.
#
# In MCP 2026-07-28 there is no handshake and no session. Each request carries its protocol version and the client's capabilities in `_meta`. Any worker can answer any request, so several workers can sit behind a load balancer.
#
# The state does not disappear. It moves to places the request names: the host's conversation list, the arguments of a tool call (such as the issue id in a later call), or a shared store. A worker's own memory is not one of them.
#
# Analogy: a print shop where every job slip states the paper size, the colour and the account. Any clerk at any counter can run the job from the slip alone.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   H[Host: one model conversation] -->|request 1, _meta: version + caps| A[Worker A :8771]
#   H -->|request 2, _meta: version + caps| B[Worker B :8772]
#   A -->|reply| H
#   B -->|reply| H
#   A -.-> MA[(A's own memory)]
#   B -.-> MB[(B's own memory)]
#   X[Unknown version 2099-01-01] -.->|-32022 Unsupported protocol version| A
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Check the lesson 03 server and write a worker file
# A worker is the lesson 03 Trackr server with a port taken from the command line. The first cell checks that the server exists. The next cell writes the worker file. Two copies of it run as two processes, so each has its own memory.

# %%
from pathlib import Path
TRACKR_DIR = Path("../apps/03").resolve()
assert (TRACKR_DIR / "trackr_server.py").exists(), "run lesson 03 first: it writes the Trackr server"
Path("../apps/07").mkdir(parents=True, exist_ok=True)
print("Trackr server found: ../apps/03/trackr_server.py")

# %% [markdown]
# The worker file below is the lesson 03 server with a port from the command line. The security settings are the same as in lesson 06.

# %%
%%writefile ../apps/07/trackr_worker.py
"""Trackr worker (lesson 07): the lesson 03 server on 127.0.0.1, one worker per port.

Each worker is its own process with its own memory. Two workers share no session."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03"))  # the lesson 03 server
from mcp.server.transport_security import TransportSecuritySettings
from trackr_server import mcp

PORT = int(sys.argv[1])   # the port is given by the notebook: 8771 or 8772
SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[f"127.0.0.1:{PORT}", f"localhost:{PORT}"],
)

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True,
            transport_security=SECURITY)

# %% [markdown]
# ### 2. The helpers: every request carries its own version
# `body` builds a JSON-RPC request. Its `_meta` holds the protocol version and the client's capabilities, so the request stands alone. `post` sends one POST to a named worker. The worker is `"A"` or `"B"`. Nothing else is sent between requests.

# %%
import httpx
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
META = {VERSION_KEY: "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {}}
URL = {"A": "http://127.0.0.1:8771/mcp", "B": "http://127.0.0.1:8772/mcp"}
BASE_HEADERS = {"Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": "2026-07-28"}

def body(method, params=None, req_id=1):
    """A JSON-RPC request. The version and capabilities ride in params._meta."""
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": {**(params or {}), "_meta": META}}

def post(worker, payload, extra=None):
    """One POST to the named worker. The headers repeat the method, and extra can add a name or a version."""
    headers = {**BASE_HEADERS, "Mcp-Method": payload["method"], **(extra or {})}
    return httpx.post(URL[worker], json=payload, headers=headers, timeout=10)

# %% [markdown]
# ### 3. Start both workers and wait until each answers
# The notebook starts two processes and polls each one with `server/discover`. It gives up after 20 seconds and stops the workers if the cell fails.

# %%
import atexit, subprocess, sys, time
WORKER_PORTS = {"A": 8771, "B": 8772}
procs, logs = {}, {}
for name, port in WORKER_PORTS.items():
    logs[name] = open(f"../apps/07/worker_{name}.log", "w")   # closed in the cleanup cell
    procs[name] = subprocess.Popen(
        [sys.executable, str(Path("../apps/07/trackr_worker.py").resolve()), str(port)],
        stdout=logs[name], stderr=subprocess.STDOUT)
atexit.register(lambda: [p.poll() is None and p.terminate() for p in procs.values()])
for name in WORKER_PORTS:
    deadline = time.monotonic() + 20
    while True:
        try:
            post(name, body("server/discover"))
            break
        except httpx.ConnectError:
            if procs[name].poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"worker {name} did not start: read ../apps/07/worker_{name}.log")
            time.sleep(0.2)
    print(f"worker {name} is up on port {WORKER_PORTS[name]}")

# %% [markdown]
# ### 4. Two workers, the same answers, and no session
# Ask each worker the same question with `server/discover`. Both reply with the same supported versions. Neither reply sets a session header, because there is no session to name.

# %%
for name in WORKER_PORTS:
    r = post(name, body("server/discover"))
    print(f"worker {name}: status {r.status_code} | versions {r.json()['result']['supportedVersions']} "
          f"| session header: {'mcp-session-id' in r.headers}")

# %% [markdown]
# ### 5. Alternate requests between the workers
# Now send four `count_open` calls and alternate the worker. Call 1 goes to A, call 2 to B, and so on. Each call is one POST with a full `_meta`. The workers never talk to each other, and no call depends on the one before it.

# %%
for i, worker in enumerate(["A", "B", "A", "B"]):
    team = ["web", "api"][i % 2]
    call = body("tools/call", {"name": "count_open", "arguments": {"team": team}}, req_id=10 + i)
    r = post(worker, call, {"Mcp-Name": "count_open"})
    print(f"call {i + 1} to worker {worker}: open {team} issues = {r.json()['result']['structuredContent']['result']}")

# %% [markdown]
# ### 6. Each request names its own version
# The version is part of the request, so a server can check each one. Build the same request with an unknown version, `2099-01-01`, in `_meta` and in the header. The worker refuses it with JSON-RPC error `-32022`, "Unsupported protocol version". Its `data` lists the versions it does support.

# %%
def with_version(payload, version):
    """The same request, with another protocol version in its _meta."""
    return {**payload, "params": {**payload["params"], "_meta": {**META, VERSION_KEY: version}}}

unknown = with_version(body("server/discover"), "2099-01-01")
r = post("A", unknown, {"MCP-Protocol-Version": "2099-01-01"})
err = r.json()["error"]
print("status:", r.status_code)
print("error code:", err["code"], "|", err["message"])
print("data:", err["data"])

# %% [markdown]
# A client that speaks 2026-07-28 can recover. It reads `supported` from the error, picks a version it also speaks, and retries the same request once. The helper below does that.

# %%
WE_SPEAK = ["2026-07-28"]

def send_negotiated(worker, payload):
    """Send with the request's own version. On -32022, retry once with a version both sides speak."""
    version = payload["params"]["_meta"][VERSION_KEY]
    reply = post(worker, payload, {"MCP-Protocol-Version": version})
    error = reply.json().get("error", {})
    if error.get("code") == -32022:
        mutual = [v for v in error["data"]["supported"] if v in WE_SPEAK]
        if not mutual:
            raise RuntimeError(f"no shared version; the server speaks {error['data']['supported']}")
        payload = with_version(payload, mutual[-1])
        reply = post(worker, payload, {"MCP-Protocol-Version": mutual[-1]})
    return reply

retry = send_negotiated("B", with_version(body("server/discover"), "2099-01-01"))
print("after retry: status", retry.status_code, "| versions", retry.json()["result"]["supportedVersions"])

# %% [markdown]
# ### 7. A real model uses both workers (`needs-llm`)
# The host is the one that keeps the conversation. It holds one tool list and one message list, and it decides which worker runs each call. Here the host alternates the calls between A and B. The model never learns which worker answered (the tool result has no worker field).
#
# The setup cell imports the adapter and the recorder. `MCPAdapter` is beta, so its logs are muted.

# %%
import logging, warnings, itertools
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)  # the adapter is still beta
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("fastmcp").setLevel(logging.WARNING)
from contextlib import AsyncExitStack
from langchain.mcp import MCPAdapter
from langchain_core.messages import AIMessage, HumanMessage
import sys
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
import llm_replay
QUESTION = HumanMessage("How many open issues do the web and api teams have? Use the tools.")
llm = None   # filled by the model cell; stays None if that cell is skipped
print("question:", QUESTION.content)

# %% [markdown]
# Each worker gets its own adapter. Both adapters list the same tools, so the host takes its list from worker A and sends the calls round-robin.

# %%
stack = AsyncExitStack()   # the adapters stay open for the model cells; closed after them
adapter_a = await stack.enter_async_context(MCPAdapter({"mcpServers": {"trackr": {"url": URL["A"]}}}))
adapter_b = await stack.enter_async_context(MCPAdapter({"mcpServers": {"trackr": {"url": URL["B"]}}}))
tools_a = {t.name: t for t in await adapter_a.list_tools()}
tools_b = {t.name: t for t in await adapter_b.list_tools()}
assert sorted(tools_a) == sorted(tools_b) and "count_open" in tools_a
print("both workers list:", sorted(tools_a))
turn = itertools.cycle([("A", tools_a), ("B", tools_b)])   # the host alternates the workers

# %% [markdown]
# The model cell asks which tools to call. It may ask for both counts in one turn. The host then runs each requested call on the next worker in turn.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("07_stateless-core", max_calls=2)
first = await llm.bind_tools(list(tools_a.values())).ainvoke([QUESTION])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model cell was skipped, scripted calls stand in for the model's first reply. The stand-in is labelled.

# %%
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[
        {"name": "count_open", "args": {"team": "web"}, "id": "scripted_1"},
        {"name": "count_open", "args": {"team": "api"}, "id": "scripted_2"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# The host runs each call on the next worker. Call 1 goes to A and call 2 goes to B. Each adapter sends its POST to its own URL.

# %%
results = []
for c in first.tool_calls:
    worker, tools = next(turn)
    result = await tools[c["name"]].ainvoke(c)
    results.append(result)
    print(f"{c['args']} ran on worker {worker} -> {result.text}")

# %% [markdown]
# The model reads both results and writes its answer. This is its second and last call (`needs-llm`). Its input is the whole list so far: the question, its own first reply and the results. That list is the conversation state, and the host holds it.

# %% tags=["needs-llm"]
final = await llm.bind_tools(list(tools_a.values())).ainvoke([QUESTION, first, *results])
print("answer:", final.text)

# %% [markdown]
# Without a model there is no written answer, so the fallback prints what the workers returned.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). The workers said:", [r.text for r in results])

# %% [markdown]
# The adapters are done, so close them here.

# %%
await stack.aclose()
print("adapters closed | the workers are still running for the checks below")

# %% [markdown]
# ### 8. Where state lives: the worker's own memory is not shared
# `create_issue` adds an issue to the memory of the worker that receives it. The stateless protocol does not copy that change to the other worker. So a search on B does not see an issue that A created. The id in the reply, 21, is an explicit handle: a request that names it finds the issue only where the record lives. In this lesson each worker holds its own copy, so the handle works only on the worker that made the issue.

# %%
new = body("tools/call", {"name": "create_issue",
                          "arguments": {"title": "Cache serves stale prices", "team": "infra", "severity": "high"}}, req_id=30)
created = post("A", new, {"Mcp-Name": "create_issue"})
print("created on A:", created.json()["result"]["structuredContent"])
for worker in ["A", "B"]:
    search = body("tools/call", {"name": "search_issues", "arguments": {"text": "stale"}}, req_id=31)
    found = post(worker, search, {"Mcp-Name": "search_issues"}).json()["result"]["structuredContent"]["result"]
    print(f"search 'stale' on worker {worker}: {len(found)} match(es)")

# %% [markdown]
# Now use the handle. Each worker gets a `close_issue` call for id 21. B does not hold the record, so it cannot find the id. A can.

# %%
for worker in ["B", "A"]:
    close = body("tools/call", {"name": "close_issue", "arguments": {"issue_id": 21}}, req_id=32)
    reply = post(worker, close, {"Mcp-Name": "close_issue"}).json()["result"]
    print(f"close 21 on worker {worker}: isError={reply.get('isError', False)} | {' '.join(reply['content'][0]['text'].split())}")

# %% [markdown]
# ## At work
# - Stateless servers scale by adding workers behind a load balancer, with no sticky sessions. Teams run many copies of one server and let any copy take any request → lesson 23.
# - The state that a session used to hold must move somewhere shared: a database, a cache or a signed token. Otherwise a worker that did not see the first request cannot answer the second → lesson 12 (state for server-to-client questions) and lesson 23 (shared keys and the subscription bus).
# - A gateway in front of many servers reads the routing headers on every request, so it can route and count without a session to look up → lesson 40.

# %% [markdown]
# ## What just happened
# - There was no handshake and no session. Every request carried its version and capabilities in `_meta`, and the header repeated the version.
# - Two workers answered the same requests with the same answers. The calls alternated between them, and no call depended on an earlier one.
# - A request with an unknown version was refused with `-32022`. Its `data` listed the versions the worker supports. The client retried once with a shared version.
# - The model ran through two adapters, one per worker. The host kept the conversation and chose the worker for each call.
# - The issue created on A was not visible on B. The id 21 worked as a handle only on A, because only A holds the record. A worker's memory is not a place a request can name, so it is not shared state.

# %% [markdown]
# ## Common mistakes
# Starting with the old handshake. An `initialize` request is not a modern request. It has no `_meta` envelope, so the worker refuses it. Print the reply first to see the reason:

# %%
init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}}}
r = post("A", init)
print("status:", r.status_code, "| error:", r.json()["error"])

# %% [markdown]
# The error gives the reason: `params._meta` must carry the version and capabilities keys. `raise_for_status()` keeps only the status code, so this is what it raises:

# %% tags=["raises-exception"]
post("A", init).raise_for_status()   # raises the 400; the reason was printed above

# %% [markdown]
# Fix: send a modern request. Put the version in `_meta` on every request, and send `server/discover` if you want the server's versions first.
#
# A second mistake is to send a version the server does not speak and then raise on the HTTP status. The refusal is a JSON error with code `-32022`, and it carries the versions the client needs to recover. `raise_for_status()` throws that away and keeps only the `400`:

# %% tags=["raises-exception"]
bad = post("B", with_version(body("tools/list"), "2099-01-01"), {"MCP-Protocol-Version": "2099-01-01"})
bad.raise_for_status()   # raises the 400 and hides the -32022 body that holds the supported versions

# %% [markdown]
# Fix: check `error.code` for `-32022`, pick a version from `error.data.supported`, and retry, as `send_negotiated` does.

# %% [markdown]
# ## Try it
# Using the `post` and `body` helpers, send a `count_open` call for `"mobile"` to worker A and to worker B, and print both counts. Then send `tools/list` with the version `2025-11-25`, and print the status, the error code and the message. `2025-11-25` is a legacy version, so the worker does not answer with `-32022`. Read the message and say what it tells you about the old protocol. Hint: the old protocol needed a session first. No model is needed.

# %%
# your code here
# Start from: post("A", body("tools/call", {"name": "count_open", "arguments": {"team": "mobile"}}), {"Mcp-Name": "count_open"})
# Then use with_version(body("tools/list"), "2025-11-25") with the matching MCP-Protocol-Version header.

# %% [markdown]
# Clean up: stop both workers and tell the recorder the lesson is done. This cell runs last.

# %%
for p in procs.values():
    p.terminate()
for p in procs.values():
    p.wait(timeout=10)
for f in logs.values():
    f.close()
llm_replay.stop()
print("workers stopped | lesson 07 done")

# %% [markdown]
# ## Key terms
# - **stateless protocol** — a protocol where each request stands alone: the server keeps no session that a later request must find.
# - **per-request version negotiation** — each request names its protocol version in `_meta`, and the server accepts or refuses that request alone.
# - **UnsupportedProtocolVersionError** — the protocol error, code `-32022`, that a server returns for a version it does not support. Its `data` lists the versions it does support.
# - **explicit state handle** — a name a request carries, such as an id, a cursor or a shared-store key, that lets a worker find the state. The name works only where the state is stored.
# - **worker** — one process that answers requests. Several workers can run behind a load balancer.
# - **server/discover** — the request that returns the server's supported versions and capabilities.
