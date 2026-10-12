# %% [markdown]
# # 02 · Checkpoint: your first MCP server, driven by a real model
# Level L1 · Part 1 · core · ~60 min · builds on 01a

# %% [markdown]
# ## Goal
# By the end you have built a Trackr MCP server with **two tools** (`count_open` and `search_issues`), checked both with raw JSON-RPC, and used a real model to answer two questions through `MCPAdapter`. This closes Part 1.

# %% [markdown]
# ## The idea
# Lessons 00 to 01a gave you the pieces one at a time: the wire format, the server, and the adapter that hands tools to a model. This checkpoint puts them together with a second tool.
#
# A good MCP tool has three things: a name the model can read, a docstring that says when to use it, and type-hinted arguments. The server turns those into the `tools/list` that the model sees. The model picks a tool from the description alone, so the description is part of the product.
#
# Analogy: a shop with two counters. One counter counts things (`count_open`). The other finds things (`search_issues`). A sign on each counter tells the customer (the model) which one to use.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   Q[Question] --> M[Model]
#   M -->|tool call| H[MCPAdapter host]
#   H -->|tools/call| S[Trackr server]
#   S -->|count_open or search_issues| H
#   H -->|ToolMessage| M
#   M --> A[Answer]
# ```

# %% [markdown]
# ## Requirements
# Your server is done when every box is ticked:
# - [ ] It is called `Trackr` and holds the same 20 issues as lessons 00 and 01.
# - [ ] It offers exactly two tools: `count_open(team)` returns a number, `search_issues(text)` returns the **open** issues whose title contains the text, in any letter case.
# - [ ] Both tools have a docstring, so the description reaches the model.
# - [ ] Raw JSON-RPC shows `server/discover`, `tools/list` and two `tools/call` results with the right values.
# - [ ] A real model answers both questions through `MCPAdapter`, with at most two model calls per question.

# %% [markdown]
# ## Build it
# ### 1. Write the server
# Write the server file. It is the lesson 01 server plus one tool. `search_issues` returns a list of issues, so its result is a list of dicts, not a number.

# %%
from pathlib import Path
APP_DIR = Path("../apps/02")
APP_DIR.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# Now the server itself. The `writefile` cell below saves it to `../apps/02/trackr_server.py`, so the file exists on disk for the next steps.

# %%
%%writefile ../apps/02/trackr_server.py
"""Trackr MCP server (lesson 02): 20 in-memory issues, two tools, stdio transport."""
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

@mcp.tool()
def search_issues(text: str) -> list[dict]:
    """Find open Trackr issues whose title contains the text, in any letter case."""
    needle = text.lower()
    return [i for i in ISSUES if i["status"] == "open" and needle in i["title"].lower()]

if __name__ == "__main__":
    mcp.run()          # default transport: stdio (reads stdin, writes stdout)

# %% [markdown]
# ### 2. Check it with raw JSON-RPC
# Before a model touches the server, check it the way lesson 01 did. Start it as a subprocess, write one JSON message per line to its stdin, and read the replies. Every request carries `_meta`, as in lesson 01.

# %%
import json, queue, subprocess, sys, threading
SERVER = (APP_DIR / "trackr_server.py").resolve()
server = subprocess.Popen(
    [sys.executable, str(SERVER)],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=open(APP_DIR / "server.log", "w"), text=True, bufsize=1)

replies: queue.Queue = queue.Queue()
def _pump():                              # stdout -> queue, one line at a time
    for line in server.stdout:
        replies.put(line)
threading.Thread(target=_pump, daemon=True).start()
print("server started, pid", server.pid)

# %% [markdown]
# Two helpers are the whole client. `send` writes one message as one line of JSON. `recv` waits for one reply with a timeout. Every request carries the same `_meta` block as in lesson 01.

# %%
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "lesson-02-notebook", "version": "0.1"},
    "io.modelcontextprotocol/clientCapabilities": {},
}

def send(id_: int, method: str, **params) -> None:
    msg = {"jsonrpc": "2.0", "id": id_, "method": method, "params": {**params, "_meta": META}}
    server.stdin.write(json.dumps(msg) + "\n")
    server.stdin.flush()

def recv(timeout: float = 10.0) -> dict:
    try:
        return json.loads(replies.get(timeout=timeout))
    except queue.Empty:
        raise TimeoutError(f"no reply within {timeout}s") from None

send(1, "server/discover")
disc = recv()
print("server up, versions:", disc["result"]["supportedVersions"])

# %% [markdown]
# Next, ask for the tool list. The names and input schemas here are what the model will see. Then call each tool once. The reply's `structuredContent` holds the typed value. For `count_open` that is a number. For `search_issues` it is a list.

# %%
send(2, "tools/list")
tools_reply = recv()["result"]["tools"]
for t in tools_reply:
    print(t["name"], "| args:", list(t["inputSchema"]["properties"]))

send(3, "tools/call", name="count_open", arguments={"team": "web"})
web = recv()["result"]["structuredContent"]["result"]
print("count_open(web)       ->", web)

send(4, "tools/call", name="search_issues", arguments={"text": "export"})
hits = recv()["result"]["structuredContent"]["result"]
print("search_issues(export) ->", [(h["id"], h["title"]) for h in hits])

# %% [markdown]
# Checks, as code. The last one searches a title that is only on a closed issue (issue 3). An open-only search must return nothing. If an assertion fails, fix the server file in the `writefile` cell, then run from step 1 again.

# %%
send(5, "tools/call", name="search_issues", arguments={"text": "dark mode"})
closed_hits = recv()["result"]["structuredContent"]["result"]
assert {t["name"] for t in tools_reply} == {"count_open", "search_issues"}
assert web == 3, f"web should have 3 open issues, got {web}"
assert [h["id"] for h in hits] == [10], f"expected issue 10, got {hits}"
assert all(h["status"] == "open" for h in hits)
assert closed_hits == [], f"closed issue should not match, got {closed_hits}"
print("raw JSON-RPC checks passed")

server.stdin.close(); _ = server.wait(timeout=5)

# %% [markdown]
# ### 3. Ask a real model two questions (`needs-llm`)
# Now the host side. `MCPAdapter` starts the server from a config, lists its tools, and gives them to the model. Each question takes at most two model calls: one to choose the tool, one to write the answer. The cells that follow run the same way with no model, so the lesson works without a key.

# %%
import warnings
from contextlib import AsyncExitStack
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)  # the adapter is still beta
from langchain.mcp import MCPAdapter
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

QUESTIONS = [
    ("How many open issues does web have?", "count_open", {"team": "web"}),
    ("Which open issues mention 'export'?", "search_issues", {"text": "export"}),
]
CONFIG = {"mcpServers": {"trackr": {"command": sys.executable, "args": [str(SERVER)]}}}
stack = AsyncExitStack()
adapter = await stack.enter_async_context(MCPAdapter(CONFIG))
tools = await adapter.list_tools()
by_name = {t.name: t for t in tools}
llm = None   # filled by the model cell; stays None if that cell is skipped
print("tools:", sorted(by_name))

# %% [markdown]
# The model reads the tool descriptions and chooses a tool. Its first reply is a tool call, not text. This cell makes one call per question (`needs-llm`).

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("02_checkpoint-first-server", max_calls=6)
firsts = []
for question, _, _ in QUESTIONS:
    firsts.append(await llm.bind_tools(tools).ainvoke([HumanMessage(question)]))
    print("model asks for:", firsts[-1].tool_calls)

# %% [markdown]
# If the model cell was skipped, scripted tool calls stand in for the model's first replies. The scripted replies are labelled as such.

# %%
if llm is None:   # fallback: the model cell was skipped
    firsts = [AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"scripted_{i}"}])
              for i, (_, name, args) in enumerate(QUESTIONS)]
    for f in firsts:
        print("SCRIPTED stand-in (no model): model asks for:", f.tool_calls)

# %% [markdown]
# The host runs each requested tool through the adapter. Each run sends one `tools/call`, and the result comes back as a `ToolMessage`.

# %%
all_results = []
for f in firsts:
    all_results.append([await by_name[c["name"]].ainvoke(c) for c in f.tool_calls])
for r_list in all_results:
    for r in r_list:
        print("ToolMessage:", r.tool_call_id, "->", r.text[:120])

# %% [markdown]
# The model reads the tool results and writes each answer. That is its second call for the question (`needs-llm`).

# %% tags=["needs-llm"]
for (question, _, _), f, r_list in zip(QUESTIONS, firsts, all_results):
    final = await llm.bind_tools(tools).ainvoke([HumanMessage(question), f, *r_list])
    print("answer:", final.text)

# %% [markdown]
# Without a model, the fallback prints what the tools said, which is the ground truth for both questions.

# %%
if llm is None:   # fallback: no model, so no written answers
    for (question, _, _), r_list in zip(QUESTIONS, all_results):
        print(f"answer (skipped: no model here) to {question!r}: {r_list[0].text[:120]}")

# %% [markdown]
# Closing the adapter ends Trackr. `llm_replay.stop()` saves the recording and ends the lesson's model budget.

# %%
await stack.aclose()
import llm_replay
llm_replay.stop()
print("checkpoint done: MCP server checked by hand and used by a model")

# %% [markdown]
# ## At work
# - Real teams keep one MCP server per system and write each tool description as a contract, reviewed like code. A vague description sends the model to the wrong tool → lesson 03.
# - Production hosts log every `tools/call` with its arguments and result, so an answer can be traced back to what the tool returned → lesson 42.

# %% [markdown]
# ## Reference solution
# <details><summary>Try the build first. Open this only to compare.</summary>
#
# The server file in step 1 is the reference. The checks in step 2 should print:
#
# - `tools/list`: `count_open | args: ['team']` and `search_issues | args: ['text']`
# - `count_open(web)` gives `3` (issues 1, 9 and 17 are open).
# - `search_issues(export)` gives one hit: issue 10, "Export to CSV drops the last row".
#
# Two design choices to notice. `search_issues` returns only open issues, so a closed match never reaches the model. Both tools take a plain `str` argument (`team` or `text`), so the schema the model reads matches what the server checks. `count_open` returns an `int`; that is the return type, not an argument.
# </details>

# %% [markdown]
# ## Key terms
# - **checkpoint** — a lesson that puts a part's pieces together into one working thing you can check.
# - **tool description** — the docstring the server sends with each tool; the model reads it to choose a tool.
# - **structuredContent** — the typed result of a tool call. A number or list is wrapped as `{"result": …}`.
# - **inputSchema** — the JSON Schema of a tool's arguments, built from the function's type hints.
# - **MCPAdapter** — the LangChain helper that starts an MCP server from a config and runs its tools for a model.
