# %% [markdown]
# # 03 · MCP tools in depth
# Level L2 · Part 2 · core · ~35 min · builds on 02

# %% [markdown]
# ## Goal
# By the end you have a Trackr server with four tools that a model and a client both read correctly: typed inputs, a typed output, annotations as hints, and errors the model can recover from. You can tell a **tool error** (`isError: true`) from a **protocol error** (a JSON-RPC `error`) on the wire, and you have seen a real model recover from a tool error.

# %% [markdown]
# ## The idea
# A tool is more than a function. The server publishes a **definition**: a name, a title, a description, an `inputSchema` (what you may send), an `outputSchema` (what you get back) and optional **annotations**. The SDK builds the schemas from your type hints, so the hints are part of the API.
#
# Two failures must not be mixed up. If the tool runs and says it cannot do the job, the reply is a normal result with `isError: true`, and the model can read the text and try again. If the request itself is broken, the reply is a JSON-RPC `error`. Annotations are the server's word, not a guarantee.
#
# Analogy: a vending machine. "Sold out" is an answer on the display. A machine with no button for what you asked for is a different kind of problem.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   T[Type hints and docstring] --> D[Tool definition]
#   D --> IS[inputSchema: what you may send]
#   D --> OS[outputSchema: what you get back]
#   D --> AN[annotations: hints, not guarantees]
#   C[tools/call] --> R{Is the request valid?}
#   R -->|no: unknown method or broken envelope| E1[JSON-RPC error]
#   R -->|yes: the tool ran or refused| E2[result with isError true or false]
# ```

# %% [markdown]
# ## Already know this?
# Part 2 (lessons 03–10a) covers MCP tools, resources, the client, transports, A2A and AG-UI. If you can answer these, skip to **lesson 11**:
# 1. A tool returns an `int`. Under which key does its typed value appear in `structuredContent`?
# 2. A tool gets an id that does not exist. Is the reply a JSON-RPC error or a result with `isError: true`?
# 3. Who controls a resource, the model or the application? And who controls a tool?
# 4. Where does an A2A client fetch an agent's card?
# 5. Which AG-UI event ends a run that finished normally, and which one reports a failed run?
#
# <details><summary>Answers</summary>
#
# 1. `result`: a non-object return is wrapped that way. 2. `isError: true`. 3. The application controls resources; the model controls tools. 4. `/.well-known/agent-card.json`. 5. `RUN_FINISHED` for a normal run, `RUN_ERROR` for a failed one.
#
# </details>

# %% [markdown]
# ## Step by step
#
# ### 1. Write the server with four tools
# The server is lesson 02's Trackr plus two tools. Read the tool definitions first. `Literal` values become an `enum` in the input schema. A `TypedDict` return type becomes an `outputSchema`. `title` and `annotations` go on the decorator. `ToolError` is the way to report a failure you expected.

# %%
from pathlib import Path
APP_DIR = Path("../apps/03")
APP_DIR.mkdir(parents=True, exist_ok=True)
print("app folder ready:", APP_DIR)

# %% [markdown]
# The `writefile` cell below saves the server to `../apps/03/trackr_server.py`. It has the same 20 issues as lesson 02.

# %%
%%writefile ../apps/03/trackr_server.py
"""Trackr MCP server (lesson 03): four tools that show titles, schemas, hints and errors."""
from typing import Literal
from typing_extensions import TypedDict
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

Team = Literal["web", "api", "mobile", "infra"]
Severity = Literal["low", "medium", "high", "critical"]

class Issue(TypedDict):
    id: int
    title: str
    team: str
    status: str
    severity: str

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
ISSUES: list[dict] = [{"id": int(h.split(" ", 1)[0]), "title": h.split(" ", 1)[1], "team": t, "status": st, "severity": sv}
                      for h, t, st, sv in (line.split("|") for line in ROWS.splitlines())]

mcp = MCPServer("Trackr")

@mcp.tool(title="Count open issues", annotations=ToolAnnotations(readOnlyHint=True))
def count_open(team: Team) -> int:
    """Count open Trackr issues for one team."""
    return sum(1 for i in ISSUES if i["team"] == team and i["status"] == "open")

@mcp.tool(title="Search open issues", annotations=ToolAnnotations(readOnlyHint=True))
def search_issues(text: str) -> list[Issue]:
    """Find open issues whose title contains the text, in any letter case."""
    needle = text.lower()
    return [i for i in ISSUES if i["status"] == "open" and needle in i["title"].lower()]

@mcp.tool(title="Create an issue", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
def create_issue(title: str, team: Team, severity: Severity) -> Issue:
    """Open a new issue and return it with its new id."""
    new = {"id": max(i["id"] for i in ISSUES) + 1, "title": title, "team": team, "status": "open", "severity": severity}
    ISSUES.append(new)
    return new

@mcp.tool(title="Close an issue", annotations=ToolAnnotations(destructiveHint=True))
def close_issue(issue_id: int) -> Issue:
    """Close one open issue by id. Fails if the id is unknown or the issue is already closed."""
    for issue in ISSUES:
        if issue["id"] == issue_id:
            if issue["status"] == "closed":
                raise ToolError(f"Issue {issue_id} is already closed")
            issue["status"] = "closed"
            return issue
    raise ToolError(f"Issue {issue_id} does not exist")

if __name__ == "__main__":
    mcp.run()          # default transport: stdio

# %% [markdown]
# ### 2. Start the server and read its tool definitions on the wire
# Start the server as a subprocess and talk to it with JSON-RPC, as in lesson 02. `rpc` sends one request and returns the whole reply, so you can see `result` and `error` as they come back. Every request carries `_meta`.

# %%
import json, queue, subprocess, sys, threading, itertools
SERVER = (APP_DIR / "trackr_server.py").resolve()
server = subprocess.Popen([sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=open(APP_DIR / "server.log", "w"), text=True, bufsize=1)
replies: queue.Queue = queue.Queue()
threading.Thread(target=lambda: [replies.put(l) for l in server.stdout], daemon=True).start()
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "lesson-03-notebook", "version": "0.1"},
        "io.modelcontextprotocol/clientCapabilities": {}}
ids = itertools.count(1)

def rpc(method: str, **params) -> dict:
    """Send one JSON-RPC request and return the whole reply (it has 'result' or 'error')."""
    msg = {"jsonrpc": "2.0", "id": next(ids), "method": method, "params": {**params, "_meta": META}}
    server.stdin.write(json.dumps(msg) + "\n"); server.stdin.flush()
    try:
        return json.loads(replies.get(timeout=10))
    except queue.Empty:
        raise TimeoutError(f"no reply to {method} within 10s") from None

print("server up:", rpc("server/discover")["result"]["supportedVersions"][0])

# %% [markdown]
# Now ask for the tool definitions. This is the first request a host sends after `server/discover`.

# %%
tools = rpc("tools/list")["result"]["tools"]
for t in tools:
    props = {k: v.get("enum", v.get("type")) for k, v in t["inputSchema"]["properties"].items()}
    print(f"{t['name']:<15} args={props}")
    print(f"{'':<15} title={t['title']!r} description={t['description'][:40]!r}")
    print(f"{'':<15} output keys={list(t['outputSchema']['properties'])} annotations={t.get('annotations', {})}")

# %% [markdown]
# Read the output. The model chooses a tool from its name, title and description, so write those for the model, not only for the developer who reads the code. `count_open` takes a `team` that must be one of four values: the `enum` came from the `Team` type. Its output is wrapped under `result` because an `int` is not an object. `close_issue` has `destructiveHint` set, so a host that shows its user what each tool does can warn before calling it.

# %% [markdown]
# ### 3. Call the tools: the success path
# Count the open mobile issues, close issue 4, count again, then open a new mobile issue. The server keeps its state while it runs, so each answer depends on the calls before it. Successful results carry `structuredContent`, the typed value.

# %%
def call(name: str, **arguments) -> dict:
    return rpc("tools/call", name=name, arguments=arguments)["result"]

before = call("count_open", team="mobile")
closed = call("close_issue", issue_id=4)
after = call("count_open", team="mobile")
new = call("create_issue", title="Login page flickers on Android", team="mobile", severity="high")
print("open mobile before:", before["structuredContent"]["result"])
print("closed:", closed["structuredContent"], "| isError:", closed["isError"])
print("open mobile after close:", after["structuredContent"]["result"])
print("created id:", new["structuredContent"]["id"])

# %% [markdown]
# ### 4. Call the tools: the failure path
# Now break things on purpose. Closing issue 4 again is an **expected** failure, so the server raises `ToolError`. Issue 99 does not exist. `"four"` is not an integer, so the SDK rejects the arguments against the `inputSchema`. Each one comes back as a normal result with `isError: true`, a text message and no `structuredContent`. The last request names a method that does not exist. That one is a **protocol error**: a JSON-RPC `error` with a code.

# %%
for label, reply in [
    ("close 4 again", call("close_issue", issue_id=4)),
    ("close 99", call("close_issue", issue_id=99)),
    ("close 'four'", call("close_issue", issue_id="four")),
]:
    print(f"{label:<14} isError={reply['isError']} | {reply['content'][0]['text'].splitlines()[0]}")
bad_method = rpc("tools/fly")
print("tools/fly      error code:", bad_method["error"]["code"], "| has result:", "result" in bad_method)

# %% [markdown]
# ### 5. Checks as code
# Each assertion matches one line of the output above. If one fails, the server file in step 1 is the place to look.

# %%
assert {t["name"] for t in tools} == {"count_open", "search_issues", "create_issue", "close_issue"}
assert [t for t in tools if t["name"] == "close_issue"][0]["annotations"]["destructiveHint"] is True
assert before["structuredContent"]["result"] == 4 and after["structuredContent"]["result"] == 3
assert closed["isError"] is False and closed["structuredContent"]["status"] == "closed"
assert new["structuredContent"]["id"] == 21 and new["structuredContent"]["team"] == "mobile"
assert call("close_issue", issue_id=4)["isError"] is True          # already closed
assert "does not exist" in call("close_issue", issue_id=99)["content"][0]["text"]
assert bad_method["error"]["code"] == -32601 and "result" not in bad_method
print("tool checks passed: the tool and protocol errors went the right way")

# %% [markdown]
# ### 6. A real model recovers from a tool error (`needs-llm`)
# Now the host side, with a real model. `MCPAdapter` starts this server from a config and gives its tools to the model. The question asks the model to close issue 99, which does not exist. The model makes its first call, the host runs it, and the error comes back as a `ToolMessage` with `status="error"`. The model then writes its answer. That is two model calls.

# %%
import warnings
from contextlib import AsyncExitStack
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)  # the adapter is still beta
from langchain.mcp import MCPAdapter
from langchain_core.messages import AIMessage, HumanMessage

CONFIG = {"mcpServers": {"trackr": {"command": sys.executable, "args": [str(SERVER)]}}}
stack = AsyncExitStack()
adapter = await stack.enter_async_context(MCPAdapter(CONFIG))
mcp_tools = await adapter.list_tools()
by_name = {t.name: t for t in mcp_tools}
QUESTION = HumanMessage("Close issue 99 in Trackr, then tell me what happened.")
llm = None   # filled by the model cell; stays None if that cell is skipped
print("tools:", sorted(by_name))

# %% [markdown]
# The model reads the tool descriptions and schemas, then chooses a tool. Its first reply is a tool call, not text. This cell makes that first call (`needs-llm`).

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("03_mcp-tools", max_calls=2)
first = await llm.bind_tools(mcp_tools).ainvoke([QUESTION])
print("model asks for:", first.tool_calls)

# %% [markdown]
# If the model cell was skipped, a scripted tool call stands in for the model's first reply. The stand-in is labelled.

# %%
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[{"name": "close_issue", "args": {"issue_id": 99}, "id": "scripted_1"}])
    print("SCRIPTED stand-in (no model): model asks for:", first.tool_calls)

# %% [markdown]
# The host runs each requested tool through the adapter. The failure is not an exception in the host. It is a `ToolMessage` with `status="error"`, so the host can pass it back to the model like any other result.

# %%
results = [await by_name[c["name"]].ainvoke(c) for c in first.tool_calls]
for r in results:
    print("ToolMessage status:", r.status, "| text:", r.text)

# %% [markdown]
# The model reads the error and writes its answer. This is its second and last call (`needs-llm`).

# %% tags=["needs-llm"]
final = await llm.bind_tools(mcp_tools).ainvoke([QUESTION, first, *results])
print("answer:", final.text)

# %% [markdown]
# Without a model there is no written answer, so the fallback prints what the tool said.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). The tool said:", results[0].text)

# %% [markdown]
# ## At work
# - Uber's MCP gateway starts each new tool disabled, and owners review every change to a tool definition as a config diff that can be rolled back. A changed description is a security event, not a typo → lesson 29.
# - Block labels its tools read-only or destructive, and asks for confirmation before a destructive one runs. The server's annotations are a hint, so the host must enforce the confirmation itself → lesson 19 (human approval) and lesson 29 (annotations as untrusted hints).
# - Every tool schema and every result is paid for in model tokens. Teams trim outputs with a typed `outputSchema` and `structuredContent`, and shrink large catalogues → lesson 24 and lesson 24b.

# %% [markdown]
# ## What just happened
# - The SDK turned your type hints into `inputSchema` (the `enum` for `Team`) and your `TypedDict` return type into `outputSchema`. The model and the client read the same definitions.
# - A successful call returned `structuredContent`. A failed call returned `isError: true` with a text message and no `structuredContent`. Both came back as normal replies.
# - `tools/fly` returned a JSON-RPC `error`, because the request itself was not valid. That is a protocol error. A host handles it in a different place from a tool error.
# - The model saw the tool error as text in a `ToolMessage` with `status="error"`, and it wrote an answer that said the issue did not exist. It did not pretend the close worked.

# %% [markdown]
# ## Common mistakes
# Reading `structuredContent` without checking `isError` first. A failed call has no `structuredContent`, so this line fails. The fix is to check `isError` first, then read the typed value:

# %% tags=["raises-exception"]
reply = call("close_issue", issue_id=99)
print("isError:", reply["isError"])                 # True: the call itself did not raise
print("id:", reply["structuredContent"]["id"])      # KeyError: there is no structuredContent

# %% [markdown]
# Fix: check `isError` before you read the result. Only a successful call has `structuredContent`.
#
# A second trap is silent. Wrapping the call in `try`/`except` for a protocol error does not catch a tool error, because a tool error is a normal reply. Also, `annotations` such as `readOnlyHint` are hints from the server. A host that skips confirmation because a tool says `readOnlyHint: true` trusts the wrong thing. The MCP roadmap also says the team should consider deprecating the content annotations (`audience`, `priority`) if they prove unhelpful. Those are not the tool hints above, but a host should build no safety on either kind.

# %% [markdown]
# ## Try it
# Without the model, close issue 2 (open, "Signup email arrives twice"). Then close it again. For both calls print `isError` and the first line of the text. Then count the open `api` issues before and after the first close. Use `call` (step 3) and `rpc` (step 2); the server is still running.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **tool definition** — what the server publishes for a tool: name, title, description, input and output schema, and annotations.
# - **annotations** — optional hints such as `readOnlyHint` and `destructiveHint`. They come from the server, so a host treats them as untrusted.
# - **outputSchema** — the JSON Schema of a tool's result, built from the return type. A non-object return is wrapped under `result`.
# - **tool error (isError)** — a normal result with `isError: true`. The tool ran or refused, and the model can read the text and recover.
# - **protocol error** — a JSON-RPC `error` object with a code. The request itself was not valid, so no tool ran.
# - **ToolError** — the SDK exception a tool raises for a failure it expected. It becomes a tool error, not a protocol error.
# - **ToolMessage status** — `"error"` when the host ran a tool and it returned a tool error, `"success"` otherwise.

# %% [markdown]
# Stop the servers. Closing the adapter ends Trackr's second process, and closing the raw server's stdin ends the first. Then tell the recorder the lesson is done.

# %%
await stack.aclose()
server.stdin.close(); _ = server.wait(timeout=5)
import llm_replay
llm_replay.stop()
print("lesson 03 done: tools defined, checked on the wire, and used by a model")
