# %% [markdown]
# # 01 · JSON-RPC 2.0 and MCP by hand
# Level L1 · Part 1 · core · ~30 min · builds on 00

# %% [markdown]
# ## Goal
# By the end you can start a tiny Trackr MCP server as a subprocess, type raw JSON-RPC 2.0 messages into its stdin, and read every reply: `server/discover`, `tools/list` and `tools/call` (each with its `_meta`), plus one **result**, one **error** and one **notification**. No model, no SDK client: just the protocol.

# %% [markdown]
# ## The idea
# MCP messages are plain JSON. They follow **JSON-RPC 2.0**, a small standard with three message kinds:
# - a **request** has an `id` and a `method`, and expects exactly one reply;
# - the reply is either a **result** or an **error**, and carries the same `id`;
# - a **notification** has a `method` but **no** `id`, so nobody replies.
#
# On the **stdio** transport, the client starts the server as a child process and writes one JSON message per line to its stdin. The server writes one reply per line to its stdout.
#
# Analogy: passing numbered notes under a door. You write "#3: how many open web issues?" and wait for a note marked "#3". A note with no number is just for information; no answer comes back.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant H as Host (this notebook)<br/>+ its MCP client
#   participant S as MCP server<br/>(subprocess: trackr_server.py)
#   H->>S: stdin: {"id":1,"method":"server/discover",...}
#   S-->>H: stdout: {"id":1,"result":{...}}
#   H->>S: stdin: {"id":2,"method":"tools/list",...}
#   S-->>H: stdout: {"id":2,"result":{"tools":[...]}}
#   H->>S: stdin: {"id":3,"method":"tools/call",...}
#   S-->>H: stdout: {"id":3,"result":{"content":[...]}}
#   H->>S: stdin: {"method":"notifications/cancelled",...} (no id)
#   Note over S: no reply to a notification
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Three roles: host, client, server
# MCP names three roles:
# - **host**: the app the user works in (Claude Desktop, an IDE, this notebook). It owns the model and the user.
# - **client**: the part of the host that speaks MCP to **one** server. A host with three servers has three clients.
# - **server**: a program that offers tools and data. Here it is Trackr.
#
# In this lesson the notebook is the host, and a few lines of Python play the client. First, make a folder for the server file.

# %%
import json, subprocess, sys, queue, threading
from pathlib import Path

APP_DIR = Path("../apps/01")
APP_DIR.mkdir(parents=True, exist_ok=True)
print("server folder:", APP_DIR.resolve().relative_to(Path("..").resolve()))

# %% [markdown]
# ### 2. The server: Trackr's 20 issues and one tool
# This is a real MCP server built with the official `mcp` 2.x SDK. It holds the same 20 issues as lesson 00 and offers one tool, `count_open(team)`. The tool logic is the same one-line count you wrote there. `MCPServer` turns the function into an MCP tool: its name, its docstring and its type hints become the tool's description.

# %%
%%writefile ../apps/01/trackr_server.py
"""Trackr MCP server (lesson 01): 20 in-memory issues, one tool, stdio transport."""
from mcp.server import MCPServer

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

mcp = MCPServer("Trackr")

@mcp.tool()
def count_open(team: str) -> int:
    """Count open Trackr issues for a team: web, api, mobile or infra."""
    return sum(1 for i in ISSUES if i["team"] == team and i["status"] == "open")

if __name__ == "__main__":
    mcp.run()          # default transport: stdio (reads stdin, writes stdout)

# %% [markdown]
# ### 3. Start the server as a subprocess
# The client starts the server and keeps three pipes: stdin (we write), stdout (we read), stderr (the server's own log, which we send to a file). A small background thread reads stdout line by line into a queue, so we can wait for a reply **with a timeout** instead of hanging forever.

# %%
server = subprocess.Popen(
    [sys.executable, str(APP_DIR / "trackr_server.py")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=open(APP_DIR / "server.log", "w"), text=True, bufsize=1)

replies: queue.Queue = queue.Queue()
def _pump():                              # stdout -> queue, one line at a time
    for line in server.stdout:
        replies.put(line)
threading.Thread(target=_pump, daemon=True).start()
print("server started, pid", server.pid)

# %% [markdown]
# Two helpers are the whole "client". `send` writes one message as **one line** of JSON plus `\n`. `recv` waits for one line and parses it.

# %%
def send(message: dict) -> None:
    line = json.dumps(message)            # compact: no newlines inside
    print(">>", line[:150])
    server.stdin.write(line + "\n")
    server.stdin.flush()

def recv(timeout: float = 10.0) -> dict:
    try:
        return json.loads(replies.get(timeout=timeout))
    except queue.Empty:
        raise TimeoutError(f"no reply within {timeout}s") from None

print("send() and recv() ready")

# %% [markdown]
# ### 4. Every request carries `_meta`
# In MCP 2026-07-28 there is no opening handshake. Instead, **every** request says who is asking and which protocol version it speaks, inside `params._meta`. The keys start with `io.modelcontextprotocol/` so they never clash with your own keys.

# %%
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "lesson-01-notebook", "version": "0.1"},
    "io.modelcontextprotocol/clientCapabilities": {},   # we offer the server nothing extra
}

def request(id_: int, method: str, **params) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": {**params, "_meta": META}}

print(json.dumps(request(1, "server/discover"), indent=2))

# %% [markdown]
# ### 5. `server/discover`: what does this server support?
# Every MCP server must answer `server/discover`. A client may call it first to learn the server's protocol versions and **capabilities** (which feature groups it offers). It also works as a health check: if a reply comes back, the server is up.

# %%
send(request(1, "server/discover"))
disc = recv()
print("id      :", disc["id"])
print("versions:", disc["result"]["supportedVersions"])
print("features:", list(disc["result"]["capabilities"]))
print("server  :", disc["result"]["_meta"]["io.modelcontextprotocol/serverInfo"])

# %% [markdown]
# The `>>` line is the request we sent. The reply has the same `id` (1) and a `result`. Its `_meta` carries `serverInfo`: the server introduces itself on every reply, just as the client does on every request. `MCPServer` lists tools, resources and prompts by default, even though Trackr only has a tool so far.

# %% [markdown]
# ### 6. `tools/list`: the server describes its own tools
# This is the fix for lesson 00's fragile glue. The client does not copy the tool's description by hand; it **asks** the server. If the server renames an argument, the next `tools/list` shows the new name.

# %%
send(request(2, "tools/list"))
tools = recv()["result"]["tools"]
for t in tools:
    print("name       :", t["name"])
    print("description:", t["description"])
    print("inputSchema:", json.dumps(t["inputSchema"]))
    print("outputSchema:", json.dumps(t["outputSchema"]))

# %% [markdown]
# `inputSchema` is JSON Schema built from the type hint `team: str`; `required: ["team"]` comes from it having no default. This is exactly what a host hands to a model as a tool description (lesson 01a).

# %% [markdown]
# ### 7. `tools/call`: run the tool (a **result**)
# Name the tool and pass its arguments. The server runs the Python function and wraps the answer.

# %%
send(request(3, "tools/call", name="count_open", arguments={"team": "web"}))
call = recv()
print("id               :", call["id"])
print("content          :", call["result"]["content"])
print("structuredContent:", call["result"]["structuredContent"])
print("isError          :", call["result"]["isError"])

# %% [markdown]
# The answer comes twice: `content` is text for a model to read; `structuredContent` is typed JSON (matching `outputSchema`) for code. The web team has 3 open issues (#1, #9, #17); the closed #3 and #13 are not counted.

# %% [markdown]
# ### 8. An unknown method (an **error**)
# Ask for something the server does not offer. JSON-RPC answers with an `error` object instead of `result`. The code `-32601` is JSON-RPC's standard "Method not found".

# %%
send(request(4, "issues/delete"))
err = recv()
print("id   :", err["id"])
print("error:", err["error"])
print("has result?", "result" in err)

# %% [markdown]
# Compare a **tool** failing. Call `count_open` without its `team` argument. The protocol call worked, so the reply is a `result`, but `isError: true` says the tool itself failed. A model can read that text and try again; a JSON-RPC error is for the client code.

# %%
send(request(5, "tools/call", name="count_open", arguments={}))
bad = recv()["result"]
print("isError:", bad["isError"])
print("text   :", bad["content"][0]["text"].splitlines()[0])

# %% [markdown]
# ### 9. A **notification**: no `id`, no reply
# A notification is a message nobody answers. On stdio, a client can send `notifications/cancelled` to say "forget request N". We send one and wait 2 seconds: nothing comes back. Then a normal request shows the server is still alive.

# %%
send({"jsonrpc": "2.0", "method": "notifications/cancelled",
      "params": {"requestId": 3, "reason": "user pressed stop"}})
try:
    print("unexpected reply:", recv(timeout=2))
except TimeoutError as e:
    print("no reply, as expected:", e)
send(request(6, "server/discover"))
print("still alive, reply id:", recv()["id"])

# %% [markdown]
# ### 10. What `_meta` is for
# Drop a required `_meta` key and the server refuses the request with `-32602` ("Invalid params"). Because each request carries its own version and capabilities, any server process can answer any request with no memory of earlier ones. That is the "stateless" core you will meet in lesson 07.

# %%
partial = {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}   # clientCapabilities missing
send({"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {"_meta": partial}})
print(recv()["error"])

# %% [markdown]
# ## At work
# - Teams check servers in CI like this, with no model: the MCP Inspector CLI runs `tools/list` and the output is snapshotted, so a changed tool description shows up in review → lesson 27.
# - A stdio server runs with **your** permissions. In April 2026 OX Security reported about 10 CVEs (Windsurf, LiteLLM, Flowise…) where an MCP config could launch any command; hosts must sandbox servers and treat configs as untrusted → lessons 05b and 29a.
# - Because every request carries its own `_meta`, any worker can answer any request; Cloudflare runs MCP on serverless workers at billions of tool calls → lesson 07.
# - Gateways route MCP traffic by method and tool name (`Mcp-Method` / `Mcp-Name` HTTP headers) without parsing the body → lessons 06 and 40.

# %% [markdown]
# ## What just happened
# - The notebook was the **host**; `send`/`recv` were its **client**; `trackr_server.py` was the **server**, started as a subprocess on the **stdio** transport.
# - Each message was one line of JSON-RPC 2.0. Requests had an `id`; each reply had the same `id` and either a `result` or an `error`.
# - `server/discover` returned versions and capabilities; `tools/list` returned the tool's own schema; `tools/call` returned `content`, `structuredContent` and `isError`.
# - An unknown method gave a JSON-RPC **error** (`-32601`); a bad tool argument gave a **result** with `isError: true`.
# - A **notification** (no `id`) got no reply.
# - Every request carried `_meta` (version, client info, capabilities), and every reply carried `serverInfo`.

# %% [markdown]
# ## Common mistakes
# Pretty-printing the JSON. On stdio, one message is one **line**. `json.dumps(..., indent=2)` puts newlines inside the message, so the server sees many broken lines, drops them, and never replies:

# %% tags=["raises-exception"]
msg = request(8, "tools/list")
server.stdin.write(json.dumps(msg, indent=2) + "\n")   # many lines, none of them valid JSON
server.stdin.flush()
recv(timeout=3)

# %% [markdown]
# Fix: send compact JSON with exactly one `\n` at the end, as `send()` does. The server ignored the broken lines and still works.

# %%
send(request(8, "tools/list"))
reply = recv()
print("reply id:", reply["id"], "- tools:", [t["name"] for t in reply["result"]["tools"]])

# %% [markdown]
# Two more: forgetting the `id` turns a request into a notification, so you wait forever for an answer that will never come; and printing debug text to **stdout** inside a stdio server mixes it into the protocol stream (log to stderr instead; lesson 05b).

# %% [markdown]
# ## Try it
# Use `send`, `recv` and `request` to ask the server for the open count of **every** team (`web`, `api`, `mobile`, `infra`) with one `tools/call` each, using ids 20–23. Read the number from `structuredContent`, print a small table and the total. Then send the unknown method `issues/close` with id 24 and print only its error code.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **JSON-RPC 2.0** — a small standard for JSON messages: requests, replies, notifications.
# - **request** — a JSON-RPC message with an `id` and a `method`; it gets exactly one reply.
# - **result / error** — the two kinds of reply; each carries the request's `id`.
# - **notification** — a JSON-RPC message with no `id`; nobody replies.
# - **host** — the app the user works in; runs one MCP client per server.
# - **MCP client** — the part of a host that talks MCP to one server.
# - **MCP server** — a program that offers tools and data over MCP.
# - **stdio transport** — the server is a subprocess; one JSON message per line over stdin/stdout.
# - **server/discover** — the request every server must answer: versions and capabilities.
# - **capabilities** — the feature groups (tools, resources, prompts…) a side supports.
# - **`_meta`** — a reserved object in params and results; every MCP request carries its version, client info and capabilities there.
# - **isError** — in a `tools/call` result: the call worked but the tool failed.

# %% [markdown]
# Stop the server. Closing stdin tells a stdio server to exit; we wait, and kill it only if it hangs.

# %%
server.stdin.close()
try:
    server.wait(timeout=5)
except subprocess.TimeoutExpired:
    server.kill()
print("server exit code:", server.returncode)
