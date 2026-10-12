# %% [markdown]
# # 05 · The Python MCP client and several servers
# Level L2 · Part 2 · core · ~30 min · builds on 03

# %% [markdown]
# ## Goal
# By the end you have one `Client` for each of two servers, Trackr over stdio and a runbooks server in the same process. You list and call tools through each client. Then one `MCPAdapter` config gives a model both servers at once, and you can say why the tool names came out as `trackr_count_open` and `runbooks_get_runbook`.

# %% [markdown]
# ## The idea
# A host keeps one MCP client per server. Each client owns one connection, so it can only reach the tools of its own server. The SDK's `Client` takes a target: a subprocess described by `StdioServerParameters`, or a server object already in your process. Both give the same calls: `list_tools` and `call_tool`.
#
# When a model needs tools from several servers, the adapter merges them into one list. Two servers can each have a tool called `search`, so the adapter prefixes each name with its server name: `{server}_{tool}`. The adapter also keeps the route back, so a call to `runbooks_get_runbook` reaches the runbooks server.
#
# Analogy: a hotel with two front desks. Each desk knows only its own rooms. The concierge who sends you to the right desk is the adapter.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   H[Host with one model] --> A[MCPAdapter config]
#   A --> C1[Client: trackr]
#   A --> C2[Client: runbooks]
#   C1 -->|stdio subprocess| T[Trackr server]
#   C2 -->|in-process server object| R[Runbooks server]
#   A --> N[One tool list: trackr_count_open, runbooks_get_runbook, ...]
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set up the servers
# Trackr is the lesson 03 server, still in `../apps/03`. The runbooks server is new: one runbook per known issue, and two tools. `get_runbook` fails for an id it does not know. The file below is a plain MCP server, the same kind as Trackr.

# %%
from pathlib import Path
TRACKR = Path("../apps/03/trackr_server.py").resolve()
assert TRACKR.exists(), "run lesson 03 first: it writes the Trackr server"
Path("../apps/05").mkdir(parents=True, exist_ok=True)
print("Trackr server:", TRACKR.name, "| runbooks server: written in the next cell")

# %% [markdown]
# The cell below saves the runbooks server to `../apps/05/runbooks_server.py`. It is plain MCP, the same kind of server as Trackr.

# %%
%%writefile ../apps/05/runbooks_server.py
"""Runbooks MCP server (lesson 05): the team's runbooks, one per known issue, as a second MCP server."""
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

RUNBOOKS = {
    4: ("App crashes when photo is rotated", "1. Reproduce on the Android 14 test device.\n2. Check the crash group in the mobile dashboard.\n3. Ship the image-rotation hotfix behind a flag."),
    7: ("Push notifications arrive late", "1. Check the push queue depth in the provider console.\n2. Ask the device owner to re-register the push token.\n3. If more than 15 minutes late for 3 users, page the mobile on-call."),
    12: ("TLS certificate expires in 9 days", "1. Renew the certificate with the infra CA.\n2. Deploy to the edge and check the chain.\n3. Add a 30-day expiry alert."),
    16: ("Backups not copied to second region", "1. Check the replication job status.\n2. Re-run the copy for the last 24 hours.\n3. Confirm the checksum in the second region."),
}

mcp = MCPServer("Runbooks")

@mcp.tool(title="Get a runbook", annotations=ToolAnnotations(readOnlyHint=True))
def get_runbook(issue_id: int) -> str:
    """Return the runbook steps for a Trackr issue id. Fails if no runbook exists for that id."""
    if issue_id not in RUNBOOKS:
        raise ToolError(f"No runbook for issue {issue_id}")
    title, steps = RUNBOOKS[issue_id]
    return f"Runbook for issue {issue_id} ({title}):\n{steps}"

@mcp.tool(title="Search runbooks", annotations=ToolAnnotations(readOnlyHint=True))
def search(text: str) -> list[int]:
    """Find the issue ids whose runbook title contains the text, in any letter case."""
    needle = text.lower()
    return [i for i, (title, _) in RUNBOOKS.items() if needle in title.lower()]

if __name__ == "__main__":
    mcp.run()          # default transport: stdio

# %% [markdown]
# ### 2. One client for the stdio server
# A `Client` built from `StdioServerParameters` starts Trackr as a subprocess and speaks MCP over its stdin and stdout. `sys.executable` runs the server with the same Python as this notebook. You do not write JSON-RPC by hand here: the client does the protocol handshake for you.

# %%
import sys
from mcp import Client
from mcp.client.stdio import StdioServerParameters
async with Client(StdioServerParameters(command=sys.executable, args=[str(TRACKR)])) as trackr:
    tools = await trackr.list_tools()
    print("trackr tools:", [t.name for t in tools.tools])
    reply = await trackr.call_tool("count_open", {"team": "mobile"})
    print("open mobile issues:", reply.structured_content, "| is_error:", reply.is_error)

# %% [markdown]
# The reply is a typed object, not a dict. `structured_content` holds the typed value and `is_error` says whether the tool refused. The SDK uses snake_case names in Python. On the wire the same fields are camelCase, as lesson 03 showed.

# %% [markdown]
# ### 3. One client for the in-process server
# The runbooks server is already a Python object. `Client(server_object)` connects to it in the same process, with no subprocess and no stdin. This is the easiest target for tests, and lesson 27 uses it for that. The import below gives the object; the `if __name__` guard stops the server from starting.

# %%
sys.path.insert(0, str(Path("../apps/05").resolve()))
from runbooks_server import mcp as runbooks_mcp
async with Client(runbooks_mcp) as runbooks:
    rb_tools = await runbooks.list_tools()
    print("runbooks tools:", [t.name for t in rb_tools.tools])
    reply = await runbooks.call_tool("get_runbook", {"issue_id": 7})
    print(reply.content[0].text.splitlines()[0])

# %% [markdown]
# ### 4. One client per server: each sees only its own tools
# Each client has one connection, so it knows only its own server. Ask Trackr for a runbook and it does not have the tool. The answer is not an exception here. It is a tool error with `is_error` set, and the text says the tool is unknown. A check on `is_error` is the only thing that catches it.

# %%
async with Client(StdioServerParameters(command=sys.executable, args=[str(TRACKR)])) as trackr, \
        Client(runbooks_mcp) as runbooks:
    wrong = await trackr.call_tool("get_runbook", {"issue_id": 7})
    print("trackr has get_runbook? is_error:", wrong.is_error, "|", wrong.content[0].text)
    right = await runbooks.call_tool("search", {"text": "push"})
    print("runbooks search 'push' ->", right.structured_content)
assert wrong.is_error is True and right.is_error is False
assert right.structured_content == {"result": [7]}

# %% [markdown]
# ### 5. One config for two servers: MCPAdapter
# Writing a client for each server is fine for a script. A model needs one list of tools. `MCPAdapter` takes the same kind of config a desktop host uses: a dictionary with `mcpServers`, one entry per server. The key is the server's name. The adapter starts both servers, merges their tools and names them `{server}_{tool}`. The adapter is beta in LangChain, so the warning is filtered.

# %%
import logging, warnings
from contextlib import AsyncExitStack
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)  # the adapter is still beta
logging.getLogger("httpx").setLevel(logging.WARNING)  # hide httpx's INFO line, which prints the model URL
from langchain.mcp import MCPAdapter
# importing fastmcp resets its "fastmcp" logger to INFO, so set the levels after the import
logging.getLogger("fastmcp").setLevel(logging.WARNING)  # hide the INFO "Proxy detected" banner on each proxied session
logging.getLogger("vcr").setLevel(logging.WARNING)  # the recorder's INFO lines show file paths
logging.getLogger("google_genai").setLevel(logging.WARNING)  # the Vertex SDK's INFO lines show the project id
stack = AsyncExitStack()   # the adapter stays open for the model cells below; closed at the end
CONFIG = {"mcpServers": {
    "trackr": {"command": sys.executable, "args": [str(TRACKR)]},
    "runbooks": {"command": sys.executable, "args": [str(Path("../apps/05/runbooks_server.py").resolve())]},
}}
adapter = await stack.enter_async_context(MCPAdapter(CONFIG))
mcp_tools = await adapter.list_tools()
by_name = {t.name: t for t in mcp_tools}
print(sorted(by_name))
assert {"trackr_count_open", "runbooks_get_runbook", "runbooks_search"} <= set(by_name)

# %% [markdown]
# Read the names. The `trackr_` and `runbooks_` prefixes come from the config keys. Two servers could both have a `search` tool, and the model would see two of them. With the prefix, the names stay unique, and the adapter can still send each call to the right server.

# %% [markdown]
# ### 6. A real model asks the right server (`needs-llm`)
# Now a model reads the merged list and answers a question that needs the runbooks server. It makes its first call, the host runs it through the adapter, and the model writes its answer. That is two model calls, which is the budget for this lesson.

# %%
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
import llm_replay
from langchain_core.messages import AIMessage, HumanMessage
QUESTION = HumanMessage("What does the runbook say about issue 7?")
llm = None   # filled by the model cell; stays None if that cell is skipped
print("question ready; the model cell below needs a model (or is skipped)")

# %% [markdown]
# The model cell below asks the model for its first reply. `get_llm` picks the model and starts the recording or the replay for this lesson. It first prints the course's model picker, a long table of providers and models. The line to read is `model asks for`.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("05_mcp-client-and-models", max_calls=2)
first = await llm.bind_tools(mcp_tools).ainvoke([QUESTION])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model cell was skipped, a scripted tool call stands in for the model's first reply. The stand-in is labelled.

# %%
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[{"name": "runbooks_get_runbook", "args": {"issue_id": 7}, "id": "scripted_1"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# The host runs each requested tool through the adapter. The adapter knows which server owns `runbooks_get_runbook`, so the call goes to the runbooks server.

# %%
results = [await by_name[c["name"]].ainvoke(c) for c in first.tool_calls]
for r in results:
    print("ToolMessage status:", r.status, "| first line:", r.text.splitlines()[0])

# %% [markdown]
# The model reads the runbook and writes its answer. This is its second and last call (`needs-llm`).

# %% tags=["needs-llm"]
final = await llm.bind_tools(mcp_tools).ainvoke([QUESTION, first, *results])
print("answer:", final.text)

# %% [markdown]
# Without a model there is no written answer, so the fallback prints what the tool returned.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). The runbook said:", results[0].text.splitlines()[1])

# %% [markdown]
# ## At work
# - Every server a team connects adds tool names, and each name costs model tokens on every call. Teams watch selection accuracy as the catalogue grows, and they rename or cap tools before names collide → lesson 24.
# - A description from a server is text the model reads. One server can steer the model to misuse another server's tool (shadowing). Teams namespace tools, but they also review descriptions and treat them as untrusted → lesson 29.
# - Dozens of servers mean dozens of client connections per host. Organisations put a gateway in front that applies auth and per-tool policy in one place → lesson 40.

# %% [markdown]
# ## What just happened
# - Each `Client` had one connection, so each knew only its own server's tools. The runbooks tools were not visible to the Trackr client.
# - A call to a tool that a server does not have came back as a tool error (`is_error: True`), not as an exception. A host that skips the `is_error` check misses it.
# - `MCPAdapter` read the `mcpServers` config and gave the model one merged list. Each name was `{server}_{tool}`, and the adapter routed each call to the server that owned it.
# - The model asked for `runbooks_get_runbook` with `issue_id: 7`. The host ran it, and the model answered from the runbook text.

# %% [markdown]
# ## Common mistakes
# Calling a tool by its server name, not its prefixed name. The adapter publishes `runbooks_get_runbook`, so the bare name is not a key in the dictionary. This fails:

# %% tags=["raises-exception"]
bare = by_name["get_runbook"]     # KeyError: the adapter publishes the prefixed name
print(bare.name)

# %% [markdown]
# Fix: look up the name the adapter printed, `runbooks_get_runbook`. Print the list once and copy the names from it.
#
# A second trap is silent. Calling `get_runbook` on the Trackr client does not raise. It returns `is_error: True`. If you print only the text, it looks like an answer. Always check `is_error` before you trust a reply.

# %% [markdown]
# ## Try it
# Use an in-process client on `runbooks_mcp`, as in step 3. Call `search` with the text `"tls"`, then call `get_runbook` for the first id it returns. Print the ids and the first line of the runbook. Check `is_error` on both calls. No model is needed.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **Client (MCP SDK)** — the `mcp` class that connects to one server and offers `list_tools` and `call_tool`. It takes a stdio subprocess description or a server object.
# - **StdioServerParameters** — the description of a subprocess the client starts and talks to over stdin and stdout.
# - **in-process server** — an `MCPServer` object used directly by a client in the same Python process. No subprocess and no transport.
# - **one client per server** — each client holds one connection. A host with several servers keeps several clients.
# - **mcpServers config** — a dictionary, one entry per server name, that `MCPAdapter` reads to start every server.
# - **namespaced tool name** — the `{server}_{tool}` name the adapter gives each tool, so names from different servers cannot collide.

# %% [markdown]
# Close the clients and the adapter, which stops both servers. Then tell the recorder the lesson is done.

# %%
await stack.aclose()
llm_replay.stop()
print("lesson 05 done: one client per server, one config for the model, names kept apart")
