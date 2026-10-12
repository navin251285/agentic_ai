# %% [markdown]
# # 06 · Remote servers: the Streamable HTTP transport
# Level L2 · Part 2 · core · ~35 min · builds on 05

# %% [markdown]
# ## Goal
# By the end Trackr runs as its own process on `127.0.0.1:8766` over Streamable HTTP. You send a `tools/call` by hand with `httpx`: one POST to one endpoint, with the routing headers. You see a `HeaderMismatch` and a forged `Origin` refused. Then a real model uses the same server by its URL.

# %% [markdown]
# ## The idea
# Stdio runs a server as a child process on one machine. A remote server runs elsewhere, and many clients call it over the network. Streamable HTTP is that network transport. It has one endpoint, `/mcp`, and every client message is an HTTP POST to it.
#
# Each POST repeats its routing facts in two headers, `Mcp-Method` and `Mcp-Name`. A proxy can route and count calls without reading the body. The server checks that the headers match the body. It also checks the `Origin` header, so a web page from another site cannot drive it, and it listens on `127.0.0.1` only.
#
# Analogy: a shop with one counter. Every order comes to the same window, and each slip shows the order type on the outside (the headers) as well as inside (the body). The clerk checks the two match, and turns away slips from shops that are not on the list.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   C[Client: httpx or the SDK] -->|POST /mcp, Mcp-Method, Mcp-Name| S[Trackr on 127.0.0.1:8766]
#   S -->|one JSON-RPC reply| C
#   C -.->|GET /mcp| S
#   S -.->|405: POST only| C
#   W[Web page from another site] -.->|Origin not in the list| S
#   S -.->|403 Forbidden| W
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Write the HTTP server file
# Trackr is the lesson 03 server, still in `../apps/03`. The first cell checks that it is there. The cell after it writes a file that imports Trackr and serves it over Streamable HTTP instead of stdio. The only new code is the transport and its security settings.

# %%
from pathlib import Path
TRACKR_DIR = Path("../apps/03").resolve()
assert (TRACKR_DIR / "trackr_server.py").exists(), "run lesson 03 first: it writes the Trackr server"
Path("../apps/06").mkdir(parents=True, exist_ok=True)
print("Trackr is in", TRACKR_DIR)

# %% [markdown]
# The file below is the whole HTTP server. `allowed_origins` lists the one web dashboard that may call it from a browser. Every other origin is refused.
#
# `json_response=True` makes each reply one plain JSON object instead of an event stream; that is why the replies in step 3 are `application/json`.
# `allowed_hosts` is the DNS-rebinding check: a hostile web page can resolve its own domain to 127.0.0.1, but the browser still sends that domain in the `Host` header, which is not on the list, so the server refuses it.
# The `sys.path` line only lets this file import the lesson 03 server.

# %%
%%writefile ../apps/06/trackr_http.py
"""Trackr over Streamable HTTP (lesson 06): the lesson 03 server on 127.0.0.1:8766."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03"))  # the lesson 03 server
from mcp.server.transport_security import TransportSecuritySettings
from trackr_server import mcp

PORT = 8766
SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[f"127.0.0.1:{PORT}", f"localhost:{PORT}"],   # Host header values we accept
    allowed_origins=["http://localhost:3000"],                  # the team's web dashboard, and no one else
)

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True,
            transport_security=SECURITY)

# %% [markdown]
# ### 2. Start the server as its own process and wait until it answers
# The server runs in a child process, as it would on a real host. The helpers below build every request the same way, so the later steps only change what they test. `body` builds the JSON-RPC message, and `_meta` carries the protocol version on every request. `post` sends one POST to `/mcp`.

# %%
import httpx
URL = "http://127.0.0.1:8766/mcp"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {}}
# Accept: the server may reply with plain JSON or an event stream, so the client must say it accepts both.
# MCP-Protocol-Version: the same version as in _meta, repeated in a header so a proxy can see it.
BASE_HEADERS = {"Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": "2026-07-28"}

def body(method, params=None, req_id=1):
    """A JSON-RPC request. Every request carries its protocol version in params._meta."""
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": {**(params or {}), "_meta": META}}

def post(payload, extra=None):
    """One POST to /mcp. Mcp-Method always comes from the body; extra holds Mcp-Name and Origin."""
    headers = {**BASE_HEADERS, "Mcp-Method": payload["method"], **(extra or {})}
    return httpx.post(URL, json=payload, headers=headers, timeout=10)

# %% [markdown]
# The cell below starts the server. The notebook does not sleep for a fixed time. It polls with a `server/discover` request until the server replies, or gives up after 20 seconds. It also stops the server if the cell fails.

# %%
import atexit, subprocess, sys, time
from pathlib import Path
server_log = open("../apps/06/server.log", "w")   # closed in the cleanup cell
proc = subprocess.Popen([sys.executable, str(Path("../apps/06/trackr_http.py").resolve())],
                        stdout=server_log, stderr=subprocess.STDOUT)
atexit.register(lambda: proc.poll() is None and proc.terminate())   # also stops it if a cell fails
deadline = time.monotonic() + 20
while True:
    try:
        up = post(body("server/discover"))
        break
    except httpx.ConnectError:
        if proc.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("server did not start: read ../apps/06/server.log")
        time.sleep(0.2)
print("server answered:", up.status_code, "| supported versions:", up.json()["result"]["supportedVersions"])

# %% [markdown]
# ### 3. One POST: a `tools/call` by hand
# There is no `initialize` step and no session id (lesson 07 explains why). Each POST stands alone. The body says which tool to run. The headers say the same thing again: `Mcp-Method` says `tools/call`, and `Mcp-Name` says `count_open`. The reply is one JSON object.
#
# `Mcp-Param-*` headers copy chosen tool arguments for gateways; a server opts in per argument. Trackr does not, so you do not send them here (lesson 40).

# %%
call = body("tools/call", {"name": "count_open", "arguments": {"team": "web"}})
r = post(call, {"Mcp-Name": "count_open"})
print("status:", r.status_code, "| content type:", r.headers["content-type"])
print("open web issues:", r.json()["result"]["structuredContent"])

# %% [markdown]
# ### 4. The routing headers must match the body
# Suppose a proxy routed the call by the `Mcp-Name` header. A client that sends `close_issue` in the header but `count_open` in the body would make the proxy and the server disagree about what ran. The server checks this. It refuses the request with JSON-RPC error `-32020`, named `HeaderMismatch`.

# %%
wrong = post(call, {"Mcp-Name": "close_issue"})   # the body still says count_open
print("status:", wrong.status_code)
print("error:", wrong.json()["error"])

# %% [markdown]
# ### 5. What the endpoint refuses: GET, and an Origin not on the list
# The endpoint takes POST only. A GET gets `405 Method Not Allowed`. The `Origin` header decides who may call. A request with no `Origin` (a script, or the Python client) is allowed. A request from the dashboard origin is allowed. A request from any other origin gets `403`.

# %%
checks = {
    "GET /mcp": httpx.get(URL, headers=BASE_HEADERS, timeout=10),
    "POST, Origin http://localhost:3000 (dashboard)": post(body("tools/list"), {"Origin": "http://localhost:3000"}),
    "POST, Origin http://evil.example": post(body("tools/list"), {"Origin": "http://evil.example"}),
    "POST, no Origin (a script)": post(body("tools/list")),
}
for name, resp in checks.items():
    print(f"{name:48} -> {resp.status_code}")

# %% [markdown]
# ### 6. The same server through the SDK `Client`
# You do not have to write headers yourself. `Client` takes the URL and does the POSTs, the headers and the `_meta` for you. It is the same server, so the answers match the raw calls above.

# %%
from mcp import Client
async with Client(URL) as client:
    tools = await client.list_tools()
    print("tools:", [t.name for t in tools.tools])
    reply = await client.call_tool("count_open", {"team": "web"})
    print("open web issues:", reply.structured_content, "| is_error:", reply.is_error)

# %% [markdown]
# ### 7. A real model uses the server by URL (`needs-llm`)
# Now the model gets the server the same way a desktop host would: a config entry with a `url`, not a command. `MCPAdapter` reads it and gives the model one tool list. The model makes two calls at most: one to ask for a tool, and one to write the answer.
#
# First, a quiet setup cell. The adapter is beta and its logs are noise here.

# %%
import logging, warnings
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)  # the adapter is still beta
logging.getLogger("httpx").setLevel(logging.WARNING)     # hide httpx's INFO line, which prints the model URL
logging.getLogger("fastmcp").setLevel(logging.WARNING)   # the adapter's proxy banner is noise here

# %% [markdown]
# The adapter connects by URL. `list_tools()` asks the server for its tools, the same `tools/list` call as before.

# %%
from contextlib import AsyncExitStack
from langchain.mcp import MCPAdapter
stack = AsyncExitStack()   # the adapter stays open for the model cells; closed at the end
adapter = await stack.enter_async_context(MCPAdapter({"mcpServers": {"trackr": {"url": URL}}}))
mcp_tools = await adapter.list_tools()
by_name = {t.name: t for t in mcp_tools}
print(sorted(by_name))
assert "count_open" in by_name

# %% [markdown]
# The question and the recorder come next. `get_llm` (in the model cell) picks the model and starts the recording or the replay for this lesson.

# %%
import sys
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
import llm_replay
from langchain_core.messages import AIMessage, HumanMessage
QUESTION = HumanMessage("How many open issues does the web team have? Use a tool.")
llm = None   # filled by the model cell; stays None if that cell is skipped
print("question:", QUESTION.content)

# %% [markdown]
# The model cell below asks the model which tool to use. It first prints the course's model picker. The line to read is `model asks for`.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("06_streamable-http", max_calls=2)
first = await llm.bind_tools(mcp_tools).ainvoke([QUESTION])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model cell was skipped, a scripted tool call stands in for the model's first reply. The stand-in is labelled.

# %%
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[{"name": "count_open", "args": {"team": "web"}, "id": "scripted_1"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# The host runs each requested tool through the adapter. The adapter sends the call to the URL as a POST, with the routing headers.

# %%
results = [await by_name[c["name"]].ainvoke(c) for c in first.tool_calls]
for r in results:
    print("ToolMessage status:", r.status, "| text:", r.text)

# %% [markdown]
# The model reads the result and writes its answer. This is its second and last call (`needs-llm`).

# %% tags=["needs-llm"]
final = await llm.bind_tools(mcp_tools).ainvoke([QUESTION, first, *results])
print("answer:", final.text)

# %% [markdown]
# Without a model there is no written answer, so the fallback prints what the tool returned.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). The tool said:", results[0].text)

# %% [markdown]
# ### 8. Close the adapter
# The adapter is done with the model cells. The server stays up for the checks that follow, and the last cell stops it.

# %%
await stack.aclose()
print("adapter closed | the server is still running for the checks below")

# %% [markdown]
# ## At work
# - A gateway in front of many remote servers reads `Mcp-Method` and `Mcp-Name` to apply per-tool limits and metrics, without parsing each body. Cloudflare's MCP gateway post describes metering per tool this way. Teams put one gateway in front of their servers, and it enforces policy in one place → lesson 40.
# - Remote servers on the 2026-07-28 revision are stateless, so any worker can answer any POST. Teams scale by adding workers behind a load balancer, with no sticky sessions → lesson 23.
# - Origin checks and localhost binding stop a browser page or a LAN host from calling your tools. They do not prove who the caller is. A remote server needs OAuth, with scopes on every tool → lesson 15.

# %% [markdown]
# ## What just happened
# - The server ran as its own process and answered on one URL. Every message was a POST to `/mcp`, so there was no handshake and no session to keep (lesson 07 explains why).
# - Each POST repeated its routing facts in headers. The server checked that `Mcp-Name` matched the body, and refused a mismatch with `-32020 HeaderMismatch`.
# - GET was refused with `405`, and an unlisted `Origin` was refused with `403`. A request with no `Origin` passed, because a script is not a browser.
# - `Client(URL)` and `MCPAdapter` with `{"url": ...}` did the same POSTs. The model asked for `count_open`, and the adapter sent the call to the URL.

# %% [markdown]
# ## Common mistakes
# Sending a header that disagrees with the body. The server answers with a 400 and a `-32020` error. Calling `raise_for_status()` on that reply turns it into an exception that names the status:

# %% tags=["raises-exception"]
bad = post(call, {"Mcp-Name": "close_issue"})   # the header says close_issue, the body says count_open
bad.raise_for_status()                          # raises httpx.HTTPStatusError: 400 Bad Request

# %% [markdown]
# Fix: send the same name in `Mcp-Name` and in `params.name`. Let the client library set the headers, and use raw headers only to learn the protocol.
#
# A second mistake is a GET to the endpoint, as if it were a stream. The endpoint answers 405, so the call fails. Here is the error as `raise_for_status()` shows it:

# %% tags=["raises-exception"]
httpx.get(URL, headers=BASE_HEADERS, timeout=10).raise_for_status()   # raises: 405 Method Not Allowed

# %% [markdown]
# Fix: send a POST for every message. The server has no GET stream in this revision (lesson 07 explains why).

# %% [markdown]
# ## Try it
# The server is still running, so use the `post` helper from step 2. Send a `tools/call` for `search_issues` with the text `"safari"` and `Mcp-Name` set to `search_issues`. Print the status and the number of matches. Then send the same call with `Origin: http://evil.example` and print the status. No model is needed.

# %%
# your code here
# Start from the helper: body("tools/call", {"name": "search_issues", "arguments": {"text": "safari"}}),
# then post(payload, {"Mcp-Name": "search_issues"}) and post(payload, {"Mcp-Name": "search_issues", "Origin": "http://evil.example"}).

# %% [markdown]
# Clean up: stop the server process and tell the recorder the lesson is done. This cell runs last.

# %%
proc.terminate()
proc.wait(timeout=10)
server_log.close()
llm_replay.stop()
print("server stopped | lesson 06 done")

# %% [markdown]
# ## Key terms
# - **Streamable HTTP** — the MCP transport for remote servers: one endpoint, `/mcp`, where every client message is an HTTP POST.
# - **POST-only endpoint** — in this revision the endpoint takes POST only. A GET gets `405`.
# - **routing headers** — `Mcp-Method` and `Mcp-Name`, copies of the method and tool name, so a proxy can route without parsing the body.
# - **HeaderMismatch** — the `-32020` error the server returns when a routing header disagrees with the body.
# - **Origin validation** — the server checks the `Origin` header and refuses origins it does not list, with `403`.
# - **TransportSecuritySettings** — the SDK object that holds the allowed hosts and origins and turns on DNS-rebinding protection.
# - **localhost binding** — listening on `127.0.0.1` so only this machine can connect.
